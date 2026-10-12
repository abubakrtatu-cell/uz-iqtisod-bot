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
  TELEGRAM_CHAT_ID   — sizning shaxsiy chat ID (bir nechta bo'lsa vergul bilan).
                       Guruh/kanalga yuborish uchun botni o'sha guruhga qo'shing va
                       guruhda /start@bot_nomi yozing — bot guruhni o'zi eslab qoladi.
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


# Guruh/supergroup ID o'zgarishi va botni chiqarib yuborgan chatlar (shu ishga tushish davomida)
MIGRATED = {}   # eski_id -> yangi_id
DEAD = set()    # bot endi yoza olmaydigan chatlar
_DEAD_MARKERS = ("kicked", "not a member", "chat not found", "bot was blocked", "deactivated")


def send_text(chat_id, text, preview=None):
    chat_id = MIGRATED.get(str(chat_id), str(chat_id))
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "link_preview_options": {"is_disabled": not (config.LINK_PREVIEW if preview is None else preview)},
    }
    res = tg_api("sendMessage", payload)
    new_id = (res.get("parameters") or {}).get("migrate_to_chat_id")
    if not res.get("ok") and new_id:
        # Oddiy guruh "supergroup"ga aylangan — yangi ID bilan qayta yuborish
        MIGRATED[str(chat_id)] = str(new_id)
        payload["chat_id"] = str(new_id)
        res = tg_api("sendMessage", payload)
    if not res.get("ok") and "parse" in str(res.get("description", "")).lower():
        # HTML xatosi bo'lsa — oddiy matn sifatida yuborish
        payload.pop("parse_mode")
        payload["text"] = html.unescape(re.sub(r"</?(?:b|i|a|code)\b[^>]*>", "", text))
        res = tg_api("sendMessage", payload)
    if not res.get("ok"):
        desc = str(res.get("description", ""))
        log.error("Yuborib bo'lmadi: %s", safe(desc))
        if any(m in desc.lower() for m in _DEAD_MARKERS):
            DEAD.add(str(payload["chat_id"]))
    return bool(res.get("ok"))


def send_to(chats, text):
    ok = False
    for cid in chats:
        if str(cid) in DEAD:
            continue
        ok = send_text(cid, text) or ok
    return ok


# ---------------------------------------------------------------------------
# Guruh / kanallarni avtomatik ulash
# ---------------------------------------------------------------------------
# Botni guruhga qo'shsangiz yoki guruhda /start@bot_nomi yozsangiz, bot shu guruhni
# eslab qoladi va yangiliklarni u yerga ham yuboradi. Faqat bot egasi
# (TELEGRAM_CHAT_ID dagi shaxsiy ID) qo'shgan guruhlar qabul qilinadi.

OWNER_IDS = {c for c in CHAT_IDS if c.isdigit()}


def is_owner(user_id):
    return not OWNER_IDS or str(user_id) in OWNER_IDS


def all_targets(state):
    out = []
    for c in CHAT_IDS + list((state or {}).get("chats", [])):
        c = str(c)
        if c not in out:
            out.append(c)
    return out


def _bot_username():
    r = tg_api("getMe", {})
    return str((r.get("result") or {}).get("username", "")).lower() if r.get("ok") else ""


