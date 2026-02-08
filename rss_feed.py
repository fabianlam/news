from flask import Flask, jsonify
import threading
import time
from datetime import datetime
import socket
import feedparser  # pip install feedparser

# ────────────────────────────────────────────────
# mDNS / Zeroconf advertisement (for auto-discovery)
# ────────────────────────────────────────────────
try:
    from zeroconf import ServiceInfo, Zeroconf
except ImportError:
    print("zeroconf not installed → run: pip install zeroconf")
    Zeroconf = ServiceInfo = None

def get_lan_ip():
    """Get the local network IP (not 127.0.0.1)"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip

def advertise_mdns():
    if not Zeroconf:
        print("mDNS disabled (zeroconf library missing)")
        return
    zeroconf = Zeroconf()
    my_ip = get_lan_ip()
    info = ServiceInfo(
        "_news._tcp.local.",
        "RTHK News Server._news._tcp.local.",
        addresses=[socket.inet_aton(my_ip)],
        port=5050,
        properties={'path': '/news'},
        server="news.local."
    )
    print(f"mDNS advertising: news.local:5050 (IP: {my_ip})")
    zeroconf.register_service(info)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Unregistering mDNS service...")
        zeroconf.unregister_service(info)
        zeroconf.close()

# Start mDNS in background thread
if Zeroconf:
    threading.Thread(target=advertise_mdns, daemon=True).start()

# ────────────────────────────────────────────────
# Flask + RSS parsing logic
# ────────────────────────────────────────────────
app = Flask(__name__)

latest_data = {}
last_update_str = "Not yet fetched"

# Updated RSS feed URLs (using official rthk.hk domain)
rss_urls = {
    "本港新聞": "https://rthk.hk/rthk/news/rss/c_expressnews_clocal.xml",
    "內地新聞": "https://rthk.hk/rthk/news/rss/c_expressnews_greaterchina.xml",
    "國際新聞": "https://rthk.hk/rthk/news/rss/c_expressnews_cinternational.xml",
    "財經新聞": "https://rthk.hk/rthk/news/rss/c_expressnews_cfinance.xml"
}

def fetch_news():
    global last_update_str
    for category, url in rss_urls.items():
        try:
            feed = feedparser.parse(url)
            items = []
            for entry in feed.entries[:10]:  # Limit to latest 10 items
                news_item = {
                    "title": entry.get('title', 'N/A'),
                    "description": entry.get('description', 'N/A'),
                    "pubDate": entry.get('published', 'N/A'),
                    "link": entry.get('link', 'N/A')
                }
                items.append(news_item)
            latest_data[category] = items
            print(f"Updated {category} with {len(items)} items")
        except Exception as e:
            print(f"Error fetching {category}: {e}")
    last_update_str = datetime.now().strftime("%Y/%m/%d %H:%M")

# ────────────────────────────────────────────────
# Endpoints
# ────────────────────────────────────────────────

@app.route('/news')
def get_news():
    """Full data - all categories with up to 10 headlines each (original endpoint)"""
    if not latest_data:
        return jsonify({"error": "No data available yet"}), 503
    return jsonify(latest_data)

@app.route('/news/<category>/<int:index>')
def get_specific_news(category, index):
    """Return a specific headline by index (1-10) from the requested category"""
    if index < 1 or index > 10:
        return jsonify({"error": "Index out of range (must be 1-10)"}), 400

    if category not in latest_data:
        return jsonify({"error": f"Unknown category: {category}"}), 404

    items = latest_data[category]
    if not items:
        return jsonify({"error": f"No news available for {category}"}), 404

    if index > len(items):
        return jsonify({"error": f"No headline at index {index} for {category} (only {len(items)} available)"}), 404

    selected = items[index - 1]  # 0-based indexing

    return jsonify({
        "category": category,
        "title": selected["title"]
        # Add more fields if needed:
        # "description": selected["description"],
        # "pubDate": selected["pubDate"],
        # "link": selected["link"]
    })

# ────────────────────────────────────────────────
# Background updater
# ────────────────────────────────────────────────
def background_updater():
    while True:
        fetch_news()
        time.sleep(60)  # Update every 60 seconds

if __name__ == '__main__':
    print("RTHK News Server starting...")
    print("Local: http://127.0.0.1:5050/news")
    print("Network: http://<your-ip>:5050/news")
    print("mDNS: http://news.local:5050/news (if client supports zeroconf)")
    print("Specific headline: http://news.local:5050/news/本港新聞/1 (1 to 10)")
    print("Data updates every 60 seconds")

    threading.Thread(target=background_updater, daemon=True).start()

    # Run on all interfaces
    app.run(host='0.0.0.0', port=5050, debug=False, use_reloader=False)