# -*- coding: utf-8 -*-
"""MASIH GUARD v7.0 — combined and hardened build; Python 3.11+"""
import os, re, json, time, logging, threading
from collections import defaultdict, deque
from datetime import datetime, timezone
import requests
import telebot
from telebot import types
from flask import Flask, jsonify

BOT_NAME = "مسیح گارد"
VERSION = "7.0"
BOT_TOKEN = (os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
AI_API_KEY = os.getenv("AI_API_KEY", "").strip()
AI_BASE_URL = (os.getenv("AI_BASE_URL") or "https://openrouter.ai/api/v1").strip().rstrip("/")
AI_MODEL = (os.getenv("AI_MODEL") or "openrouter/free").strip()
DATA_FILE = os.getenv("DATA_FILE", "masih_guard_data.json")
try: OWNER_ID = int(os.getenv("OWNER_ID", "8620924698"))
except (TypeError, ValueError): OWNER_ID = 8620924698
try: PORT = int(os.getenv("PORT", "8080"))
except (TypeError, ValueError): PORT = 8080

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper(), format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("MASIH_GUARD")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing. Add it to your hosting environment variables.")
if not AI_BASE_URL.startswith("https://"):
    AI_BASE_URL = "https://openrouter.ai/api/v1"
if not AI_MODEL or AI_MODEL.startswith(("http://", "https://")) or AI_MODEL.rstrip("/").endswith("/api/v1"):
    AI_MODEL = "openrouter/free"

bot = telebot.TeleBot(BOT_TOKEN, parse_mode=None, threaded=True, num_threads=8)
app = Flask(__name__)
data_lock = threading.RLock()
spam_history = defaultdict(deque)
duplicate_history = defaultdict(lambda: deque(maxlen=6))
bot_username = None

DEFAULT_SETTINGS = {
    "anti_link": True, "anti_spam": True, "anti_duplicate": True,
    "badword_filter": True, "welcome_enabled": True,
    "max_messages": 6, "spam_window": 8, "max_warnings": 3,
    "mute_seconds": 60, "welcome_text": "👋 خوش اومدی {name} عزیز!"
}

def default_data():
    return {"badwords": {}, "warnings": {}, "settings": {}, "logs": []}

def load_data():
    try:
        if os.path.isfile(DATA_FILE):
            with open(DATA_FILE, "r", encoding="utf-8") as f: saved = json.load(f)
            if isinstance(saved, dict):
                base = default_data()
                for k, v in base.items():
                    if isinstance(saved.get(k), type(v)): base[k] = saved[k]
                return base
    except Exception: log.exception("Could not load data; using defaults.")
    return default_data()

data = load_data()

def save_data():
    with data_lock:
        try:
            folder = os.path.dirname(os.path.abspath(DATA_FILE))
            os.makedirs(folder, exist_ok=True)
            tmp = DATA_FILE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, DATA_FILE)
        except Exception: log.exception("Could not save data; check host disk permissions.")

def chat_settings(chat_id):
    with data_lock:
        s = data["settings"].setdefault(str(chat_id), {})
        for k, v in DEFAULT_SETTINGS.items(): s.setdefault(k, v)
        return s

def log_action(chat_id, action):
    with data_lock:
        data["logs"].append({"chat": str(chat_id), "time": datetime.now(timezone.utc).isoformat(), "text": str(action)[:300]})
        data["logs"] = data["logs"][-500:]
    save_data()

def reply_safe(message, text, **kwargs):
    try: return bot.reply_to(message, str(text)[:4000], **kwargs)
    except Exception: log.exception("Telegram reply failed."); return None

def send_chunks(chat_id, text, reply_to=None):
    text = str(text or "").strip() or "پاسخی دریافت نشد."
    for i in range(0, len(text), 3900):
        try:
            opts = {"chat_id": chat_id, "text": text[i:i+3900]}
            if reply_to is not None: opts["reply_to_message_id"] = reply_to
            bot.send_message(**opts)
        except Exception: log.exception("Sending message chunk failed."); break

def is_owner(user_id): return bool(user_id and user_id == OWNER_ID)

def is_group(message): return message.chat.type in ("group", "supergroup")

