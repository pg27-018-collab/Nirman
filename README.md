# WhatsApp Student Birthday Automation

This local automation tool reads a student list from an Excel sheet, identifies whose birthday is today, and sends them a personalized birthday greeting on WhatsApp Web.

It runs locally on your computer, uses your own WhatsApp Web login session (scanned once), and includes anti-spam protections (randomized delays and daily run logs) to protect your WhatsApp account.

---

## 🛠️ Getting Started

### 1. Place Your Excel Spreadsheet Here
To run the automation:
1. Open your Google Sheet.
2. Click **File** -> **Download** -> **Microsoft Excel (.xlsx)**.
3. Save it inside this directory (`/Users/sumantonayak/Downloads/all time location/crc`) as **`students.xlsx`**.
4. Check that your spreadsheet has column headers. By default, the script looks for:
   - **`Name`** (Student Name)
   - **`Phone`** (WhatsApp Phone Number, e.g., `9876543210` or `+919876543210`)
   - **`Birthday`** (Birthday date, e.g., `24-08-2002` or standard date format)

If your columns have different names, you can change them in the **`config.json`** file.

---

### 2. Run the Dry-Run Check (Test Mode)
Before opening WhatsApp, you can check who has birthdays today and what message would be sent by running a **dry-run**:

Activate your Python virtual environment and run the main script with the `--dry-run` flag:
```bash
# Activate virtual environment
source venv/bin/activate

# Run test
python3 main.py --dry-run
```
This reads the Excel sheet and lists matches without opening any browser or sending messages.

---

### 3. Run the Message Sender
To launch the browser and send wishes:
```bash
# Activate virtual environment (if not already done)
source venv/bin/activate

# Run sender
python3 main.py
```

#### First-time Scan
On the very first run, a Chrome browser window will open.
1. Scan the **WhatsApp Web QR Code** with your phone.
2. Once the chat list loads, the script will automatically take over, search for matching students, fill in the messages, click send, and log the results.
3. The session is saved in the local `.session/` folder, so you will **not** need to scan the QR code on subsequent runs.

---

## ⚙️ Configuration (`config.json`)

You can edit `config.json` to customize behavior:
```json
{
  "excel_path": "students.xlsx",
  "columns": {
    "name": "Name",        // Column name in Excel for names
    "phone": "Phone",      // Column name in Excel for phone numbers
    "birthday": "Birthday" // Column name in Excel for birthdays
  },
  "default_country_code": "+91", // Prepended if phone number lacks country code
  "message_template": "Happy Birthday, {Name}! 🎉🎂 Wishing you a fantastic year ahead! Hope you have a wonderful day!",
  "min_delay_seconds": 15, // Minimum wait time between messages (seconds)
  "max_delay_seconds": 30  // Maximum wait time between messages (seconds)
}
```

---

## ⏰ Automating Daily execution (macOS)

Because you are on **macOS**, you can schedule this script to run automatically every morning using macOS's built-in **`launchd`**. Unlike traditional cron jobs, `launchd` runs in your graphical user session, which allows it to successfully launch the Chrome browser window.

### Setup Automated Daily Run at 9:00 AM

1. Create a launch agent plist file:
   ```bash
   nano ~/Library/LaunchAgents/com.student.bday.plist
   ```
2. Copy and paste the following XML configuration (make sure to replace `/Users/sumantonayak/Downloads/all time location/crc/` with your exact paths):
   ```xml
   <?xml version="1.0" encoding="UTF-8"?>
   <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
   <plist version="1.0">
   <dict>
       <key>Label</key>
       <string>com.student.bday</string>
       <key>ProgramArguments</key>
       <array>
           <string>/Users/sumantonayak/Downloads/all time location/crc/venv/bin/python3</string>
           <string>/Users/sumantonayak/Downloads/all time location/crc/main.py</string>
       </array>
       <key>StartCalendarInterval</key>
       <dict>
           <key>Hour</key>
           <integer>9</integer>
           <key>Minute</key>
           <integer>0</integer>
       </dict>
       <key>WorkingDirectory</key>
       <string>/Users/sumantonayak/Downloads/all time location/crc</string>
       <key>StandardOutPath</key>
       <string>/Users/sumantonayak/Downloads/all time location/crc/run.log</string>
       <key>StandardErrorPath</key>
       <string>/Users/sumantonayak/Downloads/all time location/crc/error.log</string>
   </dict>
   </plist>
   ```
3. Load the launch agent to activate the schedule:
   ```bash
   launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.student.bday.plist
   ```
   Now, every day at 9:00 AM, if your computer is on, the script will run, find the birthdays, open the browser in the background, send the wishes, and close. If your computer is off at 9:00 AM, macOS will run it as soon as you turn your computer back on.

4. To stop the schedule later:
   ```bash
   launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.student.bday.plist
   ```

---

## 🔒 Session Safety
* **Duplicates Protection:** Successful sends are saved in `history.json` with the current date. If you run the script multiple times a day, it will verify against `history.json` and skip contacts who were already messaged today.
* **Security:** All WhatsApp credentials and cookies are saved in `.session/` inside this project directory. Nothing is uploaded to external servers.
