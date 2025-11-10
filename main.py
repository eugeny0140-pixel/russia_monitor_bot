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

# === Ключевые слова (объединённые) ===
KEYWORDS = {
    # --- Россия ---
    r"\brussia\b", r"\brussian\b", r"\bputin\b", r"\bmoscow\b", r"\bkremlin\b",
    r"\bukraine\b", r"\bukrainian\b", r"\bzelensky\b", r"\bkyiv\b", r"\bkiev\b",
    r"\bcrimea\b", r"\bdonbas\b", r"\bsanction[s]?\b", r"\bgazprom\b",
    r"\bnord\s?stream\b", r"\bwagner\b", r"\blavrov\b", r"\bshoigu\b",
    r"\bmedvedev\b", r"\bpeskov\b", r"\bnato\b", r"\beuropa\b", r"\busa\b",
    r"\bsoviet\b", r"\bussr\b", r"\bpost\W?soviet\b",
    # --- СВО ---
    r"\bsvo\b", r"\bспецоперация\b", r"\bspecial\s+military\s+operation\b",
    r"\bвойна\b", r"\bwar\b", r"\bconflict\b", r"\bконфликт\b",
    r"\bнаступление\b", r"\boffensive\b", r"\bатака\b", r"\battack\b",
    r"\bудар\b", r"\bstrike\b", r"\bобстрел\b", r"\bshelling\b",
    r"\bдрон\b", r"\bdrone\b", r"\bmissile\b", r"\bракета\b",
    r"\bэскалация\b", r"\bescalation\b", r"\bмобилизация\b", r"\bmobilization\b",
    r"\bфронт\b", r"\bfrontline\b", r"\bзахват\b", r"\bcapture\b",
    r"\bосвобождение\b", r"\bliberation\b", r"\bбой\b", r"\bbattle\b",
    r"\bпотери\b", r"\bcasualties\b", r"\bпогиб\b", r"\bkilled\b",
    r"\bранен\b", r"\binjured\b", r"\bпленный\b", r"\bprisoner\s+of\s+war\b",
    r"\bпереговоры\b", r"\btalks\b", r"\bперемирие\b", r"\bceasefire\b",
    r"\bсанкции\b", r"\bsanctions\b", r"\bоружие\b", r"\bweapons\b",
    r"\bпоставки\b", r"\bsupplies\b", r"\bhimars\b", r"\batacms\b",
    # --- Криптовалюта ---
    r"\bbitcoin\b", r"\bbtc\b", r"\bбиткоин\b", r"\b比特币\b",
    r"\bethereum\b", r"\beth\b", r"\bэфир\b", r"\b以太坊\b",
    r"\bbinance\s+coin\b", r"\bbnb\b", r"\busdt\b", r"\btether\b",
    r"\bxrp\b", r"\bripple\b", r"\bcardano\b", r"\bada\b",
    r"\bsolana\b", r"\bsol\b", r"\bdoge\b", r"\bdogecoin\b",
    r"\bavalanche\b", r"\bavax\b", r"\bpolkadot\b", r"\bdot\b",
    r"\bchainlink\b", r"\blink\b", r"\btron\b", r"\btrx\b",
    r"\bcbdc\b", r"\bcentral\s+bank\s+digital\s+currency\b", r"\bцифровой\s+рубль\b",
    r"\bdigital\s+yuan\b", r"\beuro\s+digital\b", r"\bdefi\b", r"\bдецентрализованные\s+финансы\b",
    r"\bnft\b", r"\bnon\s*-\s*fungible\s+token\b", r"\bsec\b", r"\bцб\s+рф\b",
    r"\bрегуляция\b", r"\bregulation\b", r"\bзапрет\b", r"\bban\b",
    r"\bмайнинг\b", r"\bmining\b", r"\bhalving\b", r"\bхалвинг\b",
    r"\bволатильность\b", r"\bvolatility\b", r"\bcrash\b", r"\bкрах\b",
    # --- Пандемия ---
    r"\bpandemic\b", r"\bпандемия\b", r"\b疫情\b", r"\bجائحة\b",
    r"\boutbreak\b", r"\bвспышка\b", r"\bэпидемия\b", r"\bepidemic\b",
    r"\bvirus\b", r"\bвирус\b", r"\bвирусы\b", r"\b变异株\b",
    r"\bvaccine\b", r"\bвакцина\b", r"\b疫苗\b", r"\bلقاح\b",
    r"\bbooster\b", r"\bбустер\b", r"\bревакцинация\b",
    r"\bquarantine\b", r"\bкарантин\b", r"\b隔离\b", r"\bحجر\s+صحي\b",
    r"\blockdown\b", r"\bлокдаун\b", r"\b封锁\b",
    r"\bmutation\b", r"\bмутация\b", r"\b变异\b",
    r"\bstrain\b", r"\bштамм\b", r"\bomicron\b", r"\bdelta\b",
    r"\bbiosafety\b", r"\bбиобезопасность\b", r"\b生物安全\b",
    r"\blab\s+leak\b", r"\bлабораторная\s+утечка\b", r"\b实验室泄漏\b",
    r"\bgain\s+of\s+function\b", r"\bусиление\s+функции\b",
    r"\bwho\b", r"\bвоз\b", r"\bcdc\b", r"\bроспотребнадзор\b",
    r"\binfection\s+rate\b", r"\bзаразность\b", r"\b死亡率\b",
    r"\bhospitalization\b", r"\bгоспитализация\b",
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
                logger.error(f"❌ Ошибка Telegram: {resp.status_code} - {resp.text}")
    except Exception as e:
        logger.exception("Ошибка отправки")

# === RSS-источники ===
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
    {"name": "WEF", "rss": "https://www.weforum.org/feeds/root.xml"},
    {"name": "BBCNEWS", "rss": "https://feeds.bbci.co.uk/news/world/rss.xml", "filter_path": ["/russia/", "/ukraine/", "/europe/"]},
]

