import os
import sys
import json
import time
import random
import argparse
import subprocess
from datetime import datetime
import pandas as pd
from whatsapp_bot import WhatsAppBot

# Path to local directory files
CONFIG_FILE = "config.json"
HISTORY_FILE = "history.json"

def load_config():
    if not os.path.exists(CONFIG_FILE):
        print(f"❌ Configuration file '{CONFIG_FILE}' not found. Please create it first.")
        sys.exit(1)
    with open(CONFIG_FILE, "r") as f:
        return json.load(f)

def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r") as f:
                data = json.load(f)
                if not isinstance(data, dict) or "sent_records" not in data:
                    data = {"sent_records": []}
                return data
        except json.JSONDecodeError:
            print("⚠️ Warning: history.json is corrupted. Reinitializing history.")
            return {"sent_records": []}
    return {"sent_records": []}

def save_history(history):
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)

def is_already_sent_today(history, phone, today_str):
    records = history.get("sent_records", [])
    return any(r["date"] == today_str and r["phone"] == phone for r in records)

def add_history_record(history, name, phone, status, sender_profile="Default"):
    today_str = datetime.now().strftime("%Y-%m-%d")
    timestamp_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Avoid duplicate records for the same person on the same day
    records = history.get("sent_records", [])
    if not any(r["date"] == today_str and r["phone"] == phone and r["status"] == status for r in records):
        records.append({
            "date": today_str,
            "timestamp": timestamp_str,
            "name": name,
            "phone": phone,
            "status": status,
            "sender_profile": sender_profile
        })
    history["sent_records"] = records
    save_history(history)

def send_macos_notification(title, message):
    try:
        t_esc = title.replace('"', '\\"')
        m_esc = message.replace('"', '\\"')
        cmd = f'display notification "{m_esc}" with title "{t_esc}"'
        subprocess.run(["osascript", "-e", cmd], check=True)
    except Exception as e:
        print(f"Failed to send macOS notification: {e}")

def clean_phone(phone_val, default_cc):
    """
    Cleans phone number:
    - Removes spaces, dashes, parentheses
    - Handles float inputs (convert to int) to avoid scientific notation
    - Ensures it has a country code prefix (e.g. +91)
    """
    if pd.isna(phone_val):
        return None
    
    # If float, convert to int first to avoid scientific notation and decimals
    if isinstance(phone_val, float):
        try:
            phone_str = str(int(phone_val))
        except ValueError:
            phone_str = str(phone_val)
    else:
        phone_str = str(phone_val).strip()
        
    cleaned = "".join(c for c in phone_str if c.isdigit() or c == '+')
    
    if not cleaned:
        return None
        
    # If it starts with '00', replace with '+'
    if cleaned.startswith("00"):
        cleaned = "+" + cleaned[2:]
        
    # If it doesn't start with '+', check if we need to prepend country code
    if not cleaned.startswith("+"):
        # If it has 10 digits and default country code is provided, prepend it
        # E.g. 9876543210 -> +919876543210
        if len(cleaned) == 10 and default_cc:
            cc = default_cc if default_cc.startswith("+") else "+" + default_cc
            cleaned = cc + cleaned
        else:
            # If default country code is provided, and it doesn't already start with it
            cc_clean = default_cc.replace("+", "")
            if not cleaned.startswith(cc_clean) and default_cc:
                cc = default_cc if default_cc.startswith("+") else "+" + default_cc
                cleaned = cc + cleaned
            else:
                cleaned = "+" + cleaned
                
    return cleaned

