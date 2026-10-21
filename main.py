# -*- coding: utf-8 -*-
"""
MASIH GUARD v6.0 FINAL
Python 3.11+
Required environment variables:
  BOT_TOKEN (or TELEGRAM_BOT_TOKEN)
Optional:
  AI_API_KEY, AI_BASE_URL, AI_MODEL, OWNER_ID, PORT, DATA_FILE
"""

import os
import re
import json
import time
import logging
import threading
from collections import defaultdict, deque
from datetime import datetime, timezone

import requests
import telebot
from telebot import types
from flask import Flask, jsonify

BOT_NAME = "مسیح گارد"
VERSION = "6.0"

BOT_TOKEN = (os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
AI_API_KEY = os.getenv("AI_API_KEY", "").strip()
AI_BASE_URL = (os.getenv("AI_BASE_URL") or "https://openrouter.ai/api/v1").strip().rstrip("/")
AI_MODEL = (os.getenv("AI_MODEL") or "openrouter/free").strip()
DATA_FILE = os.getenv("DATA_FILE", "masih_guard_data.json")

try:
    OWNER_ID = int(os.getenv("OWNER_ID", "8620924698").strip())
except (TypeError, ValueError):
    OWNER_ID = 8620924698

try:
    PORT = int(os.getenv("PORT", "8080"))
except (TypeError, ValueError):
    PORT = 8080

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s | %(levelname)s | %(message)s"
)
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
ai_locks = defaultdict(threading.Lock)
bot_username = None

DEFAULT_SETTINGS = {
    "anti_link": True,
    "anti_spam": True,
    "anti_duplicate": True,
    "badword_filter": True,
    "welcome_enabled": True,
    "max_messages": 6,
    "spam_window": 8,
    "max_warnings": 3,
    "mute_seconds": 60,
    "welcome_text": "👋 خوش اومدی {name} عزیز!"
}


def default_data():
    return {"badwords": {}, "warnings": {}, "settings": {}, "welcome": {}, "logs": []}


def load_data():
    try:
        if os.path.isfile(DATA_FILE):
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            if isinstance(saved, dict):
                base = default_data()
                for key, value in base.items():
                    if isinstance(saved.get(key), type(value)):
                        base[key] = saved[key]
                return base
    except Exception:
        log.exception("Could not load data file; starting with defaults.")
    return default_data()


data = load_data()


def save_data():
    with data_lock:
        try:
            folder = os.path.dirname(os.path.abspath(DATA_FILE))
            os.makedirs(folder, exist_ok=True)
            temp_path = DATA_FILE + ".tmp"
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(temp_path, DATA_FILE)
        except Exception:
            log.exception("Could not save data file.")


def chat_settings(chat_id):
    with data_lock:
        settings = data["settings"].setdefault(str(chat_id), {})
        for key, value in DEFAULT_SETTINGS.items():
            settings.setdefault(key, value)
        return settings


def log_action(chat_id, text):
    with data_lock:
        data["logs"].append({
            "chat": str(chat_id),
            "time": datetime.now(timezone.utc).isoformat(),
            "text": str(text)[:300]
        })
        data["logs"] = data["logs"][-300:]
    save_data()


def reply_safe(message, text, **kwargs):
    try:
        return bot.reply_to(message, str(text)[:4000], **kwargs)
    except Exception:
        log.exception("Could not reply to Telegram message.")
        return None


def send_chunks(chat_id, text, reply_to=None):
    text = str(text or "").strip() or "پاسخی دریافت نشد."
    chunks = [text[i:i + 3900] for i in range(0, len(text), 3900)]
    for chunk in chunks:
        try:
            bot.send_message(chat_id, chunk, reply_to_message_id=reply_to)
        except Exception:
            log.exception("Could not send message chunk.")
            break


def is_owner(user_id):
    return bool(user_id and user_id == OWNER_ID)


