import os
import re
import sys
import time
import urllib.parse
from playwright.sync_api import sync_playwright

class WhatsAppBot:
    def __init__(self, user_data_dir=".session", headless=True):
        self.user_data_dir = os.path.abspath(user_data_dir)
        self.headless = headless
        self.playwright = None
        self.browser = None
        self.page = None

    def start(self):
        print("Starting browser...")
        
        # Clean any lock files left from previous crashes
        try:
            lock_path = os.path.join(self.user_data_dir, "SingletonLock")
            if os.path.exists(lock_path) or os.path.islink(lock_path):
                os.remove(lock_path)
                print(f"Cleaned up browser SingletonLock in {self.user_data_dir}")
            std_lock = os.path.join(self.user_data_dir, "lock")
            if os.path.exists(std_lock):
                os.remove(std_lock)
                print(f"Cleaned up browser lock in {self.user_data_dir}")
        except Exception as lock_err:
            print(f"Warning clearing lock files: {lock_err}")
            
        self.playwright = sync_playwright().start()
        
        # WhatsApp Web detection bypass options
        launch_args = [
            "--disable-blink-features=AutomationControlled",
        ]
        
        user_agent_str = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        try:
            self.browser = self.playwright.chromium.launch_persistent_context(
                user_data_dir=self.user_data_dir,
                headless=self.headless,
                args=launch_args,
                no_viewport=True,  # Use full window size
                user_agent=user_agent_str
            )
        except Exception as launch_err:
            if not self.headless:
                print(f"Warning: Headful browser launch failed: {launch_err}. Falling back to Headless mode...")
                self.headless = True
                self.browser = self.playwright.chromium.launch_persistent_context(
                    user_data_dir=self.user_data_dir,
                    headless=True,
                    args=launch_args,
                    no_viewport=True,
                    user_agent=user_agent_str
                )
            else:
                raise launch_err
        self.page = self.browser.pages[0]
        print("Browser started successfully.")

    def close(self):
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()
        print("Browser closed.")

    def check_login(self, timeout_sec=120):
        print("Navigating to WhatsApp Web to check login status...")
        self.page.goto("https://web.whatsapp.com/")
        
        # Selectors to identify if we are logged in or logged out
        # chatlist_selector: sidebar pane with all chats
        chatlist_selector = 'div[data-testid="chat-list"], div#pane-side'
        # qr_selector: canvas element showing the QR code
        qr_selector = 'canvas, div[data-testid="qrcode"]'
        
        print("Waiting for WhatsApp Web to load...")
        start_time = time.time()
        
        while time.time() - start_time < timeout_sec:
            # Check if chat list exists (Logged In)
            if self.page.locator(chatlist_selector).count() > 0:
                print("✅ Logged in successfully!")
                return True
                
            # Check if QR code is visible (Logged Out)
            if self.page.locator(qr_selector).count() > 0:
                print("⚠️ Not logged in. Please scan the QR code displayed on the browser window.")
                # We wait in a loop, giving the user time to scan
                while time.time() - start_time < timeout_sec:
                    if self.page.locator(chatlist_selector).count() > 0:
                        print("✅ Login detected! Scan complete.")
                        return True
                    time.sleep(2)
                break
                
            time.sleep(2)
            
        print("❌ Login check timed out or failed.")
        return False

    def send_message(self, phone, message):
        """
        Sends a WhatsApp message to the given phone number.
        Returns:
            "success": message sent successfully
            "invalid_number": phone number is not registered on WhatsApp
            "timeout": page did not load or send button didn't appear in time
            "failed: <error>": other errors
        """
        encoded_message = urllib.parse.quote(message)
        url = f"https://web.whatsapp.com/send?phone={phone}&text={encoded_message}"
        print(f"Sending message to {phone}...")
        
        try:
            self.page.goto(url)
            
            # Wait for either the send button OR the invalid phone number popup
            # Selectors
            send_btn_selector = 'span[data-testid="send"]'
            
            # WhatsApp's invalid popup elements (can contain different variations, we check standard terms)
            invalid_text_matchers = [
                "Phone number shared via url is invalid",
                "invalid",
                "phone number is invalid",
                "phone number shared via url is"
            ]
            
            # We poll for up to 35 seconds
            timeout = 35
            for elapsed in range(timeout):
                # 1. Check if Send button is visible
                send_btn = self.page.locator(send_btn_selector)
                if send_btn.is_visible():
                    print("Found send button, clicking...")
                    send_btn.click()
                    # Wait a few seconds for the message to actually send (clock icon -> single tick)
                    time.sleep(4)
                    return "success"
                
                # 2. Check for invalid number dialog
                # We search for any dialog popup with an 'OK' or 'Close' button AND invalid text
                ok_btn = self.page.get_by_role("button", name=re.compile("ok|close", re.IGNORECASE))
                if ok_btn.is_visible():
                    # Check if page contains invalid text
                    page_text = self.page.content()
                    for term in invalid_text_matchers:
                        if term.lower() in page_text.lower():
                            print(f"❌ Invalid phone number detected: {phone}")
                            # Dismiss the dialog
                            ok_btn.click()
                            time.sleep(1)
                            return "invalid_number"
                
                # Also check alternative selectors for the OK button just in case
                alt_ok_btn = self.page.locator('div[role="button"]:has-text("OK")')
                if alt_ok_btn.is_visible():
                    print(f"❌ Invalid phone number detected (alt popup): {phone}")
                    alt_ok_btn.click()
                    time.sleep(1)
                    return "invalid_number"
                
                time.sleep(1)
                
            print("❌ Timing out waiting for chat to load or send button to appear.")
            return "timeout"
            
        except Exception as e:
            print(f"❌ Exception occurred: {str(e)}")
            return f"failed: {str(e)}"