def parse_birthday(val):
    """
    Tries to parse birthday column values into (month, day).
    Returns (month, day) or None if parsing fails.
    """
    if pd.isna(val):
        return None
        
    # If already a pandas Timestamp or datetime object
    if hasattr(val, 'month') and hasattr(val, 'day'):
        return int(val.month), int(val.day)
        
    # If it's a string, attempt various formats
    val_str = str(val).strip()
    if not val_str:
        return None
        
    # Clean up string (e.g. spaces, replace dots with slashes/dashes)
    val_str = val_str.replace(".", "-").replace("/", "-")
    
    # Common date formats to try
    formats = [
        "%d-%m-%Y",  # 24-08-2002
        "%Y-%m-%d",  # 2002-08-24
        "%d-%m",     # 24-08
        "%m-%d",     # 08-24
        "%d-%b-%Y",  # 24-Aug-2002
        "%d-%b",     # 24-Aug
        "%b-%d",     # Aug-24
    ]
    
    for fmt in formats:
        try:
            dt = datetime.strptime(val_str, fmt)
            return dt.month, dt.day
        except ValueError:
            continue
            
    # Try general parsing with pandas as a fallback
    try:
        dt = pd.to_datetime(val_str)
        return int(dt.month), int(dt.day)
    except:
        pass
        
    return None

