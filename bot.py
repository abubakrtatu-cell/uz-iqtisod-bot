# -*- coding: utf-8 -*-
"""
O'zbekiston iqtisodiyoti va moliyasi bo'yicha yangiliklar yig'uvchi Telegram bot.

Manbalar:
  * Xorijiy saytlar  — Google News, Bing News va RSS lentalari orqali
  * O'zbek Telegram kanallari — ochiq kanallarning veb-ko'rinishi (t.me/s/...) orqali

Ishga tushirish:
  python bot.py              # bir marta tekshirib, yangi xabarlarni yuboradi
  python bot.py --dry-run    # hech narsa yubormaydi, faqat ekranga chiqaradi
  python bot.py --test       # Telegramga test xabari yuboradi
  python bot.py --loop 1800  # har 1800 soniyada (30 daqiqa) takrorlaydi (o'z kompyuteringizda)

Kerakli muhit o'zgaruvchilari:
  TELEGRAM_BOT_TOKEN — @BotFather bergan token
  TELEGRAM_CHAT_ID   — xabar boradigan chat ID (bir nechta bo'lsa vergul bilan),
                       yoki kanal uchun @kanal_nomi
"""
import argparse
import hashlib
import html
import json
import logging
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests
from bs4 import BeautifulSoup

import config

BASE_DIR = Path(__file__).resolve().parent
STATE_FILE = BASE_DIR / "data" / "seen.json"
STATE_KEEP_DAYS = 10

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_IDS = [c.strip() for c in os.environ.get("TELEGRAM_CHAT_ID", "").split(",") if c.strip()]

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0 Safari/537.36"
)
TZ = timezone(timedelta(hours=config.TZ_OFFSET_HOURS))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("bot")

session = requests.Session()
session.headers.update({"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9,ru;q=0.8"})


# ---------------------------------------------------------------------------
# Yordamchi funksiyalar
# ---------------------------------------------------------------------------

_APOSTROPHES = str.maketrans({c: "'" for c in "‘’ʻʼ`´′"})


def normalize(text):
    """Kichik harf + turli apostroflarni bitta ' ga keltirish."""
    return (text or "").translate(_APOSTROPHES).lower()


def _compile(patterns):
    return re.compile("|".join(f"(?:{p})" for p in patterns), re.IGNORECASE | re.MULTILINE)


ECON_RE = _compile(config.ECONOMY_KEYWORDS)
UZ_RE = _compile(config.UZBEKISTAN_PATTERNS)
EXCLUDE_RE = _compile(config.EXCLUDE_PATTERNS) if config.EXCLUDE_PATTERNS else None


def safe(msg):
    """Xato matnidan tokenni yashirish."""
    msg = str(msg)
    return msg.replace(TOKEN, "***") if TOKEN else msg


def clean_html(text):
    if not text:
        return ""
    text = BeautifulSoup(text, "html.parser").get_text(" ")
    return re.sub(r"\s+", " ", text).strip()


def truncate(text, limit):
    text = text.strip()
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return cut.rstrip(" ,.;:-") + "…"


def domain_of(url):
    try:
        host = urlparse(url).hostname or ""
        return host.lower().removeprefix("www.")
    except Exception:
        return ""


def is_excluded_domain(url):
    d = domain_of(url)
    for suffix in config.EXCLUDE_DOMAIN_SUFFIXES:
        s = suffix.lower().lstrip(".")
        if d and (d == s or d.endswith("." + s)):
            return True
    return False


def parse_date(value):
    if not value:
        return None
    value = value.strip()
    try:
        dt = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def title_key(title):
    t = normalize(title)
    t = re.sub(r"[^\w]+", " ", t).strip()
    return t[:90]


def h(key):
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


def fetch(url, retries=2):
    last = None
    for attempt in range(retries):
        try:
            r = session.get(url, timeout=25)
            if r.status_code == 200:
                return r
            last = f"HTTP {r.status_code}"
        except requests.RequestException as e:
            last = e
        time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"{url[:80]}… -> {last}")


