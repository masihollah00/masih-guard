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

# پایان بخش اول
