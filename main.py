import os
import time
import logging
import re
import feedparser
from datetime import datetime, timedelta
from urllib.parse import urlparse
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
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# === Переменные окружения ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHANNEL_IDS = [cid.strip() for cid in os.getenv("CHANNEL_ID1", "").split(",") if cid.strip()]
if os.getenv("CHANNEL_ID2"):
    CHANNEL_IDS.append(os.getenv("CHANNEL_ID2").strip())

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

PORT = int(os.getenv("PORT", 10000))

# === Инициализация Supabase ===
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# === Список источников ===
SOURCES = [
    {"name": "E3G", "rss": "https://www.e3g.org/feed/"},
    {"name": "Foreign Affairs", "rss": "https://www.foreignaffairs.com/rss.xml"},
    {"name": "Reuters Institute", "rss": "https://reutersinstitute.politics.ox.ac.uk/feed"},
    {"name": "Bruegel", "rss": "https://www.bruegel.org/rss"},
    {"name": "Chatham House", "rss": "https://www.chathamhouse.org/feed"},
    {"name": "CSIS", "rss": "https://www.csis.org/rss.xml"},
    {"name": "Atlantic Council", "rss": "https://www.atlanticcouncil.org/feed/"},
    {"name": "RAND Corporation", "rss": "https://www.rand.org/rss/recent.xml"},
    {"name": "CFR", "rss": "https://www.cfr.org/rss.xml"},
    {"name": "Carnegie Endowment", "rss": "https://carnegieendowment.org/rss"},
    {"name": "The Economist", "rss": "https://www.economist.com/rss/the_world_this_week_rss.xml"},
    {"name": "Bloomberg Politics", "rss": "https://www.bloomberg.com/politics/feeds/site.xml"},
]

# === Ключевые слова ===
KEYWORDS = {
    'russia', 'ukraine', 'putin', 'kremlin', 'sanctions', 'gas', 'oil',
    'military', 'nato', 'eu', 'usa', 'europe', 'moscow', 'kiev', 'kyiv',
    'defense', 'war', 'geopolitic', 'energy', 'export', 'grain', 'black sea'
}

def translate_text(text: str, target="ru") -> str:
    if not text.strip():
        return ""
    try:
        return GoogleTranslator(source='auto', target=target).translate(text)
    except Exception as e:
        logger.warning(f"GoogleTranslate failed: {e}. Trying MyMemory.")
        try:
            return MyMemoryTranslator(source='auto', target=target).translate(text)
        except Exception as e2:
            logger.error(f"MyMemory failed too: {e2}. Returning original.")
            return text

def escape_markdown_v2(text: str) -> str:
    # Экранируем спецсимволы для MarkdownV2
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    for c in escape_chars:
        text = text.replace(c, '\\' + c)
    return text

def is_relevant(title: str, description: str) -> bool:
    text = (title + " " + description).lower()
    return any(kw in text for kw in KEYWORDS)

def is_generic_description(desc: str) -> bool:
    # Пропускаем шаблонные описания
    generic_phrases = ["appeared first on", "read more", "click here", "©"]
    return any(phrase in desc for phrase in generic_phrases)

def send_to_telegram(prefix: str, title: str, lead: str, url: str):
    try:
        title_ru = translate_text(title)
        lead_ru = translate_text(lead)

        # Формируем сообщение
        message = f"{prefix}: {title_ru}\n\n{lead_ru}\n\n[Источник]({url})"
        message = escape_markdown_v2(message)

        for channel in CHANNEL_IDS:
            url_tg = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            payload = {
                "chat_id": channel,
                "text": message,
                "parse_mode": "MarkdownV2",
                "disable_web_page_preview": False
            }
            resp = requests.post(url_tg, json=payload, timeout=10)
            if resp.status_code == 200:
                logger.info(f"✅ Sent to {channel}: {title}")
            else:
                logger.error(f"❌ Telegram error: {resp.text}")
    except Exception as e:
        logger.exception(f"Failed sending message: {e}")

def article_already_sent(url: str) -> bool:
    try:
        response = supabase.table("published_articles").select("url").eq("url", url).execute()
        return len(response.data) > 0
    except Exception as e:
        logger.error(f"Supabase check error: {e}")
        return False  # На случай ошибки — считаем, что не отправляли

def mark_article_as_sent(url: str, title: str):
    try:
        supabase.table("published_articles").insert({"url": url, "title": title}).execute()
        logger.info(f"📌 Marked as sent: {url}")
    except Exception as e:
        logger.error(f"Supabase insert error: {e}")

def fetch_and_process():
    logger.info("📡 Starting feed check...")
    for source in SOURCES:
        name = source["name"]
        rss_url = source["rss"]
        prefix = name
        try:
            feed = feedparser.parse(rss_url)
            for entry in feed.entries:
                url = entry.get("link", "").strip()
                if not url:
                    continue

                # Пропускаем дубли
                if article_already_sent(url):
                    continue

                title = entry.get("title", "").strip()
                desc = entry.get("summary", "").strip() or entry.get("description", "").strip()

                if not title or not desc:
                    continue

                # Пропускаем шаблонные описания
                if is_generic_description(desc):
                    continue

                # Фильтрация по теме
                if not is_relevant(title, desc):
                    continue

                # Берём только первый абзац или первое предложение
                lead = desc.split("\n")[0].split(". ")[0]
                if not lead.strip():
                    continue

                logger.info(f"🔍 Found relevant: {title} ({url})")

                send_to_telegram(prefix, title, lead, url)
                mark_article_as_sent(url, title)

                time.sleep(1)  # избегаем спама

        except Exception as e:
            logger.error(f"Error processing {rss_url}: {e}")

    logger.info("✅ Feed check complete.")

# === HTTP-сервер для Render ===
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"OK")

def run_http_server():
    server = HTTPServer(("", PORT), HealthHandler)
    logger.info(f"🌐 HTTP server running on port {PORT}")
    server.serve_forever()

# === Запуск ===
if __name__ == "__main__":
    logger.info("🚀 Russia Monitor Bot starting...")

    # Запускаем HTTP-сервер в отдельном потоке
    http_thread = threading.Thread(target=run_http_server, daemon=True)
    http_thread.start()

    # Первый запуск сразу
    fetch_and_process()

    # Планировщик: каждые 30 минут
    schedule.every(30).minutes.do(fetch_and_process)

    # Костыль для cron-job: каждый час пингуем "keep-alive"
    schedule.every().hour.do(lambda: logger.info("⏰ Cron heartbeat"))

    while True:
        schedule.run_pending()
        time.sleep(30)
