# -*- coding: utf-8 -*-
# MASIH GUARD | ربات مدیریت گروه تلگرام
# نویسنده: مسیح مختاری
# کتابخانه: pyTelegramBotAPI

import os
import re
import json
import time
import ast
import math
import random
import string
import threading
from datetime import datetime
from collections import defaultdict, deque

import telebot
from telebot import types, apihelper

# ==============================
# تنظیمات اصلی
# ==============================

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()

if not TOKEN:
    raise RuntimeError(
        "متغیر TELEGRAM_BOT_TOKEN در تنظیمات میزبان وارد نشده است."
    )

# پروکسی اختیاری؛ اگر لازم نداری خالی بماند
PROXY_URL = os.getenv("TELEGRAM_PROXY_URL", "").strip()

if PROXY_URL:
    apihelper.proxy = {
        "http": PROXY_URL,
        "https": PROXY_URL
    }

bot = telebot.TeleBot(TOKEN, parse_mode="HTML")

BOT_NAME = "MASIH GUARD"
BOT_VERSION = "2.0"
DATA_FILE = "masih_guard_data.json"

LOCK = threading.RLock()

# ==============================
# اطلاعات پیش‌فرض
# ==============================

DEFAULT_DATA = {
    "groups": {},
    "logs": {},
    "warnings": {},
    "users": {},
    "started_at": time.time()
}

def load_data():
    """بارگذاری اطلاعات ذخیره‌شده."""
    if not os.path.exists(DATA_FILE):
        return DEFAULT_DATA.copy()

    try:
        with open(DATA_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)

        for key, value in DEFAULT_DATA.items():
            data.setdefault(key, value)

        return data

    except (OSError, json.JSONDecodeError):
        return DEFAULT_DATA.copy()


DATA = load_data()


def save_data():
    """ذخیره امن‌تر تنظیمات و گزارش‌ها."""
    with LOCK:
        temp_file = DATA_FILE + ".tmp"

        with open(temp_file, "w", encoding="utf-8") as file:
            json.dump(
                DATA,
                file,
                ensure_ascii=False,
                indent=2
            )

        os.replace(temp_file, DATA_FILE)


# ==============================
# ابزارهای عمومی
# ==============================

def now_text():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def get_group(chat_id):
    """ساخت تنظیمات پیش‌فرض برای هر گروه."""
    key = str(chat_id)

    with LOCK:
        if key not in DATA["groups"]:
            DATA["groups"][key] = {
                "welcome": True,
                "anti_link": False,
                "anti_spam": False,
                "bad_words": [],
                "rules": "لطفاً به اعضا احترام بگذارید و قوانین گروه را رعایت کنید.",
                "welcome_text": "سلام {name}، به گروه خوش آمدی!",
                "admins": [],
                "warnings_limit": 3
            }
            save_data()

        return DATA["groups"][key]


def add_log(chat_id, message):
    """ثبت رویدادهای مهم گروه."""
    key = str(chat_id)

    with LOCK:
        DATA["logs"].setdefault(key, [])
        DATA["logs"][key].append({
            "time": now_text(),
            "message": str(message)
        })

        # جلوگیری از رشد بی‌نهایت فایل گزارش
        DATA["logs"][key] = DATA["logs"][key][-200:]
        save_data()


def safe_html(value):
    """جلوگیری از خراب‌شدن قالب پیام‌های HTML."""
    value = str(value)
    value = value.replace("&", "&amp;")
    value = value.replace("<", "&lt;")
    value = value.replace(">", "&gt;")
    return value


def is_group(message):
    return message.chat.type in ("group", "supergroup")


def is_admin(chat_id, user_id):
    """بررسی مدیر بودن کاربر در تلگرام."""
    try:
        member = bot.get_chat_member(chat_id, user_id)
        return member.status in ("creator", "administrator")
    except Exception:
        return False


def is_owner(message):
    """فقط مدیران واقعی تلگرام مجوز مدیریتی دارند."""
    return (
        is_group(message)
        and is_admin(message.chat.id, message.from_user.id)
    )


def reply_error(message, text="این دستور فقط برای مدیران گروه است."):
    try:
        bot.reply_to(message, "⚠️ " + safe_html(text))
    except Exception:
        pass


def get_target_user(message):
    """گرفتن کاربر هدف از پاسخ به پیام."""
    if not message.reply_to_message:
        return None

    return message.reply_to_message.from_user


def format_user(user):
    name = user.first_name or "کاربر"
    return safe_html(name)


# ==============================
# محدودکردن پیام‌های تکراری
# ==============================

