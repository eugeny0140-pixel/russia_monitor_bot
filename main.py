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

# === Логирование ===
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# === Настройки ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHANNEL_IDS = [cid.strip() for cid in os.getenv("CHANNEL_ID1", "").split(",") if cid.strip()]
if os.getenv("CHANNEL_ID2"):
    CHANNEL_IDS.extend([cid.strip() for cid in os.getenv("CHANNEL_ID2").split(",") if cid.strip()])

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
PORT = int(os.getenv("PORT", 10000))

# === Проверка настроек ===
for var in ["TELEGRAM_BOT_TOKEN", "CHANNEL_ID1", "SUPABASE_URL", "SUPABASE_KEY"]:
    if not os.getenv(var):
        logger.error(f"❌ Обязательная переменная {var} не задана!")
        exit(1)

# === Подключение к Supabase ===
try:
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    supabase.table("published_articles").select("url").limit(1).execute()
    logger.info("✅ Supabase подключён")
except Exception as e:
    logger.error(f"❌ Supabase ошибка: {e}")
    exit(1)

# === Источники (с короткими префиксами) ===
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
    {"name": "ECONOMIST", "rss": "https://www.economist.com/rss/the_world_this_week_rss.xml"},
    {"name": "BLOOMBERG", "rss": "https://www.bloomberg.com/politics/feeds/site.xml"},
]

KEYWORDS = {
    r"\brussia\b", r"\brussian\b", r"\bputin\b", r"\bmoscow\b", r"\bkremlin\b",
r"\bukraine\b", r"\bukrainian\b", r"\bzelensky\b", r"\bkyiv\b", r"\bkiev\b",
r"\bcrimea\b", r"\bdonbas\b", r"\bsanction[s]?\b", r"\bgazprom\b",
r"\bnord\s?stream\b", r"\bwagner\b", r"\blavrov\b", r"\bshoigu\b",
r"\bmedvedev\b", r"\bpeskov\b", r"\bnato\b", r"\beuropa\b", r"\busa\b",
r"\bsoviet\b", r"\bussr\b", r"\bpost\W?soviet\b",
# === СВО и Война ===
r"\bsvo\b", r"\bспецоперация\b", r"\bspecial military operation\b",
r"\bвойна\b", r"\bwar\b", r"\bconflict\b", r"\bконфликт\b",
r"\bнаступление\b", r"\boffensive\b", r"\bатака\b", r"\battack\b",
r"\bудар\b", r"\bstrike\b", r"\bобстрел\b", r"\bshelling\b",
r"\bдрон\b", r"\bdrone\b", r"\bmissile\b", r"\bракета\b",
r"\bэскалация\b", r"\bescalation\b", r"\bмобилизация\b", r"\bmobilization\b",
r"\bфронт\b", r"\bfrontline\b", r"\bзахват\b", r"\bcapture\b",
r"\bосвобождение\b", r"\bliberation\b", r"\bбой\b", r"\bbattle\b",
r"\bпотери\b", r"\bcasualties\b", r"\bпогиб\b", r"\bkilled\b",
r"\bранен\b", r"\binjured\b", r"\bпленный\b", r"\bprisoner of war\b",
r"\bпереговоры\b", r"\btalks\b", r"\bперемирие\b", r"\bceasefire\b",
r"\bсанкции\b", r"\bsanctions\b", r"\bоружие\b", r"\bweapons\b",
r"\bпоставки\b", r"\bsupplies\b", r"\bhimars\b", r"\batacms\b",
r"\bhour ago\b", r"\bчас назад\b", r"\bminutos atrás\b", r"\b小时前\b",
# === Криптовалюта (топ-20 + CBDC, DeFi, регуляция) ===
r"\bbitcoin\b", r"\bbtc\b", r"\bбиткоин\b", r"\b比特币\b",
r"\bethereum\b", r"\beth\b", r"\bэфир\b", r"\b以太坊\b",
r"\bbinance coin\b", r"\bbnb\b", r"\busdt\b", r"\btether\b",
r"\bxrp\b", r"\bripple\b", r"\bcardano\b", r"\bada\b",
r"\bsolana\b", r"\bsol\b", r"\bdoge\b", r"\bdogecoin\b",
r"\bavalanche\b", r"\bavax\b", r"\bpolkadot\b", r"\bdot\b",
r"\bchainlink\b", r"\blink\b", r"\btron\b", r"\btrx\b",
r"\bcbdc\b", r"\bcentral bank digital currency\b", r"\bцифровой рубль\b",
r"\bdigital yuan\b", r"\beuro digital\b", r"\bdefi\b", r"\bдецентрализованные финансы\b",
r"\bnft\b", r"\bnon-fungible token\b", r"\bsec\b", r"\bцб рф\b",
r"\bрегуляция\b", r"\bregulation\b", r"\bзапрет\b", r"\bban\b",
r"\bмайнинг\b", r"\bmining\b", r"\bhalving\b", r"\bхалвинг\b",
r"\bволатильность\b", r"\bvolatility\b", r"\bcrash\b", r"\bкрах\b",
r"\b刚刚\b", r"\bدقائق مضت\b",
# === Пандемия и болезни (включая биобезопасность) ===
r"\bpandemic\b", r"\bпандемия\b", r"\b疫情\b", r"\bجائحة\b",
r"\boutbreak\b", r"\bвспышка\b", r"\bэпидемия\b", r"\bepidemic\b",
r"\bvirus\b", r"\bвирус\b", r"\bвирусы\b", r"\b变异株\b",
r"\bvaccine\b", r"\bвакцина\b", r"\b疫苗\b", r"\bلقاح\b",
r"\bbooster\b", r"\bбустер\b", r"\bревакцинация\b",
r"\bquarantine\b", r"\bкарантин\b", r"\b隔离\b", r"\bحجر صحي\b",
r"\blockdown\b", r"\bлокдаун\b", r"\b封锁\b",
r"\bmutation\b", r"\bмутация\b", r"\b变异\b",
r"\bstrain\b", r"\bштамм\b", r"\bomicron\b", r"\bdelta\b",
r"\bbiosafety\b", r"\bбиобезопасность\b", r"\b生物安全\b",
r"\blab leak\b", r"\bлабораторная утечка\b", r"\b实验室泄漏\b",
r"\bgain of function\b", r"\bусиление функции\b",
r"\bwho\b", r"\bвоз\b", r"\bcdc\b", r"\bроспотребнадзор\b",
r"\binfection rate\b", r"\bзаразность\b", r"\b死亡率\b",
r"\bhospitalization\b", r"\bгоспитализация\b",
r"\bقبل ساعات\b", r"\b刚刚报告\b"
}

