import os
import sys
import json
import time
import random
import threading
from datetime import datetime, timedelta
from flask import Flask, render_template, jsonify, request, send_from_directory
import pandas as pd
from whatsapp_bot import WhatsAppBot
import shutil
import main as core_main

app = Flask(__name__, template_folder="templates", static_folder="static")

# Auto-install Playwright browsers on startup to enable instant sharing compatibility
try:
    import subprocess
    print("Checking and installing Playwright Chromium driver...")
    subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
    print("Playwright Chromium check completed successfully.")
except Exception as e:
    print(f"Warning running playwright install check: {e}")

# Job status tracker
job_lock = threading.Lock()
job_status = {
    "status": "idle",        # idle, running_login, running_send
    "logs": [],
    "success_count": 0,
    "failed_count": 0,
    "total_count": 0,
    "qr_base64": None
}

def add_log(message):
    timestamp = datetime.now().strftime("%H:%M:%S")
    log_line = f"[{timestamp}] {message}"
    print(log_line)  # Also print to stdout
    with job_lock:
        job_status["logs"].append(log_line)

def get_session_dir(session_phone=""):
    base_dir = os.environ.get("DATA_DIR", ".")
    session_root = os.path.abspath(os.path.join(base_dir, ".session"))
    os.makedirs(session_root, exist_ok=True)
    if not session_phone:
        return session_root
    return os.path.abspath(os.path.join(session_root, session_phone))

def check_session_exists(session_phone="Default"):
    if not session_phone:
        return False
    session_dir = get_session_dir(session_phone)
    if os.path.exists(session_dir) and os.listdir(session_dir):
        return True
    return False

import database

def load_config():
    return database.get_config()

def save_config(config):
    database.save_config(config)

def run_login_thread(session_phone, run_headless=True):
    global job_status
    with job_lock:
        job_status["status"] = "running_login"
        job_status["logs"] = []
    import base64
    with job_lock:
        job_status["status"] = "running_login"
        job_status["logs"] = []
        job_status["qr_base64"] = None
            
    logged_in = False
    session_dir = get_session_dir(session_phone)
    
    # Standard and alternative selectors to confirm logged-in state
    chatlist_selector = 'div[data-testid="chat-list"], div#pane-side, span[data-testid="default-user-profile"], div[data-testid="intro-text"], span[data-testid="menu"], div[role="textbox"]'
    
    # 1. Quick initial check: if session directory exists, launch silently to check if already authenticated.
    # If yes, we skip showing/loading QR completely!
    if check_session_exists(session_phone):
        add_log("Profile directory exists. Performing quick background authentication check...")
        bot = WhatsAppBot(user_data_dir=session_dir, headless=True)
        try:
            bot.start()
            bot.page.goto("https://web.whatsapp.com/")
            # Wait up to 8s for session to restore
            for _ in range(4):
                if bot.page.locator(chatlist_selector).count() > 0:
                    add_log("✅ Profile is already authenticated! Skipping connection setup.")
                    logged_in = True
                    break
                time.sleep(2)
        except Exception as e:
            print(f"Quick auth check warning: {e}")
        finally:
            try:
                bot.close()
            except:
                pass
                
    if logged_in:
        with job_lock:
            job_status["status"] = "idle"
            job_status["qr_base64"] = None
        add_log("Login connection worker finished.")
        return
        
    # 2. Main check/login retry loop
    while not logged_in:
        # Check if the job was cancelled or set back to idle by some other action
        with job_lock:
            if job_status["status"] != "running_login":
                add_log("Login connection worker cancelled/stopped.")
                break
                
        add_log(f"Relaunching login browser for '{session_phone}' (headless={run_headless})...")
        bot = WhatsAppBot(user_data_dir=session_dir, headless=run_headless)
        try:
            bot.start()
            add_log("Browser context initialized. Checking authentication status...")
            bot.page.goto("https://web.whatsapp.com/")
            
            qr_selector = 'canvas, div[data-testid="qrcode"]'
            qr_alert_shown = False
            # Check status inside browser page loop (runs up to 10 minutes per browser instance before restarting context)
            start_time = time.time()
            browser_instance_timeout = 600 # 10 minutes
            
            while time.time() - start_time < browser_instance_timeout:
                # Check cancellation
                with job_lock:
                    if job_status["status"] != "running_login":
                        break
                        
                # Check Logged In
                if bot.page.locator(chatlist_selector).count() > 0:
                    logged_in = True
                    add_log("✅ Login successful! WhatsApp connected. Saving session storage to disk (please wait 8s)...")
                    with job_lock:
                        job_status["qr_base64"] = None
                    time.sleep(8)
                    break
                    
                # Check QR code
                if bot.page.locator(qr_selector).count() > 0:
                    if not qr_alert_shown:
                        add_log("⚠️ NOT LOGGED IN. Displaying QR code on dashboard. Please scan it.")
                        qr_alert_shown = True
                        
                    # Take screenshot of the QR element and save it in memory as base64 data URL
                    try:
                        qr_el = bot.page.locator(qr_selector).first
                        if qr_el.is_visible():
                            qr_bytes = qr_el.screenshot()
                            qr_b64_str = base64.b64encode(qr_bytes).decode("utf-8")
                            with job_lock:
                                job_status["qr_base64"] = f"data:image/png;base64,{qr_b64_str}"
                    except Exception as qr_err:
                        print(f"Error capturing QR: {qr_err}")
                        
                time.sleep(2)
                
            if logged_in:
                break
                
        except Exception as e:
            add_log(f"⚠️ Connection check interrupted: {str(e)}. Rechecking/relaunching browser in 5s...")
            time.sleep(5)
        finally:
            try:
                bot.close()
            except:
                pass
                
    with job_lock:
        job_status["status"] = "idle"
        job_status["qr_base64"] = None
    add_log("Login connection worker finished.")