def is_admin(chat_id, user_id):
    if is_owner(user_id):
        return True
    try:
        member = bot.get_chat_member(chat_id, user_id)
        return member.status in ("administrator", "creator")
    except Exception:
        return False


def is_group(message):
    return message.chat.type in ("group", "supergroup")


def get_badwords(chat_id):
    with data_lock:
        words = data["badwords"].get(str(chat_id), [])
        return list(words) if isinstance(words, list) else []


def is_link(text):
    if not text:
        return False
    value = str(text)
    patterns = [
        r"(?i)\b(?:https?://|ftp://|www\.)[^\s<>]+",
        r"(?i)(?<![\w@])(?:t\.me|telegram\.me|telegram\.dog)/[^\s<>]*",
        r"(?i)(?<![\w@])(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+(?:com|net|org|io|co|me|info|biz|xyz|app|dev|site|online|ir|de|uk|ru|tr)(?::\d+)?(?:[/?:#][^\s<>]*)?"
    ]
    return any(re.search(p, value) for p in patterns)


def message_has_link(message, text_value):
    if is_link(text_value):
        return True
    for attr in ("entities", "caption_entities"):
        for entity in (getattr(message, attr, None) or []):
            if getattr(entity, "type", "") in ("url", "text_link"):
                return True
    return False


def extract_target(message):
    replied = getattr(message, "reply_to_message", None)
    if replied and getattr(replied, "from_user", None):
        return replied.from_user
    parts = (message.text or "").split()
    if len(parts) > 1 and parts[1].lstrip("-").isdigit():
        try:
            return bot.get_chat_member(message.chat.id, int(parts[1])).user
        except Exception:
            return None
    return None


def target_user_id(message):
    user = extract_target(message)
    return user.id if user else None


def ensure_manageable(message, target_id):
    if not is_group(message):
        reply_safe(message, "این دستور را داخل گروه اجرا کن.")
        return False
    if not is_admin(message.chat.id, message.from_user.id):
        reply_safe(message, "⛔ این دستور مخصوص مدیران گروه است.")
        return False
    if not target_id:
        reply_safe(message, "⚠️ روی پیام کاربر ریپلای کن یا آیدی عددی او را بنویس.")
        return False
    if target_id in (message.from_user.id, OWNER_ID):
        reply_safe(message, "⛔ این کاربر را نمی‌توانی هدف قرار بدهی.")
        return False
    try:
        member = bot.get_chat_member(message.chat.id, target_id)
        if member.status in ("administrator", "creator"):
            reply_safe(message, "⛔ این دستور روی مدیران گروه اجرا نمی‌شود.")
            return False
    except Exception:
        pass
    return True


def add_warning(chat_id, user_id):
    key = f"{chat_id}:{user_id}"
    with data_lock:
        data["warnings"][key] = int(data["warnings"].get(key, 0)) + 1
        count = data["warnings"][key]
    save_data()
    return count


def warning_count(chat_id, user_id):
    with data_lock:
        return int(data["warnings"].get(f"{chat_id}:{user_id}", 0))


# ---------------- HEALTH ENDPOINTS ----------------

@app.get("/")
def home():
    return jsonify({"name": BOT_NAME, "version": VERSION, "status": "running"})


@app.get("/health")
def health():
    return jsonify({"status": "ok", "bot": BOT_NAME, "version": VERSION})


# ---------------- AI ----------------

