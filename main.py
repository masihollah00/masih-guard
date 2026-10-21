# -*- coding: utf-8 -*-
"""MASIH GUARD — consolidated Telegram group manager and utility bot.
Python 3.11+. Configure secrets as hosting environment variables; never hard-code tokens.
"""
import os, re, json, time, logging, threading, random
from collections import defaultdict, deque
from datetime import datetime, timezone

import requests
import telebot
from telebot import types
from flask import Flask, jsonify

BOT_NAME = "MASIH GUARD"
BOT_TITLE = "مسیح گارد"
VERSION = "8.0"
BOT_TOKEN = (os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
AI_API_KEY = os.getenv("AI_API_KEY", "").strip()
AI_BASE_URL = (os.getenv("AI_BASE_URL") or "https://openrouter.ai/api/v1").strip().rstrip("/")
AI_MODEL = (os.getenv("AI_MODEL") or "openrouter/free").strip()
DATA_FILE = os.getenv("DATA_FILE", "masih_guard_data.json")
CHANNEL_URL = "https://t.me/IRHACK_APP33"
CREATOR_URL = "https://t.me/Ma3ih01"
try: OWNER_ID = int(os.getenv("OWNER_ID", "8620924698"))
except (TypeError, ValueError): OWNER_ID = 8620924698
try: PORT = int(os.getenv("PORT", "8080"))
except (TypeError, ValueError): PORT = 8080

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper(), format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger(BOT_NAME)
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing. Set BOT_TOKEN in hosting environment variables.")
if not AI_BASE_URL.startswith("https://"):
    AI_BASE_URL = "https://openrouter.ai/api/v1"
if not AI_MODEL or AI_MODEL.startswith(("http://", "https://")) or AI_MODEL.endswith("/api/v1"):
    AI_MODEL = "openrouter/free"

bot = telebot.TeleBot(BOT_TOKEN, parse_mode=None, threaded=True, num_threads=6)
app = Flask(__name__)
lock = threading.RLock()
spam_history = defaultdict(deque)
duplicate_history = defaultdict(lambda: deque(maxlen=8))
user_last_seen = {}
bot_username = ""

DEFAULT_SETTINGS = {
    "anti_link": True, "anti_spam": True, "anti_duplicate": True,
    "badword_filter": True, "welcome_enabled": True,
    "max_messages": 6, "spam_window": 8, "max_warnings": 3,
    "mute_seconds": 60, "welcome_text": "👋 خوش اومدی {name} عزیز! به گروه خوش اومدی 💜"
}

def default_data():
    return {"badwords": {}, "warnings": {}, "settings": {}, "logs": [], "stats": {}}

def load_data():
    try:
        if os.path.isfile(DATA_FILE):
            with open(DATA_FILE, "r", encoding="utf-8") as f: saved = json.load(f)
            if isinstance(saved, dict):
                base = default_data()
                for k, v in base.items():
                    if isinstance(saved.get(k), type(v)): base[k] = saved[k]
                return base
    except Exception: log.exception("Failed to load data; using defaults")
    return default_data()

data = load_data()

def save_data():
    with lock:
        try:
            os.makedirs(os.path.dirname(os.path.abspath(DATA_FILE)), exist_ok=True)
            tmp = DATA_FILE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, DATA_FILE)
        except Exception: log.exception("Could not save data")

def settings(chat_id):
    with lock:
        s = data["settings"].setdefault(str(chat_id), {})
        for k, v in DEFAULT_SETTINGS.items(): s.setdefault(k, v)
        return s

def log_action(chat_id, message):
    with lock:
        data["logs"].append({"chat": str(chat_id), "time": datetime.now(timezone.utc).isoformat(), "text": str(message)[:240]})
        data["logs"] = data["logs"][-500:]
    save_data()

def reply(message, text, **kwargs):
    try: return bot.reply_to(message, str(text)[:4000], **kwargs)
    except Exception: log.exception("Reply failed"); return None

def send_text(chat_id, text, reply_to=None):
    text = str(text or "پاسخی دریافت نشد.")
    for pos in range(0, len(text), 3900):
        try:
            kw = {"chat_id": chat_id, "text": text[pos:pos+3900]}
            if reply_to is not None: kw["reply_to_message_id"] = reply_to
            bot.send_message(**kw)
        except Exception: log.exception("Send message failed"); break

def group_chat(m): return m.chat.type in ("group", "supergroup")
def owner(uid): return bool(uid and uid == OWNER_ID)
def is_admin(chat_id, uid):
    if owner(uid): return True
    try: return bot.get_chat_member(chat_id, uid).status in ("administrator", "creator")
    except Exception: return False