def run_send_thread(session_phone="Default", force_send=False):
    global job_status
    with job_lock:
        job_status["status"] = "running_send"
        job_status["logs"] = []
        job_status["success_count"] = 0
        job_status["failed_count"] = 0
        job_status["total_count"] = 0
        
    config = load_config()
    history = core_main.load_history()
    
    try:
        db_students = database.get_students()
    except Exception as e:
        add_log(f"❌ Error reading database: {str(e)}")
        with job_lock:
            job_status["status"] = "idle"
        return
        
    if not db_students:
        add_log("❌ No students directory found in database. Please upload Excel spreadsheet first.")
        with job_lock:
            job_status["status"] = "idle"
        return
        
    today = datetime.now()
    today_month = today.month
    today_day = today.day
    today_str = today.strftime("%Y-%m-%d")
    
    add_log(f"Filtering students with birthdays matching: Month {today_month}, Day {today_day}...")
    
    birthdays_today = []
    for s in db_students:
        name = s["name"]
        phone_raw = s["phone"]
        bday_raw = s["birthday"]
        
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
    session_dir = get_session_dir(session_phone)
    bot = WhatsAppBot(user_data_dir=session_dir, headless=True)
    try:
        bot.start()
        add_log(f"Checking authentication for profile '{session_phone}'...")
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
                core_main.add_history_record(history, name, phone, "success", sender_profile=session_phone)
                with job_lock:
                    job_status["success_count"] += 1
            elif result == "invalid_number":
                add_log(f"❌ Failed: Phone number {phone} is not registered on WhatsApp.")
                core_main.add_history_record(history, name, phone, "invalid_number", sender_profile=session_phone)
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

def get_active_sessions():
    session_dir = os.path.abspath(".session")
    sessions = []
    if os.path.exists(session_dir):
        try:
            for name in os.listdir(session_dir):
                path = os.path.join(session_dir, name)
                if os.path.isdir(path) and name not in ("BrowserMetrics", "GrShaderCache"):
                    sessions.append(name)
        except Exception as e:
            print(f"Error listing sessions: {e}")
    if "Default" not in sessions and check_session_exists("Default"):
        sessions.append("Default")
    return sessions

