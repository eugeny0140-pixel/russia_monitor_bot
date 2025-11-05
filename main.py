import os
import time
import logging
import re
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading
import schedule
import requests
from bs4 import BeautifulSoup
from deep_translator import GoogleTranslator
from supabase import create_client
# === Логирование ===
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)
# === Переменные окружения ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHANNEL_IDS = [cid.strip() for cid in os.getenv("CHANNEL_ID1", "").split(",") if cid.strip()]
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
PORT = int(os.getenv("PORT", 10000))
# Проверка обязательных переменных
for var in ["TELEGRAM_BOT_TOKEN", "CHANNEL_ID1", "SUPABASE_URL", "SUPABASE_KEY"]:
    if not os.getenv(var):
        logger.error(f"❌ Отсутствует переменная: {var}")
        exit(1)
# === Supabase ===
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
# === Ключевые слова (без дублей) ===
# === Ключевые слова (без дублей, с поддержкой латиницы и кириллицы) ===
KEYWORDS = {
        # --- Геополитика ---
    r"\brussia\b", r"\brussian\b", r"\bputin\b", r"\bmoscow\b", r"\bkremlin\b", r"\bukraine\b", r"\bukrainian\b", r"\bzelensky\b", r"\bkyiv\b", r"\bkiev\b", r"\bcrimea\b", r"\bdonbas\b", r"\bsanction[s]?\b", r"\bgazprom\b",  r"\bnord\s?stream\b", r"\bwagner\b", r"\blavrov\b", r"\bshoigu\b", r"\bmedvedev\b", r"\bpeskov\b", r"\bnato\b", r"\beuropa\b", r"\busa\b",r"\bsoviet\b", r"\bussr\b", r"\bpost\W?soviet\b", r"\bbelarus\b", r"\bminsk\b", r"\bmoldova\b", r"\bgeorgia\b", r"\bbaltic\b", r"\bestonia\b", r"\blatvia\b", r"\blithuania\b", r"\bblack\s?sea\b", r"\bcaucasus\b", r"\beastern\s?europe\b",
        # --- СВО и Военные действия ---
    r"\bsvo\b", r"\bспецоперация\b", r"\bspecial\s+military\s+operation\b", r"\bвойна\b", r"\bwar\b", r"\bconflict\b", r"\bконфликт\b", r"\bнаступление\b", r"\boffensive\b", r"\bатака\b", r"\battack\b", r"\bудар\b", r"\bstrike\b", r"\bобстрел\b", r"\bshelling\b", r"\bдрон\b", r"\bdrone\b", r"\bmissile\b", r"\bракета\b", r"\bэскалация\b", r"\bescalation\b", r"\bмобилизация\b", r"\bmobilization\b", r"\bфронт\b", r"\bfrontline\b", r"\bзахват\b", r"\bcapture\b", r"\bосвобождение\b", r"\bliberation\b", r"\bбой\b", r"\bbattle\b",  r"\bпотери\b", r"\bcasualties\b", r"\bпогиб\b", r"\bkilled\b", r"\bранен\b", r"\binjured\b", r"\bпленный\b", r"\bprisoner\s+of\s+war\b", r"\bпереговоры\b", r"\btalks\b", r"\bперемирие\b", r"\bceasefire\b", r"\bсанкции\b", r"\bsanctions\b", r"\bоружие\b", r"\bweapons\b",  r"\bпоставки\b", r"\bsupplies\b", r"\bhimars\b", r"\batacms\b",   r"\bhour\s+ago\b", r"\bчас\s+назад\b", r"\bminutos\s+atrás\b", r"\b小时前\b",
        # --- Криптовалюта и финтех ---
    r"\bbitcoin\b", r"\bbtc\b", r"\bбиткоин\b", r"\b比特币\b",  r"\bethereum\b", r"\beth\b", r"\bэфир\b", r"\b以太坊\b",  r"\bbinance\s+coin\b", r"\bbnb\b", r"\busdt\b", r"\btether\b",  r"\bxrp\b", r"\bripple\b", r"\bcardano\b", r"\bada\b",  r"\bsolana\b", r"\bsol\b", r"\bdoge\b", r"\bdogecoin\b",  r"\bavalanche\b", r"\bavax\b", r"\bpolkadot\b", r"\bdot\b",  r"\bchainlink\b", r"\blink\b", r"\btron\b", r"\btrx\b", r"\bcbdc\b", r"\bcentral\s+bank\s+digital\s+currency\b", r"\bцифровой\s+рубль\b",  r"\bdigital\s+yuan\b", r"\beuro\s+digital\b", r"\bdefi\b", r"\bдецентрализованные\s+финансы\b",  r"\bnft\b", r"\bnon\s*-\s*fungible\s+token\b", r"\bsec\b", r"\bцб\s+рф\b",  r"\bрегуляция\b", r"\bregulation\b", r"\bзапрет\b", r"\bban\b",  r"\bмайнинг\b", r"\bmining\b", r"\bhalving\b", r"\bхалвинг\b",  r"\bволатильность\b", r"\bvolatility\b", r"\bcrash\b", r"\bкрах\b",  r"\b刚刚\b", r"\bدقائق\s+مضت\b",
        # --- Пандемия и биобезопасность ---
        r"\bpandemic\b", r"\bпандемия\b", r"\b疫情\b", r"\bجائحة\b",  r"\boutbreak\b", r"\bвспышка\b", r"\bэпидемия\b", r"\bepidemic\b",  r"\bvirus\b", r"\bвирус\b", r"\bвирусы\b", r"\b变异株\b",  r"\bvaccine\b", r"\bвакцина\b", r"\b疫苗\b", r"\bلقاح\b", r"\bbooster\b", r"\bбустер\b", r"\bревакцинация\b", r"\bquarantine\b", r"\bкарантин\b", r"\b隔离\b", r"\bحجر\s+صحي\b", r"\blockdown\b", r"\bлокдаун\b", r"\b封锁\b", r"\bmutation\b", r"\bмутация\b", r"\b变异\b", r"\bstrain\b", r"\bштамм\b", r"\bomicron\b", r"\bdelta\b", r"\bbiosafety\b", r"\bбиобезопасность\b", r"\b生物安全\b", r"\blab\s+leak\b", r"\bлабораторная\s+утечка\b", r"\b实验室泄漏\b", r"\bgain\s+of\s+function\b", r"\bусиление\s+функции\b", r"\bwho\b", r"\bвоз\b", r"\bcdc\b", r"\bроспотребнадзор\b", r"\binfection\s+rate\b", r"\bзаразность\b", r"\b死亡率\b",  r"\bhospitalization\b", r"\bгоспитализация\b", r"\bقبل\s+ساعات\b", r"\b刚刚报告\b"
}
def is_relevant(text: str) -> bool:
    text = text.lower()
    return any(re.search(kw, text) for kw in KEYWORDS)