def is_admin(chat_id, user_id):
    if is_owner(user_id): return True
    try: return bot.get_chat_member(chat_id, user_id).status in ("administrator", "creator")
    except Exception: return False

def get_badwords(chat_id):
    with data_lock:
        words = data["badwords"].get(str(chat_id), [])
        return list(words) if isinstance(words, list) else []

def is_link(text):
    if not text: return False
    patterns = [
        r"(?i)\b(?:https?://|ftp://|www\.)[^\s<>]+",
        r"(?i)(?<![\w@])(?:t\.me|telegram\.me|telegram\.dog)/[^\s<>]*",
        r"(?i)(?<![\w@])(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+(?:com|net|org|io|co|me|info|biz|xyz|app|dev|site|online|ir|de|uk|ru|tr)(?::\d+)?(?:[/?:#][^\s<>]*)?"
    ]
    return any(re.search(p, str(text)) for p in patterns)

def message_has_link(message, text):
    if is_link(text): return True
    for attr in ("entities", "caption_entities"):
        for entity in (getattr(message, attr, None) or []):
            if getattr(entity, "type", "") in ("url", "text_link"): return True
    return False

def extract_target(message):
    replied = getattr(message, "reply_to_message", None)
    if replied and getattr(replied, "from_user", None): return replied.from_user
    parts = (message.text or "").split()
    if len(parts) > 1 and parts[1].lstrip("-").isdigit():
        try: return bot.get_chat_member(message.chat.id, int(parts[1])).user
        except Exception: return None
    return None

def target_user_id(message):
    user = extract_target(message)
    return user.id if user else None

def ensure_manageable(message, target_id):
    if not is_group(message): reply_safe(message, "این دستور را داخل گروه اجرا کن."); return False
    if not is_admin(message.chat.id, message.from_user.id): reply_safe(message, "⛔ این دستور مخصوص مدیران گروه است."); return False
    if not target_id: reply_safe(message, "⚠️ روی پیام کاربر ریپلای کن یا آیدی عددی او را بنویس."); return False
    if target_id in (message.from_user.id, OWNER_ID): reply_safe(message, "⛔ این کاربر را نمی‌توانی هدف قرار بدهی."); return False
    try:
        if bot.get_chat_member(message.chat.id, target_id).status in ("administrator", "creator"):
            reply_safe(message, "⛔ این دستور روی مدیران گروه اجرا نمی‌شود."); return False
    except Exception: pass
    return True

def add_warning(chat_id, user_id):
    key = f"{chat_id}:{user_id}"
    with data_lock:
        data["warnings"][key] = int(data["warnings"].get(key, 0)) + 1
        count = data["warnings"][key]
    save_data(); return count

def warning_count(chat_id, user_id):
    with data_lock: return int(data["warnings"].get(f"{chat_id}:{user_id}", 0))

@app.get("/")
def home(): return jsonify({"name": BOT_NAME, "version": VERSION, "status": "running"})
@app.get("/health")
def health(): return jsonify({"status": "ok", "bot": BOT_NAME, "version": VERSION})

# AI