def ai_answer(question, chat_title=""):
    if not AI_API_KEY:
        return "⚠️ هوش مصنوعی هنوز تنظیم نشده؛ مدیر ربات باید AI_API_KEY را در تنظیمات میزبانی وارد کند."
    url = AI_BASE_URL + "/chat/completions"
    payload = {
        "model": AI_MODEL,
        "messages": [
            {"role": "system", "content": (
                "تو دستیار فارسی‌زبان ربات مسیح گارد هستی. "
                "به فارسی روان، دقیق، محترمانه و مفید پاسخ بده. "
                "اگر مطمئن نیستی، صادقانه بگو. پاسخ را بی‌جهت طولانی نکن."
            )},
            {"role": "user", "content": f"گفتگو: {chat_title or 'خصوصی'}\nپرسش: {str(question)[:3500]}"}
        ],
        "temperature": 0.7,
        "max_tokens": 900
    }
    try:
        response = requests.post(
            url,
            headers={
                "Authorization": "Bearer " + AI_API_KEY,
                "Content-Type": "application/json",
                "HTTP-Referer": "https://github.com/masihollah00/masih-guard",
                "X-OpenRouter-Title": "Masih Guard"
            },
            json=payload,
            timeout=(10, 45)
        )
        if not response.ok:
            log.error("AI API HTTP %s: %s", response.status_code, response.text[:500])
            if response.status_code in (401, 403):
                return "⚠️ کلید API یا دسترسی سرویس رد شد؛ تنظیم AI_API_KEY را بررسی کن."
            if response.status_code == 429:
                return "⚠️ محدودیت درخواست هوش مصنوعی رسیده؛ کمی بعد دوباره امتحان کن."
            if response.status_code == 402:
                return "⚠️ سرویس هوش مصنوعی درخواست را به‌دلیل اعتبار یا پرداخت نپذیرفت."
            if response.status_code in (400, 404):
                return "⚠️ مدل هوش مصنوعی در دسترس نیست؛ مقدار AI_MODEL را بررسی کن."
            return f"⚠️ سرویس هوش مصنوعی خطای HTTP {response.status_code} داد."
        result = response.json()
        choices = result.get("choices") or []
        if not choices:
            return "⚠️ سرویس هوش مصنوعی پاسخ قابل استفاده‌ای نداد."
        content = (choices[0].get("message") or {}).get("content")
        if isinstance(content, list):
            content = "\n".join(str(x.get("text", "")) for x in content if isinstance(x, dict))
        return content.strip() if isinstance(content, str) and content.strip() else "⚠️ پاسخ هوش مصنوعی خالی بود."
    except requests.Timeout:
        log.warning("AI request timed out.")
        return "⚠️ پاسخ هوش مصنوعی طول کشید؛ دوباره امتحان کن."
    except requests.RequestException:
        log.exception("AI request failed.")
        return "⚠️ اتصال به سرویس هوش مصنوعی برقرار نشد."
    except Exception:
        log.exception("Unexpected AI error.")
        return "⚠️ خطای غیرمنتظره در بخش هوش مصنوعی رخ داد."


def send_ai_reply(message, question):
    status = reply_safe(message, "🤖 دارم فکر می‌کنم...")
    answer = ai_answer(question, getattr(message.chat, "title", "") or "")
    if status:
        try:
            bot.edit_message_text(str(answer)[:4000], message.chat.id, status.message_id)
            return
        except Exception:
            log.exception("Could not edit AI status message.")
    send_chunks(message.chat.id, answer, reply_to=message.message_id)


# ---------------- BASIC COMMANDS ----------------

@bot.message_handler(commands=["start", "help"])
def start_command(message):
    reply_safe(message,
        f"🛡 {BOT_NAME} v{VERSION}\n\n"
        "ربات مدیریت گروه و دستیار فارسی فعال است.\n\n"
        "🤖 هوش مصنوعی:\n"
        "• خصوصی: پیام عادی بفرست.\n"
        "• گروه: /ai سؤال\n"
        "• گروه: منشن ربات یا ریپلای به پیامش\n\n"
        "📌 عمومی: /start /help /ping /id /rules /ai\n"
        "⚙️ مدیریت: /panel /stats\n"
        "🔗 ضدلینک: /antilink_on /antilink_off\n"
        "🚫 ضداسپم: /antispam_on /antispam_off\n"
        "👋 خوشامد: /welcome_on /welcome_off\n"
        "🤬 فیلتر: /addbadword کلمه /delbadword کلمه /badwords\n"
        "👮 مدیریت: /warn /warnings /unwarn /mute /unmute /ban /unban آیدی /kick /purge\n\n"
        "برای دستورات مدیریتی، ربات باید در گروه دسترسی ادمین مناسب داشته باشد."
    )


