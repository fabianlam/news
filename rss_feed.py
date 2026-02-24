import asyncio
import json
import datetime
import time
import hashlib
import feedparser
from bleak import BleakClient

# ==================== CONFIG ====================
ESP32_BLE_ADDRESS = "80:B5:4E:D7:14:25"   # ← Your ESP32 MAC

# === EXACT UUIDs FROM YOUR ARDUINO CODE ===
SERVICE_UUID        = "4fafc201-1fb5-459e-8fcc-c5c9c331914b"
CHARACTERISTIC_UUID = "beb5483e-36e1-4688-b7f5-ea07361b26a8"  # This is the write target

MIN_PUSH_INTERVAL = 300   # 5 minutes debounce
# ===============================================

last_hash = None
last_push_time = 0


def fetch_rss(url: str):
    feed = feedparser.parse(url)
    titles = [entry.title for entry in feed.entries[:10]]
    while len(titles) < 10:
        titles.append("")
    return titles


async def push_to_esp32(data: dict):
    """Send JSON to your custom characteristic"""
    global last_push_time
    try:
        async with BleakClient(ESP32_BLE_ADDRESS) as client:
            json_str = json.dumps(data, ensure_ascii=False)
            bytes_data = json_str.encode("utf-8")

            await client.write_gatt_char(
                CHARACTERISTIC_UUID, 
                bytes_data, 
                response=False   # Faster, no response needed
            )

            print(f"✅ PUSH SUCCESS → {len(bytes_data)} bytes sent at {datetime.datetime.now().strftime('%H:%M:%S')}")
            last_push_time = time.time()
            return True

    except Exception as e:
        print(f"❌ BLE Push Error: {e}")
        return False


async def update_news():
    global last_hash, last_push_time

    categories = {
        "本港新聞": "https://rthk.hk/rthk/news/rss/c_expressnews_clocal.xml",
        "內地新聞": "https://rthk.hk/rthk/news/rss/c_expressnews_greaterchina.xml",
        "國際新聞": "https://rthk.hk/rthk/news/rss/c_expressnews_cinternational.xml",
        "財經新聞": "https://rthk.hk/rthk/news/rss/c_expressnews_cfinance.xml"
    }

    headlines = {}
    for label, url in categories.items():
        headlines[label] = fetch_rss(url)

    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    data = {"timestamp": timestamp, "headlines": headlines}

    # Hash only the content (ignore timestamp)
    headlines_str = json.dumps(headlines, sort_keys=True, ensure_ascii=False)
    current_hash = hashlib.sha256(headlines_str.encode('utf-8')).hexdigest()

    if (last_hash is None or 
        (last_hash != current_hash and time.time() - last_push_time > MIN_PUSH_INTERVAL)):
        
        print("📰 News changed → pushing via BLE...")
        success = await push_to_esp32(data)
        if success:
            last_hash = current_hash

    print(f"Next check in 60 seconds... (last push was {int(time.time() - last_push_time)}s ago)")


async def main():
    global last_hash, last_push_time
    last_hash = None
    last_push_time = 0

    print("🚀 BLE News Updater started (custom UUIDs). Press Ctrl+C to exit.")

    while True:
        await update_news()
        await asyncio.sleep(60)   # Check every minute


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Shutting down...")
    except Exception as e:
        print(f"Critical error: {e}")