def is_link(text):
    if not text: return False
    patterns = [r"(?i)\b(?:https?://|ftp://|www\.)[^\s<>]+", r"(?i)(?<![\w@])(?:t\.me|telegram\.me|telegram\.dog)/[^\s<>]*", r"(?i)(?<![\w@])(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+(?:com|net|org|io|co|me|info|biz|xyz|app|dev|site|online|ir|de|uk|ru|tr)(?::\d+)?(?:[/?:#][^\s<>]*)?"]
    return any(re.search(p, str(text)) for p in patterns)

def has_link(m, text):
    if is_link(text): return True
    for attr in ("entities", "caption_entities"):
        if any(getattr(e, "type", "") in ("url", "text_link") for e in (getattr(m, attr, None) or [])): return True
    return False

def target_user(m):
    r = getattr(m, "reply_to_message", None)
    if r and getattr(r, "from_user", None): return r.from_user
    parts = (m.text or "").split()
    if len(parts) > 1 and parts[1].lstrip("-").isdigit():
        try: return bot.get_chat_member(m.chat.id, int(parts[1])).user
        except Exception: return None
    return None

def manageable(m):
    if not group_chat(m): reply(m, "این دستور را داخل گروه اجرا کن."); return None
    if not is_admin(m.chat.id, m.from_user.id): reply(m, "⛔ فقط مدیران گروه می‌توانند این کار را انجام دهند."); return None
    u = target_user(m)
    if not u: reply(m, "⚠️ روی پیام کاربر ریپلای کن یا آیدی عددی او را بنویس."); return None
    if u.id in (m.from_user.id, OWNER_ID): reply(m, "⛔ این کاربر قابل هدف‌گیری نیست."); return None
    try:
        if bot.get_chat_member(m.chat.id, u.id).status in ("administrator", "creator"):
            reply(m, "⛔ این دستور روی مدیران گروه اجرا نمی‌شود."); return None
    except Exception: pass
    return u

def badwords(chat_id):
    with lock:
        v = data["badwords"].get(str(chat_id), [])
        return list(v) if isinstance(v, list) else []

def add_warning(chat_id, uid):
    key = f"{chat_id}:{uid}"
    with lock:
        data["warnings"][key] = int(data["warnings"].get(key, 0)) + 1
        n = data["warnings"][key]
    save_data(); return n

def get_warnings(chat_id, uid):
    with lock: return int(data["warnings"].get(f"{chat_id}:{uid}", 0))

# Health endpoints for hosting
@app.get("/")
def root(): return jsonify({"name": BOT_NAME, "version": VERSION, "status": "running"})
@app.get("/health")
def health(): return jsonify({"status": "ok", "bot": BOT_NAME, "version": VERSION})

# AI service
def ai_answer(question, context=""):
    if not AI_API_KEY: return "⚠️ هوش مصنوعی تنظیم نشده؛ مقدار AI_API_KEY را در محیط هاست قرار بده."
    payload = {"model": AI_MODEL, "messages": [
        {"role": "system", "content": "تو دستیار فارسی‌زبان MASIH GUARD هستی. روشن، مودب، دقیق و ایمن جواب بده؛ اگر مطمئن نیستی صادقانه بگو."},
        {"role": "user", "content": f"گفتگو: {context or 'خصوصی'}\nپرسش: {str(question)[:3500]}"}], "temperature": 0.7, "max_tokens": 900}
    try:
        r = requests.post(AI_BASE_URL + "/chat/completions", headers={"Authorization": "Bearer " + AI_API_KEY, "Content-Type": "application/json", "HTTP-Referer": "https://github.com/masihollah00/masih-guard", "X-OpenRouter-Title": "MASIH GUARD"}, json=payload, timeout=(10, 45))
        if not r.ok:
            log.error("AI API HTTP %s: %s", r.status_code, r.text[:250])
            return {401:"⚠️ کلید API نامعتبر است.",403:"⚠️ دسترسی سرویس رد شد.",429:"⚠️ محدودیت درخواست؛ کمی بعد دوباره امتحان کن.",402:"⚠️ سرویس اعتبار کافی ندارد یا پرداخت لازم است.",400:"⚠️ تنظیمات مدل را بررسی کن.",404:"⚠️ مدل پیدا نشد؛ AI_MODEL را بررسی کن."}.get(r.status_code, f"⚠️ خطای سرویس هوش مصنوعی: HTTP {r.status_code}")
        choices = r.json().get("choices") or []
        content = (choices[0].get("message") or {}).get("content") if choices else None
        if isinstance(content, list): content = "\n".join(str(x.get("text", "")) for x in content if isinstance(x, dict))
        return content.strip() if isinstance(content, str) and content.strip() else "⚠️ پاسخ هوش مصنوعی خالی بود."
    except requests.Timeout: return "⚠️ پاسخ هوش مصنوعی طول کشید؛ دوباره امتحان کن."
    except requests.RequestException: log.exception("AI request failed"); return "⚠️ اتصال به سرویس هوش مصنوعی برقرار نشد."
    except Exception: log.exception("Unexpected AI error"); return "⚠️ خطای غیرمنتظره در هوش مصنوعی."