def run_scheduler():
    print("Automated Daily Sending Scheduler Thread started.")
    while True:
        try:
            config = load_config()
            if config.get("automated_sending", False):
                now = datetime.now()
                sched_str = config.get("scheduled_time", "09:00")
                try:
                    sched_parts = sched_str.strip().split(":")
                    sched_hour = int(sched_parts[0])
                    sched_minute = int(sched_parts[1])
                except Exception as parse_err:
                    print(f"Scheduler time parse error for '{sched_str}': {parse_err}")
                    sched_hour = 9
                    sched_minute = 0
                
                # Check if hour and minute matches
                if now.hour == sched_hour and now.minute == sched_minute:
                    today_str = now.strftime("%Y-%m-%d")
                    # Check if already executed today
                    if config.get("last_scheduler_run_date", "") != today_str:
                        # Find an authenticated session to send messages
                        sessions = get_active_sessions()
                        session_to_use = None
                        for s in sessions:
                            if check_session_exists(s):
                                session_to_use = s
                                break
                                
                        if session_to_use:
                            print(f"Scheduler: Matches daily time {sched_str}. Starting automated send for profile '{session_to_use}'...")
                            with job_lock:
                                if job_status["status"] == "idle":
                                    # Update run date config
                                    config["last_scheduler_run_date"] = today_str
                                    save_config(config)
                                    
                                    job_status["status"] = "running_send"
                                    job_status["success_count"] = 0
                                    job_status["failed_count"] = 0
                                    job_status["total_count"] = 0
                                    job_status["logs"] = []
                                    
                                    threading.Thread(
                                        target=run_send_thread,
                                        args=(session_to_use, False) # force_send=False
                                    ).start()
                        else:
                            print("Scheduler: Automated sending skipped because no authenticated WhatsApp sessions are available.")
                            # Prevent continuous log spamming in this minute
                            config["last_scheduler_run_date"] = today_str
                            save_config(config)
        except Exception as e:
            print(f"Error in scheduler loop: {e}")
        time.sleep(30) # Sleep 30 seconds

# --- ROUTES ---

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/status")
def get_status():
    config = load_config()
    excel_path = config.get("excel_path", "students.xlsx")
    excel_exists = os.path.exists(excel_path)
    session_phone = request.args.get("session", "").strip()
    
    total_students = 0
    birthdays_count = 0
    birthdays_tomorrow_count = 0
    sent_today_count = 0
    headers = []
    
    # Load sheet headers if file exists (for mapping select options)
    if excel_exists:
        try:
            df = pd.read_excel(excel_path)
            headers = [str(h).strip() for h in df.columns]
            
            # Heuristic guessing of column mapping config
            columns_changed = False
            cols_config = config.setdefault("columns", {})
            
            # Name guess
            c_name = cols_config.get("name")
            if not c_name or c_name not in headers:
                for h in headers:
                    if any(x in h.lower() for x in ("full name", "student name", "name", "full_name")):
                        cols_config["name"] = h
                        columns_changed = True
                        break
                else:
                    if headers:
                        cols_config["name"] = headers[0]
                        columns_changed = True
            
            # Phone guess
            c_phone = cols_config.get("phone")
            if not c_phone or c_phone not in headers:
                for h in headers:
                    if any(x in h.lower() for x in ("phone", "contact", "number", "whatsapp", "mobile", "no")):
                        cols_config["phone"] = h
                        columns_changed = True
                        break
                else:
                    if len(headers) > 1:
                        cols_config["phone"] = headers[1]
                        columns_changed = True
                        
            # Birthday guess
            c_bday = cols_config.get("birthday")
            if not c_bday or c_bday not in headers:
                for h in headers:
                    if any(x in h.lower() for x in ("dob", "birth", "date", "bday", "birthday")):
                        cols_config["birthday"] = h
                        columns_changed = True
                        break
                else:
                    if len(headers) > 2:
                        cols_config["birthday"] = headers[2]
                        columns_changed = True
                        
            if columns_changed:
                save_config(config)
        except Exception as e:
            print(f"Error guessing excel headers: {e}")
            
    try:
        db_students = database.get_students()
        total_students = len(db_students)
        
        today = datetime.now()
        tomorrow = today + timedelta(days=1)
        today_str = today.strftime("%Y-%m-%d")
        history = core_main.load_history()
        
        for s in db_students:
            parsed_dob = core_main.parse_birthday(s["birthday"])
            if parsed_dob:
                dob_month, dob_day = parsed_dob
                
                # Check if today is birthday
                if dob_month == today.month and dob_day == today.day:
                    birthdays_count += 1
                    
                    cleaned_p = core_main.clean_phone(s["phone"], config.get("default_country_code", "+91"))
                    if cleaned_p and core_main.is_already_sent_today(history, cleaned_p, today_str):
                        sent_today_count += 1
                        
                # Check if tomorrow is birthday
                if dob_month == tomorrow.month and dob_day == tomorrow.day:
                    birthdays_tomorrow_count += 1
    except Exception as e:
        print(f"Error loading SQLite stats: {str(e)}")
        
    return jsonify({
        "excel_exists": excel_exists or total_students > 0,
        "excel_path": excel_path,
        "whatsapp_authenticated": check_session_exists(session_phone),
        "total_students": total_students,
        "birthdays_count": birthdays_count,
        "birthdays_tomorrow_count": birthdays_tomorrow_count,
        "sent_today_count": sent_today_count,
        "pending_count": max(0, birthdays_count - sent_today_count),
        "headers": headers
    })