def ai_answer(question, chat_title=""):
    if not AI_API_KEY: return "⚠️ هوش مصنوعی تنظیم نشده؛ مدیر باید AI_API_KEY را در تنظیمات میزبان وارد کند."
    payload = {"model": AI_MODEL, "messages": [
        {"role": "system", "content": "تو دستیار فارسی‌زبان ربات مسیح گارد هستی. فارسی روان، دقیق، محترمانه و مفید پاسخ بده؛ اگر مطمئن نیستی صادقانه بگو."},
        {"role": "user", "content": f"گفتگو: {chat_title or 'خصوصی'}\nپرسش: {str(question)[:3500]}"}], "temperature": 0.7, "max_tokens": 900}
    try:
        r = requests.post(AI_BASE_URL + "/chat/completions", headers={"Authorization": "Bearer " + AI_API_KEY,
            "Content-Type": "application/json", "HTTP-Referer": "https://github.com/masihollah00/masih-guard",
            "X-OpenRouter-Title": "Masih Guard"}, json=payload, timeout=(10, 45))
        if not r.ok:
            log.error("AI API HTTP %s: %s", r.status_code, r.text[:300])
            if r.status_code in (401, 403): return "⚠️ کلید API یا دسترسی سرویس رد شد؛ AI_API_KEY را بررسی کن."
            if r.status_code == 429: return "⚠️ محدودیت درخواست هوش مصنوعی رسیده؛ کمی بعد دوباره امتحان کن."
            if r.status_code == 402: return "⚠️ سرویس هوش مصنوعی درخواست را به‌دلیل اعتبار یا پرداخت نپذیرفت."
            if r.status_code in (400, 404): return "⚠️ مدل در دسترس نیست؛ AI_MODEL را بررسی کن."
            return f"⚠️ سرویس هوش مصنوعی خطای HTTP {r.status_code} داد."
        choices = r.json().get("choices") or []
        if not choices: return "⚠️ سرویس هوش مصنوعی پاسخ قابل استفاده‌ای نداد."
        content = (choices[0].get("message") or {}).get("content")
        if isinstance(content, list): content = "\n".join(str(x.get("text", "")) for x in content if isinstance(x, dict))
        return content.strip() if isinstance(content, str) and content.strip() else "⚠️ پاسخ هوش مصنوعی خالی بود."
    except requests.Timeout: return "⚠️ پاسخ هوش مصنوعی طول کشید؛ دوباره امتحان کن."
    except requests.RequestException: log.exception("AI request failed."); return "⚠️ اتصال به سرویس هوش مصنوعی برقرار نشد."
    except Exception: log.exception("Unexpected AI error."); return "⚠️ خطای غیرمنتظره در بخش هوش مصنوعی رخ داد."

def send_ai_reply(message, question):
    status = reply_safe(message, "🤖 دارم فکر می‌کنم...")
    answer = ai_answer(question, getattr(message.chat, "title", "") or "")
    if status:
        try: bot.edit_message_text(str(answer)[:4000], message.chat.id, status.message_id); return
        except Exception: log.exception("Could not edit AI status message.")
    send_chunks(message.chat.id, answer, reply_to=message.message_id)

# Basic commands
@bot.message_handler(commands=["start", "help"])
def start_command(m):
    reply_safe(m, f"🛡 {BOT_NAME} v{VERSION}\n\nمدیریت گروه و دستیار فارسی فعال است.\n\n🤖 خصوصی: پیام عادی بفرست.\nگروه: /ai سؤال یا منشن ربات/ریپلای به ربات\n\n📌 /start /help /ping /id /rules /ai\n⚙️ /panel /stats\n🔗 /antilink_on /antilink_off\n🚫 /antispam_on /antispam_off\n👋 /welcome_on /welcome_off\n🤬 /addbadword کلمه /delbadword کلمه /badwords\n👮 /warn /warnings /unwarn /mute /unmute /ban /unban آیدی /kick /purge")
@bot.message_handler(commands=["ping"])
def ping_command(m): reply_safe(m, f"✅ {BOT_NAME} آنلاین است | نسخه {VERSION}")
@bot.message_handler(commands=["id"])
def id_command(m): reply_safe(m, f"👤 آیدی شما: {m.from_user.id}\n💬 آیدی گفتگو: {m.chat.id}")
@bot.message_handler(commands=["rules"])
def rules_command(m): reply_safe(m, "📘 قوانین: احترام به اعضا، پرهیز از اسپم و رعایت قوانین گروه.")
@bot.message_handler(commands=["ai"])
def ai_command(m):
    q = (m.text or "").partition(" ")[2].strip()
    if not q and getattr(m, "reply_to_message", None): q = (m.reply_to_message.text or m.reply_to_message.caption or "").strip()
    if not q: reply_safe(m, "مثال: /ai درباره فضا توضیح بده"); return
    send_ai_reply(m, q)

# Panel: Telegram does not support custom button colors; use colorful status icons.
def build_panel_markup(chat_id):
    s = chat_settings(chat_id); markup = types.InlineKeyboardMarkup(row_width=2)
    items = [("anti_link", "🔗 ضدلینک"), ("anti_spam", "🚫 ضداسپم"), ("anti_duplicate", "🔁 ضدتکرار"),
             ("badword_filter", "🤬 فیلتر کلمات"), ("welcome_enabled", "👋 خوشامدگویی")]
    for key, label in items:
        state = "🟢 روشن" if s[key] else "🔴 خاموش"
        markup.add(types.InlineKeyboardButton(f"{label} | {state}", callback_data=f"toggle:{key}"))
    markup.add(types.InlineKeyboardButton("🟣 آمار گروه", callback_data="panel:stats"))
    return markup