def ai_reply(m, question):
    status = reply(m, "🤖 دارم فکر می‌کنم...")
    answer = ai_answer(question, getattr(m.chat, "title", "") or "")
    if status:
        try: bot.edit_message_text(str(answer)[:4000], m.chat.id, status.message_id); return
        except Exception: pass
    send_text(m.chat.id, answer, m.message_id)

# Font styles. These map Latin letters only; Persian remains unchanged.
FONT_MAPS = {
    "bold": ("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz", "𝐀𝐁𝐂𝐃𝐄𝐅𝐆𝐇𝐈𝐉𝐊𝐋𝐌𝐍𝐎𝐏𝐐𝐑𝐒𝐓𝐔𝐕𝐖𝐗𝐘𝐙𝐚𝐛𝐜𝐝𝐞𝐟𝐠𝐡𝐢𝐣𝐤𝐥𝐦𝐧𝐨𝐩𝐪𝐫𝐬𝐭𝐮𝐯𝐰𝐱𝐲𝐳"),
    "italic": ("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz", "𝐴𝐵𝐶𝐷𝐸𝐹𝐺𝐻𝐼𝐽𝐾𝐿𝑀𝑁𝑂𝑃𝑄𝑅𝑆𝑇𝑈𝑉𝑊𝑋𝑌𝑍𝑎𝑏𝑐𝑑𝑒𝑓𝑔ℎ𝑖𝑗𝑘𝑙𝑚𝑛𝑜𝑝𝑞𝑟𝑠𝑡𝑢𝑣𝑤𝑥𝑦𝑧"),
    "mono": ("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz", "𝙰𝙱𝙲𝙳𝙴𝙵𝙶𝙷𝙸𝙹𝙺𝙻𝙼𝙽𝙾𝙿𝚀𝚁𝚂𝚃𝚄𝚅𝚆𝚇𝚈𝚉𝚊𝚋𝚌𝚍𝚎𝚏𝚐𝚑𝚒𝚓𝚔𝚕𝚖𝚗𝚘𝚙𝚚𝚛𝚜𝚝𝚞𝚟𝚠𝚡𝚢𝚣"),
    "double": ("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz", "𝔸𝔹ℂ𝔻𝔼𝔽𝔾ℍ𝕀𝕁𝕂𝕃𝕄ℕ𝕆ℙℚℝ𝕊𝕋𝕌𝕍𝕎𝕏𝕐ℤ𝕒𝕓𝕔𝕕𝕖𝕗𝕘𝕙𝕚𝕛𝕜𝕝𝕞𝕟𝕠𝕡𝕢𝕣𝕤𝕥𝕦𝕧𝕨𝕩𝕪𝕫")
}
def convert_font(text, style):
    src, dst = FONT_MAPS[style]
    return str.maketrans(src, dst) and text.translate(str.maketrans(src, dst))

# Menus
def home_markup():
    k = types.InlineKeyboardMarkup(row_width=2)
    k.add(types.InlineKeyboardButton("🛡 مدیریت گروه", callback_data="menu:manage"), types.InlineKeyboardButton("✨ قابلیت‌ها", callback_data="menu:features"))
    k.add(types.InlineKeyboardButton("🖋 فونت‌ساز", callback_data="menu:fonts"), types.InlineKeyboardButton("🌐 پروکسی", callback_data="menu:proxy"))
    k.add(types.InlineKeyboardButton("🤖 هوش مصنوعی", callback_data="menu:ai"), types.InlineKeyboardButton("📊 آمار", callback_data="menu:stats"))
    k.add(types.InlineKeyboardButton("👑 درباره تیم", callback_data="menu:team"), types.InlineKeyboardButton("💎 ربات اشتراکی", callback_data="menu:shared"))
    k.add(types.InlineKeyboardButton("📢 کانال", url=CHANNEL_URL), types.InlineKeyboardButton("👨‍💻 سازنده", url=CREATOR_URL))
    return k

