import json
import datetime
import time
import threading
import hashlib
import feedparser
import requests
from flask import Flask, jsonify

app = Flask(__name__)

LED_URL = "http://192.168.1.120/notify"  # LED panel's notify endpoint (use mDNS if preferred: "http://lednews.local/notify")
current_data = {"status": "updating"}  # Initial state
last_hash = None  # Force push on startup

def fetch_rss(url):
    feed = feedparser.parse(url)
    return [entry.title for entry in feed.entries[:10]]

def update_news():
    global current_data, last_hash
    headlines = {}
categories = {
    "本港新聞": "https://rthk.hk/rthk/news/rss/c_expressnews_clocal.xml",
    "內地新聞": "https://rthk.hk/rthk/news/rss/c_expressnews_greaterchina.xml",
    "國際新聞": "https://rthk.hk/rthk/news/rss/c_expressnews_cinternational.xml",
    "財經新聞": "https://rthk.hk/rthk/news/rss/c_expressnews_cfinance.xml"
}

    for label, url in categories.items():
        titles = fetch_rss(url)
        # Pad to exactly 10 headlines if fewer are available
        while len(titles) < 10:
            titles.append("")
        headlines[label] = titles

    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    data = {"timestamp": timestamp, "headlines": headlines}
    data_str = json.dumps(data, sort_keys=True, ensure_ascii=False)
    current_hash = hashlib.sha256(data_str.encode('utf-8')).hexdigest()

    # Push if changed or on startup (last_hash is None initially)
    if last_hash is None or last_hash != current_hash:
        print("News content changed or server startup - pushing to LED panel")
        try:
            response = requests.post(LED_URL, json=data)
            if response.status_code == 200:
                print("Push successful")
            else:
                print(f"Push failed with status: {response.status_code}")
        except Exception as e:
            print(f"Error during push: {e}")
        last_hash = current_hash

    current_data = data

def news_updater():
    global last_hash
    last_hash = None  # Ensure initial push on server startup
    while True:
        update_news()
        time.sleep(60)  # Check every minute

@app.route('/all_news')
def all_news():
    return jsonify(current_data)

if __name__ == '__main__':
    updater_thread = threading.Thread(target=news_updater)
    updater_thread.daemon = True
    updater_thread.start()
    app.run(host='0.0.0.0', port=5050)