@bot.message_handler(commands=["ping"])
def ping_command(message):
    reply_safe(message, f"✅ {BOT_NAME} آنلاین است | نسخه {VERSION}")


@bot.message_handler(commands=["id"])
def id_command(message):
    reply_safe(message, f"👤 آیدی شما: {message.from_user.id}\n💬 آیدی گفتگو: {message.chat.id}")


@bot.message_handler(commands=["rules"])
def rules_command(message):
    reply_safe(message, "📘 قوانین: احترام به اعضا، پرهیز از اسپم و رعایت قوانین گروه. مدیران می‌توانند قوانین گروه را ویرایش کنند.")


@bot.message_handler(commands=["ai"])
def ai_command(message):
    question = (message.text or "").partition(" ")[2].strip()
    if not question and getattr(message, "reply_to_message", None):
        replied = message.reply_to_message
        question = (replied.text or replied.caption or "").strip()
    if not question:
        reply_safe(message, "مثال: /ai درباره فضا توضیح بده")
        return
    send_ai_reply(message, question)


# ---------------- PANEL ----------------

def build_panel_markup(chat_id):
    settings = chat_settings(chat_id)
    markup = types.InlineKeyboardMarkup(row_width=2)
    labels = [
        ("anti_link", "🔗 ضدلینک"),
        ("anti_spam", "🚫 ضداسپم"),
        ("anti_duplicate", "🔁 ضدتکرار"),
        ("badword_filter", "🤬 فیلتر کلمات"),
        ("welcome_enabled", "👋 خوشامد")
    ]
    for key, label in labels:
        state = "روشن" if settings[key] else "خاموش"
        markup.add(types.InlineKeyboardButton(f"{label}: {state}", callback_data=f"toggle:{key}"))
    markup.add(types.InlineKeyboardButton("📊 آمار", callback_data="panel:stats"))
    return markup


@bot.message_handler(commands=["panel"])
def panel_command(message):
    if not is_group(message):
        reply_safe(message, "⚙️ پنل را داخل گروه باز کن.")
        return
    if not is_admin(message.chat.id, message.from_user.id):
        reply_safe(message, "⛔ پنل فقط برای مدیران گروه است.")
        return
    bot.send_message(message.chat.id, f"⚙️ پنل مدیریت {BOT_NAME}\nبرای تغییر وضعیت، دکمه‌ها را بزن.", reply_markup=build_panel_markup(message.chat.id))


@bot.callback_query_handler(func=lambda call: bool(call.data and (call.data.startswith("toggle:") or call.data == "panel:stats")))
def panel_callback(call):
    try:
        if not call.message:
            bot.answer_callback_query(call.id, "پیام پنل پیدا نشد.")
            return
        chat_id = call.message.chat.id
        if not is_admin(chat_id, call.from_user.id):
            bot.answer_callback_query(call.id, "فقط مدیر گروه می‌تواند تنظیمات را تغییر دهد.", show_alert=True)
            return
        if call.data == "panel:stats":
            with data_lock:
                count = sum(1 for item in data["logs"] if item.get("chat") == str(chat_id))
            bot.answer_callback_query(call.id, f"ثبت‌های ذخیره‌شده: {count}", show_alert=True)
            return
        key = call.data.split(":", 1)[1]
        if key not in ("anti_link", "anti_spam", "anti_duplicate", "badword_filter", "welcome_enabled"):
            bot.answer_callback_query(call.id, "تنظیم نامعتبر است.")
            return
        settings = chat_settings(chat_id)
        settings[key] = not bool(settings[key])
        save_data()
        bot.answer_callback_query(call.id, "تنظیم ذخیره شد.")
        bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=build_panel_markup(chat_id))
    except Exception:
        log.exception("Panel callback failed.")
        try:
            bot.answer_callback_query(call.id, "خطا در تغییر تنظیمات.")
        except Exception:
            pass