# ---------------------------------------------------------------------------
# Xorijiy manbalar (RSS / Atom)
# ---------------------------------------------------------------------------

def _local(tag):
    return tag.rsplit("}", 1)[-1].lower() if isinstance(tag, str) else ""


def _child(el, name):
    for c in el:
        if _local(c.tag) == name:
            return c
    return None


def _child_text(el, name):
    c = _child(el, name)
    return (c.text or "").strip() if c is not None and c.text else ""


def parse_feed(content):
    """RSS 2.0 va Atom formatini o'qiydi (qo'shimcha kutubxonasiz)."""
    root = ET.fromstring(content)
    items = []
    for el in root.iter():
        tag = _local(el.tag)
        if tag not in ("item", "entry"):
            continue
        title = re.sub(r"\s+", " ", html.unescape(_child_text(el, "title"))).strip()
        link = _child_text(el, "link")
        if not link:  # Atom: <link href="..."/>
            for c in el:
                if _local(c.tag) == "link" and c.get("href"):
                    if c.get("rel", "alternate") == "alternate":
                        link = c.get("href")
                        break
        summary = _child_text(el, "description") or _child_text(el, "summary") or _child_text(el, "content")
        published = (_child_text(el, "pubdate") or _child_text(el, "published")
                     or _child_text(el, "updated") or _child_text(el, "date"))
        src_el = _child(el, "source")
        source_name = (src_el.text or "").strip() if src_el is not None and src_el.text else ""
        source_url = src_el.get("url", "") if src_el is not None else ""
        items.append({
            "title": title,
            "link": link,
            "summary": clean_html(summary),
            "published": parse_date(published),
            "source_name": source_name,
            "source_url": source_url,
        })
    return items


def fetch_foreign(src):
    r = fetch(src["url"])
    raw = parse_feed(r.content)
    out = []
    for it in raw:
        title, link = it["title"], it["link"]
        if not title or not link:
            continue
        real_url = link
        publisher = it["source_name"]

        if src["type"] == "google":
            # Sarlavha oxiridagi " - Reuters" ni olib tashlash
            if publisher and title.endswith(" - " + publisher):
                title = title[: -len(publisher) - 3].strip()
            check_url = it["source_url"] or link
            # Google tavsifi faqat sarlavhani takrorlaydi
            summary = ""
        elif src["type"] == "bing":
            qs = parse_qs(urlparse(link).query)
            if qs.get("url"):
                real_url = qs["url"][0]
            link = real_url
            check_url = real_url
            summary = it["summary"]
        else:
            check_url = link
            summary = it["summary"]

        if not publisher:
            publisher = domain_of(check_url) or src["name"]
        if title_key(summary).startswith(title_key(title)[:50]):
            summary = ""

        out.append({
            "kind": "foreign",
            "source": publisher,
            "feed": src["name"],
            "lang": src.get("lang", ""),
            "title": title,
            "summary": summary,
            "link": link,
            "check_url": check_url,
            "published": it["published"],
            "require_uzbekistan": src.get("require_uzbekistan", True),
            "require_keywords": src.get("require_keywords", True),
            "keys": ["u:" + real_url.split("#")[0], "t:" + title_key(title)],
        })
    return out


# ---------------------------------------------------------------------------
# Telegram kanallari (t.me/s/kanal)
# ---------------------------------------------------------------------------

def parse_tg_html(content, username):
    soup = BeautifulSoup(content, "html.parser")
    og = soup.find("meta", attrs={"property": "og:title"})
    channel_title = og["content"].strip() if og and og.get("content") else username
    posts = []
    for msg in soup.select("div.tgme_widget_message[data-post]"):
        if "service_message" in (msg.get("class") or []):
            continue
        post = msg["data-post"]
        text_el = msg.select_one("div.tgme_widget_message_text.js-message_text") or \
            msg.select_one("div.tgme_widget_message_text:not(.js-message_reply_text)")
        text = ""
        if text_el:
            for br in text_el.find_all("br"):
                br.replace_with("\n")
            text = text_el.get_text()
            text = re.sub(r"[ \t]+", " ", text)
            text = re.sub(r"\n{3,}", "\n\n", text).strip()
        t = msg.select_one("a.tgme_widget_message_date time[datetime]") or msg.select_one("time[datetime]")
        published = parse_date(t["datetime"]) if t else None
        posts.append({
            "post": post,
            "text": text,
            "published": published,
            "channel_title": channel_title,
        })
    return posts