@bot.message_handler(commands=["panel"])
def panel_command(m):
    if not is_group(m): reply_safe(m, "⚙️ پنل را داخل گروه باز کن."); return
    if not is_admin(m.chat.id, m.from_user.id): reply_safe(m, "⛔ پنل فقط برای مدیران گروه است."); return
    bot.send_message(m.chat.id, f"✨ پنل مدیریت {BOT_NAME} v{VERSION}\n🟢 روشن | 🔴 خاموش | 🟣 آمار\nبرای تغییر وضعیت روی دکمه‌ها بزن:", reply_markup=build_panel_markup(m.chat.id))

@bot.callback_query_handler(func=lambda c: bool(c.data and (c.data.startswith("toggle:") or c.data == "panel:stats")))
def panel_callback(c):
    try:
        if not c.message: bot.answer_callback_query(c.id, "پیام پنل پیدا نشد."); return
        cid = c.message.chat.id
        if not is_admin(cid, c.from_user.id): bot.answer_callback_query(c.id, "فقط مدیر گروه می‌تواند تنظیمات را تغییر دهد.", show_alert=True); return
        if c.data == "panel:stats":
            with data_lock: count = sum(1 for x in data["logs"] if x.get("chat") == str(cid))
            bot.answer_callback_query(c.id, f"🟣 گزارش‌های ذخیره‌شده: {count}", show_alert=True); return
        key = c.data.split(":", 1)[1]
        if key not in ("anti_link", "anti_spam", "anti_duplicate", "badword_filter", "welcome_enabled"):
            bot.answer_callback_query(c.id, "تنظیم نامعتبر است."); return
        s = chat_settings(cid); s[key] = not bool(s[key]); save_data()
        bot.answer_callback_query(c.id, "✅ تنظیم ذخیره شد.")
        bot.edit_message_reply_markup(cid, c.message.message_id, reply_markup=build_panel_markup(cid))
    except Exception:
        log.exception("Panel callback failed.")
        try: bot.answer_callback_query(c.id, "خطا در تغییر تنظیمات.")
        except Exception: pass

@bot.message_handler(commands=["stats"])
def stats_command(m):
    if not is_group(m) or not is_admin(m.chat.id, m.from_user.id): reply_safe(m, "⛔ این دستور فقط برای مدیران گروه است."); return
    with data_lock:
        logs = [x for x in data["logs"] if x.get("chat") == str(m.chat.id)]
        warns = sum(1 for k, v in data["warnings"].items() if k.startswith(str(m.chat.id)+":") and int(v or 0) > 0)
    s = chat_settings(m.chat.id)
    enabled = [label for key, label in [("anti_link","ضدلینک"),("anti_spam","ضداسپم"),("anti_duplicate","ضدتکرار"),("badword_filter","فیلتر کلمات"),("welcome_enabled","خوشامدگویی")] if s[key]]
    reply_safe(m, f"📊 آمار مسیح گارد\nگزارش‌ها: {len(logs)}\nکاربران دارای اخطار: {warns}\nقابلیت‌های روشن: {', '.join(enabled) if enabled else 'هیچ‌کدام'}")

# Moderation commands
@bot.message_handler(commands=["warn"])
def warn_command(m):
    tid = target_user_id(m)
    if not ensure_manageable(m, tid): return
    count = add_warning(m.chat.id, tid); maximum = int(chat_settings(m.chat.id)["max_warnings"])
    reply_safe(m, f"⚠️ اخطار ثبت شد: {count}/{maximum}")
    if count >= maximum:
        try: bot.ban_chat_member(m.chat.id, tid); reply_safe(m, "⛔ سقف اخطارها رسید؛ کاربر مسدود شد."); log_action(m.chat.id, f"Auto-ban user {tid}")
        except Exception: log.exception("Auto-ban failed."); reply_safe(m, "⚠️ بن خودکار ناموفق بود؛ دسترسی ادمین ربات را بررسی کن.")
