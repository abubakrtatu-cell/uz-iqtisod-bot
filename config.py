# -*- coding: utf-8 -*-
"""
BOT SOZLAMALARI
================
Shu faylni tahrirlab manbalar, kanallar va kalit so'zlarni o'zgartirishingiz mumkin.
Python bilmasangiz ham bo'ladi: faqat qo'shtirnoq ("...") va vergullarni saqlang.
"""
from urllib.parse import quote_plus

# ---------------------------------------------------------------------------
# 1. UMUMIY SOZLAMALAR
# ---------------------------------------------------------------------------

# Necha soatdan eski xabarlar yuborilmaydi
MAX_AGE_HOURS = 36

# Bir ishga tushishda ko'pi bilan nechta xabar yuborilsin
# (qolganlari keyingi safar yuboriladi)
MAX_MESSAGES_PER_RUN = 40

# Bot birinchi marta ishga tushganda eski xabarlar bilan "bombardimon" qilmasligi
# uchun faqat eng yangi shuncha xabar yuboriladi, qolganlari "ko'rilgan" deb belgilanadi
FIRST_RUN_SEND_LIMIT = 8

# Xabarlar orasidagi pauza (soniya). Kanal/guruhga yuborsangiz 3 qiling.
SEND_DELAY_SECONDS = 1.2

# Havola ko'rinishi (preview) yoqilsinmi: True / False
LINK_PREVIEW = False

# Telegram post matnining maksimal uzunligi (belgi)
TG_TEXT_LIMIT = 700

# Xorijiy maqola qisqa matnining maksimal uzunligi (belgi)
FOREIGN_SNIPPET_LIMIT = 350

# Shu domenlar bilan tugaydigan saytlar "xorijiy" hisoblanmaydi va o'tkazib yuboriladi
# (o'zbek saytlari Telegram kanallari orqali baribir keladi)
EXCLUDE_DOMAIN_SUFFIXES = [".uz"]

# Vaqt mintaqasi (UTC+5, Toshkent)
TZ_OFFSET_HOURS = 5


# ---------------------------------------------------------------------------
# 2. XORIJIY MANBALAR (RSS)
# ---------------------------------------------------------------------------
# type: "google" | "bing" | "rss"
# lang: xabarda ko'rsatiladigan til belgisi
# require_uzbekistan: sarlavha/matnda O'zbekiston tilga olinishi shartmi
# require_keywords: iqtisodiy kalit so'z bo'lishi shartmi

def google_news(query, lang="en", country="US"):
    """Google News qidiruv RSS havolasini yasaydi (bepul, kalit kerak emas)."""
    return (
        "https://news.google.com/rss/search?q=" + quote_plus(query)
        + f"&hl={lang}&gl={country}&ceid={country}:{lang}"
    )


def bing_news(query, market="en-US"):
    """Bing News RSS (oxirgi 24 soat, sana bo'yicha tartiblangan)."""
    return (
        "https://www.bing.com/news/search?q=" + quote_plus(query)
        + "&format=rss&qft=interval%3d%227%22+sortbydate%3d%221%22&setmkt=" + market
    )


FOREIGN_SOURCES = [
    # --- Google News: ingliz tilidagi barcha xorijiy nashrlar ---
    {
        "name": "Google News (EN)",
        "type": "google",
        "lang": "EN",
        "url": google_news(
            'Uzbekistan (economy OR economic OR finance OR investment OR bank OR GDP '
            'OR inflation OR IMF OR "World Bank" OR Eurobond OR exports OR tariff '
            'OR "central bank" OR budget OR privatization) when:1d',
            "en", "US",
        ),
        "require_uzbekistan": True,
        "require_keywords": True,
    },
    # --- Google News: yirik nufuzli nashrlar va xalqaro tashkilotlar ---
    {
        "name": "Google News (Top nashrlar)",
        "type": "google",
        "lang": "EN",
        "url": google_news(
            "Uzbekistan (site:reuters.com OR site:bloomberg.com OR site:ft.com "
            "OR site:wsj.com OR site:economist.com OR site:intellinews.com "
            "OR site:eurasianet.org OR site:fitchratings.com OR site:moodys.com "
            "OR site:spglobal.com OR site:imf.org OR site:worldbank.org "
            "OR site:adb.org OR site:ebrd.com OR site:cnbc.com) when:2d",
            "en", "US",
        ),
        "require_uzbekistan": True,
        "require_keywords": True,
    },
    # --- Google News: rus tilidagi xorijiy nashrlar (RBC, Kommersant, Interfax, TASS, Kursiv...) ---
    {
        "name": "Google News (RU)",
        "type": "google",
        "lang": "RU",
        "url": google_news(
            "Узбекистан (экономика OR финансы OR инвестиции OR банк OR ВВП OR инфляция "
            "OR МВФ OR экспорт OR кредит OR бюджет OR еврооблигации) when:1d",
            "ru", "RU",
        ),
        "require_uzbekistan": True,
        "require_keywords": True,
    },
    # --- Bing News: zaxira manba (Google o'tkazib yuborganlarini topadi) ---
    {
        "name": "Bing News (EN)",
        "type": "bing",
        "lang": "EN",
        "url": bing_news("Uzbekistan economy OR finance OR investment OR bank", "en-US"),
        "require_uzbekistan": True,
        "require_keywords": True,
    },
    {
        "name": "Bing News (RU)",
        "type": "bing",
        "lang": "RU",
        "url": bing_news("Узбекистан экономика OR финансы OR инвестиции OR банк", "ru-RU"),
        "require_uzbekistan": True,
        "require_keywords": True,
    },
    # --- To'g'ridan-to'g'ri RSS lentalari ---
    {
        "name": "The Times of Central Asia",
        "type": "rss",
        "lang": "EN",
        "url": "https://timesca.com/feed/",
        "require_uzbekistan": True,
        "require_keywords": True,
    },
    # Yangi RSS qo'shish namunasi (oldidagi # ni olib tashlang):
    # {
    #     "name": "The Diplomat",
    #     "type": "rss",
    #     "lang": "EN",
    #     "url": "https://thediplomat.com/feed/",
    #     "require_uzbekistan": True,
    #     "require_keywords": True,
    # },
]


