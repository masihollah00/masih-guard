# -*- coding: utf-8 -*-
"""
MASIH GUARD PRO
Python 3.11+
Dependencies: pyTelegramBotAPI, Flask, requests

Environment variables:
BOT_TOKEN            Required
OWNER_ID             Optional
AI_API_KEY           Optional
AI_BASE_URL          Optional (default OpenRouter API)
AI_MODEL             Optional
PORT                 Set by hosting provider
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

BOT_NAME = "MASIH GUARD PRO"
VERSION = "4.0"

BOT_TOKEN = (
    os.getenv("BOT_TOKEN")
    or os.getenv("TELEGRAM_BOT_TOKEN")
    or ""
).strip()

OWNER_ID = int(os.getenv("OWNER_ID", "8620924698"))

AI_API_KEY = os.getenv("AI_API_KEY", "").strip()
AI_BASE_URL = os.getenv(
    "AI_BASE_URL", "https://openrouter.ai/api/v1"
).strip().rstrip("/")
AI_MODEL = os.getenv("AI_MODEL", "").strip()

PORT = int(os.getenv("PORT", "8080"))
DATA_FILE = os.getenv("DATA_FILE", "masih_guard_data.json")

if not BOT_TOKEN:
    raise RuntimeError(
        "BOT_TOKEN is missing. Add BOT_TOKEN in hosting Environment."
    )

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
log = logging.getLogger(BOT_NAME)

bot = telebot.TeleBot(BOT_TOKEN, parse_mode=None)
app = Flask(__name__)

# ---------------- STORAGE ----------------

lock = threading.RLock()

def default_data():
    return {
        "chats": {},
        "badwords": {},
        "warnings": {},
        "settings": {},
        "welcome": {},
        "logs": []
    }

def load_data():
    try:
        if os.path.isfile(DATA_FILE):
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                result = json.load(f)
                if isinstance(result, dict):
                    base = default_data()
                    base.update(result)
                    return base
    except Exception:
        log.exception("Could not load data file")
    return default_data()

data = load_data()

def save_data():
    with lock:
        try:
            temp = DATA_FILE + ".tmp"
            with open(temp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(temp, DATA_FILE)
        except Exception:
            log.exception("Could not save data")

def chat_settings(chat_id):
    key = str(chat_id)
    with lock:
        return data["settings"].setdefault(key, {
            "anti_link": True,
            "anti_spam": True,
            "badword_filter": True,
            "welcome_enabled": True,
            "max_messages": 6,
            "spam_window": 8,
            "max_warnings": 3
        })

def log_action(chat_id, text):
    with lock:
        data["logs"].append({
            "chat": str(chat_id),
            "time": datetime.now(timezone.utc).isoformat(),
            "text": str(text)[:500]
        })
        data["logs"] = data["logs"][-300:]
    save_data()

# ---------------- FLASK HEALTH SERVER ----------------

@app.get("/")
def home():
    return jsonify({
        "name": BOT_NAME,
        "version": VERSION,
        "status": "running"
    })

@app.get("/health")
def health():
    return jsonify({"status": "ok", "bot": BOT_NAME})

# ---------------- HELPERS ----------------

spam_history = defaultdict(deque)

def is_owner(user_id):
    return user_id == OWNER_ID

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
        log.exception("Could not reply")
        return None

def is_link(text):
    if not text:
        return False
    pattern = (
        r"(https?://|www\.|t\.me/|telegram\.me/|"
        r"telegram\.dog/|@\w{5,})"
    )
    return bool(re.search(pattern, text, re.IGNORECASE))

def get_badwords(chat_id):
    with lock:
        words = data["badwords"].get(str(chat_id), [])
        return list(words) if isinstance(words, list) else []

def add_warning(chat_id, user_id):
    key = f"{chat_id}:{user_id}"
    with lock:
        data["warnings"][key] = data["warnings"].get(key, 0) + 1
        count = data["warnings"][key]
    save_data()
    return count

def warning_count(chat_id, user_id):
    return data["warnings"].get(f"{chat_id}:{user_id}", 0)

def extract_target(message):
    if message.reply_to_message:
        return message.reply_to_message.from_user
    parts = (message.text or "").split()
    if len(parts) > 1 and parts[1].isdigit():
        try:
            return bot.get_chat_member(
                message.chat.id, int(parts[1])
            ).user
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
        reply_safe(
            message,
            "⚠️ روی پیام کاربر ریپلای کن یا آیدی عددی او را بنویس."
        )
        return False
    if target_id == message.from_user.id:
        reply_safe(message, "⚠️ این کار را روی خودت انجام نده.")
        return False
    if target_id == OWNER_ID:
        reply_safe(message, "⛔ این کاربر مالک ربات است.")
        return False
    return True

# ---------------- AI ----------------

def ai_answer(question, chat_title=""):
    if not AI_API_KEY or not AI_MODEL:
        return (
            "🤖 هوش مصنوعی هنوز تنظیم نشده است.\n"
            "مدیر باید AI_API_KEY و AI_MODEL سازگار را در Environment هاست تنظیم کند."
        )

    url = AI_BASE_URL + "/chat/completions"
    payload = {
        "model": AI_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "تو دستیار فارسی‌زبان ربات MASIH GUARD PRO هستی. "
                    "به فارسی روان، مودبانه و مفید جواب بده. "
                    "اگر مطمئن نیستی، صادقانه بگو."
                )
            },
            {
                "role": "user",
                "content": (
                    f"گروه: {chat_title}\n"
                    f"سؤال: {question[:3500]}"
                )
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
                "HTTP-Referer": "https://masih-guard.local",
                "X-Title": BOT_NAME
            },
            json=payload,
            timeout=35
        )
        if response.status_code != 200:
            log.error(
                "AI API error %s: %s",
                response.status_code, response.text[:500]
            )
            return (
                "⚠️ سرویس هوش مصنوعی جواب نداد. "
                "کلید، نام مدل و آدرس API را بررسی کن."
            )

        result = response.json()
        answer = result["choices"][0]["message"]["content"]
        if isinstance(answer, str) and answer.strip():
            return answer[:4000]
        return "⚠️ پاسخ هوش مصنوعی خالی بود."
    except Exception:
        log.exception("AI request failed")
        return "⚠️ اتصال به هوش مصنوعی ناموفق بود."

# ---------------- COMMANDS ----------------

@bot.message_handler(commands=["start", "help"])
def start_command(message):
    text = (
        f"🛡 {BOT_NAME} v{VERSION}\n\n"
        "ربات مدیریت گروه فعال است.\n\n"
        "دستورات:\n"
        "/ping — بررسی وضعیت\n"
        "/id — نمایش آیدی\n"
        "/panel — پنل مدیریت\n"
        "/rules — راهنمای دستورات\n"
        "/ai سؤال — پرسیدن از هوش مصنوعی\n\n"
        "دستورات مدیریتی در گروه:\n"
        "/warn /warnings /unwarn\n"
        "/mute /unmute /ban /unban /kick\n"
        "/purge /addbadword /delbadword\n"
        "/antilink_on /antilink_off\n"
        "/antispam_on /antispam_off\n"
        "/welcome_on /welcome_off"
    )
    reply_safe(message, text)

@bot.message_handler(commands=["ping"])
def ping_command(message):
    reply_safe(message, f"✅ {BOT_NAME} فعال است.\nنسخه: {VERSION}")

@bot.message_handler(commands=["id"])
def id_command(message):
    user = message.from_user
    reply_safe(
        message,
        f"👤 آیدی شما: {user.id}\n"
        f"💬 آیدی گفتگو: {message.chat.id}"
    )

@bot.message_handler(commands=["rules"])
def rules_command(message):
    reply_safe(
        message,
        "📘 راهنمای مدیران\n"
        "برای مدیریت کاربر، روی پیام او ریپلای کن و دستور را بفرست.\n"
        "برای مثال: /warn\n"
        "برای حذف چند پیام: روی پیام آخر ریپلای کن و /purge بزن.\n"
        "برای پرسیدن سؤال: /ai سؤال خودت"
    )

@bot.message_handler(commands=["ai"])
def ai_command(message):
    question = (message.text or "").partition(" ")[2].strip()
    if not question and message.reply_to_message:
        question = (
            message.reply_to_message.text
            or message.reply_to_message.caption
            or ""
        ).strip()
    if not question:
        reply_safe(message, "مثال: /ai درباره فضا توضیح بده")
        return

    status = reply_safe(message, "🤖 دارم فکر می‌کنم...")
    answer = ai_answer(question, getattr(message.chat, "title", "") or "")
    try:
        if status:
            bot.edit_message_text(
                answer, message.chat.id, status.message_id
            )
        else:
            reply_safe(message, answer)
    except Exception:
        reply_safe(message, answer)

@bot.message_handler(commands=["panel"])
def panel_command(message):
    if not is_admin(message.chat.id, message.from_user.id):
        reply_safe(message, "⛔ پنل فقط برای مدیران گروه است.")
        return

    settings = chat_settings(message.chat.id)
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton(
            "لینک: روشن" if settings["anti_link"] else "لینک: خاموش",
            callback_data="toggle:anti_link"
        ),
        types.InlineKeyboardButton(
            "ضداسپم: روشن" if settings["anti_spam"] else "ضداسپم: خاموش",
            callback_data="toggle:anti_spam"
        ),
        types.InlineKeyboardButton(
            "فیلتر کلمات: روشن" if settings["badword_filter"] else "فیلتر کلمات: خاموش",
            callback_data="toggle:badword_filter"
        ),
        types.InlineKeyboardButton(
            "خوشامد: روشن" if settings["welcome_enabled"] else "خوشامد: خاموش",
            callback_data="toggle:welcome_enabled"
        )
    )
    bot.send_message(
        message.chat.id,
        "⚙️ پنل تنظیمات MASIH GUARD PRO",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("toggle:"))
def panel_callback(call):
    try:
        if not is_admin(call.message.chat.id, call.from_user.id):
            bot.answer_callback_query(
                call.id, "فقط مدیر گروه می‌تواند تنظیمات را تغییر دهد.",
                show_alert=True
            )
            return
        key = call.data.split(":", 1)[1]
        allowed = {
            "anti_link", "anti_spam",
            "badword_filter", "welcome_enabled"
        }
        if key not in allowed:
            bot.answer_callback_query(call.id, "تنظیم نامعتبر است.")
            return
        settings = chat_settings(call.message.chat.id)
        settings[key] = not settings[key]
        save_data()
        bot.answer_callback_query(call.id, "تنظیمات ذخیره شد.")
        panel_command(call.message)
    except Exception:
        log.exception("Panel callback failed")

# ---------------- ADMIN COMMANDS ----------------

@bot.message_handler(commands=["warn"])
def warn_command(message):
    target_id = target_user_id(message)
    if not ensure_manageable(message, target_id):
        return
    count = add_warning(message.chat.id, target_id)
    max_warnings = chat_settings(message.chat.id)["max_warnings"]
    reply_safe(
        message,
        f"⚠️ اخطار ثبت شد.\nتعداد اخطار: {count}/{max_warnings}"
    )
    if count >= max_warnings:
        try:
            bot.ban_chat_member(message.chat.id, target_id)
            reply_safe(message, "⛔ سقف اخطارها رسید؛ کاربر مسدود شد.")
            log_action(message.chat.id, f"Auto-ban {target_id}")
        except Exception:
            reply_safe(message, "⚠️ ربات اجازه مسدودسازی ندارد.")

@bot.message_handler(commands=["warnings"])
def warnings_command(message):
    target_id = target_user_id(message) or message.from_user.id
    reply_safe(
        message,
        f"⚠️ تعداد اخطارها: {warning_count(message.chat.id, target_id)}"
    )

@bot.message_handler(commands=["unwarn"])
def unwarn_command(message):
    target_id = target_user_id(message)
    if not ensure_manageable(message, target_id):
        return
    key = f"{message.chat.id}:{target_id}"
    data["warnings"][key] = 0
    save_data()
    reply_safe(message, "✅ اخطارهای این کاربر پاک شد.")

@bot.message_handler(commands=["mute"])
def mute_command(message):
    target_id = target_user_id(message)
    if not ensure_manageable(message, target_id):
        return
    try:
        until = int(time.time()) + 3600
        bot.restrict_chat_member(
            message.chat.id,
            target_id,
            until_date=until,
            permissions=types.ChatPermissions(
                can_send_messages=False,
                can_send_audios=False,
                can_send_documents=False,
                can_send_photos=False,
                can_send_videos=False,
                can_send_video_notes=False,
                can_send_voice_notes=False,
                can_send_polls=False,
                can_send_other_messages=False,
                can_add_web_page_previews=False
            )
        )
        reply_safe(message, "🔇 کاربر برای یک ساعت سکوت شد.")
        log_action(message.chat.id, f"Mute {target_id}")
    except Exception:
        log.exception("Mute failed")
        reply_safe(message, "⚠️ نتوانستم کاربر را سکوت کنم؛ دسترسی ادمین را بررسی کن.")

@bot.message_handler(commands=["unmute"])
def unmute_command(message):
    target_id = target_user_id(message)
    if not ensure_manageable(message, target_id):
        return
    try:
        bot.restrict_chat_member(
            message.chat.id,
            target_id,
            permissions=types.ChatPermissions(
                can_send_messages=True,
                can_send_audios=True,
                can_send_documents=True,
                can_send_photos=True,
                can_send_videos=True,
                can_send_video_notes=True,
                can_send_voice_notes=True,
                can_send_polls=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True
            )
        )
        reply_safe(message, "🔊 سکوت کاربر برداشته شد.")
    except Exception:
        reply_safe(message, "⚠️ نتوانستم سکوت را بردارم.")

@bot.message_handler(commands=["ban"])
def ban_command(message):
    target_id = target_user_id(message)
    if not ensure_manageable(message, target_id):
        return
    try:
        bot.ban_chat_member(message.chat.id, target_id)
        reply_safe(message, "⛔ کاربر مسدود شد.")
        log_action(message.chat.id, f"Ban {target_id}")
    except Exception:
        reply_safe(message, "⚠️ مسدودسازی ناموفق بود.")

@bot.message_handler(commands=["unban"])
def unban_command(message):
    if not is_admin(message.chat.id, message.from_user.id):
        reply_safe(message, "⛔ فقط مدیر گروه.")
        return
    parts = (message.text or "").split()
    if len(parts) < 2 or not parts[1].isdigit():
        reply_safe(message, "استفاده: /unban آیدی_عددی")
        return
    try:
        bot.unban_chat_member(message.chat.id, int(parts[1]))
        reply_safe(message, "✅ مسدودیت برداشته شد.")
    except Exception:
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
        reply_safe(message, "⚠️ اخراج کاربر ناموفق بود.")

@bot.message_handler(commands=["purge"])
def purge_command(message):
    if not is_admin(message.chat.id, message.from_user.id):
        reply_safe(message, "⛔ فقط مدیر گروه.")
        return
    if not message.reply_to_message:
        reply_safe(message, "برای پاک‌کردن پیام‌ها، روی پیام آخر ریپلای کن.")
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
    try:
        bot.send_message(
            message.chat.id,
            f"🧹 پاک‌سازی انجام شد. تعداد پیام‌های پاک‌شده: {deleted}"
        )
    except Exception:
        pass

# ---------------- FILTER SETTINGS ----------------

def set_setting_command(message, setting, value):
    if not is_admin(message.chat.id, message.from_user.id):
        reply_safe(message, "⛔ فقط مدیر گروه.")
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
    if not is_admin(message.chat.id, message.from_user.id):
        reply_safe(message, "⛔ فقط مدیر گروه.")
        return
    word = (message.text or "").partition(" ")[2].strip()
    if not word:
        reply_safe(message, "استفاده: /addbadword کلمه")
        return
    with lock:
        words = data["badwords"].setdefault(str(message.chat.id), [])
        if word.casefold() not in [w.casefold() for w in words]:
            words.append(word[:100])
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
    with lock:
        key = str(message.chat.id)
        data["badwords"][key] = [
            w for w in data["badwords"].get(key, [])
            if w.casefold() != word.casefold()
        ]
    save_data()
    reply_safe(message, "✅ کلمه از فیلتر حذف شد.")

@bot.message_handler(commands=["badwords"])
def badwords_command(message):
    if not is_admin(message.chat.id, message.from_user.id):
        reply_safe(message, "⛔ فقط مدیر گروه.")
        return
    words = get_badwords(message.chat.id)
    reply_safe(
        message,
        "📃 کلمات فیلتر:\n" + ("\n".join(words) if words else "هنوز کلمه‌ای ثبت نشده.")
    )

# ---------------- NEW MEMBERS ----------------

@bot.message_handler(content_types=["new_chat_members"])
def welcome_new_members(message):
    settings = chat_settings(message.chat.id)
    if not settings["welcome_enabled"]:
        return
    for user in message.new_chat_members:
        if user.is_bot:
            continue
        name = user.first_name or "دوست عزیز"
        try:
            bot.send_message(
                message.chat.id,
                f"👋 خوش اومدی {name}!\n"
                f"به گروه {message.chat.title or ''} خوش اومدی 🌹"
            )
        except Exception:
            log.exception("Welcome message failed")

# ---------------- MESSAGE MODERATION ----------------

@bot.message_handler(
    func=lambda m: bool(m.text or m.caption),
    content_types=["text", "photo", "video", "document",
                   "audio", "voice", "animation", "sticker"]
)
def moderate_message(message):
    if not message.from_user:
        return
    if message.from_user.is_bot:
        return
    if message.chat.type not in ("group", "supergroup"):
        return

    text_value = (message.text or message.caption or "").strip()
    settings = chat_settings(message.chat.id)

    if is_admin(message.chat.id, message.from_user.id):
        return

    if settings["anti_link"] and is_link(text_value):
        try:
            bot.delete_message(message.chat.id, message.message_id)
            bot.send_message(
                message.chat.id,
                f"🔗 {message.from_user.first_name} ارسال لینک در گروه مجاز نیست."
            )
            log_action(message.chat.id, f"Link removed from {message.from_user.id}")
        except Exception:
            log.exception("Could not remove link")
        return

    if settings["badword_filter"] and text_value:
        words = get_badwords(message.chat.id)
        if any(w.casefold() in text_value.casefold() for w in words):
            try:
                bot.delete_message(message.chat.id, message.message_id)
                log_action(message.chat.id, f"Bad word removed from {message.from_user.id}")
            except Exception:
                log.exception("Could not remove bad word message")
            return

    if settings["anti_spam"]:
        now = time.time()
        key = (message.chat.id, message.from_user.id)
        history = spam_history[key]
        history.append(now)
        window = settings["spam_window"]
        while history and now - history[0] > window:
            history.popleft()

        if len(history) > settings["max_messages"]:
            try:
                bot.delete_message(message.chat.id, message.message_id)
                bot.restrict_chat_member(
                    message.chat.id,
                    message.from_user.id,
                    until_date=int(time.time()) + 60,
                    permissions=types.ChatPermissions(can_send_messages=False)
                )
                bot.send_message(
                    message.chat.id,
                    f"🚫 {message.from_user.first_name} به دلیل ارسال پیام‌های زیاد، یک دقیقه سکوت شد."
                )
                history.clear()
                log_action(message.chat.id, f"Anti-spam mute {message.from_user.id}")
            except Exception:
                log.exception("Anti-spam action failed")

# ---------------- BOT RUNNER ----------------

def run_bot_forever():
    delay = 3
    while True:
        try:
            log.info("Starting %s v%s", BOT_NAME, VERSION)
            try:
                # Compatible with pyTelegramBotAPI versions
                bot.remove_webhook()
            except Exception:
                log.exception("Could not remove webhook; continuing")
            bot.infinity_polling(
                timeout=30,
                long_polling_timeout=25,
                skip_pending=False
            )
            delay = 3
        except KeyboardInterrupt:
            log.info("Stopped by keyboard")
            break
        except Exception:
            log.exception(
                "Polling stopped unexpectedly; reconnecting in %s seconds",
                delay
            )
            time.sleep(delay)
            delay = min(delay * 2, 60)

def start_flask():
    app.run(host="0.0.0.0", port=PORT, use_reloader=False)

if __name__ == "__main__":
    thread = threading.Thread(target=start_flask, daemon=True)
    thread.start()
    run_bot_forever()