@bot.message_handler(commands=["stats"])
def stats_command(message):
    if not is_group(message) or not is_admin(message.chat.id, message.from_user.id):
        reply_safe(message, "⛔ این دستور فقط برای مدیران گروه است.")
        return
    with data_lock:
        logs = [x for x in data["logs"] if x.get("chat") == str(message.chat.id)]
        warn_count = sum(1 for key, value in data["warnings"].items() if key.startswith(str(message.chat.id) + ":") and int(value or 0) > 0)
    settings = chat_settings(message.chat.id)
    enabled = [label for key, label in [
        ("anti_link", "ضدلینک"), ("anti_spam", "ضداسپم"),
        ("anti_duplicate", "ضدتکرار"), ("badword_filter", "فیلتر کلمات"),
        ("welcome_enabled", "خوشامد")
    ] if settings[key]]
    reply_safe(message, "📊 آمار مسیح گارد\n"
        f"گزارش‌های ذخیره‌شده: {len(logs)}\n"
        f"کاربران دارای اخطار: {warn_count}\n"
        f"قابلیت‌های روشن: {', '.join(enabled) if enabled else 'هیچ‌کدام'}")


# ---------------- MODERATION COMMANDS ----------------

@bot.message_handler(commands=["warn"])
def warn_command(message):
    target_id = target_user_id(message)
    if not ensure_manageable(message, target_id):
        return
    count = add_warning(message.chat.id, target_id)
    maximum = int(chat_settings(message.chat.id)["max_warnings"])
    reply_safe(message, f"⚠️ اخطار ثبت شد: {count}/{maximum}")
    if count >= maximum:
        try:
            bot.ban_chat_member(message.chat.id, target_id)
            reply_safe(message, "⛔ سقف اخطارها رسید؛ کاربر مسدود شد.")
            log_action(message.chat.id, f"Auto-ban user {target_id}")
        except Exception:
            log.exception("Auto-ban failed.")
            reply_safe(message, "⚠️ مسدودسازی خودکار ناموفق بود؛ دسترسی ادمین ربات را بررسی کن.")


@bot.message_handler(commands=["warnings"])
def warnings_command(message):
    target_id = target_user_id(message) or message.from_user.id
    reply_safe(message, f"⚠️ تعداد اخطارها: {warning_count(message.chat.id, target_id)}")


@bot.message_handler(commands=["unwarn"])
def unwarn_command(message):
    target_id = target_user_id(message)
    if not ensure_manageable(message, target_id):
        return
    with data_lock:
        data["warnings"][f"{message.chat.id}:{target_id}"] = 0
    save_data()
    reply_safe(message, "✅ اخطارهای کاربر پاک شد.")


@bot.message_handler(commands=["mute"])
def mute_command(message):
    target_id = target_user_id(message)
    if not ensure_manageable(message, target_id):
        return
    try:
        bot.restrict_chat_member(message.chat.id, target_id,
            until_date=int(time.time()) + 3600,
            permissions=types.ChatPermissions(can_send_messages=False))
        reply_safe(message, "🔇 کاربر برای یک ساعت سکوت شد.")
        log_action(message.chat.id, f"Mute user {target_id}")
    except Exception:
        log.exception("Mute failed.")
        reply_safe(message, "⚠️ سکوت ناموفق بود؛ دسترسی محدودکردن اعضا را بررسی کن.")