@app.route("/api/birthdays")
def get_birthdays():
    config = load_config()
    session_phone = request.args.get("session", "")
    day_param = request.args.get("day", "today").lower()
    
    birthdays = []
    try:
        db_students = database.get_students()
        if not db_students:
            return jsonify({"date": datetime.now().strftime("%Y-%m-%d"), "birthdays": []})
            
        today = datetime.now()
        
        if day_param == "tomorrow":
            target_date = today + timedelta(days=1)
        else:
            target_date = today
            
        target_date_str = target_date.strftime("%Y-%m-%d")
        history = core_main.load_history()
        month_val = int(request.args.get("month", today.month))
        
        for s in db_students:
            name = s["name"]
            phone = s["phone"]
            dob_val = s["birthday"]
            
            parsed_dob = core_main.parse_birthday(dob_val)
            if not parsed_dob:
                continue
            dob_month, dob_day = parsed_dob
            
            match = False
            status = "pending"
            
            if day_param == "all":
                match = True
                try:
                    bday_this_year = datetime(today.year, dob_month, dob_day)
                except ValueError:
                    bday_this_year = datetime(today.year, 3, 1)
                    
                today_midnight = datetime(today.year, today.month, today.day)
                
                if bday_this_year.date() < today_midnight.date():
                    status = "passed"
                elif bday_this_year.date() == today_midnight.date():
                    cleaned_p = core_main.clean_phone(phone, config.get("default_country_code", "+91"))
                    if cleaned_p and core_main.is_already_sent_today(history, cleaned_p, today.strftime("%Y-%m-%d")):
                        records = history.get("sent_records", [])
                        record = next((r for r in records if r["date"] == today.strftime("%Y-%m-%d") and r["phone"] == cleaned_p), None)
                        if record and record["status"] == "invalid_number":
                            status = "failed"
                        else:
                            status = "sent"
                    else:
                        status = "pending"
                else:
                    status = "upcoming"
            elif day_param == "month":
                if dob_month == month_val:
                    match = True
                    try:
                        bday_this_year = datetime(today.year, dob_month, dob_day)
                    except ValueError:
                        bday_this_year = datetime(today.year, 3, 1)
                        
                    today_midnight = datetime(today.year, today.month, today.day)
                    
                    if bday_this_year.date() < today_midnight.date():
                        status = "passed"
                    elif bday_this_year.date() == today_midnight.date():
                        cleaned_p = core_main.clean_phone(phone, config.get("default_country_code", "+91"))
                        if cleaned_p and core_main.is_already_sent_today(history, cleaned_p, today.strftime("%Y-%m-%d")):
                            records = history.get("sent_records", [])
                            record = next((r for r in records if r["date"] == today.strftime("%Y-%m-%d") and r["phone"] == cleaned_p), None)
                            if record and record["status"] == "invalid_number":
                                status = "failed"
                            else:
                                status = "sent"
                        else:
                            status = "pending"
                    else:
                        status = "upcoming"
            else:
                if dob_month == target_date.month and dob_day == target_date.day:
                    match = True
                    cleaned_p = core_main.clean_phone(phone, config.get("default_country_code", "+91"))
                    
                    if day_param == "tomorrow":
                        status = "upcoming"
                    else:
                        status = "pending"
                        if cleaned_p and core_main.is_already_sent_today(history, cleaned_p, target_date_str):
                            records = history.get("sent_records", [])
                            record = next((r for r in records if r["date"] == target_date_str and r["phone"] == cleaned_p), None)
                            if record and record["status"] == "invalid_number":
                                status = "failed"
                            else:
                                status = "sent"
                                
            if match:
                month_name = datetime(2000, dob_month, 1).strftime('%B')
                display_bday = f"{dob_day:02d} {month_name}"
                
                birthdays.append({
                    "name": str(name).strip(),
                    "phone": str(phone).strip(),
                    "birthday": display_bday,
                    "status": status,
                    "month_num": dob_month,
                    "day_of_month": dob_day,
                    "row": s["row_number"]
                })
                
        if day_param == "month":
            birthdays.sort(key=lambda x: x["day_of_month"])
        elif day_param == "all":
            birthdays.sort(key=lambda x: (x["month_num"], x["day_of_month"]))
            
        return jsonify({
            "date": target_date_str,
            "birthdays": birthdays
        })
    except Exception as e:
        print(f"Error loading birthdays: {str(e)}")
        return jsonify({"error": f"Failed to load birthdays: {str(e)}", "birthdays": []}), 500

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
        config["automated_sending"] = data.get("automated_sending", config.get("automated_sending", False))
        config["scheduled_time"] = data.get("scheduled_time", config.get("scheduled_time", "09:00"))
        
        cols = data.get("columns", {})
        config["columns"]["name"] = cols.get("name", config["columns"]["name"])
        config["columns"]["phone"] = cols.get("phone", config["columns"]["phone"])
        config["columns"]["birthday"] = cols.get("birthday", config["columns"]["birthday"])
        
        save_config(config)
        return jsonify({"message": "Configuration saved successfully!"})
        
    return jsonify(load_config())