@bot.message_handler(commands=["warnings"])
def warnings_command(m): reply_safe(m, f"⚠️ تعداد اخطارها: {warning_count(m.chat.id, target_user_id(m) or m.from_user.id)}")
@bot.message_handler(commands=["unwarn"])
def unwarn_command(m):
    tid = target_user_id(m)
    if not ensure_manageable(m, tid): return
    with data_lock: data["warnings"][f"{m.chat.id}:{tid}"] = 0
    save_data(); reply_safe(m, "✅ اخطارهای کاربر پاک شد.")
@bot.message_handler(commands=["mute"])
def mute_command(m):
    tid = target_user_id(m)
    if not ensure_manageable(m, tid): return
    try:
        seconds = max(30, min(86400, int(chat_settings(m.chat.id).get("mute_seconds", 60))))
        bot.restrict_chat_member(m.chat.id, tid, until_date=int(time.time())+seconds, permissions=types.ChatPermissions(can_send_messages=False))
        reply_safe(m, f"🔇 کاربر برای {seconds} ثانیه سکوت شد."); log_action(m.chat.id, f"Mute user {tid} for {seconds}s")
    except Exception: log.exception("Mute failed."); reply_safe(m, "⚠️ سکوت ناموفق بود؛ دسترسی محدودکردن اعضا را بررسی کن.")
@bot.message_handler(commands=["unmute"])
def unmute_command(m):
    tid = target_user_id(m)
    if not ensure_manageable(m, tid): return
    try:
        bot.restrict_chat_member(m.chat.id, tid, permissions=types.ChatPermissions(can_send_messages=True, can_send_audios=True, can_send_documents=True, can_send_photos=True, can_send_videos=True, can_send_video_notes=True, can_send_voice_notes=True, can_send_polls=True, can_send_other_messages=True, can_add_web_page_previews=True))
        reply_safe(m, "🔊 سکوت کاربر برداشته شد.")
    except Exception: log.exception("Unmute failed."); reply_safe(m, "⚠️ رفع سکوت ناموفق بود؛ نسخه کتابخانه و مجوزها را بررسی کن.")
@bot.message_handler(commands=["ban"])
def ban_command(m):
    tid = target_user_id(m)
    if not ensure_manageable(m, tid): return
    try: bot.ban_chat_member(m.chat.id, tid); reply_safe(m, "⛔ کاربر مسدود شد."); log_action(m.chat.id, f"Ban user {tid}")
    except Exception: log.exception("Ban failed."); reply_safe(m, "⚠️ مسدودسازی ناموفق بود.")
@bot.message_handler(commands=["unban"])
def unban_command(m):
    if not is_group(m) or not is_admin(m.chat.id, m.from_user.id): reply_safe(m, "⛔ فقط مدیر گروه."); return
    p = (m.text or "").split()
    if len(p)<2 or not p[1].lstrip("-").isdigit(): reply_safe(m, "استفاده: /unban آیدی_عددی"); return
    try: bot.unban_chat_member(m.chat.id, int(p[1])); reply_safe(m, "✅ مسدودیت برداشته شد.")
    except Exception: log.exception("Unban failed."); reply_safe(m, "⚠️ رفع مسدودیت ناموفق بود.")
@bot.message_handler(commands=["kick"])
def kick_command(m):
    tid = target_user_id(m)
    if not ensure_manageable(m, tid): return
    try: bot.ban_chat_member(m.chat.id, tid); bot.unban_chat_member(m.chat.id, tid); reply_safe(m, "👢 کاربر از گروه اخراج شد."); log_action(m.chat.id, f"Kick user {tid}")
    except Exception: log.exception("Kick failed."); reply_safe(m, "⚠️ اخراج ناموفق بود.")
@bot.message_handler(commands=["purge"])
def purge_command(m):
    if not is_group(m) or not is_admin(m.chat.id, m.from_user.id): reply_safe(m, "⛔ فقط مدیر گروه."); return
    if not m.reply_to_message: reply_safe(m, "روی اولین پیامی که می‌خواهی پاک شود ریپلای کن و /purge بزن."); return
    start_id, end_id = m.reply_to_message.message_id, m.message_id - 1
    if end_id - start_id > 100: start_id = end_id - 100
    deleted = 0
    for mid in range(start_id, end_id + 1):
        try: bot.delete_message(m.chat.id, mid); deleted += 1
        except Exception: pass
    # Send a new status message instead of replying to a message that may have been deleted.
    try: bot.send_message(m.chat.id, f"🧹 پاک‌سازی تمام شد. پیام‌های پاک‌شده: {deleted}")
    except Exception: log.exception("Could not send purge report.")