def fetch_telegram(ch):
    username = ch["username"].lstrip("@")
    r = fetch(f"https://t.me/s/{username}")
    out = []
    for p in parse_tg_html(r.text, username):
        out.append({
            "kind": "telegram",
            "source": p["channel_title"],
            "username": username,
            "mode": ch.get("mode", "filter"),
            "title": "",
            "text": p["text"],
            "link": f"https://t.me/{p['post']}",
            "published": p["published"],
            "keys": ["tg:" + p["post"].lower()],
        })
    return out


# ---------------------------------------------------------------------------
# Filtrlash
# ---------------------------------------------------------------------------

def passes_filters(item, now):
    pub = item.get("published")
    if pub and now - pub > timedelta(hours=config.MAX_AGE_HOURS):
        return False, "eski"
    if pub and pub - now > timedelta(hours=6):
        return False, "sana xato"

    if item["kind"] == "telegram":
        body = normalize(item["text"])
        if EXCLUDE_RE and EXCLUDE_RE.search(body):
            return False, "reklama"
        if item["mode"] == "all":
            return True, ""
        if not body:
            return False, "matnsiz"
        return (True, "") if ECON_RE.search(body) else (False, "iqtisodiy emas")

    # foreign
    if not pub:
        return False, "sanasiz"
    if is_excluded_domain(item["check_url"]):
        return False, "o'zbek sayti"
    body = normalize(item["title"] + " " + item["summary"])
    if EXCLUDE_RE and EXCLUDE_RE.search(body):
        return False, "reklama"
    if item["require_uzbekistan"] and not UZ_RE.search(body):
        return False, "O'zbekiston yo'q"
    if item["require_keywords"] and not ECON_RE.search(body):
        return False, "iqtisodiy emas"
    return True, ""


# ---------------------------------------------------------------------------
# Holat (qaysi xabarlar yuborilgan)
# ---------------------------------------------------------------------------

def load_state():
    if not STATE_FILE.exists():
        return None
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        log.warning("Holat faylini o'qib bo'lmadi, yangisi yaratiladi")
        return None


def save_state(state):
    cutoff = time.time() - STATE_KEEP_DAYS * 86400
    state["seen"] = {k: v for k, v in state["seen"].items() if v >= cutoff}
    state["last_run"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=0, sort_keys=True), encoding="utf-8")
    tmp.replace(STATE_FILE)


def is_seen(state, item):
    return any(h(k) in state["seen"] for k in item["keys"])


def mark_seen(state, item):
    now = int(time.time())
    for k in item["keys"]:
        state["seen"][h(k)] = now


# ---------------------------------------------------------------------------
# Xabar formatlash va yuborish
# ---------------------------------------------------------------------------

def fmt_time(dt):
    return dt.astimezone(TZ).strftime("%d.%m %H:%M") if dt else ""


def format_message(item):
    e = lambda s: html.escape(s or "", quote=False)
    when = fmt_time(item.get("published"))
    link = html.escape(item["link"], quote=True)
    footer_time = f" · 🕒 {when}" if when else ""
    if item["kind"] == "foreign":
        msg = f"🌍 <b>{e(item['source'])}</b> · {e(item['lang'])}\n<b>{e(item['title'])}</b>"
        if item["summary"]:
            msg += "\n\n" + e(truncate(item["summary"], config.FOREIGN_SNIPPET_LIMIT))
        msg += f'\n\n🔗 <a href="{link}">Maqolani o\'qish</a>{footer_time}\n#xorij'
        return msg
    text = item["text"] or "🖼 Media post (matnsiz)"
    msg = f"📢 <b>{e(item['source'])}</b>\n\n" + e(truncate(text, config.TG_TEXT_LIMIT))
    msg += f'\n\n🔗 <a href="{link}">Postni ochish</a>{footer_time}\n#telegram'
    return msg


