import os
import sys
import json
import time
import random
import threading
from datetime import datetime
from flask import Flask, render_template, jsonify, request, send_from_directory
import pandas as pd
from whatsapp_bot import WhatsAppBot
import main as core_main

app = Flask(__name__, template_folder="templates", static_folder="static")

# Job status tracker
job_lock = threading.Lock()
job_status = {
    "status": "idle",        # idle, running_login, running_send
    "logs": [],
    "success_count": 0,
    "failed_count": 0,
    "total_count": 0
}

def add_log(message):
    timestamp = datetime.now().strftime("%H:%M:%S")
    log_line = f"[{timestamp}] {message}"
    print(log_line)  # Also print to stdout
    with job_lock:
        job_status["logs"].append(log_line)

def check_session_exists():
    session_dir = os.path.abspath(".session")
    # If the directory exists and contains files/folders, we assume a session is cached
    if os.path.exists(session_dir) and os.listdir(session_dir):
        return True
    return False

def load_config():
    if not os.path.exists(core_main.CONFIG_FILE):
        return {
            "excel_path": "students.xlsx",
            "columns": {"name": "Name", "phone": "Phone", "birthday": "Birthday"},
            "default_country_code": "+91",
            "message_template": "Happy Birthday, {Name}! 🎉🎂 Wishing you a fantastic year ahead! Hope you have a wonderful day!",
            "min_delay_seconds": 15,
            "max_delay_seconds": 30
        }
    with open(core_main.CONFIG_FILE, "r") as f:
        return json.load(f)

def save_config(config):
    with open(core_main.CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)

def run_login_thread():
    global job_status
    with job_lock:
        job_status["status"] = "running_login"
        job_status["logs"] = []
    
    add_log("Starting browser in headful mode for login...")
    bot = WhatsAppBot(user_data_dir=".session", headless=False)
    try:
        bot.start()
        add_log("Browser launched. Checking login status (waiting for QR code if not logged in)...")
        # Let's check login with a timeout of 120s
        # Custom logging behavior during login check
        bot.page.goto("https://web.whatsapp.com/")
        
        chatlist_selector = 'div[data-testid="chat-list"], div#pane-side'
        qr_selector = 'canvas, div[data-testid="qrcode"]'
        
        start_time = time.time()
        timeout_sec = 120
        logged_in = False
        qr_alert_shown = False
        
        while time.time() - start_time < timeout_sec:
            # Check if chat list exists (Logged In)
            if bot.page.locator(chatlist_selector).count() > 0:
                logged_in = True
                add_log("✅ Login successful!")
                break
                
            # Check if QR code is visible (Logged Out)
            if bot.page.locator(qr_selector).count() > 0:
                if not qr_alert_shown:
                    add_log("⚠️ NOT LOGGED IN. Please look at the Chrome browser window and scan the QR code using your phone.")
                    qr_alert_shown = True
                
                # Wait in a loop
                while time.time() - start_time < timeout_sec:
                    if bot.page.locator(chatlist_selector).count() > 0:
                        logged_in = True
                        add_log("✅ Login detected! Scan complete.")
                        break
                    time.sleep(2)
                break
                
            time.sleep(2)
            
        if not logged_in:
            add_log("❌ Login check timed out or failed.")
            
    except Exception as e:
        add_log(f"❌ Error during login: {str(e)}")
    finally:
        bot.close()
        with job_lock:
            job_status["status"] = "idle"
        add_log("Login runner thread finished.")