def set_setting_command(m, setting, value):
    if not is_group(m) or not is_admin(m.chat.id, m.from_user.id): reply_safe(m, "⛔ این دستور را مدیر گروه باید داخل گروه اجرا کند."); return
    chat_settings(m.chat.id)[setting] = value; save_data(); reply_safe(m, "✅ تنظیم ذخیره شد.")
@bot.message_handler(commands=["antilink_on"])
def antilink_on(m): set_setting_command(m, "anti_link", True)
@bot.message_handler(commands=["antilink_off"])
def antilink_off(m): set_setting_command(m, "anti_link", False)
@bot.message_handler(commands=["antispam_on"])
def antispam_on(m): set_setting_command(m, "anti_spam", True)
@bot.message_handler(commands=["antispam_off"])
def antispam_off(m): set_setting_command(m, "anti_spam", False)
@bot.message_handler(commands=["welcome_on"])
def welcome_on(m): set_setting_command(m, "welcome_enabled", True)
@bot.message_handler(commands=["welcome_off"])
def welcome_off(m): set_setting_command(m, "welcome_enabled", False)
@bot.message_handler(commands=["addbadword"])
def addbadword_command(m):
    if not is_group(m) or not is_admin(m.chat.id, m.from_user.id): reply_safe(m, "⛔ فقط مدیر گروه، داخل گروه."); return
    word = (m.text or "").partition(" ")[2].strip()[:100]
    if not word: reply_safe(m, "استفاده: /addbadword کلمه"); return
    with data_lock:
        words = data["badwords"].setdefault(str(m.chat.id), [])
        if word.casefold() not in [str(x).casefold() for x in words]: words.append(word)
    save_data(); reply_safe(m, "✅ کلمه به فیلتر اضافه شد.")
@bot.message_handler(commands=["delbadword"])
def delbadword_command(m):
    if not is_group(m) or not is_admin(m.chat.id, m.from_user.id): reply_safe(m, "⛔ فقط مدیر گروه، داخل گروه."); return
    word = (m.text or "").partition(" ")[2].strip()
    if not word: reply_safe(m, "استفاده: /delbadword کلمه"); return
    with data_lock:
        key = str(m.chat.id); data["badwords"][key] = [x for x in data["badwords"].get(key, []) if str(x).casefold() != word.casefold()]
    save_data(); reply_safe(m, "✅ کلمه از فیلتر حذف شد.")
@bot.message_handler(commands=["badwords"])
def badwords_command(m):
    if not is_group(m) or not is_admin(m.chat.id, m.from_user.id): reply_safe(m, "⛔ فقط مدیر گروه، داخل گروه."); return
    words = get_badwords(m.chat.id); reply_safe(m, "📃 کلمات فیلتر:\n" + ("\n".join(words) if words else "هنوز کلمه‌ای ثبت نشده."))

@bot.message_handler(content_types=["new_chat_members"])
def welcome_new_members(m):
    if not chat_settings(m.chat.id)["welcome_enabled"]: return
    text = str(chat_settings(m.chat.id).get("welcome_text") or DEFAULT_SETTINGS["welcome_text"])
    for user in m.new_chat_members:
        if user.is_bot: continue
        try: bot.send_message(m.chat.id, text.replace("{name}", user.first_name or "دوست عزیز"))
        except Exception: log.exception("Welcome message failed.")

def ask_ai_in_group(m, text_value):
    if not text_value: return False
    mentioned = bool(bot_username and re.search(r"@"+re.escape(bot_username)+r"\b", text_value, re.I))
    replied = getattr(m, "reply_to_message", None)
    replied_to_bot = bool(replied and getattr(replied, "from_user", None) and replied.from_user.is_bot and (replied.from_user.username or "").lower() == (bot_username or "").lower())
    if not (mentioned or replied_to_bot): return False
    cleaned = re.sub(r"@"+re.escape(bot_username)+r"\b", "", text_value, flags=re.I).strip() if bot_username else text_value.strip()
    if not cleaned and replied: cleaned = (replied.text or replied.caption or "").strip()
    if cleaned: send_ai_reply(m, cleaned)
    else: reply_safe(m, "سؤالت رو هم بنویس تا جواب بدم.")
    return True