def tg_api(method, payload, retries=4):
    url = f"https://api.telegram.org/bot{TOKEN}/{method}"
    for attempt in range(retries):
        try:
            r = requests.post(url, json=payload, timeout=30)
            data = r.json()
        except (requests.RequestException, ValueError) as e:
            log.warning("Telegram so'rovi xato: %s", safe(e))
            time.sleep(3 * (attempt + 1))
            continue
        if data.get("ok"):
            return data
        if r.status_code == 429:
            wait = data.get("parameters", {}).get("retry_after", 5)
            log.info("Telegram limiti: %s soniya kutilmoqda", wait)
            time.sleep(wait + 1)
            continue
        return data  # boshqa xato (400/403) — qayta urinib foyda yo'q
    return {"ok": False, "description": "qayta urinishlar tugadi"}


def send_text(chat_id, text, preview=None):
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "link_preview_options": {"is_disabled": not (config.LINK_PREVIEW if preview is None else preview)},
    }
    res = tg_api("sendMessage", payload)
    if not res.get("ok") and "parse" in str(res.get("description", "")).lower():
        # HTML xatosi bo'lsa — oddiy matn sifatida yuborish
        payload.pop("parse_mode")
        payload["text"] = html.unescape(re.sub(r"</?(?:b|i|a|code)\b[^>]*>", "", text))
        res = tg_api("sendMessage", payload)
    if not res.get("ok"):
        log.error("Yuborib bo'lmadi: %s", safe(res.get("description")))
    return bool(res.get("ok"))


def send_to_all(text):
    ok = False
    for cid in CHAT_IDS:
        ok = send_text(cid, text) or ok
    return ok


def setup_mode():
    """CHAT_ID hali kiritilmagan bo'lsa: botga yozgan odamga uning ID sini yuboradi."""
    log.info("TELEGRAM_CHAT_ID kiritilmagan — sozlash rejimi")
    data = tg_api("getUpdates", {"timeout": 0, "allowed_updates": ["message", "channel_post"]})
    if not data.get("ok"):
        log.error("getUpdates xato: %s", safe(data.get("description")))
        return
    chats = {}
    for u in data.get("result", []):
        m = u.get("message") or u.get("channel_post") or {}
        c = m.get("chat") or {}
        if c.get("id"):
            chats[c["id"]] = c.get("type", "")
    if not chats:
        log.info("Hech kim botga yozmagan. Botingizga Telegramda /start yuboring va qayta ishga tushiring.")
        return
    for cid, ctype in chats.items():
        send_text(cid, (
            "👋 Salom! Bot deyarli tayyor.\n\n"
            f"Sizning CHAT ID: <code>{cid}</code>\n\n"
            "Shu raqamni GitHub → Settings → Secrets and variables → Actions bo'limiga "
            "<b>TELEGRAM_CHAT_ID</b> nomi bilan qo'shing. Shundan keyin yangiliklar shu yerga keladi."
        ))
    log.info("Chat ID %d ta chatga yuborildi (xavfsizlik uchun bu yerda ko'rsatilmaydi).", len(chats))


# ---------------------------------------------------------------------------
# Asosiy jarayon
# ---------------------------------------------------------------------------

def collect():
    items, report = [], []
    for src in config.FOREIGN_SOURCES:
        try:
            got = fetch_foreign(src)
            items += got
            report.append(f"{src['name']}: {len(got)}")
        except Exception as e:
            report.append(f"{src['name']}: XATO")
            log.warning("Manba xatosi [%s]: %s", src["name"], safe(e))
    for ch in config.TELEGRAM_CHANNELS:
        try:
            got = fetch_telegram(ch)
            items += got
            report.append(f"@{ch['username']}: {len(got)}")
        except Exception as e:
            report.append(f"@{ch['username']}: XATO")
            log.warning("Kanal xatosi [@%s]: %s", ch["username"], safe(e))
        time.sleep(0.5)
    log.info("Yig'ildi: %s", " | ".join(report))
    return items