@bot.message_handler(commands=["unmute"])
def unmute_command(message):
    target_id = target_user_id(message)
    if not ensure_manageable(message, target_id):
        return
    try:
        bot.restrict_chat_member(message.chat.id, target_id,
            permissions=types.ChatPermissions(
                can_send_messages=True, can_send_audios=True, can_send_documents=True,
                can_send_photos=True, can_send_videos=True, can_send_video_notes=True,
                can_send_voice_notes=True, can_send_polls=True,
                can_send_other_messages=True, can_add_web_page_previews=True))
        reply_safe(message, "🔊 سکوت کاربر برداشته شد.")
    except Exception:
        log.exception("Unmute failed.")
        reply_safe(message, "⚠️ رفع سکوت ناموفق بود.")


@bot.message_handler(commands=["ban"])
def ban_command(message):
    target_id = target_user_id(message)
    if not ensure_manageable(message, target_id):
        return
    try:
        bot.ban_chat_member(message.chat.id, target_id)
        reply_safe(message, "⛔ کاربر مسدود شد.")
        log_action(message.chat.id, f"Ban user {target_id}")
    except Exception:
        log.exception("Ban failed.")
        reply_safe(message, "⚠️ مسدودسازی ناموفق بود.")


@bot.message_handler(commands=["unban"])
def unban_command(message):
    if not is_group(message) or not is_admin(message.chat.id, message.from_user.id):
        reply_safe(message, "⛔ فقط مدیر گروه.")
        return
    parts = (message.text or "").split()
    if len(parts) < 2 or not parts[1].lstrip("-").isdigit():
        reply_safe(message, "استفاده: /unban آیدی_عددی")
        return
    try:
        bot.unban_chat_member(message.chat.id, int(parts[1]))
        reply_safe(message, "✅ مسدودیت برداشته شد.")
    except Exception:
        log.exception("Unban failed.")
        reply_safe(message, "⚠️ رفع مسدودیت ناموفق بود.")


@bot.message_handler(commands=["kick"])
def kick_command(message):
    target_id = target_user_id(message)
    if not ensure_manageable(message, target_id):
        return
    try:
        bot.ban_chat_member(message.chat.id, target_id)
        bot.unban_chat_member(message.chat.id, target_id)
        reply_safe(message, "👢 کاربر از گروه اخراج شد.")
        log_action(message.chat.id, f"Kick user {target_id}")
    except Exception:
        log.exception("Kick failed.")
        reply_safe(message, "⚠️ اخراج ناموفق بود.")


@bot.message_handler(commands=["purge"])
def purge_command(message):
    if not is_group(message) or not is_admin(message.chat.id, message.from_user.id):
        reply_safe(message, "⛔ فقط مدیر گروه.")
        return
    if not message.reply_to_message:
        reply_safe(message, "روی اولین پیامی که می‌خواهی پاک شود ریپلای کن و /purge بزن.")
        return
    start_id = message.reply_to_message.message_id
    end_id = message.message_id
    if end_id - start_id > 100:
        start_id = end_id - 100
    deleted = 0
    for msg_id in range(start_id, end_id + 1):
        try:
            bot.delete_message(message.chat.id, msg_id)
            deleted += 1
        except Exception:
            pass
    # The command itself may have been deleted; report only if possible.
    reply_safe(message, f"🧹 پاک‌سازی تمام شد. پیام‌های پاک‌شده: {deleted}")


def set_setting_command(message, setting, value):
    if not is_group(message) or not is_admin(message.chat.id, message.from_user.id):
        reply_safe(message, "⛔ این دستور را مدیر گروه باید داخل گروه اجرا کند.")
        return
    chat_settings(message.chat.id)[setting] = value
    save_data()
    reply_safe(message, "✅ تنظیم ذخیره شد.")


@bot.message_handler(commands=["antilink_on"])
def antilink_on(message):
    set_setting_command(message, "anti_link", True)


@bot.message_handler(commands=["antilink_off"])
def antilink_off(message):
    set_setting_command(message, "anti_link", False)


@bot.message_handler(commands=["antispam_on"])
def antispam_on(message):
    set_setting_command(message, "anti_spam", True)


@bot.message_handler(commands=["antispam_off"])
def antispam_off(message):
    set_setting_command(message, "anti_spam", False)


