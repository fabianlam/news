import asyncio
import json
import datetime
import hashlib
import feedparser
from bleak import BleakClient

# ==================== CONFIG ====================
ESP32_BLE_ADDRESS = "80:B5:4E:D7:14:25"   # Your ESP32 MAC address

# Nordic UART Service (NUS) - standard for ESP32 BLE serial
NUS_SERVICE_UUID = "6E400001-B5A3-F393-E0A9-E50E24DCCA9E"
NUS_RX_CHAR_UUID = "6E400002-B5A3-F393-E0A9-E50E24DCCA9E"   # Write to this (Python → ESP32)

MIN_PUSH_INTERVAL = 300   # 5 minutes debounce
# ===============================================

current_data = {"status": "updating"}
last_hash = None
last_push_time = 0


def fetch_rss(url: str):
    feed = feedparser.parse(url)
    titles = [entry.title for entry in feed.entries[:10]]
    while len(titles) < 10:
        titles.append("")
    return titles


async def push_to_esp32(data: dict):
    """Send JSON via BLE to ESP32 NUS RX characteristic"""
    global last_push_time
    try:
        async with BleakClient(ESP32_BLE_ADDRESS) as client:
            if not await client.is_connected():
                print("❌ Failed to connect to ESP32 via BLE")
                return False

            json_str = json.dumps(data, ensure_ascii=False)
            await client.write_gatt_char(
                NUS_RX_CHAR_UUID,
                json_str.encode("utf-8"),
                response=False   # faster, no ACK needed for this use case
            )
            print(f"✅ Pushed {len(json_str)} bytes to ESP32 via BLE at {datetime.datetime.now().strftime('%H:%M:%S')}")
            last_push_time = time.time()
            return True

    except Exception as e:
        print(f"❌ BLE push error: {e}")
        return False


async def update_news():
    global current_data, last_hash, last_push_time

    categories = {
        "本港新聞": "https://rthk.hk/rthk/news/rss/c_expressnews_clocal.xml",
        "內地新聞": "https://rthk.hk/rthk/news/rss/c_expressnews_greaterchina.xml",
        "國際新聞": "https://rthk.hk/rthk/news/rss/c_expressnews_cinternational.xml",
        "財經新聞": "https://rthk.hk/rthk/news/rss/c_expressnews_cfinance.xml"
    }

    headlines = {}
    for label, url in categories.items():
        titles = fetch_rss(url)
        headlines[label] = titles

    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    data = {"timestamp": timestamp, "headlines": headlines}

    # Hash ONLY the headlines content (timestamp ignored for change detection)
    headlines_str = json.dumps(headlines, sort_keys=True, ensure_ascii=False)
    current_hash = hashlib.sha256(headlines_str.encode('utf-8')).hexdigest()

    # Push only on real content change or first run, and respect debounce
    if (last_hash is None or 
        (last_hash != current_hash and time.time() - last_push_time > MIN_PUSH_INTERVAL)):
        
        print("📰 News content changed → pushing to ESP32 via BLE")
        success = await push_to_esp32(data)
        if success:
            last_hash = current_hash

    current_data = data


async def main():
    global last_hash, last_push_time
    last_hash = None
    last_push_time = 0

    print("🚀 BLE News updater started (using Bleak). Press Ctrl+C to exit.")

    while True:
        await update_news()
        await asyncio.sleep(60)   # Check every minute, push is debounced


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Shutting down...")
    except Exception as e:
        print(f"Critical error: {e}")