USER_MESSAGES = defaultdict(lambda: deque(maxlen=12))
USER_LAST_TEXT = defaultdict(str)


def record_message(chat_id, user_id, text):
    key = (chat_id, user_id)
    current_time = time.time()

    USER_MESSAGES[key].append(current_time)
    USER_LAST_TEXT[key] = text or ""

    recent = [
        stamp for stamp in USER_MESSAGES[key]
        if current_time - stamp <= 8
    ]

    USER_MESSAGES[key] = deque(recent, maxlen=12)

    return len(recent)


# ==============================
# وضعیت ربات
# ==============================

BOT_START_TIME = time.time()

def uptime_text():
    seconds = int(time.time() - BOT_START_TIME)

    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)

    return (
        f"{days} روز، {hours} ساعت، "
        f"{minutes} دقیقه و {seconds} ثانیه"
    )

# ==============================
# پنل مدیریتی فارسی MASIH GUARD
# این بخش را به انتهای main.py اضافه کن
# ==============================

from telebot import types


def build_main_panel():
    panel = types.InlineKeyboardMarkup(row_width=2)

    panel.add(
        types.InlineKeyboardButton(
            "🛡️ امنیت گروه",
            callback_data="security"
        ),
        types.InlineKeyboardButton(
            "👮 مدیریت اعضا",
            callback_data="moderation"
        )
    )

    panel.add(
        types.InlineKeyboardButton(
            "📜 قوانین گروه",
            callback_data="rules"
        ),
        types.InlineKeyboardButton(
            "👋 خوشامدگویی",
            callback_data="welcome"
        )
    )

    panel.add(
        types.InlineKeyboardButton(
            "📊 وضعیت ربات",
            callback_data="status"
        ),
        types.InlineKeyboardButton(
            "📋 راهنمای دستورات",
            callback_data="help"
        )
    )

    return panel


def build_security_panel(chat_id):
    settings = get_group(chat_id)
    panel = types.InlineKeyboardMarkup(row_width=1)

    link_status = "روشن ✅" if settings["anti_link"] else "خاموش ❌"
    spam_status = "روشن ✅" if settings["anti_spam"] else "خاموش ❌"

    panel.add(
        types.InlineKeyboardButton(
            f"🔗 ضدلینک: {link_status}",
            callback_data="toggle_link"
        ),
        types.InlineKeyboardButton(
            f"🚫 ضداسپم: {spam_status}",
            callback_data="toggle_spam"
        ),
        types.InlineKeyboardButton(
            "🔙 بازگشت به پنل",
            callback_data="home"
        )
    )

    return panel


@bot.message_handler(commands=["panel", "پنل"])
def show_main_panel(message):
    bot.send_message(
        message.chat.id,
        "🌈 <b>MASIH GUARD | پنل هفت‌رنگ</b>\n\n"
        "یکی از بخش‌های زیر را انتخاب کن:",
        reply_markup=build_main_panel()
    )