# === Вспомогательные функции ===
def clean_html(raw: str) -> str:
    if not raw:
        return ""
    return re.sub(r'<[^>]+>', '', raw).strip()

def translate(text: str) -> str:
    if not text.strip():
        return ""
    try:
        return GoogleTranslator(source='auto', target='ru').translate(text)
    except:
        return text

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
                json={"chat_id": ch, "text": message, "parse_mode": "HTML"},
                timeout=10
            )
            if resp.status_code == 200:
                logger.info(f"📤 Отправлено: {title[:60]}...")
            else:
                logger.error(f"❌ Ошибка Telegram: {resp.status_code}")
    except Exception as e:
        logger.exception("Ошибка отправки")
# === Парсер RSS ===
RSS_SOURCES = [
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
    {"name": "ECONOMIST", "rss": "https://www.economist.com/leaders/rss.xml"},
    {"name": "BLOOMBERG", "rss": "https://www.bloomberg.com/politics/feeds/site.xml"},
     # --- Новостные с расширенной фильтрацией по URL ---
    {"name": "REUTERS", "rss": "https://www.reuters.com/rss/world/", "filter_path": [ "/russia/", "/ukraine/", "/europe/", "/nato/", "/defense/", "/sanctions/",  "/energy/", "/gas/", "/putin/", "/kremlin/", "/moscow/", "/kiev/", "/kyiv/" ]},
    {"name": "AP", "rss": "https://feeds.apnews.com/apf-topnews", "filter_path": [ "/russia/", "/ukraine/", "/europe/", "/nato/", "/military/", "/sanctions/", "/energy-crisis/", "/putin/", "/war/", "/conflict/", "/eastern-europe/" ]},
    {"name": "POLITICO", "rss": "https://www.politico.com/rss/politicopicks.xml", "filter_path": [ "/russia/", "/ukraine/", "/europe/", "/defense/", "/national-security/", "/foreign-policy/", "/nato/", "/sanctions/", "/energy/", "/kremlin/" ]},
    {"name": "BBCNEWS", "rss": "https://feeds.bbci.co.uk/news/world/rss.xml", "filter_path": [ "/russia/", "/ukraine/", "/europe/", "/nato/", "/putin/", "/war-in-ukraine/", "/sanctions/", "/eastern-europe/", "/moscow/", "/kyiv/", "/kremlin/" ]},]
