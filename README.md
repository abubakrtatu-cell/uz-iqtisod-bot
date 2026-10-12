# 🇺🇿 O'zbekiston iqtisodiyoti va moliyasi — yangiliklar boti

Bu bot har 30 daqiqada **chet el saytlari** va **o'zbek Telegram kanallaridagi** O'zbekiston iqtisodiyoti va moliyasiga oid yangiliklarni yig'adi va sizning Telegramingizga yuboradi.

- **Butunlay bepul**: server kerak emas, bot GitHub Actions'da ishlaydi (ochiq/public repozitoriyalar uchun cheksiz bepul).
- **Kalit kerak emas**: Google News, Bing News, RSS va Telegram kanallarining ochiq veb-sahifasi ishlatiladi.
- **Takrorlamaydi**: bir xabar ikki marta kelmaydi.
- Har bir yangilik **alohida xabar** bo'lib, asl tilida keladi.

---

## 📰 Qaysi manbalarni kuzatadi

### Chet el manbalari
| Manba | Nimani qamraydi |
|---|---|
| Google News (EN) | Ingliz tilidagi barcha xorijiy nashrlar |
| Google News (Top) | Reuters, Bloomberg, FT, WSJ, The Economist, bne IntelliNews, Eurasianet, Fitch, Moody's, S&P, IMF, World Bank, ADB, EBRD, CNBC |
| Google News (RU) | RBC, Kommersant, Interfax, TASS, Vedomosti, Kursiv va boshqa rus tilidagi xorijiy nashrlar |
| Bing News (EN, RU) | Zaxira manba: Google o'tkazib yuborganlarini topadi |
| The Times of Central Asia | To'g'ridan-to'g'ri RSS |

`.uz` bilan tugaydigan o'zbek saytlari bu ro'yxatdan chiqarib tashlanadi, chunki ular quyidagi Telegram kanallari orqali baribir keladi.

### O'zbekiston Telegram kanallari
| Kanal | Nima yuboriladi |
|---|---|
| @centralbankuzbekistan — Markaziy bank | barcha postlar |
| @minecofinuz — Iqtisodiyot va moliya vazirligi | barcha postlar |
| @uzstataxborot — Milliy statistika qo'mitasi | barcha postlar |
| @pul_top_uzb — Pultop (kurslar, omonatlar, kreditlar) | barcha postlar |
| @spotuz, @spotuz_uz — Spot.uz | faqat iqtisodiy |
| @kunuzofficial, @kunuzru — Kun.uz | faqat iqtisodiy |
| @daryo — Daryo | faqat iqtisodiy |
| @gazetauz, @gazetauz_ozb — Gazeta.uz | faqat iqtisodiy |
| @uzdaily — UzDaily | faqat iqtisodiy |

"Faqat iqtisodiy" degani: bot postni o'zbek (lotin va kirill), rus va ingliz tilidagi kalit so'zlar (bank, soliq, inflyatsiya, dollar, investitsiya, eksport, narx...) bo'yicha tekshiradi. Reklama postlari o'tkazib yuboriladi.

---

## 🚀 O'rnatish (taxminan 15 daqiqa)