# === Вспомогательные функции ===
def clean_html(raw: str) -> str:
    """Удаляет HTML-теги."""
    return re.sub(r'<[^>]+>', '', raw)

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

def is_relevant(title: str, desc: str) -> bool:
    text = (title + " " + desc).lower()
    return any(kw in text for kw in KEYWORDS)

def is_generic(desc: str) -> bool:
    return any(phrase in desc.lower() for phrase in ["appeared first", "read more", "©", "all rights"])

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
        message = f"<b>{prefix}</b>: {title_ru}\n\n{lead_ru}\n\nИсточник: {url}"

        for ch in CHANNEL_IDS:
            resp = requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={
                    "chat_id": ch,
                    "text": message,
                    "parse_mode": "HTML"
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
                desc = clean_html(desc)  # ← КРИТИЧЕСКИ ВАЖНО для CSIS и др.
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
            logger.error(f"Error on {src['name']}: {e}")

    logger.info("✅ Feed check completed.")

# === HTTP-сервер для Render ===
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ["/", "/health"]:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")
        else:
            self.send_response(404)
            self.end_headers()

def run_http():
    server = HTTPServer(("", PORT), Handler)
    logger.info(f"🌐 HTTP server on port {PORT}")
    server.serve_forever()

# === Запуск ===
if __name__ == "__main__":
    logger.info("🚀 Starting Russia Monitor Bot...")
    threading.Thread(target=run_http, daemon=True).start()
    fetch_and_process()
    schedule.every(30).minutes.do(fetch_and_process)
    schedule.every().hour.do(lambda: logger.info("⏰ Heartbeat"))

    while True:
        schedule.run_pending()
        time.sleep(30)