def run_once(dry_run=False):
    state = load_state()
    first_run = state is None
    if first_run:
        state = {"version": 1, "seen": {}}
        log.info("Birinchi ishga tushish: faqat eng yangi %d ta xabar yuboriladi", config.FIRST_RUN_SEND_LIMIT)

    now = datetime.now(timezone.utc)
    items = collect()

    fresh, run_keys, stats = [], set(), {}
    for it in items:
        ok, why = passes_filters(it, now)
        if not ok:
            stats[why] = stats.get(why, 0) + 1
            continue
        hk = {h(k) for k in it["keys"]}
        if hk & run_keys or is_seen(state, it):
            stats["takror"] = stats.get("takror", 0) + 1
            continue
        run_keys |= hk
        fresh.append(it)
    log.info("Filtr natijasi: %d ta yangi | o'tkazib yuborildi: %s", len(fresh), stats)

    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    fresh.sort(key=lambda x: x.get("published") or epoch)

    if first_run:
        to_send = fresh[-config.FIRST_RUN_SEND_LIMIT:]
        for it in fresh:
            mark_seen(state, it)
    else:
        to_send = fresh[: config.MAX_MESSAGES_PER_RUN]

    if dry_run:
        for it in to_send:
            print("-" * 60)
            print(format_message(it))
        print("-" * 60)
        log.info("[dry-run] %d ta xabar yuborilardi (hech narsa yuborilmadi, holat saqlanmadi)", len(to_send))
        return

    if first_run:
        send_to_all(
            "✅ <b>Bot ishga tushdi!</b>\n\n"
            f"Endi har 30 daqiqada {len(config.FOREIGN_SOURCES)} ta xorijiy manba va "
            f"{len(config.TELEGRAM_CHANNELS)} ta Telegram kanaldagi O'zbekiston iqtisodiyoti va "
            "moliyasiga oid yangiliklar shu yerga keladi.\n\n"
            "#xorij — chet el saytlari, #telegram — o'zbek kanallari"
        )

    sent = 0
    for i, it in enumerate(to_send):
        if send_to_all(format_message(it)):
            sent += 1
        mark_seen(state, it)  # xato bo'lsa ham qayta-qayta yubormaslik uchun
        if i % 5 == 4:
            save_state(state)
        time.sleep(config.SEND_DELAY_SECONDS)
    save_state(state)
    left = len(fresh) - len(to_send) if not first_run else 0
    log.info("Yuborildi: %d ta%s", sent, f" | keyingi safarga qoldi: {left}" if left > 0 else "")


def main():
    ap = argparse.ArgumentParser(description="O'zbekiston iqtisodiy yangiliklar boti")
    ap.add_argument("--dry-run", action="store_true", help="yubormasdan ekranga chiqarish")
    ap.add_argument("--test", action="store_true", help="test xabari yuborish")
    ap.add_argument("--loop", type=int, default=0, metavar="SONIYA", help="takroriy ishga tushirish oralig'i")
    args = ap.parse_args()

    if not args.dry_run:
        if not TOKEN:
            log.error("TELEGRAM_BOT_TOKEN topilmadi. README dagi yo'riqnomani ko'ring.")
            sys.exit(1)
        if not CHAT_IDS:
            setup_mode()
            return

    if args.test:
        ok = send_to_all("✅ Test: bot Telegram bilan muvaffaqiyatli bog'landi!")
        log.info("Test xabari %s", "yuborildi" if ok else "YUBORILMADI")
        sys.exit(0 if ok else 1)

    while True:
        try:
            run_once(dry_run=args.dry_run)
        except Exception as e:  # loop rejimida bot to'xtab qolmasligi uchun
            log.exception("Kutilmagan xato: %s", safe(e))
            if not args.loop:
                raise
        if not args.loop:
            break
        log.info("Keyingi tekshiruv %d soniyadan keyin", args.loop)
        time.sleep(args.loop)


if __name__ == "__main__":
    main()