@app.route("/api/upload", methods=["POST"])
def upload_file():
    try:
        if "file" not in request.files:
            return jsonify({"error": "No file part in request"}), 400
        file = request.files["file"]
        if file.filename == "":
            return jsonify({"error": "No file selected"}), 400
            
        if file and file.filename.lower().endswith((".xlsx", ".xls")):
            config = load_config()
            save_path = config.get("excel_path", "students.xlsx")
            file.save(save_path)
            
            df = pd.read_excel(save_path)
            name_col = config.get("columns", {}).get("name", "Name")
            phone_col = config.get("columns", {}).get("phone", "Phone")
            bday_col = config.get("columns", {}).get("birthday", "Birthday")
            
            for col in [name_col, phone_col, bday_col]:
                if col not in df.columns:
                    return jsonify({"error": f"Excel missing column '{col}'. Update configuration columns first."}), 400
                    
            students_list = []
            for idx, row in df.iterrows():
                name = row.get(name_col)
                phone = row.get(phone_col)
                dob_val = row.get(bday_col)
                if pd.notna(name) and pd.notna(dob_val):
                    students_list.append({
                        "name": str(name).strip(),
                        "phone": str(phone).strip() if pd.notna(phone) else "",
                        "birthday": str(dob_val).strip(),
                        "row_number": idx + 2
                    })
                    
            database.clear_students()
            database.insert_students(students_list)
            return jsonify({"message": f"Successfully parsed and updated database with {len(students_list)} students."})
        else:
            return jsonify({"error": "Only Microsoft Excel (.xlsx or .xls) spreadsheets are supported. Make sure the file extension is correct."}), 400
    except Exception as e:
        return jsonify({"error": f"Failed to save file: {str(e)}"}), 500

@app.route("/api/sessions")
def get_sessions():
    session_dir = get_session_dir("")
    sessions = []
    if os.path.exists(session_dir):
        try:
            for name in os.listdir(session_dir):
                path = os.path.join(session_dir, name)
                if os.path.isdir(path):
                    # We check if it is a directory representing a phone session (e.g. not chromium cache directories)
                    if name not in ("BrowserMetrics", "GrShaderCache"):
                        sessions.append(name)
        except Exception as e:
            print(f"Error listing sessions: {e}")
            
    return jsonify(sessions)

