# -*- coding: utf-8 -*-
"""
MASIH GUARD — stable starter build
Python 3.11+
Required environment variables on FadeHost:
  BOT_TOKEN      Telegram bot token (required)
  AI_API_KEY     OpenRouter API key beginning with sk-or-v1- (required for AI)
Optional:
  OWNER_ID       Your numeric Telegram ID (default: 8620924698)
  AI_BASE_URL    Default: https://openrouter.ai/api/v1
  AI_MODEL       Default: openrouter/free
  PORT           Default: 8080
  DATA_FILE      Default: masih_guard_data.json

AI behavior:
- In private chat: replies to normal text messages.
- In groups: use /ai your question, or reply to the bot / mention it.
- Group moderation commands require the bot to be an admin for actions such as delete/mute/ban.
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

# ---------------- CONFIG ----------------

BOT_NAME = "مسیح گارد"
VERSION = "5.0"

BOT_TOKEN = (os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
AI_API_KEY = os.getenv("AI_API_KEY", "").strip()
AI_BASE_URL = os.getenv("AI_BASE_URL", "https://openrouter.ai/api/v1").strip().rstrip("/")
AI_MODEL = os.getenv("AI_MODEL", "openrouter/free").strip() or "openrouter/free"
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
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
log = logging.getLogger(BOT_NAME)

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing. Add BOT_TOKEN in FadeHost Environment Variables.")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode=None, threaded=True)
app = Flask(__name__)

# ---------------- STORAGE ----------------

data_lock = threading.RLock()

def default_data():
    return {"badwords": {}, "warnings": {}, "settings": {}, "welcome": {}, "logs": []}

def load_data():
    try:
        if os.path.isfile(DATA_FILE):
            with open(DATA_FILE, "r", encoding="utf-8") as file:
                saved = json.load(file)
            if isinstance(saved, dict):
                base = default_data()
                for key in base:
                    if isinstance(saved.get(key), type(base[key])):
                        base[key] = saved[key]
                return base
    except Exception:
        log.exception("Could not load data file; starting with defaults.")
    return default_data()

data = load_data()

def save_data():
    with data_lock:
        try:
            temp_path = DATA_FILE + ".tmp"
            with open(temp_path, "w", encoding="utf-8") as file:
                json.dump(data, file, ensure_ascii=False, indent=2)
            os.replace(temp_path, DATA_FILE)
        except Exception:
            log.exception("Could not save data file.")

DEFAULT_SETTINGS = {
    "anti_link": True,
    "anti_spam": True,
    "badword_filter": True,
    "welcome_enabled": True,
    "max_messages": 6,
    "spam_window": 8,
    "max_warnings": 3
}

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
        data["logs"] = data["logs"][-200:]
    save_data()

def get_badwords(chat_id):
    with data_lock:
        words = data["badwords"].get(str(chat_id), [])
        return list(words) if isinstance(words, list) else []

# ---------------- HEALTH SERVER ----------------

@app.get("/")
def home():
    return jsonify({"name": BOT_NAME, "version": VERSION, "status": "running"})

@app.get("/health")
def health():
    return jsonify({"status": "ok", "bot": BOT_NAME, "version": VERSION})

# ---------------- HELPERS ----------------

spam_history = defaultdict(deque)
bot_username = None

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

def reply_safe(message, text, **kwargs):
    try:
        return bot.reply_to(message, text, **kwargs)
    except Exception:
        log.exception("Could not reply to Telegram message.")
        return None

def is_link(text):
    if not text:
        return False
    return bool(re.search(r"(https?://|www\.|t\.me/|telegram\.me/|telegram\.dog/)", text, re.I))

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
    target = extract_target(message)
    return target.id if target else None

def ensure_manageable(message, target_id):
    if not is_admin(message.chat.id, message.from_user.id):
        reply_safe(message, "⛔ این دستور مخصوص مدیران گروه است.")
        return False
    if not target_id:
        reply_safe(message, "⚠️ روی پیام کاربر ریپلای کن یا آیدی عددی او را بنویس.")
        return False
    if target_id in (message.from_user.id, OWNER_ID):
        reply_safe(message, "⛔ این کاربر را نمی‌توانی هدف قرار بدهی.")
        return False
    return True

def split_long_text(text, limit=3900):
    text = str(text or "")
    return [text[i:i + limit] for i in range(0, len(text), limit)] or ["پاسخی دریافت نشد."]

# ---------------- AI ----------------

def ai_answer(question, chat_title=""):
    if not AI_API_KEY:
        log.error("AI is not configured: AI_API_KEY is empty.")
        return "⚠️ کلید هوش مصنوعی تنظیم نشده است. متغیر AI_API_KEY را در هاست بررسی کن."
    if not AI_BASE_URL.startswith("https://"):
        log.error("AI_BASE_URL must use HTTPS.")
        return "⚠️ آدرس سرویس هوش مصنوعی معتبر نیست؛ AI_BASE_URL را بررسی کن."

    url = AI_BASE_URL + "/chat/completions"
    payload = {
        "model": AI_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "تو دستیار فارسی‌زبان ربات «مسیح گارد» هستی. "
                    "به فارسی روان، محترمانه و مفید پاسخ بده. "
                    "اگر پاسخ را نمی‌دانی، صادقانه بگو."
                )
            },
            {
                "role": "user",
                "content": f"گفتگو: {chat_title or 'خصوصی'}\nپرسش: {question[:3500]}"
            }
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
                "HTTP-Referer": "https://masih-guard.example",
                "X-OpenRouter-Title": "Masih Guard"
            },
            json=payload,
            timeout=(10, 45)
        )
        if not response.ok:
            # Log a bounded error response; never log API keys.
            log.error("AI API returned HTTP %s: %s", response.status_code, response.text[:700])
            if response.status_code in (401, 403):
                return "⚠️ کلید API یا دسترسی سرویس رد شد. مقدار AI_API_KEY را در هاست بررسی کن."
            if response.status_code == 404:
                return "⚠️ آدرس API یا نام مدل پیدا نشد. AI_BASE_URL و AI_MODEL را بررسی کن."
            if response.status_code == 429:
                return "⚠️ محدودیت درخواست سرویس هوش مصنوعی رسیدیم. کمی بعد دوباره امتحان کن."
            if response.status_code in (402,):
                return "⚠️ سرویس درخواست را به دلیل اعتبار/پرداخت نپذیرفت؛ وضعیت حساب API را بررسی کن."
            return f"⚠️ سرویس هوش مصنوعی خطای HTTP {response.status_code} داد. لاگ Console را بررسی کن."

        result = response.json()
        choices = result.get("choices") or []
        if not choices:
            log.error("AI API response had no choices: %s", str(result)[:500])
            return "⚠️ سرویس هوش مصنوعی پاسخ قابل استفاده‌ای نداد."
        content = (choices[0].get("message") or {}).get("content")
        if isinstance(content, list):
            content = "\n".join(
                str(part.get("text", "")) for part in content if isinstance(part, dict)
            )
        if isinstance(content, str) and content.strip():
            return content.strip()
        log.error("AI API returned empty content.")
        return "⚠️ پاسخ هوش مصنوعی خالی بود؛ یک بار دیگر امتحان کن."
    except requests.Timeout:
        log.exception("AI request timed out.")
        return "⚠️ اتصال هوش مصنوعی بیش از حد طول کشید. دوباره امتحان کن."
    except requests.RequestException:
        log.exception("AI request failed.")
        return "⚠️ اتصال به سرویس هوش مصنوعی برقرار نشد؛ Console را بررسی کن."
    except (ValueError, KeyError, TypeError):
        log.exception("Could not parse AI response.")
        return "⚠️ پاسخ سرویس قابل خواندن نبود؛ Console را بررسی کن."
    except Exception:
        log.exception("Unexpected AI error.")
        return "⚠️ خطای غیرمنتظره در بخش هوش مصنوعی رخ داد."

def send_ai_reply(message, question):
    status = reply_safe(message, "🤖 دارم فکر می‌کنم...")
    answer = ai_answer(question, getattr(message.chat, "title", "") or "")
    try:
        if status:
            bot.edit_message_text(answer[:4000], message.chat.id, status.message_id)
        else:
            for chunk in split_long_text(answer):
                bot.send_message(message.chat.id, chunk, reply_to_message_id=message.message_id)
    except Exception:
        log.exception("Could not send AI answer.")
        try:
            for chunk in split_long_text(answer):
                bot.send_message(message.chat.id, chunk, reply_to_message_id=message.message_id)
        except Exception:
            log.exception("Fallback AI reply failed.")

# ---------------- BASIC COMMANDS ----------------

@bot.message_handler(commands=["start", "help"])
def start_command(message):
    reply_safe(
        message,
        f"🛡 {BOT_NAME} v{VERSION}\n\n"
        "ربات مدیریت گروه و دستیار فارسی فعال است.\n\n"
        "هوش مصنوعی:\n"
        "• چت خصوصی: پیام عادی بفرست.\n"
        "• گروه: /ai سؤال خودت\n"
        "• گروه: روی پیام ربات ریپلای کن یا نام ربات را منشن کن.\n\n"
        "دستورات:\n"
        "/ping — وضعیت ربات\n"
        "/id — آیدی گفتگو و کاربر\n"
        "/panel — پنل مدیران گروه\n"
        "/rules — راهنما\n"
        "/ai سؤال — پرسش از هوش مصنوعی\n"
        "/warn /warnings /unwarn /mute /unmute /ban /unban /kick\n"
        "/addbadword /delbadword /badwords\n"
        "/antilink_on /antilink_off\n"
        "/antispam_on /antispam_off\n"
        "/welcome_on /welcome_off"
    )

@bot.message_handler(commands=["ping"])
def ping_command(message):
    reply_safe(message, f"✅ {BOT_NAME} فعال است.\nنسخه: {VERSION}")

@bot.message_handler(commands=["id"])
def id_command(message):
    reply_safe(message, f"👤 آیدی شما: {message.from_user.id}\n💬 آیدی گفتگو: {message.chat.id}")

@bot.message_handler(commands=["rules"])
def rules_command(message):
    reply_safe(message, "📘 برای پرسش از AI در گروه از /ai سؤال استفاده کن. در چت خصوصی پیام عادی بفرست. دستورات مدیریتی فقط برای مدیران گروه هستند.")

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

# ---------------- INLINE ADMIN PANEL ----------------

def build_panel_markup(chat_id):
    settings = chat_settings(chat_id)
    markup = types.InlineKeyboardMarkup(row_width=2)
    options = [
        ("anti_link", "🔗 ضدلینک"),
        ("anti_spam", "🚫 ضداسپم"),
        ("badword_filter", "🤬 فیلتر کلمات"),
        ("welcome_enabled", "👋 خوشامد")
    ]
    buttons = []
    for key, label in options:
        state = "روشن" if settings[key] else "خاموش"
        buttons.append(types.InlineKeyboardButton(f"{label}: {state}", callback_data=f"toggle:{key}"))
    markup.add(*buttons)
    markup.add(types.InlineKeyboardButton("📊 آمار پنل", callback_data="panel:stats"))
    return markup

@bot.message_handler(commands=["panel"])
def panel_command(message):
    if message.chat.type not in ("group", "supergroup"):
        reply_safe(message, "⚙️ پنل مدیریت را داخل گروه باز کن.")
        return
    if not is_admin(message.chat.id, message.from_user.id):
        reply_safe(message, "⛔ پنل فقط برای مدیران گروه است.")
        return
    bot.send_message(
        message.chat.id,
        f"⚙️ پنل مدیریت {BOT_NAME}\nتنظیمات گروه را با دکمه‌ها تغییر بده.",
        reply_markup=build_panel_markup(message.chat.id)
    )

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
                log_count = len([x for x in data["logs"] if x.get("chat") == str(chat_id)])
            bot.answer_callback_query(call.id, f"ثبت‌های اخیر: {log_count}", show_alert=True)
            return
        key = call.data.split(":", 1)[1]
        if key not in ("anti_link", "anti_spam", "badword_filter", "welcome_enabled"):
            bot.answer_callback_query(call.id, "تنظیم نامعتبر است.")
            return
        settings = chat_settings(chat_id)
        settings[key] = not settings[key]
        save_data()
        bot.answer_callback_query(call.id, "تنظیمات ذخیره شد.")
        bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=build_panel_markup(chat_id))
    except Exception:
        log.exception("Panel callback failed.")
        try:
            bot.answer_callback_query(call.id, "خطا در تغییر تنظیمات.")
        except Exception:
            pass

# ---------------- MODERATION COMMANDS ----------------

@bot.message_handler(commands=["warn"])
def warn_command(message):
    target_id = target_user_id(message)
    if not ensure_manageable(message, target_id):
        return
    count = add_warning(message.chat.id, target_id)
    max_warnings = int(chat_settings(message.chat.id)["max_warnings"])
    reply_safe(message, f"⚠️ اخطار ثبت شد: {count}/{max_warnings}")
    if count >= max_warnings:
        try:
            bot.ban_chat_member(message.chat.id, target_id)
            reply_safe(message, "⛔ سقف اخطارها رسید؛ کاربر مسدود شد.")
            log_action(message.chat.id, f"Auto-ban user {target_id}")
        except Exception:
            log.exception("Auto-ban failed.")
            reply_safe(message, "⚠️ ربات نتوانست کاربر را مسدود کند؛ دسترسی ادمین را بررسی کن.")

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
        bot.restrict_chat_member(
            message.chat.id, target_id,
            until_date=int(time.time()) + 3600,
            permissions=types.ChatPermissions(can_send_messages=False)
        )
        reply_safe(message, "🔇 کاربر برای یک ساعت سکوت شد.")
        log_action(message.chat.id, f"Mute user {target_id}")
    except Exception:
        log.exception("Mute failed.")
        reply_safe(message, "⚠️ سکوت ناموفق بود؛ ادمین بودن ربات را بررسی کن.")

@bot.message_handler(commands=["unmute"])
def unmute_command(message):
    target_id = target_user_id(message)
    if not ensure_manageable(message, target_id):
        return
    try:
        bot.restrict_chat_member(
            message.chat.id, target_id,
            permissions=types.ChatPermissions(
                can_send_messages=True, can_send_audios=True, can_send_documents=True,
                can_send_photos=True, can_send_videos=True, can_send_video_notes=True,
                can_send_voice_notes=True, can_send_polls=True, can_send_other_messages=True,
                can_add_web_page_previews=True
            )
        )
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
    if not is_admin(message.chat.id, message.from_user.id):
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
    except Exception:
        log.exception("Kick failed.")
        reply_safe(message, "⚠️ اخراج ناموفق بود.")

@bot.message_handler(commands=["purge"])
def purge_command(message):
    if not is_admin(message.chat.id, message.from_user.id):
        reply_safe(message, "⛔ فقط مدیر گروه.")
        return
    if not message.reply_to_message:
        reply_safe(message, "روی پیام آخر ریپلای کن و /purge بزن.")
        return
    start_id = message.reply_to_message.message_id
    end_id = message.message_id
    start_id = max(start_id, end_id - 100)
    deleted = 0
    for msg_id in range(start_id, end_id + 1):
        try:
            bot.delete_message(message.chat.id, msg_id)
            deleted += 1
        except Exception:
            pass
    reply_safe(message, f"🧹 پاک‌سازی تمام شد. پیام‌های پاک‌شده: {deleted}")

def set_setting_command(message, setting, value):
    if not is_admin(message.chat.id, message.from_user.id):
        reply_safe(message, "⛔ فقط مدیر گروه.")
        return
    chat_settings(message.chat.id)[setting] = value
    save_data()
    reply_safe(message, "✅ تنظیم ذخیره شد.")

@bot.message_handler(commands=["antilink_on"])
def antilink_on(message): set_setting_command(message, "anti_link", True)

@bot.message_handler(commands=["antilink_off"])
def antilink_off(message): set_setting_command(message, "anti_link", False)

@bot.message_handler(commands=["antispam_on"])
def antispam_on(message): set_setting_command(message, "anti_spam", True)

@bot.message_handler(commands=["antispam_off"])
def antispam_off(message): set_setting_command(message, "anti_spam", False)

@bot.message_handler(commands=["welcome_on"])
def welcome_on(message): set_setting_command(message, "welcome_enabled", True)

@bot.message_handler(commands=["welcome_off"])
def welcome_off(message): set_setting_command(message, "welcome_enabled", False)

@bot.message_handler(commands=["addbadword"])
def addbadword_command(message):
    if not is_admin(message.chat.id, message.from_user.id):
        reply_safe(message, "⛔ فقط مدیر گروه.")
        return
    word = (message.text or "").partition(" ")[2].strip()[:100]
    if not word:
        reply_safe(message, "استفاده: /addbadword کلمه")
        return
    with data_lock:
        words = data["badwords"].setdefault(str(message.chat.id), [])
        if word.casefold() not in [w.casefold() for w in words]:
            words.append(word)
    save_data()
    reply_safe(message, "✅ کلمه به فیلتر اضافه شد.")

@bot.message_handler(commands=["delbadword"])
def delbadword_command(message):
    if not is_admin(message.chat.id, message.from_user.id):
        reply_safe(message, "⛔ فقط مدیر گروه.")
        return
    word = (message.text or "").partition(" ")[2].strip()
    if not word:
        reply_safe(message, "استفاده: /delbadword کلمه")
        return
    with data_lock:
        key = str(message.chat.id)
        data["badwords"][key] = [w for w in data["badwords"].get(key, []) if w.casefold() != word.casefold()]
    save_data()
    reply_safe(message, "✅ کلمه از فیلتر حذف شد.")

@bot.message_handler(commands=["badwords"])
def badwords_command(message):
    if not is_admin(message.chat.id, message.from_user.id):
        reply_safe(message, "⛔ فقط مدیر گروه.")
        return
    words = get_badwords(message.chat.id)
    reply_safe(message, "📃 کلمات فیلتر:\n" + ("\n".join(words) if words else "هنوز کلمه‌ای ثبت نشده."))

# ---------------- WELCOME ----------------

@bot.message_handler(content_types=["new_chat_members"])
def welcome_new_members(message):
    settings = chat_settings(message.chat.id)
    if not settings["welcome_enabled"]:
        return
    for user in message.new_chat_members:
        if user.is_bot:
            continue
        try:
            bot.send_message(message.chat.id, f"👋 خوش اومدی {user.first_name or 'دوست عزیز'}!")
        except Exception:
            log.exception("Welcome message failed.")

# ---------------- NORMAL TEXT + MODERATION ----------------

def ask_ai_in_group(message, text_value):
    if not text_value:
        return False
    mentioned = bool(bot_username and f"@{bot_username.lower()}" in text_value.lower())
    replied_to_bot = False
    replied = getattr(message, "reply_to_message", None)
    if replied and getattr(replied, "from_user", None):
        replied_to_bot = bool(replied.from_user.is_bot and replied.from_user.username == bot_username)
    if mentioned or replied_to_bot:
        cleaned = text_value
        if bot_username:
            cleaned = re.sub(rf"@{re.escape(bot_username)}\b", "", cleaned, flags=re.I).strip()
        if not cleaned and replied and (replied.text or replied.caption):
            cleaned = (replied.text or replied.caption).strip()
        if cleaned:
            send_ai_reply(message, cleaned)
        else:
            reply_safe(message, "سؤالت رو هم بنویس تا جواب بدم.")
        return True
    return False

@bot.message_handler(
    func=lambda m: bool(m.text) and not (m.text or "").startswith("/"),
    content_types=["text"]
)
def private_ai_handler(message):
    if message.chat.type == "private" and message.from_user and not message.from_user.is_bot:
        send_ai_reply(message, message.text.strip())

@bot.message_handler(
    func=lambda m: True,
    content_types=["text", "photo", "video", "document", "audio", "voice",
                   "animation", "sticker", "video_note", "contact", "location", "venue", "poll"]
)
def moderate_message(message):
    if not message.from_user or message.from_user.is_bot:
        return
    if message.chat.type not in ("group", "supergroup"):
        return

    text_value = (message.text or message.caption or "").strip()
    settings = chat_settings(message.chat.id)
    admin = is_admin(message.chat.id, message.from_user.id)

    # Apply moderation to non-admins only.
    if not admin:
        if settings["anti_link"] and is_link(text_value):
            try:
                bot.delete_message(message.chat.id, message.message_id)
                bot.send_message(message.chat.id, "🔗 ارسال لینک در گروه مجاز نیست.")
                log_action(message.chat.id, f"Link removed from {message.from_user.id}")
            except Exception:
                log.exception("Could not remove link.")
            return

        if settings["badword_filter"] and text_value:
            words = get_badwords(message.chat.id)
            if any(word and word.casefold() in text_value.casefold() for word in words):
                try:
                    bot.delete_message(message.chat.id, message.message_id)
                    log_action(message.chat.id, f"Bad word removed from {message.from_user.id}")
                except Exception:
                    log.exception("Could not remove bad word message.")
                return

        if settings["anti_spam"] and text_value:
            now = time.time()
            key = (message.chat.id, message.from_user.id)
            history = spam_history[key]
            history.append(now)
            window = int(settings["spam_window"])
            while history and now - history[0] > window:
                history.popleft()
            if len(history) > int(settings["max_messages"]):
                try:
                    bot.delete_message(message.chat.id, message.message_id)
                    bot.restrict_chat_member(
                        message.chat.id, message.from_user.id,
                        until_date=int(time.time()) + 60,
                        permissions=types.ChatPermissions(can_send_messages=False)
                    )
                    bot.send_message(message.chat.id, "🚫 به دلیل ارسال پیام‌های زیاد، کاربر برای یک دقیقه سکوت شد.")
                    history.clear()
                    log_action(message.chat.id, f"Anti-spam mute {message.from_user.id}")
                except Exception:
                    log.exception("Anti-spam action failed.")
                return

    # In groups AI replies only when mentioned or when replying to the bot.
    ask_ai_in_group(message, text_value)

# ---------------- RUNNER ----------------

def run_bot_forever():
    global bot_username
    delay = 3
    while True:
        try:
            log.info("Starting %s v%s", BOT_NAME, VERSION)
            try:
                me = bot.get_me()
                bot_username = me.username
                log.info("Telegram connected as @%s", bot_username or "unknown")
            except Exception:
                log.exception("Could not verify Telegram bot token.")
            try:
                bot.remove_webhook()
                log.info("Webhook cleared; polling will start.")
            except Exception:
                log.exception("Could not remove webhook.")
            bot.infinity_polling(timeout=30, long_polling_timeout=25, skip_pending=False)
            delay = 3
        except KeyboardInterrupt:
            log.info("Bot stopped.")
            break
        except Exception:
            log.exception("Polling stopped unexpectedly; reconnecting in %s seconds.", delay)
            time.sleep(delay)
            delay = min(delay * 2, 60)

def start_flask():
    app.run(host="0.0.0.0", port=PORT, use_reloader=False)

if __name__ == "__main__":
    threading.Thread(target=start_flask, daemon=True).start()
    run_bot_forever()
