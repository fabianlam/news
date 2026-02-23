import json
import datetime
import time
import threading
import hashlib
import feedparser
import requests
from flask import Flask, jsonify

app = Flask(__name__)

LED_URL = "http://192.168.1.120/notify"        # ← change if you use mDNS
current_data = {"status": "updating"}
last_hash = None                               # Force push on first start

def fetch_rss(url):
    feed = feedparser.parse(url)
    return [entry.title for entry in feed.entries[:10]]

def update_news():
    global current_data, last_hash
    headlines = {}
    categories = {
        "本港新聞":   "https://rthk.hk/rthk/news/rss/c_expressnews_clocal.xml",
        "內地新聞":   "https://rthk.hk/rthk/news/rss/c_expressnews_greaterchina.xml",
        "國際新聞":   "https://rthk.hk/rthk/news/rss/c_expressnews_cinternational.xml",
        "財經新聞":   "https://rthk.hk/rthk/news/rss/c_expressnews_cfinance.xml"
    }

    for label, url in categories.items():
        titles = fetch_rss(url)
        while len(titles) < 10:
            titles.append("")
        headlines[label] = titles

    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # ──────────────────────── KEY FIX ────────────────────────
    # Hash ONLY the headlines → timestamp no longer triggers a push
    headlines_str = json.dumps(headlines, sort_keys=True, ensure_ascii=False)
    current_hash = hashlib.sha256(headlines_str.encode('utf-8')).hexdigest()

    data = {"timestamp": timestamp, "headlines": headlines}

    # Push only when real news changed or first boot
    if last_hash is None or last_hash != current_hash:
        print("News content changed or server startup → pushing to LED")
        try:
            r = requests.post(LED_URL, json=data, timeout=5)
            print("Push OK" if r.status_code == 200 else f"Push failed {r.status_code}")
        except Exception as e:
            print("Push error:", e)
        last_hash = current_hash

    current_data = data

def news_updater():
    global last_hash
    last_hash = None
    while True:
        update_news()
        time.sleep(60)

@app.route('/all_news')
def all_news():
    return jsonify(current_data)

if __name__ == '__main__':
    threading.Thread(target=news_updater, daemon=True).start()
    app.run(host='0.0.0.0', port=5050)