def parse_rss_sources():
    import feedparser
    for src in RSS_SOURCES:
        try:
            feed = feedparser.parse(src["rss"])
            for entry in feed.entries:
                url = entry.get("link", "").strip()
                if not url or is_article_sent(url):
                    continue
                # Фильтр по URL (только для новостных)
                if "filter_path" in src and not any(p in url.lower() for p in src["filter_path"]):
                    continue

                # Фильтр по дате (игнорировать старше 7 дней)
                published = getattr(entry, "published", None)
                if published:
                    try:
                        pub_date = datetime.strptime(published, "%a, %d %b %Y %H:%M:%S %Z")
                    except:
                        try:
                            pub_date = datetime.strptime(published, "%Y-%m-%dT%H:%M:%S%z")
                        except:
                            pub_date = None
                    if pub_date and (datetime.now(timezone.utc) - pub_date).days > 7:
                        continue
                title = entry.get("title", "").strip()
                desc = clean_html(entry.get("summary", "")).strip()
                if not title or not desc:
                    continue
                # Убрать дубль заголовка и шаблонные фразы
                if desc.lower().startswith(title.lower()):
                    desc = desc[len(title):].lstrip(" –-:,.")

                desc = re.sub(r"(Сводная информация о листинге|Пожалуйста, присоединяйтесь|Drupal-администратор).*", "", desc, flags=re.IGNORECASE | re.DOTALL)
                desc = "\n".join(line.strip() for line in desc.splitlines() if line.strip())

                if not is_relevant(f"{title} {desc}"):
                    continue
                lead = ""
                sentences = [s.strip() for s in re.split(r'[.!?]+', desc) if s.strip()]
                if sentences:
                    lead = sentences[0] + "."
                else:
                    lead = desc[:150] + "..."
                send_to_telegram(src["name"], title, lead, url)
                mark_article_sent(url, title)
                time.sleep(0.5)
        except Exception as e:
            logger.error(f"Ошибка RSS {src['name']}: {e}")
# === Основная функция ===
def fetch_all():
    logger.info("📡 Проверка всех источников...")
    parse_rss_sources()
    logger.info("✅ Проверка завершена.")

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
    logger.info(f"🌐 HTTP-сервер на порту {PORT}")
    server.serve_forever()
# === Запуск ===
if __name__ == "__main__":
    logger.info("🚀 Запуск бота...")
    threading.Thread(target=run_http, daemon=True).start()
    # Проверка подключения к Supabase
    try:
        supabase.table("published_articles").select("url").limit(1).execute()
        logger.info("✅ Supabase подключён")
    except Exception as e:
        logger.error(f"❌ Ошибка подключения к Supabase: {e}")
        exit(1)
    fetch_all()
    schedule.every(15).minutes.do(fetch_all)
    while True:
        schedule.run_pending()
        time.sleep(60)