def back_markup():
    k = types.InlineKeyboardMarkup(); k.add(types.InlineKeyboardButton("🔙 بازگشت به منوی اصلی", callback_data="menu:home")); return k

def panel_markup(cid):
    s = settings(cid); k = types.InlineKeyboardMarkup(row_width=2)
    items = [("anti_link","🔗 ضدلینک"),("anti_spam","🚫 ضداسپم"),("anti_duplicate","🔁 ضدتکرار"),("badword_filter","🤬 فیلتر کلمات"),("welcome_enabled","👋 خوشامدگویی")]
    for key, label in items:
        k.add(types.InlineKeyboardButton(f"{label} {'🟢' if s[key] else '🔴'}", callback_data="toggle:"+key))
    k.add(types.InlineKeyboardButton("📊 آمار گروه", callback_data="menu:stats"), types.InlineKeyboardButton("🔙 منوی اصلی", callback_data="menu:home"))
    return k

@bot.message_handler(commands=["start", "help"])
def start(m):
    text = (f"⚡ {BOT_TITLE} | {BOT_NAME} v{VERSION}\n\n"
            "🛡 مدیریت گروه، فونت‌ساز، هوش مصنوعی و ابزارهای کاربردی\n\n"
            "برای دیدن منو از دکمه‌های زیر استفاده کن.\n"
            "در گفت‌وگوی خصوصی پیام بفرست یا از /ai سؤال بپرس.\n\n"
            "دستورات: /panel /ping /id /rules /ai /font /proxy /proxies /stats")
    bot.send_message(m.chat.id, text, reply_markup=home_markup())

@bot.callback_query_handler(func=lambda c: bool(c.data and c.data.startswith("menu:")))
def menu_callback(c):
    try:
        key = c.data.split(":",1)[1]
        pages = {
            "home": (f"⚡ {BOT_TITLE} | {BOT_NAME} v{VERSION}\nهمه ابزارها از این منو در دسترس‌اند.", home_markup()),
            "features": ("✨ قابلیت‌های MASIH GUARD\n• ضدلینک، ضداسپم و ضدتکرار\n• فیلتر کلمات و خوشامدگویی\n• اخطار، سکوت، بن، اخراج و پاک‌سازی\n• فونت‌ساز انگلیسی فانتزی\n• دستیار هوش مصنوعی فارسی\n• آمار و تنظیمات گروه", back_markup()),
            "manage": ("🛡 مدیریت گروه\nبرای تنظیمات گروه، ربات را ادمین کن و /panel را داخل گروه بزن.\nدستورها: /warn /warnings /unwarn /mute /unmute /ban /unban /kick /purge", back_markup()),
            "fonts": ("🖋 فونت‌ساز\nنمونه: /font bold Hello World\nسبک‌ها: bold، italic، mono، double\nتبدیل ویژه برای حروف انگلیسی است؛ متن فارسی بدون تغییر می‌ماند.", back_markup()),
            "proxy": ("🌐 ابزار پروکسی\nبا /proxy راهنما را ببین. با /proxies می‌توانی از منبع عمومی، در صورت دسترسی شبکه، چند آدرس عمومی دریافت کنی.\n⚠️ عمومی‌بودن به معنی امن یا فعال‌بودن نیست؛ پیش از استفاده بررسی کن. پینگ فقط در صورت تست واقعی اعلام می‌شود.", back_markup()),
            "ai": ("🤖 هوش مصنوعی\nدر خصوصی پیام بفرست یا از /ai سؤال استفاده کن. باید AI_API_KEY و مدل مناسب در تنظیمات هاست تنظیم شده باشد.", back_markup()),
            "team": ("👑 درباره تیم\nما روی ساخت ربات‌های تلگرام، وب‌سایت و نرم‌افزار کار می‌کنیم. هرگونه آزمون امنیتی فقط با اجازه و روی سامانه‌های مجاز انجام می‌شود.\nسازنده: @Ma3ih01", back_markup()),
            "shared": ("💎 چرا ربات اشتراکی؟\nراه‌اندازی آسان، ابزارهای مدیریت گروه و قابلیت‌های کاربردی در یک ربات. دسترسی و پایداری به امکانات هاست و تنظیمات بستگی دارد؛ هیچ تضمین uptime غیرواقعی داده نمی‌شود.", back_markup()),
            "stats": ("📊 آمار کلی\nبرای آمار دقیق گروه، دستور /stats را به‌عنوان مدیر گروه اجرا کن.", back_markup())
        }
        text, markup = pages.get(key, pages["home"])
        if c.message: bot.edit_message_text(text, c.message.chat.id, c.message.message_id, reply_markup=markup)
        bot.answer_callback_query(c.id)
    except Exception:
        log.exception("Menu callback failed")
        try: bot.answer_callback_query(c.id, "خطا در بازکردن منو")
        except Exception: pass

