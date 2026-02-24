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
ESP32_MAC = "80:B5:4E:D7:14:25"          # Your ESP32 MAC
ESP32_NAME = "LEDNewsDisplay"

SERVICE_UUID = "4fafc201-1fb5-459e-8fcc-c5c9c331914b"
CHAR_UUID    = "beb5483e-36e1-4688-b7f5-ea07361b26a8"

MIN_PUSH_INTERVAL = 300   # 5 minutes
# ===============================================

last_hash = None
last_push_time = 0


def fetch_rss(url: str):
    feed = feedparser.parse(url)
    titles = [entry.title for entry in feed.entries[:10]]
    while len(titles) < 10:
        titles.append("")
    return titles


async def discover_and_connect():
    print(f"🔍 Scanning for {ESP32_NAME}...")
    devices = await BleakScanner.discover(timeout=10)
    for d in devices:
        if d.address.upper() == ESP32_MAC.upper() or (d.name and ESP32_NAME in (d.name or "")):
            print(f"✅ Found {d.name} | {d.address}")
            return d
    print("❌ ESP32 not found. Check power, range, advertising.")
    return None


async def push_to_esp32(data: dict):
    global last_push_time
    device = await discover_and_connect()
    if not device:
        return False

    try:
        async with BleakClient(device) as client:
            # === CRITICAL: Negotiate higher MTU ===
            print(f"Connected. Current MTU: {client.mtu_size} bytes")
            await client.request_mtu(512)          # Ask for 512 bytes (safe max for most ESP32)
            print(f"MTU negotiated to: {client.mtu_size} bytes")

            json_str = json.dumps(data, ensure_ascii=False)
            bytes_data = json_str.encode("utf-8")

            # Use response=True for large writes (more reliable)
            await client.write_gatt_char(CHAR_UUID, bytes_data, response=True)

            print(f"✅ PUSH SUCCESS → {len(bytes_data)} bytes at {datetime.datetime.now().strftime('%H:%M:%S')}")
            last_push_time = time.time()
            return True

    except Exception as e:
        print(f"❌ BLE Write Failed: {type(e).__name__}: {e}")
        if "MTU" in str(e) or "write" in str(e).lower():
            print("   → Try placing ESP32 closer to computer or restart ESP32")
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

    current_hash = hashlib.sha256(json.dumps(headlines, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

    if last_hash is None or (last_hash != current_hash and time.time() - last_push_time > MIN_PUSH_INTERVAL):
        print("📰 News changed → pushing via BLE...")
        await push_to_esp32(data)
        last_hash = current_hash
    else:
        print(f"⏳ No change (debounce active)")


async def main():
    global last_hash, last_push_time
    last_hash = None
    last_push_time = 0

    print("🚀 BLE News Updater with MTU negotiation started.")
    print("Press Ctrl+C to stop.\n")

    while True:
        await update_news()
        await asyncio.sleep(60)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, asyncio.CancelledError):
        print("\n👋 Stopped by user.")
    except Exception as e:
        print(f"Critical error: {e}")
        traceback.print_exc()
