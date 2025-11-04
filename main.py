import os
import time
import logging
import re
import feedparser
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading
import schedule
import requests
from deep_translator import GoogleTranslator, MyMemoryTranslator
from supabase import create_client

# === Настройка логирования ===
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# === Переменные окружения ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHANNEL_IDS = [cid.strip() for cid in os.getenv("CHANNEL_ID1", "").split(",") if cid.strip()]
if os.getenv("CHANNEL_ID2"):
    CHANNEL_IDS.extend([cid.strip() for cid in os.getenv("CHANNEL_ID2").split(",") if cid.strip()])

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
PORT = int(os.getenv("PORT", 10000))

# === Проверка обязательных переменных ===
if not TELEGRAM_TOKEN or not CHANNEL_IDS:
    logger.error("❌ TELEGRAM_BOT_TOKEN и CHANNEL_ID1 обязательны!")
    exit(1)

if not SUPABASE_URL or not SUPABASE_KEY:
    logger.error("❌ SUPABASE_URL и SUPABASE_KEY обязательны!")
    exit(1)

# === Подключение к Supabase ===
try:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    # Пробный запрос для проверки
    supabase.table("published_articles").select("url").limit(1).execute()
    logger.info("✅ Supabase подключён успешно")
except Exception as e:
    logger.error(f"❌ Ошибка подключения к Supabase: {e}")
    exit(1)

# === Источники ===
SOURCES = [
    {"name": "E3G", "rss": "https://www.e3g.org/feed/"},
    {"name": "Foreign Affairs", "rss": "https://www.foreignaffairs.com/rss.xml"},
    {"name": "Reuters Institute", "rss": "https://reutersinstitute.politics.ox.ac.uk/feed"},
    {"name": "Bruegel", "rss": "https://www.bruegel.org/rss"},
    {"name": "Chatham House", "rss": "https://www.chathamhouse.org/feed"},
    {"name": "CSIS", "rss": "https://www.csis.org/rss.xml"},
    {"name": "Atlantic Council", "rss": "https://www.atlanticcouncil.org/feed/"},
    {"name": "RAND", "rss": "https://www.rand.org/rss/recent.xml"},
    {"name": "CFR", "rss": "https://www.cfr.org/rss.xml"},
    {"name": "Carnegie", "rss": "https://carnegieendowment.org/rss"},
    {"name": "The Economist", "rss": "https://www.economist.com/rss/the_world_this_week_rss.xml"},
    {"name": "Bloomberg", "rss": "https://www.bloomberg.com/politics/feeds/site.xml"},
]

KEYWORDS = {
    'russia', 'ukraine', 'putin', 'kremlin', 'sanctions', 'gas', 'oil',
    'military', 'nato', 'eu', 'usa', 'europe', 'moscow', 'kyiv', 'kiev',
    'war', 'geopolitic', 'energy', 'defense', 'grain', 'black sea'
}

# === Вспомогательные функции ===
def translate(text: str) -> str:
    if not text.strip():
        return ""
    try:
        return GoogleTranslator(source='auto', target='ru').translate(text)
    except Exception as e:
        logger.warning(f"GoogleTranslate failed: {e}. Trying MyMemory.")
        try:
            return MyMemoryTranslator(source='auto', target='ru').translate(text)
        except:
            return text

def escape_md(text: str) -> str:
    return re.sub(r"([_*[\]()~`>#+\-=|{}.!])", r"\\\1", text)

def is_relevant(title: str, desc: str) -> bool:
    text = (title + " " + desc).lower()
    return any(kw in text for kw in KEYWORDS)

def is_generic(desc: str) -> bool:
    generic = ["appeared first on", "read more", "click here", "©", "all rights reserved"]
    return any(phrase in desc.lower() for phrase in generic)

def is_article_sent(url: str) -> bool:
    try:
        resp = supabase.table("published_articles").select("url").eq("url", url).execute()
        return len(resp.data) > 0
    except Exception as e:
        logger.error(f"Supabase check error: {e}")
        return False

def mark_article_sent(url: str, title: str):
    try:
        supabase.table("published_articles").insert({"url": url, "title": title}).execute()
        logger.info(f"✅ Saved: {url}")
    except Exception as e:
        logger.error(f"Supabase insert error: {e}")

def send_to_telegram(prefix: str, title: str, lead: str, url: str):
    try:
        title_ru = translate(title)
        lead_ru = translate(lead)
        msg = f"{prefix}: {title_ru}\n\n{lead_ru}\n\n[Источник]({url})"
        msg = escape_md(msg)

        for ch in CHANNEL_IDS:
            resp = requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={
                    "chat_id": ch,
                    "text": msg,
                    "parse_mode": "MarkdownV2"
                },
                timeout=10
            )
            if resp.status_code == 200:
                logger.info(f"📤 Sent: {title[:60]}...")
            else:
                logger.error(f"❌ TG error: {resp.status_code} {resp.text}")
    except Exception as e:
        logger.exception(f"Telegram send failed: {e}")

def fetch_and_process():
    logger.info("📡 Checking feeds...")
    for src in SOURCES:
        try:
            feed = feedparser.parse(src["rss"])
            for entry in feed.entries:
                url = entry.get("link", "").strip()
                if not url or is_article_sent(url):
                    continue

                title = entry.get("title", "").strip()
                desc = (entry.get("summary") or entry.get("description") or "").strip()
                if not title or not desc or is_generic(desc):
                    continue

                if not is_relevant(title, desc):
                    continue

                lead = desc.split("\n")[0].split(". ")[0].strip()
                if not lead:
                    continue

                send_to_telegram(src["name"], title, lead, url)
                mark_article_sent(url, title)
                time.sleep(0.5)

        except Exception as e:
            logger.error(f"Error processing {src['name']}: {e}")

    logger.info("✅ Feed check completed.")

# === HTTP-сервер для Render ===
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ["/", "/health"]:
            self.send_response(200)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            self.wfile.write(b"OK")
        else:
            self.send_response(404)
            self.end_headers()

def run_http():
    server = HTTPServer(("", PORT), HealthHandler)
    logger.info(f"🌐 HTTP server running on port {PORT}")
    server.serve_forever()

# === Основной запуск ===
if __name__ == "__main__":
    logger.info("🚀 Starting Russia Monitor Bot...")

    # Запуск HTTP-сервера в фоне
    threading.Thread(target=run_http, daemon=True).start()

    # Первый запуск сразу
    fetch_and_process()

    # Планировщик: каждые 30 минут
    schedule.every(30).minutes.do(fetch_and_process)

    # Keep-alive для cron-job
    schedule.every().hour.do(lambda: logger.info("⏰ Heartbeat"))

    while True:
        schedule.run_pending()
        time.sleep(30)