def run_send_thread(force_send=False):
    global job_status
    with job_lock:
        job_status["status"] = "running_send"
        job_status["logs"] = []
        job_status["success_count"] = 0
        job_status["failed_count"] = 0
        job_status["total_count"] = 0
        
    config = load_config()
    history = core_main.load_history()
    excel_path = config.get("excel_path", "students.xlsx")
    
    if not os.path.exists(excel_path):
        add_log(f"❌ Excel spreadsheet file '{excel_path}' not found. Please upload it first.")
        with job_lock:
            job_status["status"] = "idle"
        return
        
    add_log(f"Reading spreadsheet: {excel_path}...")
    try:
        df = pd.read_excel(excel_path)
    except Exception as e:
        add_log(f"❌ Error reading Excel: {str(e)}")
        with job_lock:
            job_status["status"] = "idle"
        return
        
    cols = config.get("columns", {})
    name_col = cols.get("name", "Name")
    phone_col = cols.get("phone", "Phone")
    bday_col = cols.get("birthday", "Birthday")
    
    # Check columns
    missing_cols = [c for c in [name_col, phone_col, bday_col] if c not in df.columns]
    if missing_cols:
        add_log(f"❌ Configuration error: Excel is missing columns: {missing_cols}")
        with job_lock:
            job_status["status"] = "idle"
        return
        
    today = datetime.now()
    today_month = today.month
    today_day = today.day
    today_str = today.strftime("%Y-%m-%d")
    
    add_log(f"Filtering students with birthdays matching: Month {today_month}, Day {today_day}...")
    
    birthdays_today = []
    for idx, row in df.iterrows():
        name = row[name_col]
        phone_raw = row[phone_col]
        bday_raw = row[bday_col]
        
        if pd.isna(name) or pd.isna(phone_raw) or pd.isna(bday_raw):
            continue
            
        parsed_bday = core_main.parse_birthday(bday_raw)
        if not parsed_bday:
            continue
            
        b_month, b_day = parsed_bday
        if b_month == today_month and b_day == today_day:
            cleaned_phone = core_main.clean_phone(phone_raw, config.get("default_country_code", "+91"))
            if cleaned_phone:
                birthdays_today.append({
                    "name": str(name).strip(),
                    "phone": cleaned_phone
                })
                
    if not birthdays_today:
        add_log("🎉 No student birthdays found for today.")
        with job_lock:
            job_status["status"] = "idle"
        return
        
    pending_birthdays = []
    for b in birthdays_today:
        if not force_send and core_main.is_already_sent_today(history, b["phone"], today_str):
            add_log(f"ℹ️ Already messaged today: {b['name']} ({b['phone']}). Skipping.")
        else:
            pending_birthdays.append(b)
            
    if not pending_birthdays:
        add_log("✅ All birthday wishes for today have already been sent!")
        core_main.send_macos_notification("Birthday Automation", "✅ All birthday wishes for today have already been sent!")
        with job_lock:
            job_status["status"] = "idle"
        return
        
    add_log(f"Found {len(pending_birthdays)} pending birthday wishes to send.")
    with job_lock:
        job_status["total_count"] = len(pending_birthdays)
        
    # Start bot
    bot = WhatsAppBot(user_data_dir=".session", headless=False)
    try:
        bot.start()
        add_log("Checking authentication...")
        # Check login status
        bot.page.goto("https://web.whatsapp.com/")
        
        chatlist_selector = 'div[data-testid="chat-list"], div#pane-side'
        
        # Wait up to 15s to check if already logged in. If not, we abort (user must login via the login button first)
        try:
            bot.page.wait_for_selector(chatlist_selector, timeout=15000)
            logged_in = True
        except:
            logged_in = False
            
        if not logged_in:
            add_log("❌ WhatsApp Web is not authenticated. Please scan QR code first by clicking 'Login to WhatsApp'.")
            bot.close()
            with job_lock:
                job_status["status"] = "idle"
            return
            
        add_log("✅ Authenticated. Starting wishing sequence...")
        
        for i, student in enumerate(pending_birthdays):
            name = student["name"]
            phone = student["phone"]
            message = config.get("message_template", "").format(Name=name)
            
            add_log(f"Sending to {name} ({phone})...")
            result = bot.send_message(phone, message)
            
            if result == "success":
                add_log(f"✅ Sent successfully to {name}!")
                core_main.add_history_record(history, name, phone, "success")
                with job_lock:
                    job_status["success_count"] += 1
            elif result == "invalid_number":
                add_log(f"❌ Failed: Phone number {phone} is not registered on WhatsApp.")
                core_main.add_history_record(history, name, phone, "invalid_number")
                with job_lock:
                    job_status["failed_count"] += 1
            else:
                add_log(f"⚠️ Failed: {result}")
                with job_lock:
                    job_status["failed_count"] += 1
                    
            if i < len(pending_birthdays) - 1:
                delay = random.randint(config.get("min_delay_seconds", 15), config.get("max_delay_seconds", 30))
                add_log(f"Waiting {delay} seconds to mimic human typing...")
                time.sleep(delay)
                
        add_log("🎉 Wishing sequence completed successfully.")
        
        # Trigger macOS notifications
        success_count = job_status["success_count"]
        failed_count = job_status["failed_count"]
        if success_count > 0:
            core_main.send_macos_notification("Birthday Wishes Sent!", f"✅ Successfully sent wishes to {success_count} student(s).")
        else:
            core_main.send_macos_notification("Birthday Wishes Failed", f"❌ Failed to send wishes to {failed_count} student(s).")
        
    except Exception as e:
        add_log(f"❌ Error during sending: {str(e)}")
    finally:
        bot.close()
        with job_lock:
            job_status["status"] = "idle"
        add_log("Sender runner thread finished.")

# --- ROUTES ---

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/status")
def get_status():
    config = load_config()
    excel_path = config.get("excel_path", "students.xlsx")
    excel_exists = os.path.exists(excel_path)
    
    total_students = 0
    birthdays_count = 0
    sent_today_count = 0
    
    # Read info if excel exists
    if excel_exists:
        try:
            df = pd.read_excel(excel_path)
            total_students = len(df)
            
            # Count today's birthdays
            cols = config.get("columns", {})
            bday_col = cols.get("birthday", "Birthday")
            phone_col = cols.get("phone", "Phone")
            
            if bday_col in df.columns:
                today = datetime.now()
                for idx, val in df[bday_col].items():
                    parsed = core_main.parse_birthday(val)
                    if parsed and parsed[0] == today.month and parsed[1] == today.day:
                        birthdays_count += 1
                        
                        # Check if sent
                        history = core_main.load_history()
                        today_str = today.strftime("%Y-%m-%d")
                        cleaned_p = core_main.clean_phone(df.iloc[idx].get(phone_col), config.get("default_country_code", "+91"))
                        if cleaned_p and core_main.is_already_sent_today(history, cleaned_p, today_str):
                            sent_today_count += 1
        except Exception as e:
            print(f"Error loading stats: {str(e)}")
            
    return jsonify({
        "excel_exists": excel_exists,
        "excel_path": excel_path,
        "whatsapp_authenticated": check_session_exists(),
        "total_students": total_students,
        "birthdays_count": birthdays_count,
        "sent_today_count": sent_today_count,
        "pending_count": max(0, birthdays_count - sent_today_count)
    })