# ---------------------------------------------------------------------------
# 3. O'ZBEKISTON TELEGRAM KANALLARI
# ---------------------------------------------------------------------------
# username: kanal manzili (t.me/ dan keyingi qism)
# mode: "all"    -> kanaldagi barcha postlar yuboriladi (sof iqtisodiy kanallar uchun)
#       "filter" -> faqat iqtisod/moliyaga oid postlar yuboriladi (umumiy yangilik kanallari)
# Faqat ochiq (public) kanallar ishlaydi.

TELEGRAM_CHANNELS = [
    # Rasmiy iqtisodiy idoralar
    {"username": "centralbankuzbekistan", "mode": "all"},     # Markaziy bank
    {"username": "minecofinuz",           "mode": "all"},     # Iqtisodiyot va moliya vazirligi
    {"username": "uzstataxborot",         "mode": "all"},     # Milliy statistika qo'mitasi
    # Biznes va moliya nashrlari
    {"username": "spotuz",                "mode": "filter"},  # Spot.uz (ruscha)
    {"username": "spotuz_uz",             "mode": "filter"},  # Spot.uz (o'zbekcha)
    {"username": "pul_top_uzb",           "mode": "all"},     # Pultop: kurslar, omonatlar, kreditlar
    # Umumiy yangilik kanallari (faqat iqtisodiy xabarlar olinadi)
    {"username": "kunuzofficial",         "mode": "filter"},  # Kun.uz
    {"username": "kunuzru",               "mode": "filter"},  # Kun.uz (ruscha)
    {"username": "daryo",                 "mode": "filter"},  # Daryo
    {"username": "gazetauz",              "mode": "filter"},  # Gazeta.uz (ruscha)
    {"username": "gazetauz_ozb",          "mode": "filter"},  # Gazeta.uz (o'zbekcha)
    {"username": "uzdaily",               "mode": "filter"},  # UzDaily (ruscha)
    # Yangi kanal qo'shish: {"username": "kanal_nomi", "mode": "filter"},
]


# ---------------------------------------------------------------------------
# 4. KALIT SO'ZLAR (regex, katta-kichik harf farqi yo'q)
# ---------------------------------------------------------------------------
# \b — so'z boshi. Masalan r"\bbank" -> "bank", "banki", "banking" ga mos keladi.