@bot.callback_query_handler(func=lambda c: bool(c.data and c.data.startswith("toggle:")))
def toggle_callback(c):
    try:
        if not c.message: return
        cid = c.message.chat.id
        if not is_admin(cid, c.from_user.id): bot.answer_callback_query(c.id, "فقط مدیر گروه اجازه دارد.", show_alert=True); return
        key = c.data.split(":",1)[1]
        if key not in ("anti_link","anti_spam","anti_duplicate","badword_filter","welcome_enabled"): bot.answer_callback_query(c.id,"تنظیم نامعتبر"); return
        s = settings(cid); s[key] = not bool(s[key]); save_data()
        bot.answer_callback_query(c.id, "تنظیم ذخیره شد.")
        bot.edit_message_reply_markup(cid, c.message.message_id, reply_markup=panel_markup(cid))
    except Exception: log.exception("Toggle callback failed")

@bot.message_handler(commands=["panel"])
def panel(m):
    if not group_chat(m): reply(m,"⚙️ پنل مدیریت را داخل گروه باز کن."); return
    if not is_admin(m.chat.id,m.from_user.id): reply(m,"⛔ پنل فقط برای مدیران گروه است."); return
    bot.send_message(m.chat.id, "✨ پنل مدیریت MASIH GUARD\n🟢 روشن | 🔴 خاموش", reply_markup=panel_markup(m.chat.id))

@bot.message_handler(commands=["ping"])
def ping(m): reply(m, f"✅ {BOT_NAME} آنلاین است | نسخه {VERSION}")
@bot.message_handler(commands=["id"])
def ids(m): reply(m, f"👤 آیدی شما: {m.from_user.id}\n💬 آیدی گفتگو: {m.chat.id}")
@bot.message_handler(commands=["rules"])
def rules(m): reply(m,"📘 قوانین پیشنهادی: احترام، پرهیز از اسپم و لینک ناخواسته، رعایت قوانین تلگرام و گروه.")
@bot.message_handler(commands=["ai"])
def ai_cmd(m):
    q = (m.text or "").partition(" ")[2].strip()
    if not q and m.reply_to_message: q = (m.reply_to_message.text or m.reply_to_message.caption or "").strip()
    if not q: reply(m,"نمونه: /ai درباره فضا توضیح بده"); return
    ai_reply(m,q)

@bot.message_handler(commands=["font"])
def font_cmd(m):
    parts = (m.text or "").split(maxsplit=2)
    if len(parts) < 3:
        reply(m,"استفاده: /font bold متن\nسبک‌ها: bold، italic، mono، double\nمثال: /font mono Hello Masih"); return
    style, value = parts[1].lower(), parts[2]
    if style not in FONT_MAPS: reply(m,"سبک نامعتبر است. یکی از این‌ها: bold، italic، mono، double"); return
    reply(m, convert_font(value,style))

@bot.message_handler(commands=["proxy"])
def proxy_help(m):
    reply(m,"🌐 راهنمای پروکسی\n/proxies — دریافت چند لینک عمومی از منبع عمومی در دسترس\n⚠️ فعال‌بودن، امنیت و سرعت تضمین‌شده نیست؛ برای حساب‌های حساس از پروکسی ناشناس استفاده نکن.")

@bot.message_handler(commands=["proxies"])
def proxies(m):
    status = reply(m,"🌐 در حال بررسی منبع عمومی پروکسی…")
    try:
        # Public list endpoint; entries are links, not certified working proxies.
        r = requests.get("https://raw.githubusercontent.com/ALIILAPRO/MTProtoProxy/main/proxy.txt", timeout=12)
        r.raise_for_status()
        candidates = re.findall(r"https?://t\.me/proxy\?[^\s<>]+", r.text)
        unique = list(dict.fromkeys(candidates))[:10]
        if not unique: out = "⚠️ منبع فعلاً لینک قابل استفاده‌ای نداد. بعداً دوباره امتحان کن."
        else: out = "🌐 لینک‌های عمومی پیدا شده (فعال‌بودن تأیید نشده):\n\n" + "\n".join(f"{i+1}. {url}" for i,url in enumerate(unique)) + "\n\n⚠️ قبل از استفاده، اعتماد و امنیت منبع را بررسی کن."
    except Exception:
        log.exception("Proxy list fetch failed")
        out = "⚠️ دریافت فهرست پروکسی ممکن نشد؛ اتصال هاست یا منبع عمومی را بررسی کن."
    try:
        if status: bot.edit_message_text(out[:4000],m.chat.id,status.message_id)
        else: send_text(m.chat.id,out)
    except Exception: send_text(m.chat.id,out)