def process_updates(state):
    """Telegramdan kelgan yangilanishlarni o'qiydi. Yangi ulangan chatlar ro'yxatini qaytaradi."""
    chats = state.setdefault("chats", [])
    data = tg_api("getUpdates", {
        "offset": state.get("update_offset", 0),
        "timeout": 0,
        "allowed_updates": ["message", "channel_post", "my_chat_member"],
    })
    if not data.get("ok"):
        log.warning("getUpdates xato: %s", safe(data.get("description")))
        return []

    new, me = [], None

    def add(cid):
        cid = str(cid)
        if cid not in chats and cid not in CHAT_IDS:
            chats.append(cid)
            new.append(cid)

    def remove(cid):
        cid = str(cid)
        if cid in chats:
            chats.remove(cid)
        if cid in new:
            new.remove(cid)

    for u in data.get("result", []):
        state["update_offset"] = u["update_id"] + 1

        if "my_chat_member" in u:  # bot guruh/kanalga qo'shildi yoki chiqarildi
            m = u["my_chat_member"]
            chat = m.get("chat", {})
            if chat.get("type") == "private":
                continue
            status = (m.get("new_chat_member") or {}).get("status")
            if status in ("member", "administrator"):
                if is_owner((m.get("from") or {}).get("id")):
                    add(chat["id"])
                else:
                    log.info("Botni begona foydalanuvchi qo'shdi — e'tiborsiz qoldirildi")
            elif status in ("left", "kicked"):
                remove(chat["id"])
            continue

        msg = u.get("message") or u.get("channel_post")
        if not msg:
            continue
        chat = msg.get("chat", {})
        if msg.get("migrate_to_chat_id"):  # guruh supergroupga aylandi
            if str(chat.get("id")) in chats:
                remove(chat["id"])
                add(msg["migrate_to_chat_id"])
            continue

        text = (msg.get("text") or "").strip()
        if not text.startswith("/"):
            continue
        name, _, target = text.split()[0][1:].lower().partition("@")
        if name not in ("start", "id"):
            continue
        if target:
            if me is None:
                me = _bot_username()
            if me and target != me:
                continue  # buyruq boshqa botga yozilgan

        if chat.get("type") == "private":
            send_text(chat["id"], (
                "👋 Salom! Bu bot O'zbekiston iqtisodiyoti va moliyasiga oid yangiliklarni yuboradi.\n\n"
                f"Sizning chat ID: <code>{chat['id']}</code>"
            ))
        else:
            sender = (msg.get("from") or {}).get("id")
            anonymous_admin = (msg.get("sender_chat") or {}).get("id") == chat.get("id")
            if chat.get("type") == "channel" or anonymous_admin or is_owner(sender):
                add(chat["id"])

    if new:
        log.info("Yangi ulangan guruh/kanal: %d ta", len(new))
    return new


def finalize_chats(state):
    """Supergroupga aylangan va botni chiqarib yuborgan chatlarni holatda yangilash."""
    chats = state.setdefault("chats", [])
    for old, new in MIGRATED.items():
        if old in chats:
            chats[chats.index(old)] = new
        elif old in CHAT_IDS:
            log.warning("TELEGRAM_CHAT_ID dagi guruh ID si o'zgargan. Yangi ID: %s — secret'ni yangilang.", new)
    for d in DEAD:
        if d in chats:
            chats.remove(d)
            log.info("Bot chiqarib yuborilgan chat ro'yxatdan olib tashlandi")


# ---------------------------------------------------------------------------
# Asosiy jarayon
# ---------------------------------------------------------------------------