@bot.message_handler(func=lambda m: bool(m.text) and not (m.text or "").startswith("/") and m.chat.type == "private", content_types=["text"])
def private_ai_handler(m):
    if m.from_user and not m.from_user.is_bot: send_ai_reply(m, m.text.strip())

GROUP_CONTENT = ["text", "photo", "video", "document", "audio", "voice", "animation", "sticker", "video_note", "contact", "location", "venue", "poll"]
@bot.message_handler(func=lambda m: True, content_types=GROUP_CONTENT)
def moderate_message(m):
    if not m.from_user or m.from_user.is_bot or not is_group(m): return
    text_value = (m.text or m.caption or "").strip(); s = chat_settings(m.chat.id)
    admin = is_admin(m.chat.id, m.from_user.id)
    if not admin:
        if s["anti_link"] and message_has_link(m, text_value):
            try: bot.delete_message(m.chat.id, m.message_id); log_action(m.chat.id, f"Link removed from {m.from_user.id}"); bot.send_message(m.chat.id, "🔗 ارسال لینک در گروه مجاز نیست.")
            except Exception: log.exception("Anti-link action failed; check bot delete-message permission.")
            return
        if s["badword_filter"] and text_value:
            words = get_badwords(m.chat.id)
            if any(w and w.casefold() in text_value.casefold() for w in words):
                try: bot.delete_message(m.chat.id, m.message_id); log_action(m.chat.id, f"Bad word removed from {m.from_user.id}")
                except Exception: log.exception("Bad-word delete failed.")
                return
        if s["anti_duplicate"] and text_value:
            key = (m.chat.id, m.from_user.id); normalized = re.sub(r"\s+", " ", text_value).casefold(); history = duplicate_history[key]
            if normalized and normalized in history:
                try: bot.delete_message(m.chat.id, m.message_id); log_action(m.chat.id, f"Duplicate message removed from {m.from_user.id}")
                except Exception: log.exception("Duplicate-message delete failed.")
                return
            history.append(normalized)
        if s["anti_spam"]:
            now = time.time(); key = (m.chat.id, m.from_user.id); history = spam_history[key]; history.append(now)
            window = max(1, min(60, int(s.get("spam_window", 8))))
            while history and now-history[0] > window: history.popleft()
            maximum = max(2, min(30, int(s.get("max_messages", 6))))
            if len(history) > maximum:
                try:
                    bot.delete_message(m.chat.id, m.message_id)
                    seconds = max(30, min(86400, int(s.get("mute_seconds", 60))))
                    bot.restrict_chat_member(m.chat.id, m.from_user.id, until_date=int(time.time())+seconds, permissions=types.ChatPermissions(can_send_messages=False))
                    bot.send_message(m.chat.id, f"🚫 به دلیل ارسال پیام‌های زیاد، کاربر برای {seconds} ثانیه سکوت شد.")
                    log_action(m.chat.id, f"Anti-spam mute {m.from_user.id}")
                except Exception: log.exception("Anti-spam action failed; check bot permissions.")
                finally: history.clear()
                return
    ask_ai_in_group(m, text_value)

def start_flask(): app.run(host="0.0.0.0", port=PORT, use_reloader=False)
def run_bot_forever():
    global bot_username
    delay = 3
    while True:
        try:
            log.info("Starting %s v%s", BOT_NAME, VERSION)
            me = bot.get_me(); bot_username = me.username
            log.info("Telegram connected as @%s", bot_username or "unknown")
            bot.remove_webhook(); log.info("Webhook cleared; polling will start.")
            bot.infinity_polling(timeout=30, long_polling_timeout=25, skip_pending=False)
            delay = 3
        except KeyboardInterrupt: log.info("Bot stopped."); break
        except Exception:
            log.exception("Polling stopped; reconnecting in %s seconds.", delay); time.sleep(delay); delay = min(delay*2, 60)

if __name__ == "__main__":
    threading.Thread(target=start_flask, daemon=True).start()
    run_bot_forever()