@bot.message_handler(commands=["stats"])
def stats(m):
    if not group_chat(m) or not is_admin(m.chat.id,m.from_user.id): reply(m,"⛔ این دستور فقط برای مدیر گروه است."); return
    with lock:
        logs = [x for x in data["logs"] if x.get("chat")==str(m.chat.id)]
        warned = sum(1 for k,v in data["warnings"].items() if k.startswith(str(m.chat.id)+":") and int(v or 0)>0)
    s = settings(m.chat.id)
    active = [label for key,label in [("anti_link","ضدلینک"),("anti_spam","ضداسپم"),("anti_duplicate","ضدتکرار"),("badword_filter","فیلتر کلمات"),("welcome_enabled","خوشامدگویی")] if s[key]]
    reply(m,f"📊 آمار MASIH GUARD\nگزارش‌های ثبت‌شده: {len(logs)}\nکاربران دارای اخطار: {warned}\nقابلیت‌های روشن: {', '.join(active) if active else 'هیچ‌کدام'}")

@bot.message_handler(commands=["warn"])
def warn(m):
    u=manageable(m)
    if not u:return
    n=add_warning(m.chat.id,u.id); limit=int(settings(m.chat.id)["max_warnings"])
    reply(m,f"⚠️ اخطار ثبت شد: {n}/{limit}"); log_action(m.chat.id,f"Warning for {u.id}: {n}")
    if n>=limit:
        try: bot.ban_chat_member(m.chat.id,u.id); reply(m,"⛔ سقف اخطار رسید؛ کاربر مسدود شد."); log_action(m.chat.id,f"Auto-ban {u.id}")
        except Exception: log.exception("Auto-ban failed"); reply(m,"⚠️ بن خودکار ناموفق بود؛ دسترسی ربات را بررسی کن.")
@bot.message_handler(commands=["warnings"])
def warnings(m):
    u=target_user(m); uid=u.id if u else m.from_user.id
    reply(m,f"⚠️ تعداد اخطارها: {get_warnings(m.chat.id,uid)}")
@bot.message_handler(commands=["unwarn"])
def unwarn(m):
    u=manageable(m)
    if not u:return
    with lock:data["warnings"][f"{m.chat.id}:{u.id}"]=0
    save_data(); reply(m,"✅ اخطارهای کاربر پاک شد.")

@bot.message_handler(commands=["mute"])
def mute(m):
    u=manageable(m)
    if not u:return
    try:
        secs=max(30,min(86400,int(settings(m.chat.id)["mute_seconds"])))
        bot.restrict_chat_member(m.chat.id,u.id,until_date=int(time.time())+secs,permissions=types.ChatPermissions(can_send_messages=False))
        reply(m,f"🔇 کاربر برای {secs} ثانیه سکوت شد."); log_action(m.chat.id,f"Mute {u.id} {secs}s")
    except Exception: log.exception("Mute failed"); reply(m,"⚠️ سکوت ناموفق بود؛ دسترسی محدودکردن اعضا را بررسی کن.")
@bot.message_handler(commands=["unmute"])
def unmute(m):
    u=manageable(m)
    if not u:return
    try:
        bot.restrict_chat_member(m.chat.id,u.id,permissions=types.ChatPermissions(can_send_messages=True,can_send_audios=True,can_send_documents=True,can_send_photos=True,can_send_videos=True,can_send_video_notes=True,can_send_voice_notes=True,can_send_polls=True,can_send_other_messages=True,can_add_web_page_previews=True))
        reply(m,"🔊 سکوت کاربر برداشته شد.")
    except Exception: log.exception("Unmute failed"); reply(m,"⚠️ رفع سکوت ناموفق بود؛ مجوزها و نسخهٔ کتابخانه را بررسی کن.")
@bot.message_handler(commands=["ban"])
def ban(m):
    u=manageable(m)
    if not u:return
    try: bot.ban_chat_member(m.chat.id,u.id); reply(m,"⛔ کاربر مسدود شد."); log_action(m.chat.id,f"Ban {u.id}")
    except Exception: log.exception("Ban failed"); reply(m,"⚠️ مسدودسازی ناموفق بود؛ دسترسی ربات را بررسی کن.")