WELCOME = (
    "✅ <b>Bot ishga tushdi!</b>\n\n"
    "Endi har 30 daqiqada {f} ta xorijiy manba va {t} ta Telegram kanaldagi O'zbekiston "
    "iqtisodiyoti va moliyasiga oid yangiliklar shu yerga keladi.\n\n"
    "#xorij — chet el saytlari, #telegram — o'zbek kanallari"
)


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
    MIGRATED.clear()
    DEAD.clear()
    state = load_state() or {"version": 1, "seen": {}}
    initialized = state.get("initialized", bool(state.get("seen")))

    new_chats = [] if dry_run else process_updates(state)
    targets = all_targets(state)
    if not targets and not dry_run:
        log.info("Hali hech qanday chat ulanmagan. Botga /start yozing yoki uni guruhga qo'shing.")
        save_state(state)
        return

    now = datetime.now(timezone.utc)
    items = collect()

    candidates, run_keys, stats = [], set(), {}
    for it in items:
        ok, why = passes_filters(it, now)
        if not ok:
            stats[why] = stats.get(why, 0) + 1
            continue
        hk = {h(k) for k in it["keys"]}
        if hk & run_keys:
            stats["takror"] = stats.get("takror", 0) + 1
            continue
        run_keys |= hk
        candidates.append(it)

    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    candidates.sort(key=lambda x: x.get("published") or epoch)
    fresh = [it for it in candidates if not is_seen(state, it)]
    stats["avval yuborilgan"] = len(candidates) - len(fresh)
    log.info("Filtr natijasi: %d ta yangi | o'tkazib yuborildi: %s", len(fresh), stats)

    if not initialized:
        log.info("Birinchi ishga tushish: faqat eng yangi %d ta xabar yuboriladi", config.FIRST_RUN_SEND_LIMIT)
        to_send = fresh[-config.FIRST_RUN_SEND_LIMIT:]
        for it in fresh:
            mark_seen(state, it)
        intro_chats = []
    else:
        to_send = fresh[: config.MAX_MESSAGES_PER_RUN]
        intro_chats = [c for c in new_chats if c in targets]
    # Yangi ulangan guruhga eng so'nggi yangiliklar (avval yuborilganlari ham)
    intro = candidates[-config.FIRST_RUN_SEND_LIMIT:] if intro_chats else []

    if dry_run:
        for it in to_send:
            print("-" * 60)
            print(format_message(it))
        print("-" * 60)
        log.info("[dry-run] %d ta xabar yuborilardi (hech narsa yuborilmadi, holat saqlanmadi)", len(to_send))
        return

    # Guruh/kanallarga daqiqasiga 20 tadan ko'p yuborib bo'lmaydi
    has_group = any(c.startswith(("-", "@")) for c in targets)
    delay = max(config.SEND_DELAY_SECONDS, 3.1) if has_group else config.SEND_DELAY_SECONDS
    welcome = WELCOME.format(f=len(config.FOREIGN_SOURCES), t=len(config.TELEGRAM_CHANNELS))

    if not initialized:
        send_to(targets, welcome)
    if intro_chats:
        send_to(intro_chats, welcome)
        for it in intro:
            send_to(intro_chats, format_message(it))
            time.sleep(delay)
    intro_ids = {id(it) for it in intro}
    regular = [c for c in targets if c not in intro_chats]

    sent = 0
    for i, it in enumerate(to_send):
        chats = regular + ([] if id(it) in intro_ids else intro_chats)
        if chats and send_to(chats, format_message(it)):
            sent += 1
        mark_seen(state, it)  # xato bo'lsa ham qayta-qayta yubormaslik uchun
        if i % 5 == 4:
            save_state(state)
        time.sleep(delay)

    state["initialized"] = True
    finalize_chats(state)
    save_state(state)
    left = len(fresh) - len(to_send) if initialized else 0
    log.info("Yuborildi: %d ta | chatlar soni: %d%s", sent, len(all_targets(state)),
             f" | keyingi safarga qoldi: {left}" if left > 0 else "")


def main():
    ap = argparse.ArgumentParser(description="O'zbekiston iqtisodiy yangiliklar boti")
    ap.add_argument("--dry-run", action="store_true", help="yubormasdan ekranga chiqarish")
    ap.add_argument("--test", action="store_true", help="test xabari yuborish")
    ap.add_argument("--loop", type=int, default=0, metavar="SONIYA", help="takroriy ishga tushirish oralig'i")
    args = ap.parse_args()

    if not args.dry_run and not TOKEN:
        log.error("TELEGRAM_BOT_TOKEN topilmadi. README dagi yo'riqnomani ko'ring.")
        sys.exit(1)

    if args.test:
        ok = send_to(all_targets(load_state()), "✅ Test: bot Telegram bilan muvaffaqiyatli bog'landi!")
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
