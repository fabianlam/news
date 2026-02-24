import asyncio
import json
import datetime
import time
import hashlib
import feedparser
import traceback
from bleak import BleakScanner, BleakClient
from bleak.exc import BleakError, BleakDeviceNotFoundError

# ==================== CONFIG ====================
ESP32_MAC = "80:B5:4E:D7:14:25"          # ← Change only if your MAC is different
ESP32_NAME = "LEDNewsDisplay"            # Device name from Arduino

SERVICE_UUID = "4fafc201-1fb5-459e-8fcc-c5c9c331914b"
CHAR_UUID = "beb5483e-36e1-4688-b7f5-ea07361b26a8"   # Your write characteristic

MIN_PUSH_INTERVAL = 300   # 5 minutes
SCAN_TIMEOUT = 10         # seconds
# ===============================================

last_hash = None
last_push_time = 0


def fetch_rss(url: str):
    feed = feedparser.parse(url)
    titles = [entry.title for entry in feed.entries[:10]]
    while len(titles) < 10:
        titles.append("")
    return titles


async def discover_device():
    """Scan and find the ESP32 by MAC or name"""
    print(f"🔍 Scanning for ESP32 ({ESP32_MAC} or name '{ESP32_NAME}')...")
    devices = await BleakScanner.discover(timeout=SCAN_TIMEOUT)
    
    for d in devices:
        if d.address.upper() == ESP32_MAC.upper() or (d.name and ESP32_NAME in d.name):
            print(f"✅ Found device: {d.name} | MAC: {d.address}")
            return d
    print("❌ ESP32 not found in scan. Check power, range, or MAC.")
    return None


async def push_to_esp32(data: dict):
    global last_push_time
    device = await discover_device()
    if not device:
        return False

    try:
        async with BleakClient(device) as client:   # Use discovered device object (most reliable)
            json_str = json.dumps(data, ensure_ascii=False)
            bytes_data = json_str.encode("utf-8")

            await client.write_gatt_char(CHAR_UUID, bytes_data, response=False)

            print(f"✅ PUSH SUCCESS → {len(bytes_data)} bytes at {datetime.datetime.now().strftime('%H:%M:%S')}")
            last_push_time = time.time()
            return True

    except BleakDeviceNotFoundError:
        print("❌ Device not reachable (out of range or not advertising)")
    except BleakError as e:
        print(f"❌ BleakError: {e}")
    except Exception as e:
        print(f"❌ Unexpected error: {type(e).__name__}: {e}")
        traceback.print_exc()
    return False


async def update_news():
    global last_hash, last_push_time

    categories = {
        "本港新聞": "https://rthk.hk/rthk/news/rss/c_expressnews_clocal.xml",
        "內地新聞": "https://rthk.hk/rthk/news/rss/c_expressnews_greaterchina.xml",
        "國際新聞": "https://rthk.hk/rthk/news/rss/c_expressnews_cinternational.xml",
        "財經新聞": "https://rthk.hk/rthk/news/rss/c_expressnews_cfinance.xml"
    }

    headlines = {label: fetch_rss(url) for label, url in categories.items()}

    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    data = {"timestamp": timestamp, "headlines": headlines}

    headlines_str = json.dumps(headlines, sort_keys=True, ensure_ascii=False)
    current_hash = hashlib.sha256(headlines_str.encode('utf-8')).hexdigest()

    if (last_hash is None or 
        (last_hash != current_hash and time.time() - last_push_time > MIN_PUSH_INTERVAL)):
        
        print("📰 News changed → attempting BLE push...")
        success = await push_to_esp32(data)
        if success:
            last_hash = current_hash
    else:
        print(f"⏳ No change or debounce active ({int(time.time() - last_push_time)}s since last push)")


async def main():
    global last_hash, last_push_time
    last_hash = None
    last_push_time = 0

    print("🚀 BLE News Updater (with discovery + full error logging) started.")
    print("Press Ctrl+C to stop.\n")

    while True:
        await update_news()
        await asyncio.sleep(60)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Stopped by user.")
    except Exception as e:
        print(f"Critical crash: {e}")
        traceback.print_exc()