@bot.message_handler(commands=["unban"])
def unban(m):
    if not group_chat(m) or not is_admin(m.chat.id,m.from_user.id): reply(m,"⛔ فقط مدیر گروه."); return
    p=(m.text or "").split()
    if len(p)<2 or not p[1].lstrip("-").isdigit(): reply(m,"استفاده: /unban آیدی_عددی"); return
    try: bot.unban_chat_member(m.chat.id,int(p[1])); reply(m,"✅ مسدودیت برداشته شد.")
    except Exception: log.exception("Unban failed"); reply(m,"⚠️ رفع مسدودیت ناموفق بود.")
@bot.message_handler(commands=["kick"])
def kick(m):
    u=manageable(m)
    if not u:return
    try: bot.ban_chat_member(m.chat.id,u.id); bot.unban_chat_member(m.chat.id,u.id); reply(m,"👢 کاربر از گروه اخراج شد."); log_action(m.chat.id,f"Kick {u.id}")
    except Exception: log.exception("Kick failed"); reply(m,"⚠️ اخراج ناموفق بود.")
@bot.message_handler(commands=["purge"])
def purge(m):
    if not group_chat(m) or not is_admin(m.chat.id,m.from_user.id): reply(m,"⛔ فقط مدیر گروه."); return
    if not m.reply_to_message: reply(m,"روی اولین پیام موردنظر ریپلای کن و /purge بزن."); return
    first=m.reply_to_message.message_id; last=m.message_id-1
    if last-first>100: first=last-100
    deleted=0
    for mid in range(first,last+1):
        try: bot.delete_message(m.chat.id,mid); deleted+=1
        except Exception: pass
    try: bot.send_message(m.chat.id,f"🧹 پاک‌سازی تمام شد؛ تعداد پیام‌های پاک‌شده: {deleted}")
    except Exception: pass

def set_setting(m,key,value):
    if not group_chat(m) or not is_admin(m.chat.id,m.from_user.id): reply(m,"⛔ مدیر گروه باید این دستور را داخل گروه اجرا کند."); return
    settings(m.chat.id)[key]=value; save_data(); reply(m,"✅ تنظیم ذخیره شد.")
for _cmd,_key,_value in [("antilink_on","anti_link",True),("antilink_off","anti_link",False),("antispam_on","anti_spam",True),("antispam_off","anti_spam",False),("welcome_on","welcome_enabled",True),("welcome_off","welcome_enabled",False)]:
    def _make_handler(key,value):
        def _handler(m): set_setting(m,key,value)
        return _handler
    bot.message_handler(commands=[_cmd])(_make_handler(_key,_value))

@bot.message_handler(commands=["addbadword"])
def add_badword(m):
    if not group_chat(m) or not is_admin(m.chat.id,m.from_user.id): reply(m,"⛔ فقط مدیر گروه."); return
    word=(m.text or "").partition(" ")[2].strip()[:100]
    if not word: reply(m,"استفاده: /addbadword کلمه"); return
    with lock:
        arr=data["badwords"].setdefault(str(m.chat.id),[])
        if word.casefold() not in [str(x).casefold() for x in arr]: arr.append(word)
    save_data(); reply(m,"✅ کلمه به فیلتر اضافه شد.")
@bot.message_handler(commands=["delbadword"])
def del_badword(m):
    if not group_chat(m) or not is_admin(m.chat.id,m.from_user.id): reply(m,"⛔ فقط مدیر گروه."); return
    word=(m.text or "").partition(" ")[2].strip()
    if not word: reply(m,"استفاده: /delbadword کلمه"); return
    with lock: data["badwords"][str(m.chat.id)]=[x for x in data["badwords"].get(str(m.chat.id),[]) if str(x).casefold()!=word.casefold()]
    save_data(); reply(m,"✅ کلمه از فیلتر حذف شد.")
@bot.message_handler(commands=["badwords"])
def list_badwords(m):
    if not group_chat(m) or not is_admin(m.chat.id,m.from_user.id): reply(m,"⛔ فقط مدیر گروه."); return
    arr=badwords(m.chat.id); reply(m,"📃 کلمات فیلتر:\n"+("\n".join(arr) if arr else "هنوز کلمه‌ای ثبت نشده."))

@bot.message_handler(content_types=["new_chat_members"])
def welcome_members(m):
    s=settings(m.chat.id)
    if not s["welcome_enabled"]: return
    template=str(s.get("welcome_text") or DEFAULT_SETTINGS["welcome_text"])
    for u in m.new_chat_members:
        if not u.is_bot:
            try: bot.send_message(m.chat.id,template.replace("{name}",u.first_name or "دوست عزیز"))
            except Exception: log.exception("Welcome failed")