def parse_rss_sources():
    import feedparser
    for src in RSS_SOURCES:
        try:
            feed = feedparser.parse(src["rss"])
            for entry in feed.entries:
                url = entry.get("link", "").strip()
                if not url or is_article_sent(url):
                    continue

                if "filter_path" in src and not any(p in url.lower() for p in src["filter_path"]):
                    continue

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

                if not is_relevant(f"{title} {desc}"):
                    continue

                lead = desc.split(". ")[0].strip() or desc[:150] + "..."
                send_to_telegram(src["name"], title, lead, url)
                mark_article_sent(url, title)
                time.sleep(0.5)

        except Exception as e:
            logger.error(f"Ошибка RSS {src['name']}: {e}")

# === HTML-источники ===
def parse_goodjudgment():
    url = "https://goodjudgment.com/open-questions/"
    try:
        resp = requests.get(url, timeout=10)
        soup = BeautifulSoup(resp.text, 'html.parser')
        for item in soup.select('.question-title a'):
            title = item.get_text(strip=True)
            href = item['href']
            if href.startswith('/'): href = 'https://goodjudgment.com' + href
            if not href.startswith('http') or is_article_sent(href): continue
            if not is_relevant(title): continue
            send_to_telegram("GOODJ", title, "Superforecasting question", href)
            mark_article_sent(href, title)
    except Exception as e:
        logger.error(f"Ошибка GOODJ: {e}")

def parse_jhchs():
    url = "https://www.centerforhealthsecurity.org"
    try:
        resp = requests.get(url, timeout=10)
        soup = BeautifulSoup(resp.text, 'html.parser')
        for item in soup.select('h2 a, h3 a'):
            title = item.get_text(strip=True)
            href = item['href']
            if href.startswith('/'): href = url + href
            if not href.startswith('http') or is_article_sent(href): continue
            if not is_relevant(title): continue
            send_to_telegram("JHCHS", title, "Report from Johns Hopkins", href)
            mark_article_sent(href, title)
    except Exception as e:
        logger.error(f"Ошибка JHCHS: {e}")

def parse_metaculus():
    api_url = "https://www.metaculus.com/api2/questions/?status=open&limit=10"
    try:
        data = requests.get(api_url, timeout=10).json()
        for q in data.get('results', []):
            title = q.get('title', '').strip()
            page_url = q.get('page_url', '').strip()
            if not title or not page_url: continue
            full_url = "https://www.metaculus.com" + page_url
            if is_article_sent(full_url) or not is_relevant(title): continue
            desc = clean_html(q.get('description', ''))[:200] + "..."
            send_to_telegram("META", title, desc, full_url)
            mark_article_sent(full_url, title)
    except Exception as e:
        logger.error(f"Ошибка META: {e}")

def parse_dni():
    url = "https://www.dni.gov"
    try:
        resp = requests.get(url, timeout=10)
        soup = BeautifulSoup(resp.text, 'html.parser')
        for a in soup.find_all('a', href=True):
            if 'global' in a['href'].lower() and 'trend' in a['href'].lower():
                full_url = a['href']
                if not full_url.startswith('http'): full_url = url + full_url
                if is_article_sent(full_url): continue
                title = "DNI Global Trends Report"
                send_to_telegram("DNI", title, "US intelligence forecast", full_url)
                mark_article_sent(full_url, title)
                return
    except Exception as e:
        logger.error(f"Ошибка DNI: {e}")

def parse_bbc_future():
    url = "https://www.bbc.com/future"
    try:
        resp = requests.get(url, timeout=10)
        soup = BeautifulSoup(resp.text, 'html.parser')
        for item in soup.select('a[href*="/future/article/"]'):
            href = item['href']
            if href.startswith('/'): href = 'https://www.bbc.com' + href
            if is_article_sent(href): continue
            title = item.get_text(strip=True)
            if not title or not is_relevant(title): continue
            send_to_telegram("BBCFUTURE", title, "From BBC Future", href)
            mark_article_sent(href, title)
    except Exception as e:
        logger.error(f"Ошибка BBCFUTURE: {e}")

def parse_future_timeline():
    url = "https://www.futuretimeline.net"
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code != 200: return
        soup = BeautifulSoup(resp.text, 'html.parser')
        for item in soup.select('li a'):
            href = item['href']
            if href.startswith('/'): href = 'https://www.futuretimeline.net' + href
            if 'futuretimeline.net' not in href or is_article_sent(href): continue
            title = item.get_text(strip=True)
            if not title or not is_relevant(title): continue
            send_to_telegram("FUTTL", title, "Long-term forecast", href)
            mark_article_sent(href, title)
    except Exception as e:
        logger.error(f"Ошибка FUTTL: {e}")

# === Основная функция ===
def fetch_all():
    logger.info("📡 Проверка всех источников...")
    parse_rss_sources()
    parse_goodjudgment()
    parse_jhchs()
    parse_metaculus()
    parse_dni()
    parse_bbc_future()
    parse_future_timeline()
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
    logger.info("🚀 Запуск бота (все 19 источников)...")
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