@bot.callback_query_handler(
    func=lambda call: call.data in [
        "home", "security", "moderation", "rules",
        "welcome", "status", "help",
        "toggle_link", "toggle_spam", "toggle_welcome"
    ]
)
def handle_panel_buttons(call):
    chat_id = call.message.chat.id
    data = call.data

    try:
        bot.answer_callback_query(call.id)
    except Exception:
        pass

    if data == "home":
        bot.edit_message_text(
            "🌈 <b>MASIH GUARD</b>\n\n"
            "بخش موردنظر را انتخاب کن:",
            chat_id,
            call.message.message_id,
            reply_markup=build_main_panel()
        )
        return

    if data in ("toggle_link", "toggle_spam", "toggle_welcome"):
        if not is_group(call.message):
            bot.send_message(
                chat_id,
                "⚠️ این تنظیم فقط داخل گروه قابل تغییر است."
            )
            return

        if not is_admin(chat_id, call.from_user.id):
            bot.send_message(
                chat_id,
                "⛔ فقط مدیران گروه اجازه تغییر تنظیمات را دارند."
            )
            return

        settings = get_group(chat_id)

        key = {
            "toggle_link": "anti_link",
            "toggle_spam": "anti_spam",
            "toggle_welcome": "welcome"
        }[data]

        settings[key] = not settings[key]
        save_data()

        add_log(
            chat_id,
            f"تنظیم {key} توسط {call.from_user.id} تغییر کرد."
        )

        if data == "toggle_welcome":
            bot.edit_message_text(
                "👋 <b>تنظیم خوشامدگویی</b>\n\n"
                f"وضعیت: {'روشن ✅' if settings['welcome'] else 'خاموش ❌'}",
                chat_id,
                call.message.message_id,
                reply_markup=types.InlineKeyboardMarkup().add(
                    types.InlineKeyboardButton(
                        "🔄 تغییر وضعیت",
                        callback_data="toggle_welcome"
                    ),
                    types.InlineKeyboardButton(
                        "🔙 بازگشت",
                        callback_data="home"
                    )
                )
            )
        else:
            bot.edit_message_text(
                "🛡️ <b>تنظیمات امنیت گروه</b>\n\n"
                "تنظیم موردنظر را انتخاب کن:",
                chat_id,
                call.message.message_id,
                reply_markup=build_security_panel(chat_id)
            )
        return

    if data == "security":
        if not is_group(call.message):
            bot.send_message(
                chat_id,
                "برای تنظیم امنیت، این بخش را از داخل گروه باز کن."
            )
            return

        bot.edit_message_text(
            "🛡️ <b>امنیت گروه</b>\n\n"
            "وضعیت قابلیت‌ها را از دکمه‌های زیر تغییر بده.",
            chat_id,
            call.message.message_id,
            reply_markup=build_security_panel(chat_id)
        )
        return

    if data == "moderation":
        bot.send_message(
            chat_id,
            "👮 <b>دستورات مدیریت اعضا</b>\n\n"
            "برای استفاده از این دستورات، در گروه روی پیام کاربر پاسخ بده:\n\n"
            "• <code>/warn</code> — ثبت اخطار\n"
            "• <code>/mute 10</code> — محدودیت ۱۰ دقیقه‌ای\n"
            "• <code>/unmute</code> — برداشتن محدودیت\n"
            "• <code>/ban</code> — مسدودکردن کاربر\n"
            "• <code>/kick</code> — اخراج کاربر\n"
            "• <code>/purge 10</code> — حذف پیام‌ها\n\n"
            "این دستورات به مجوزهای لازم ربات در گروه نیاز دارند."
        )
        return

    if data == "rules":
        if not is_group(call.message):
            bot.send_message(
                chat_id,
                "📜 قوانین را از داخل گروه مشاهده کن."
            )
            return

        settings = get_group(chat_id)

        bot.send_message(
            chat_id,
            "📜 <b>قوانین گروه</b>\n\n" +
            safe_html(settings["rules"])
        )
        return

    if data == "welcome":
        if not is_group(call.message):
            bot.send_message(
                chat_id,
                "👋 این تنظیم را از داخل گروه باز کن."
            )
            return

        settings = get_group(chat_id)

        status = "روشن ✅" if settings["welcome"] else "خاموش ❌"

        panel = types.InlineKeyboardMarkup(row_width=1)
        panel.add(
            types.InlineKeyboardButton(
                "🔄 تغییر وضعیت خوشامدگویی",
                callback_data="toggle_welcome"
            ),
            types.InlineKeyboardButton(
                "🔙 بازگشت",
                callback_data="home"
            )
        )

        bot.send_message(
            chat_id,
            f"👋 <b>خوشامدگویی</b>\n\nوضعیت فعلی: {status}",
            reply_markup=panel
        )
        return

    if data == "status":
        bot.send_message(
            chat_id,
            "📊 <b>وضعیت MASIH GUARD</b>\n\n"
            "🟢 ربات در حال اجراست.\n"
            f"⏱️ زمان فعالیت: {uptime_text()}\n"
            f"🧩 نسخه: {BOT_VERSION}"
        )
        return

    if data == "help":
        bot.send_message(
            chat_id,
            "📋 <b>راهنمای MASIH GUARD</b>\n\n"
            "• <code>/start</code> — شروع ربات\n"
            "• <code>/panel</code> — نمایش پنل\n"
            "• <code>/rules</code> — قوانین گروه\n"
            "• <code>/id</code> — شناسه کاربر یا گروه\n"
            "• <code>/warn</code> — اخطار به کاربر با پاسخ به پیام\n\n"
            "برای دستورات مدیریتی، ربات باید مجوز مناسب داشته باشد."
        )
        return


@bot.message_handler(commands=["rules"])
def show_rules(message):
    if not is_group(message):
        bot.reply_to(message, "این دستور را داخل گروه استفاده کن.")
        return

    settings = get_group(message.chat.id)

    bot.reply_to(
        message,
        "📜 <b>قوانین گروه</b>\n\n" +
        safe_html(settings["rules"])
    )


@bot.message_handler(commands=["id"])
def show_id(message):
    bot.reply_to(
        message,
        f"🆔 شناسه گروه: <code>{message.chat.id}</code>\n"
        f"👤 شناسه شما: <code>{message.from_user.id}</code>"
    )

