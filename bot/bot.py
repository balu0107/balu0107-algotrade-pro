import os
import time
import requests

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_telegram_message(message):
    if not TOKEN or not CHAT_ID:
        print("Telegram token or chat ID environment variables are missing!")
        return
    
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message
    }
    
    try:
        response = requests.post(url, json=payload)
        if response.status_code == 200:
            print("Notification sent successfully to Telegram!")
        else:
            print(f"Failed to send message: {response.text}")
    except Exception as e:
        print(f"Error connecting to Telegram API: {e}")

if __name__ == "__main__":
    print("Stock Bot service is active...")
    send_telegram_message("🚀 Stock Application Bot has started successfully!")
    
    # Keep the container running and ready to handle updates or periodic alerts
    while True:
        time.sleep(3600)