@app.route("/api/birthdays")
def get_birthdays():
    config = load_config()
    excel_path = config.get("excel_path", "students.xlsx")
    
    if not os.path.exists(excel_path):
        return jsonify({"date": datetime.now().strftime("%Y-%m-%d"), "birthdays": []})
        
    birthdays = []
    try:
        df = pd.read_excel(excel_path)
        cols = config.get("columns", {})
        name_col = cols.get("name", "Name")
        phone_col = cols.get("phone", "Phone")
        bday_col = cols.get("birthday", "Birthday")
        
        today = datetime.now()
        history = core_main.load_history()
        today_str = today.strftime("%Y-%m-%d")
        
        for idx, row in df.iterrows():
            name = row.get(name_col)
            phone = row.get(phone_col)
            bday = row.get(bday_col)
            
            if pd.isna(name) or pd.isna(bday):
                continue
                
            parsed = core_main.parse_birthday(bday)
            if parsed and parsed[0] == today.month and parsed[1] == today.day:
                cleaned_p = core_main.clean_phone(phone, config.get("default_country_code", "+91"))
                
                status = "pending"
                if cleaned_p and core_main.is_already_sent_today(history, cleaned_p, today_str):
                    # Check status in history
                    records = history.get("sent_records", [])
                    record = next((r for r in records if r["date"] == today_str and r["phone"] == cleaned_p), None)
                    if record and record["status"] == "invalid_number":
                        status = "failed"
                    else:
                        status = "sent"
                    
                birthdays.append({
                    "name": str(name).strip(),
                    "phone": cleaned_p or str(phone),
                    "birthday": str(bday).strip(),
                    "status": status,
                    "row": idx + 2
                })
    except Exception as e:
        print(f"Error loading birthdays: {str(e)}")
        
    return jsonify({
        "date": datetime.now().strftime("%Y-%m-%d"),
        "birthdays": birthdays
    })

@app.route("/api/config", methods=["GET", "POST"])
def manage_configuration():
    if request.method == "POST":
        data = request.json
        config = load_config()
        
        config["excel_path"] = data.get("excel_path", config["excel_path"])
        config["default_country_code"] = data.get("default_country_code", config["default_country_code"])
        config["message_template"] = data.get("message_template", config["message_template"])
        config["min_delay_seconds"] = int(data.get("min_delay_seconds", config["min_delay_seconds"]))
        config["max_delay_seconds"] = int(data.get("max_delay_seconds", config["max_delay_seconds"]))
        
        cols = data.get("columns", {})
        config["columns"]["name"] = cols.get("name", config["columns"]["name"])
        config["columns"]["phone"] = cols.get("phone", config["columns"]["phone"])
        config["columns"]["birthday"] = cols.get("birthday", config["columns"]["birthday"])
        
        save_config(config)
        return jsonify({"message": "Configuration saved successfully!"})
        
    return jsonify(load_config())

@app.route("/api/upload", methods=["POST"])
def upload_file():
    if "file" not in request.files:
        return jsonify({"error": "No file part in request"}), 400
    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400
        
    if file and file.filename.endswith((".xlsx", ".xls")):
        config = load_config()
        save_path = config.get("excel_path", "students.xlsx")
        file.save(save_path)
        return jsonify({"message": f"Successfully uploaded spreadsheet and saved to {save_path}"})
    else:
        return jsonify({"error": "Only Microsoft Excel (.xlsx or .xls) spreadsheets are supported."}), 400

@app.route("/api/login-whatsapp", methods=["POST"])
def login_whatsapp():
    global job_status
    with job_lock:
        if job_status["status"] != "idle":
            return jsonify({"error": f"Another process is already running ({job_status['status']})"}), 400
            
    thread = threading.Thread(target=run_login_thread)
    thread.daemon = True
    thread.start()
    return jsonify({"message": "WhatsApp Login launched. Scan QR code in Chrome window."})

@app.route("/api/send-wishes", methods=["POST"])
def send_wishes():
    global job_status
    data = request.json or {}
    force_send = data.get("force", False)
    
    with job_lock:
        if job_status["status"] != "idle":
            return jsonify({"error": f"Another process is already running ({job_status['status']})"}), 400
            
    thread = threading.Thread(target=run_send_thread, args=(force_send,))
    thread.daemon = True
    thread.start()
    return jsonify({"message": "Birthday sending process started in background."})

@app.route("/api/job-status")
def get_job_status():
    with job_lock:
        return jsonify(job_status)

@app.route("/api/history")
def get_history_log():
    return jsonify(core_main.load_history().get("sent_records", []))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8082, debug=True)
