import asyncio
import json
import datetime
import time
import hashlib
import feedparser
import traceback
import signal
from bleak import BleakScanner, BleakClient
from bleak.exc import BleakError, BleakDeviceNotFoundError

# ==================== CONFIG ====================
ESP32_MAC = "80:B5:4E:D7:14:25"          # ← Your ESP32 MAC
ESP32_NAME = "LEDNewsDisplay"

SERVICE_UUID = "4fafc201-1fb5-459e-8fcc-c5c9c331914b"
CHAR_UUID    = "beb5483e-36e1-4688-b7f5-ea07361b26a8"

MIN_PUSH_INTERVAL = 300   # 5 minutes
SCAN_TIMEOUT = 10
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
    print(f"🔍 Scanning for {ESP32_NAME} ({ESP32_MAC})...")
    devices = await BleakScanner.discover(timeout=SCAN_TIMEOUT)
    for d in devices:
        if d.address.upper() == ESP32_MAC.upper() or (d.name and ESP32_NAME.lower() in (d.name or "").lower()):
            print(f"✅ Found: {d.name} | {d.address}")
            return d
    print("❌ ESP32 not found. Check power / range / advertising.")
    return None


async def push_to_esp32(data: dict):
    global last_push_time
    device = await discover_device()
    if not device:
        return False

    try:
        async with BleakClient(device) as client:
            json_str = json.dumps(data, ensure_ascii=False)
            await client.write_gatt_char(CHAR_UUID, json_str.encode("utf-8"), response=False)

            print(f"✅ PUSH SUCCESS → {len(json_str)} bytes at {datetime.datetime.now().strftime('%H:%M:%S')}")
            last_push_time = time.time()
            return True

    except Exception as e:
        print(f"❌ BLE Push Failed: {type(e).__name__}: {e}")
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

    current_hash = hashlib.sha256(json.dumps(headlines, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

    if last_hash is None or (last_hash != current_hash and time.time() - last_push_time > MIN_PUSH_INTERVAL):
        print("📰 News changed → pushing via BLE...")
        await push_to_esp32(data)
        last_hash = current_hash


async def main():
    global last_hash, last_push_time
    last_hash = None
    last_push_time = 0

    print("🚀 BLE News Updater started (robust version). Press Ctrl+C to stop.\n")

    try:
        while True:
            await update_news()
            await asyncio.sleep(60)
    except (KeyboardInterrupt, asyncio.CancelledError, EOFError):
        print("\n\n👋 Shutting down gracefully...")
    except Exception as e:
        print(f"\n💥 Unexpected error: {e}")
        traceback.print_exc()
    finally:
        print("Goodbye!")


if __name__ == "__main__":
    # Handle Ctrl+C cleanly on all platforms
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(main())
    except (KeyboardInterrupt, EOFError):
        print("\n👋 Stopped.")
    finally:
        loop.close()