@bot.message_handler(commands=["welcome_on"])
def welcome_on(message):
    set_setting_command(message, "welcome_enabled", True)


@bot.message_handler(commands=["welcome_off"])
def welcome_off(message):
    set_setting_command(message, "welcome_enabled", False)


@bot.message_handler(commands=["addbadword"])
def addbadword_command(message):
    if not is_group(message) or not is_admin(message.chat.id, message.from_user.id):
        reply_safe(message, "⛔ فقط مدیر گروه، داخل گروه.")
        return
    word = (message.text or "").partition(" ")[2].strip()[:100]
    if not word:
        reply_safe(message, "استفاده: /addbadword کلمه")
        return
    with data_lock:
        words = data["badwords"].setdefault(str(message.chat.id), [])
        if word.casefold() not in [str(item).casefold() for item in words]:
            words.append(word)
    save_data()
    reply_safe(message, "✅ کلمه به فیلتر اضافه شد.")


@bot.message_handler(commands=["delbadword"])
def delbadword_command(message):
    if not is_group(message) or not is_admin(message.chat.id, message.from_user.id):
        reply_safe(message, "⛔ فقط مدیر گروه، داخل گروه.")
        return
    word = (message.text or "").partition(" ")[2].strip()
    if not word:
        reply_safe(message, "استفاده: /delbadword کلمه")
        return
    with data_lock:
        key = str(message.chat.id)
        data["badwords"][key] = [x for x in data["badwords"].get(key, []) if str(x).casefold() != word.casefold()]
    save_data()
    reply_safe(message, "✅ کلمه از فیلتر حذف شد.")


@bot.message_handler(commands=["badwords"])
def badwords_command(message):
    if not is_group(message) or not is_admin(message.chat.id, message.from_user.id):
        reply_safe(message, "⛔ فقط مدیر گروه، داخل گروه.")
        return
    words = get_badwords(message.chat.id)
    reply_safe(message, "📃 کلمات فیلتر:\n" + ("\n".join(words) if words else "هنوز کلمه‌ای ثبت نشده."))


# ---------------- WELCOME ----------------

@bot.message_handler(content_types=["new_chat_members"])
def welcome_new_members(message):
    if not chat_settings(message.chat.id)["welcome_enabled"]:
        return
    for user in message.new_chat_members:
        if user.is_bot:
            continue
        text = str(chat_settings(message.chat.id).get("welcome_text") or DEFAULT_SETTINGS["welcome_text"])
        try:
            bot.send_message(message.chat.id, text.replace("{name}", user.first_name or "دوست عزیز"))
        except Exception:
            log.exception("Welcome message failed.")


# ---------------- AI + GROUP MODERATION ----------------

def ask_ai_in_group(message, text_value):
    if not text_value:
        return False
    mentioned = bool(bot_username and re.search(r"@" + re.escape(bot_username) + r"\b", text_value, re.I))
    replied = getattr(message, "reply_to_message", None)
    replied_to_bot = bool(replied and getattr(replied, "from_user", None)
                          and replied.from_user.is_bot
                          and (replied.from_user.username or "").lower() == (bot_username or "").lower())
    if not (mentioned or replied_to_bot):
        return False
    cleaned = re.sub(r"@" + re.escape(bot_username) + r"\b", "", text_value, flags=re.I).strip() if bot_username else text_value.strip()
    if not cleaned and replied:
        cleaned = (replied.text or replied.caption or "").strip()
    if cleaned:
        send_ai_reply(message, cleaned)
    else:
        reply_safe(message, "سؤالت رو هم بنویس تا جواب بدم.")
    return True


@bot.message_handler(
    func=lambda m: bool(m.text) and not (m.text or "").startswith("/") and m.chat.type == "private",
    content_types=["text"]
)
def private_ai_handler(message):
    if message.from_user and not message.from_user.is_bot:
        send_ai_reply(message, message.text.strip())


