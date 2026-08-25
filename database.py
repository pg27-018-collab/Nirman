import os
import sqlite3
import json

DB_FILE = os.path.abspath("database.db")

def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Settings table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )
    """)
    
    # Students table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS students (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        phone TEXT,
        birthday TEXT,
        row_number INTEGER
    )
    """)
    
    # History table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT,
        name TEXT,
        phone TEXT,
        status TEXT,
        session_phone TEXT
    )
    """)
    
    conn.commit()
    conn.close()
    
    # Set default settings if not already present
    config = get_config()
    # Ensure default fields are written
    save_config(config)

def get_setting(key, default=None):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return row[0]
    return default

def set_setting(key, value):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
    conn.commit()
    conn.close()

def get_config():
    config = {
        "excel_path": get_setting("excel_path", "students.xlsx"),
        "default_country_code": get_setting("default_country_code", "+91"),
        "message_template": get_setting("message_template", "Happy Birthday, {Name}! 🎉🎂 Wishing you a fantastic year ahead! Hope you have a wonderful day!"),
        "min_delay_seconds": int(get_setting("min_delay_seconds", 15)),
        "max_delay_seconds": int(get_setting("max_delay_seconds", 30)),
        "automated_sending": get_setting("automated_sending", "False") == "True",
        "scheduled_time": get_setting("scheduled_time", "09:00"),
        "last_scheduler_run_date": get_setting("last_scheduler_run_date", "")
    }
    
    columns_str = get_setting("columns", None)
    if columns_str:
        try:
            config["columns"] = json.loads(columns_str)
        except:
            config["columns"] = {"name": "Name", "phone": "Phone", "birthday": "Birthday"}
    else:
        config["columns"] = {"name": "Name", "phone": "Phone", "birthday": "Birthday"}
        
    return config

def save_config(config):
    set_setting("excel_path", config.get("excel_path", "students.xlsx"))
    set_setting("default_country_code", config.get("default_country_code", "+91"))
    set_setting("message_template", config.get("message_template", ""))
    set_setting("min_delay_seconds", config.get("min_delay_seconds", 15))
    set_setting("max_delay_seconds", config.get("max_delay_seconds", 30))
    set_setting("automated_sending", "True" if config.get("automated_sending", False) else "False")
    set_setting("scheduled_time", config.get("scheduled_time", "09:00"))
    set_setting("last_scheduler_run_date", config.get("last_scheduler_run_date", ""))
    set_setting("columns", json.dumps(config.get("columns", {"name": "Name", "phone": "Phone", "birthday": "Birthday"})))

def clear_students():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM students")
    conn.commit()
    conn.close()

def insert_students(students_list):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.executemany("""
    INSERT INTO students (name, phone, birthday, row_number)
    VALUES (?, ?, ?, ?)
    """, [(s["name"], s["phone"], s["birthday"], s["row_number"]) for s in students_list])
    conn.commit()
    conn.close()

def get_students():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name, phone, birthday, row_number FROM students ORDER BY row_number ASC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def add_history_record(timestamp, name, phone, status, session_phone):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
    INSERT INTO history (timestamp, name, phone, status, session_phone)
    VALUES (?, ?, ?, ?, ?)
    """, (timestamp, name, phone, status, session_phone))
    conn.commit()
    conn.close()

def get_history_records():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT timestamp, name, phone, status, session_phone FROM history ORDER BY id DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]