ECONOMY_KEYWORDS = [
    # --- O'zbekcha (lotin) ---
    r"\biqtisod", r"\bmoliya", r"\bbank", r"\bkredit", r"\bqarz", r"\binflyatsiya",
    r"\bvalyuta", r"\bdollar", r"\byevro\b", r"\bevro\b", r"\bsoliq", r"\bbyudjet", r"\bbudjet",
    r"\binvest", r"\beksport", r"\bimport(?:s|ed|er|ers|ing|i|ga|ni|ning|dan|da|chi|chilar|lar)?\b", r"\bsavdo", r"\byaim\b", r"\byalpi ichki",
    r"\bbirja", r"\baksiya", r"\bobligatsiya", r"\bye?vrobond", r"\bnarx", r"\btarif",
    r"\bstavka", r"\bxususiylashtir", r"\bprivatizatsiya", r"\bbiznes", r"\btadbirkor",
    r"\bsanoat", r"\boltin(?:ni|ga|ning|dan|da|lar)?\b(?!\s+medal)", r"\bneft", r"\bgaz(?:ni|ga|ning|dan|da|lar)?\b", r"\btabiiy gaz",
    r"\bish haqi", r"\bmaosh", r"\bdaromad", r"\bdepozit", r"\bomonat", r"\bipoteka",
    r"\blizing", r"\bsug'urta", r"\bto'lov", r"\bmlrd", r"\btrln", r"\bso'm(?:ga|ni|dan|lik|lar|ning)?\b",
    r"\bbojxona", r"\baksiz", r"\bqqs\b", r"\bdividend", r"\bkapital bozor",
    r"\bfond bozor", r"\bqimmatla", r"\barzonla", r"\bjamg'arma", r"\bpul o'tkazma",
    r"\bfintex", r"\bfintech",
    # --- O'zbekcha (kirill) ---
    r"\bиқтисод", r"\bмолия", r"\bбанк", r"\bкредит", r"\bқарз", r"\bинфляция",
    r"\bвалюта", r"\bдоллар", r"\bсолиқ", r"\bбюджет", r"\bинвест", r"\bэкспорт",
    r"\bимпорт", r"\bсавдо", r"\bялпи ички", r"\bбиржа", r"\bнарх", r"\bтариф",
    r"\bтадбиркор", r"\bсаноат", r"\bолтин", r"\bнефт", r"\bсўм\b", r"\bбожхона",
    r"\bиш ҳақи", r"\bмаош", r"\bдаромад", r"\bомонат", r"\bқимматла",
    # --- Ruscha ---
    r"\bэконом", r"минэконом", r"минфин", r"\bфинанс", r"\bдолг(?:а|и|ов|у|ом|ам|ами|овой|овая|овые|овых)?\b", r"\bинфляци", r"\bвалют", r"\bдолл",
    r"\bевро\b", r"\bрубл", r"\bналог", r"\bинвестиц", r"\bторгов", r"\bввп\b",
    r"\bбирж", r"\bакци[яийю]", r"\bоблигаци", r"\bеврооблигаци", r"\bцен[аыуе]\b",
    r"\bцены\b", r"\bподорож", r"\bподешев", r"\bставк", r"\bцб\b", r"\bцентробанк",
    r"\bприватизац", r"\bбизнес", r"\bпредприним", r"\bпромышлен", r"\bзолот(?:о|а|ом|е)\b", r"\bзолотовалют",
    r"\bгаз(?:а|у|ом|е|ов|овый|ового|опровод\w*)?\b", r"\bмлрд", r"\bтрлн",
    r"\bмлн\s+(?:долл|сум|евро|руб)", r"\bсум(?:ов|ах)?\b", r"\bмвф\b",
    r"\bвсемирн\w* банк", r"\bабр\b", r"\bеабр\b", r"\bебрр\b", r"\bвто\b", r"\bтаможн",
    r"\bакциз", r"\bндс\b", r"\bзарплат", r"\bипотек", r"\bлизинг", r"\bстрахов",
    r"\bдепозит", r"\bвклад", r"\bденежн\w* перевод", r"\bдивиденд", r"\bфондов\w* рын",
    r"\bрынок капитала", r"\bфинтех", r"\bрейтинг\w* (?:fitch|moody|s&p)",
    # --- Inglizcha ---
    r"\becono", r"\bfinanc", r"\bbank", r"\bcredit", r"\bloan", r"\bdebt", r"\binflation",
    r"\bcurrenc", r"\bexchange rate", r"\btax(?:es|ed|ation|payers?)?\b", r"\bbudget", r"\binvest", r"\bexport",
    r"\btrade", r"\bgdp\b", r"\bstock", r"\bshares\b", r"\bbonds?\b",
    r"\beurobond", r"\bprices?\b", r"\btariff", r"\binterest rate", r"\bprivati[sz]",
    r"\bbusiness", r"\bindustr", r"\bgold\b(?!\s+medal)", r"\boil\b", r"\bgas\b", r"\bbillion",
    r"\bmillion", r"\$\s?\d", r"\b\d+(?:\.\d+)?\s?(?:bn|mln|mn)\b", r"\bimf\b",
    r"\bworld bank", r"\badb\b", r"\bebrd\b", r"\baiib\b", r"\bwto\b", r"\bcustoms",
    r"\bremittance", r"\bipo\b", r"\bfitch", r"\bmoody", r"\bs&p\b", r"\bmining",
    r"\buranium", r"\bcopper", r"\bmarket", r"\bfintech", r"\bdeal\b", r"\bfund\b",
]

# O'zbekiston tilga olinganini aniqlash (xorijiy manbalar uchun)
UZBEKISTAN_PATTERNS = [
    r"uzbek", r"o'zbek", r"ўзбек", r"узбек", r"tashkent", r"toshkent", r"ташкент",
    r"тошкент", r"samarkand", r"samarqand", r"самарканд", r"mirziyoyev", r"мирзиёев",
    r"navoi", r"навои",
]

# Shu so'zlar bo'lgan postlar yuborilmaydi (reklama va h.k.)
EXCLUDE_PATTERNS = [
    r"#reklama", r"#реклама", r"#rek\b", r"#ad\b", r"#promo", r"#промо", r"#hamkorlik",
    r"^\W*(?:reklama|реклама)\W*$",          # alohida qatorda "Reklama" yozuvi
    r"на правах рекламы", r"reklama huquqi",
]