def main():
    parser = argparse.ArgumentParser(description="WhatsApp Student Birthday Automation")
    parser.add_argument("--dry-run", action="store_true", help="List birthdays and print wishes without opening browser or sending")
    parser.add_argument("--force", action="store_true", help="Ignore sent history and force send to everyone who has a birthday today")
    args = parser.parse_args()

    print("--- WhatsApp Birthday Automation ---")
    config = load_config()
    history = load_history()
    
    excel_path = config.get("excel_path", "students.xlsx")
    if not os.path.exists(excel_path):
        print(f"❌ Excel spreadsheet file '{excel_path}' not found.")
        print("Please place your Excel file in the workspace or check 'excel_path' in config.json.")
        sys.exit(1)
        
    print(f"Reading student list from: {excel_path}...")
    try:
        # Read Excel sheet
        df = pd.read_excel(excel_path)
    except Exception as e:
        print(f"❌ Error reading Excel file: {str(e)}")
        sys.exit(1)
        
    cols = config.get("columns", {})
    name_col = cols.get("name", "Name")
    phone_col = cols.get("phone", "Phone")
    bday_col = cols.get("birthday", "Birthday")
    
    # Validate columns exist
    missing_cols = []
    for col_desc, col_name in [("Name", name_col), ("Phone", phone_col), ("Birthday", bday_col)]:
        if col_name not in df.columns:
            missing_cols.append(f"'{col_name}' ({col_desc})")
            
    if missing_cols:
        print(f"❌ Configuration error: Excel sheet is missing the following configured columns: {', '.join(missing_cols)}")
        print(f"Available columns in Excel: {list(df.columns)}")
        print("Please update 'config.json' to match your column names.")
        sys.exit(1)
        
    # Get today's month and day
    today = datetime.now()
    today_month = today.month
    today_day = today.day
    today_str = today.strftime("%Y-%m-%d")
    
    print(f"Today's date is: {today.strftime('%B %d')} (Month: {today_month}, Day: {today_day})")
    
    birthdays_today = []
    
    # Identify birthdays
    for idx, row in df.iterrows():
        name = row[name_col]
        phone_raw = row[phone_col]
        bday_raw = row[bday_col]
        
        if pd.isna(name) or pd.isna(phone_raw) or pd.isna(bday_raw):
            continue
            
        parsed_bday = parse_birthday(bday_raw)
        if not parsed_bday:
            # Print warning only if there is a value that failed parsing
            if str(bday_raw).strip() != "":
                print(f"⚠️ Could not parse birthday '{bday_raw}' for student '{name}' at row {idx + 2}")
            continue
            
        b_month, b_day = parsed_bday
        if b_month == today_month and b_day == today_day:
            cleaned_phone = clean_phone(phone_raw, config.get("default_country_code", "+91"))
            if not cleaned_phone:
                print(f"⚠️ Row {idx + 2}: Student '{name}' has a birthday today, but phone number '{phone_raw}' is invalid or empty.")
                continue
                
            birthdays_today.append({
                "name": str(name).strip(),
                "phone": cleaned_phone,
                "row": idx + 2
            })
            
    if not birthdays_today:
        print("🎉 No birthdays found for today!")
        send_macos_notification("Birthday Automation", "🎉 No student birthdays found for today.")
        sys.exit(0)
        
    print(f"Found {len(birthdays_today)} student(s) with birthdays today:")
    for b in birthdays_today:
        print(f"  - {b['name']} ({b['phone']}) - Row {b['row']}")
        
    # Filter sent history
    pending_birthdays = []
    
    for b in birthdays_today:
        if not args.force and is_already_sent_today(history, b["phone"], today_str):
            print(f"ℹ️ Already sent today's birthday wish to {b['name']} ({b['phone']}). Skipping.")
        else:
            pending_birthdays.append(b)
            
    if not pending_birthdays:
        print("✅ All birthday wishes for today have already been sent!")
        send_macos_notification("Birthday Automation", "✅ All birthday wishes for today have already been sent!")
        sys.exit(0)
        
    print(f"\nPending to send: {len(pending_birthdays)} student(s)")
    
    # Dry-run check
    if args.dry_run:
        print("\n--- DRY-RUN MODE: Printing messages that would be sent ---")
        for b in pending_birthdays:
            msg = config.get("message_template", "").format(Name=b["name"])
            print(f"To: {b['name']} ({b['phone']})")
            print(f"Message: {msg}")
            print("-" * 30)
        print("Dry-run finished. No messages were sent.")
        sys.exit(0)
        
    # Start WhatsApp Bot
    bot = WhatsAppBot(user_data_dir=".session", headless=False)
    try:
        bot.start()
        
        # Check login status (opens Chrome to WhatsApp Web)
        if not bot.check_login(timeout_sec=120):
            print("❌ WhatsApp Web authentication failed. Closing script.")
            send_macos_notification("Birthday Automation Error", "❌ WhatsApp authentication failed. Wishes not sent.")
            bot.close()
            sys.exit(1)
            
        success_count = 0
        failed_count = 0
        
        for i, student in enumerate(pending_birthdays):
            name = student["name"]
            phone = student["phone"]
            
            message = config.get("message_template", "").format(Name=name)
            
            # Send message
            result = bot.send_message(phone, message)
            
            if result == "success":
                print(f"✅ Successfully sent birthday wish to {name} ({phone})")
                add_history_record(history, name, phone, "success")
                success_count += 1
            elif result == "invalid_number":
                print(f"❌ Failed to send to {name} ({phone}): Phone number is not on WhatsApp.")
                # We save in history to avoid retrying invalid number on subsequent runs today
                add_history_record(history, name, phone, "invalid_number")
                failed_count += 1
            else:
                print(f"⚠️ Failed to send to {name} ({phone}): {result}")
                failed_count += 1
                
            # Random delay between sending (if not the last one) to prevent spam flags
            if i < len(pending_birthdays) - 1:
                min_d = config.get("min_delay_seconds", 15)
                max_d = config.get("max_delay_seconds", 30)
                delay = random.randint(min_d, max_d)
                print(f"Waiting {delay} seconds before the next message to prevent spam triggers...")
                time.sleep(delay)
                
        print(f"\n--- Run Completed ---")
        print(f"Successfully sent: {success_count}")
        print(f"Failed / Skipped: {failed_count}")
        
        # Notification trigger
        if success_count > 0:
            send_macos_notification("Birthday Wishes Sent!", f"✅ Successfully sent wishes to {success_count} student(s).")
        else:
            send_macos_notification("Birthday Wishes Failed", f"❌ Failed to send wishes to {failed_count} student(s).")
        
    except KeyboardInterrupt:
        print("\n⚠️ Execution interrupted by user.")
    finally:
        bot.close()

if __name__ == "__main__":
    main()