@bot.message_handler(
    func=lambda m: True,
    content_types=["text", "photo", "video", "document", "audio", "voice",
                   "animation", "sticker", "video_note", "contact", "location", "venue", "poll"]
)
def moderate_message(message):
    if not message.from_user or message.from_user.is_bot or not is_group(message):
        return
    text_value = (message.text or message.caption or "").strip()
    settings = chat_settings(message.chat.id)
    admin = is_admin(message.chat.id, message.from_user.id)

    # Moderation checks intentionally skip admins and the configured owner.
    if not admin:
        if settings["anti_link"] and message_has_link(message, text_value):
            try:
                bot.delete_message(message.chat.id, message.message_id)
                log_action(message.chat.id, f"Link removed from {message.from_user.id}")
                bot.send_message(message.chat.id, "🔗 ارسال لینک در گروه مجاز نیست.")
            except Exception:
                log.exception("Anti-link action failed; check bot delete-message permission.")
            return

        if settings["badword_filter"] and text_value:
            words = get_badwords(message.chat.id)
            if any(word and word.casefold() in text_value.casefold() for word in words):
                try:
                    bot.delete_message(message.chat.id, message.message_id)
                    log_action(message.chat.id, f"Bad word removed from {message.from_user.id}")
                except Exception:
                    log.exception("Bad-word delete failed.")
                return

        if settings["anti_duplicate"] and text_value:
            key = (message.chat.id, message.from_user.id)
            normalized = re.sub(r"\s+", " ", text_value).casefold()
            history = duplicate_history[key]
            if normalized and normalized in history:
                try:
                    bot.delete_message(message.chat.id, message.message_id)
                    log_action(message.chat.id, f"Duplicate message removed from {message.from_user.id}")
                except Exception:
                    log.exception("Duplicate-message delete failed.")
                return
            history.append(normalized)

        if settings["anti_spam"] and text_value:
            now = time.time()
            key = (message.chat.id, message.from_user.id)
            history = spam_history[key]
            history.append(now)
            window = max(1, min(60, int(settings.get("spam_window", 8))))
            while history and now - history[0] > window:
                history.popleft()
            maximum = max(2, min(30, int(settings.get("max_messages", 6))))
            if len(history) > maximum:
                try:
                    bot.delete_message(message.chat.id, message.message_id)
                    bot.restrict_chat_member(
                        message.chat.id, message.from_user.id,
                        until_date=int(time.time()) + int(settings.get("mute_seconds", 60)),
                        permissions=types.ChatPermissions(can_send_messages=False)
                    )
                    bot.send_message(message.chat.id, "🚫 به دلیل ارسال پیام‌های زیاد، کاربر موقتاً سکوت شد.")
                    log_action(message.chat.id, f"Anti-spam mute {message.from_user.id}")
                except Exception:
                    log.exception("Anti-spam action failed; check bot restrict/delete permissions.")
                finally:
                    history.clear()
                return

    ask_ai_in_group(message, text_value)


# ---------------- RUNNER ----------------

def start_flask():
    app.run(host="0.0.0.0", port=PORT, use_reloader=False)


def run_bot_forever():
    global bot_username
    delay = 3
    while True:
        try:
            log.info("Starting %s v%s", BOT_NAME, VERSION)
            me = bot.get_me()
            bot_username = me.username
            log.info("Telegram connected as @%s", bot_username or "unknown")
            bot.remove_webhook()
            log.info("Webhook cleared; polling will start.")
            bot.infinity_polling(timeout=30, long_polling_timeout=25, skip_pending=False)
            delay = 3
        except KeyboardInterrupt:
            log.info("Bot stopped.")
            break
        except Exception:
            log.exception("Polling stopped; reconnecting in %s seconds.", delay)
            time.sleep(delay)
            delay = min(delay * 2, 60)


if __name__ == "__main__":
    threading.Thread(target=start_flask, daemon=True).start()
    run_bot_forever()