@app.route("/api/delete-session", methods=["POST"])
def delete_session():
    global job_status
    with job_lock:
        if job_status["status"] != "idle":
            return jsonify({"error": "Cannot delete profile while a process is running."}), 400
            
    data = request.json or {}
    session_phone = data.get("session_phone", "").strip()
    if not session_phone:
        return jsonify({"error": "No profile specified."}), 400
        
    if session_phone == "Default":
        # Clear default folder
        session_dir = os.path.abspath(".session/Default")
        if os.path.exists(session_dir):
            try:
                shutil.rmtree(session_dir)
            except Exception as e:
                return jsonify({"error": f"Failed to clear Default folder: {str(e)}"}), 500
        
        # Clear legacy browser files directly under .session/
        root_session = os.path.abspath(".session")
        if os.path.exists(root_session):
            try:
                for name in os.listdir(root_session):
                    path = os.path.join(root_session, name)
                    if os.path.isfile(path):
                        os.remove(path)
                    elif name in ("BrowserMetrics", "GrShaderCache", "Local State", "lock", "SingletonLock"):
                        if os.path.isdir(path):
                            shutil.rmtree(path)
                        else:
                            os.remove(path)
            except Exception as e:
                print(f"Warning clearing legacy files: {e}")
        return jsonify({"message": "Default session profile cleared successfully."})
        
    # Clear custom phone session folder
    session_dir = get_session_dir(session_phone)
    if os.path.exists(session_dir):
        try:
            shutil.rmtree(session_dir)
            return jsonify({"message": f"WhatsApp profile '{session_phone}' deleted successfully."})
        except Exception as e:
            return jsonify({"error": f"Failed to delete profile: {str(e)}"}), 500
    else:
        return jsonify({"error": f"Profile '{session_phone}' directory not found."}), 404

@app.route("/api/qr-status")
def get_qr_status():
    with job_lock:
        qr_b64 = job_status.get("qr_base64")
        if qr_b64:
            return jsonify({
                "qr_available": True,
                "qr_url": qr_b64
            })
    return jsonify({"qr_available": False})

@app.route("/api/login-whatsapp", methods=["POST"])
def login_whatsapp():
    global job_status
    data = request.json or {}
    session_phone = data.get("session_phone", "Default").strip()
    if not session_phone:
        session_phone = "Default"
    run_headless = data.get("headless", True)
        
    with job_lock:
        if job_status["status"] != "idle":
            return jsonify({"error": f"Another process is already running ({job_status['status']})"}), 400
            
    thread = threading.Thread(target=run_login_thread, args=(session_phone, run_headless))
    thread.daemon = True
    thread.start()
    return jsonify({"message": f"WhatsApp Login launched for '{session_phone}'. Scan QR code."})

@app.route("/api/send-wishes", methods=["POST"])
def send_wishes():
    global job_status
    data = request.json or {}
    force_send = data.get("force", False)
    session_phone = data.get("session_phone", "Default").strip()
    if not session_phone:
        session_phone = "Default"
        
    with job_lock:
        if job_status["status"] != "idle":
            return jsonify({"error": f"Another process is already running ({job_status['status']})"}), 400
            
    thread = threading.Thread(target=run_send_thread, args=(session_phone, force_send))
    thread.daemon = True
    thread.start()
    return jsonify({"message": f"Birthday sending process started for '{session_phone}' in background."})

@app.route("/api/job-status")
def get_job_status():
    with job_lock:
        return jsonify(job_status)

@app.route("/api/history")
def get_history_log():
    return jsonify(core_main.load_history().get("sent_records", []))

if __name__ == "__main__":
    # Initialize SQLite database
    database.init_db()
    
    # Start background daily wisher scheduler
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true" or not app.debug:
        scheduler_thread = threading.Thread(target=run_scheduler)
        scheduler_thread.daemon = True
        scheduler_thread.start()

    port = int(os.environ.get("PORT", 8082))
    app.run(host="0.0.0.0", port=port, debug=True)
