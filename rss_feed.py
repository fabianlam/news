import json
import datetime
import time
import threading
import hashlib
import feedparser
import bluetooth  # Requires pybluez: pip install pybluez

ESP32_BT_MAC = "80:B5:4E:D7:14:25"  # ← Replace with your ESP32's Bluetooth MAC address
ESP32_BT_NAME = "LEDNewsDisplay"   # For discovery if needed
RFCOMM_CHANNEL = 1                 # Standard serial channel

current_data = {"status": "updating"}
last_hash = None  # Force push on first start
last_push_time = 0  # For debounce
MIN_PUSH_INTERVAL = 300  # 5 minutes in seconds

def fetch_rss(url):
    feed = feedparser.parse(url)
    return [entry.title for entry in feed.entries[:10]]

def update_news():
    global current_data, last_hash, last_push_time
    headlines = {}
    categories = {
        "本港新聞": "https://rthk.hk/rthk/news/rss/c_expressnews_clocal.xml",
        "內地新聞": "https://rthk.hk/rthk/news/rss/c_expressnews_greaterchina.xml",
        "國際新聞": "https://rthk.hk/rthk/news/rss/c_expressnews_cinternational.xml",
        "財經新聞": "https://rthk.hk/rthk/news/rss/c_expressnews_cfinance.xml"
    }
    for label, url in categories.items():
        titles = fetch_rss(url)
        while len(titles) < 10:
            titles.append("")
        headlines[label] = titles
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    # Hash ONLY the headlines → timestamp no longer triggers a push
    headlines_str = json.dumps(headlines, sort_keys=True, ensure_ascii=False)
    current_hash = hashlib.sha256(headlines_str.encode('utf-8')).hexdigest()
    data = {"timestamp": timestamp, "headlines": headlines}
    # Push only when real news changed or first boot, and at least MIN_PUSH_INTERVAL since last push
    if last_hash is None or (last_hash != current_hash and time.time() - last_push_time > MIN_PUSH_INTERVAL):
        print("News content changed or server startup → pushing to LED via Bluetooth")
        try:
            sock = bluetooth.BluetoothSocket(bluetooth.RFCOMM)
            sock.connect((ESP32_BT_MAC, RFCOMM_CHANNEL))
            json_str = json.dumps(data, ensure_ascii=False)  # Send as string
            sock.send(json_str.encode('utf-8'))
            sock.close()
            print("Push OK")
            last_push_time = time.time()
        except Exception as e:
            print("Push error:", e)
        last_hash = current_hash
    current_data = data

def news_updater():
    global last_hash, last_push_time
    last_hash = None
    last_push_time = 0
    while True:
        update_news()
        time.sleep(60)  # Still check every minute, but push debounced

if __name__ == '__main__':
    # Removed Flask since no HTTP needed anymore
    news_updater_thread = threading.Thread(target=news_updater, daemon=True)
    news_updater_thread.start()
    print("News updater started. Press Ctrl+C to exit.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Shutting down...")