### 1-qadam. Telegram bot yaratish
1. Telegramda **@BotFather** ni oching va `/newbot` yozing.
2. Botga nom bering (masalan: `Iqtisod Yangiliklari`) va username bering (oxiri `bot` bilan tugashi kerak, masalan: `uz_iqtisod_news_bot`).
3. BotFather sizga **token** beradi (`1234567890:AAH...` ko'rinishida). Uni saqlab qo'ying, hech kimga bermang.
4. Yangi botingizni oching va **Start** (`/start`) tugmasini bosing.

### 2-qadam. GitHub'ga yuklash
1. [github.com](https://github.com) da bepul akkaunt oching (agar yo'q bo'lsa).
2. Yuqori o'ngdagi **+** → **New repository**:
   - Nomi: `uz-iqtisod-bot`
   - **Public** ni tanlang (cheksiz bepul daqiqalar uchun. Token va chat ID maxfiy saqlanadi, ular ko'rinmaydi.)
   - **Create repository** ni bosing.
3. **uploading an existing file** havolasini bosing va arxivdagi barcha fayllarni sudrab tashlang: `bot.py`, `config.py`, `requirements.txt`, `README.md`, `.gitignore` va `.github` papkasi. Keyin **Commit changes** ni bosing.

> ⚠️ **Muhim:** `.github` papkasi yashirin bo'lgani uchun ba'zan yuklanmay qoladi. Yuklangandan keyin repozitoriyada `.github/workflows/newsbot.yml` borligini tekshiring. Agar yo'q bo'lsa: **Add file → Create new file**, nomiga aynan `.github/workflows/newsbot.yml` deb yozing, arxivdagi shu fayl matnini nusxalab qo'ying va **Commit** qiling.

### 3-qadam. Tokenni maxfiy qilib qo'shish
1. Repozitoriyada **Settings → Secrets and variables → Actions** bo'limiga kiring.
2. **New repository secret** tugmasini bosing:
   - Name: `TELEGRAM_BOT_TOKEN`
   - Secret: BotFather bergan token
3. **Add secret** ni bosing.

### 4-qadam. Chat ID ni olish
1. Repozitoriyada **Actions** bo'limiga kiring. Agar so'ralsa, **"I understand my workflows, go ahead and enable them"** tugmasini bosing.
2. Chapdan **Iqtisodiy yangiliklar boti** → **Run workflow** → yashil **Run workflow** tugmasini bosing.
3. 1 daqiqa ichida bot sizga Telegramda **chat ID** raqamingizni yuboradi.
4. Yana **Settings → Secrets and variables → Actions → New repository secret**:
   - Name: `TELEGRAM_CHAT_ID`
   - Secret: bot yuborgan raqam

> Muqobil yo'l: **@userinfobot** ga yozsangiz, u ham ID raqamingizni beradi.

### 5-qadam. Ishga tushirish ✅
**Actions → Iqtisodiy yangiliklar boti → Run workflow** ni yana bir marta bosing. Telegramga **"✅ Bot ishga tushdi!"** xabari va eng so'nggi yangiliklar keladi.

Shundan keyin bot **har 30 daqiqada o'zi ishlaydi**. Kompyuteringiz o'chiq bo'lsa ham ishlayveradi.

---

## 📢 Kanal yoki guruhga yuborish (ixtiyoriy)
1. Botni kanalingizga **administrator** qilib qo'shing (xabar yuborish huquqi bilan).
2. `TELEGRAM_CHAT_ID` secret qiymatiga `@kanalingiz_nomi` ni yozing.
3. Bir nechta joyga yuborish uchun vergul bilan yozing: `123456789,@kanalim`
4. `config.py` da `SEND_DELAY_SECONDS = 3` qiling (Telegram kanallar uchun tezlik limiti bor).

---

## ⚙️ Sozlash (`config.py`)
GitHub'da `config.py` faylini oching → ✏️ (Edit) belgisini bosing → o'zgartiring → **Commit changes**.

- **Yangi Telegram kanal qo'shish:**
  ```python
  {"username": "kanal_nomi", "mode": "filter"},
  ```
  Barcha postlarni olish uchun `"mode": "all"` deb yozing. Faqat ochiq (public) kanallar ishlaydi.
- **Yangi RSS sayt qo'shish:** `FOREIGN_SOURCES` ro'yxatidagi namunaga qarang.
- **Kalit so'z qo'shish:** `ECONOMY_KEYWORDS` ro'yxatiga, masalan `r"\bkripto"`.
- **Chastotani o'zgartirish:** `.github/workflows/newsbot.yml` dagi `*/30` ni o'zgartiring (`0 * * * *` = har soatda).
- **Havola rasmini ko'rsatish:** `LINK_PREVIEW = True`.

---

## 💻 O'z kompyuteringizda ishlatish (GitHub'siz)
```bash
pip install -r requirements.txt
# Windows (PowerShell):
$env:TELEGRAM_BOT_TOKEN="token"; $env:TELEGRAM_CHAT_ID="123456789"
# Mac/Linux:
export TELEGRAM_BOT_TOKEN="token" TELEGRAM_CHAT_ID="123456789"

python bot.py --test        # Telegramga test xabari
python bot.py --dry-run     # yubormasdan ekranda ko'rish
python bot.py --loop 1800   # har 30 daqiqada (kompyuter yoniq turishi kerak)
```

---

## ❓ Muammolar
| Muammo | Yechim |
|---|---|
| Hech narsa kelmayapti | **Actions** bo'limida oxirgi ishga tushishni oching va logni o'qing. Secretlar nomi to'g'ri yozilganini tekshiring. |
| `Yuborib bo'lmadi: chat not found` | Botga `/start` bosmagansiz yoki chat ID xato. |
| `Forbidden: bot is not a member` | Botni kanalga administrator qilib qo'shing. |
| Ba'zi kanallar `XATO` | Kanal yopiq yoki username o'zgargan: `config.py` dan tekshiring. |
| 30 daqiqadan kech keladi | GitHub ba'zan rejadagi ishni 5–20 daqiqa kechiktiradi, bu normal holat. |
| Juda ko'p xabar | `config.py` da `"mode": "all"` larni `"filter"` ga o'zgartiring yoki kanallarni olib tashlang. |

**Eslatma:** bot har ishga tushganda `data/seen.json` faylini yangilaydi (yuborilgan xabarlar ro'yxati, faqat qisqa xesh-kodlar, matn emas). Bu commitlar repozitoriyani "faol" holatda ushlab turadi, shuning uchun GitHub jadvalni o'chirib qo'ymaydi.