def group_ai(m,text_value):
    if not bot_username or not text_value:return False
    mentioned=bool(re.search(r"@"+re.escape(bot_username)+r"\b",text_value,re.I))
    r=m.reply_to_message
    replied=bool(r and r.from_user and r.from_user.is_bot and (r.from_user.username or "").lower()==bot_username.lower())
    if not (mentioned or replied):return False
    cleaned=re.sub(r"@"+re.escape(bot_username)+r"\b","",text_value,flags=re.I).strip()
    if not cleaned and r:cleaned=(r.text or r.caption or "").strip()
    if cleaned:ai_reply(m,cleaned)
    else:reply(m,"سؤالت رو هم بنویس تا جواب بدم.")
    return True

@bot.message_handler(func=lambda m: bool(m.text) and not m.text.startswith("/") and m.chat.type == "private", content_types=["text"])
def private_ai(m):
    if m.chat.type=="private" and m.from_user and not m.from_user.is_bot: ai_reply(m,m.text.strip())

GROUP_CONTENT=["text","photo","video","document","audio","voice","animation","sticker","video_note","contact","location","venue","poll"]
@bot.message_handler(func=lambda m: True, content_types=GROUP_CONTENT)
def moderate(m):
    if not m.from_user or m.from_user.is_bot or not group_chat(m):return
    text_value=(m.text or m.caption or "").strip(); s=settings(m.chat.id); admin=is_admin(m.chat.id,m.from_user.id)
    with lock: data["stats"][str(m.chat.id)]=int(data["stats"].get(str(m.chat.id),0))+1
    if not admin:
        if s["anti_link"] and has_link(m,text_value):
            try:bot.delete_message(m.chat.id,m.message_id);log_action(m.chat.id,f"Link removed from {m.from_user.id}");bot.send_message(m.chat.id,"🔗 ارسال لینک در گروه مجاز نیست.")
            except Exception:log.exception("Anti-link failed; check delete permission")
            return
        words=badwords(m.chat.id)
        if s["badword_filter"] and text_value and any(w and w.casefold() in text_value.casefold() for w in words):
            try:bot.delete_message(m.chat.id,m.message_id);log_action(m.chat.id,f"Filtered word from {m.from_user.id}")
            except Exception:log.exception("Badword delete failed")
            return
        if s["anti_duplicate"] and text_value:
            hist=duplicate_history[(m.chat.id,m.from_user.id)]; norm=re.sub(r"\s+"," ",text_value).casefold()
            if norm and norm in hist:
                try:bot.delete_message(m.chat.id,m.message_id);log_action(m.chat.id,f"Duplicate removed from {m.from_user.id}")
                except Exception:log.exception("Duplicate delete failed")
                return
            hist.append(norm)
        if s["anti_spam"]:
            now=time.time();hist=spam_history[(m.chat.id,m.from_user.id)];hist.append(now)
            window=max(1,min(60,int(s.get("spam_window",8))))
            while hist and now-hist[0]>window:hist.popleft()
            maximum=max(2,min(30,int(s.get("max_messages",6))))
            if len(hist)>maximum:
                try:
                    bot.delete_message(m.chat.id,m.message_id)
                    secs=max(30,min(86400,int(s.get("mute_seconds",60))))
                    bot.restrict_chat_member(m.chat.id,m.from_user.id,until_date=int(time.time())+secs,permissions=types.ChatPermissions(can_send_messages=False))
                    bot.send_message(m.chat.id,f"🚫 به دلیل ارسال پیام‌های زیاد، کاربر برای {secs} ثانیه سکوت شد.")
                    log_action(m.chat.id,f"Anti-spam mute {m.from_user.id}")
                except Exception:log.exception("Anti-spam failed; check admin permissions")
                finally:hist.clear()
                return
    group_ai(m,text_value)

def flask_thread(): app.run(host="0.0.0.0",port=PORT,use_reloader=False)
def polling_loop():
    global bot_username
    delay=3
    while True:
        try:
            log.info("Starting %s v%s",BOT_NAME,VERSION)
            me=bot.get_me();bot_username=me.username or ""
            log.info("Telegram connected as @%s",bot_username or "unknown")
            bot.remove_webhook()
            bot.infinity_polling(timeout=30,long_polling_timeout=25,skip_pending=False)
            delay=3
        except KeyboardInterrupt:log.info("Bot stopped");break
        except Exception:log.exception("Polling stopped; reconnect in %s seconds",delay);time.sleep(delay);delay=min(delay*2,60)

if __name__=="__main__":
    threading.Thread(target=flask_thread,daemon=True).start()
    polling_loop()
