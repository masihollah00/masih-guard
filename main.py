
# -*- coding: utf-8 -*-
# MASIH GUARD S1000+
# Single-file Telegram bot foundation
# بخش 1 از 5: تنظیمات، ذخیره‌سازی و پنل اصلی

import os
import re
import json
import time
import random
import threading
import traceback
from datetime import datetime

import telebot
from telebot import types

# ---------------- CONFIG ----------------

BOT_TOKEN = (
    os.getenv("BOT_TOKEN")
    or os.getenv("TELEGRAM_BOT_TOKEN")
    or ""
).strip()

OWNER_ID = int(os.getenv("OWNER_ID", "8620924698"))

DATA_FILE = os.getenv(
    "DATA_FILE",
    "masih_guard_data.json"
)

AI_API_KEY = os.getenv("AI_API_KEY", "")
AI_BASE_URL = os.getenv(
    "AI_BASE_URL",
    "https://openrouter.ai/api/v1"
).rstrip("/")

AI_MODEL = os.getenv(
    "AI_MODEL",
    "openai/gpt-4o-mini"
)

WEBSITE_URL = os.getenv(
    "WEBSITE_URL",
    "https://neon-portfolio-7vhj.onrender.com"
)

CHANNEL_URL = os.getenv(
    "CHANNEL_URL",
    "https://t.me/"
)

BRAND = "MASIH GUARD"
VERSION = "S1000+"

if not BOT_TOKEN:
    raise RuntimeError(
        "BOT_TOKEN is missing. "
        "Set BOT_TOKEN in your host environment."
    )

bot = telebot.TeleBot(
    BOT_TOKEN,
    parse_mode="HTML",
    threaded=True,
    num_threads=4
)

LOCK = threading.RLock()
WAITING = {}

# ---------------- DEFAULT SETTINGS ----------------

DEFAULT_GROUP = {
    "anti_link": True,
    "anti_ads": True,
    "anti_spam": True,
    "anti_repeat": True,
    "anti_forward": False,
    "media_lock": False,
    "welcome_on": True,
    "farewell_on": False,
    "join_approval": False,
    "bad_words": [],
    "whitelist": [],
    "warn_limit": 3,
    "rules": "احترام به اعضا الزامی است.",
    "welcome_text": "سلام {name}، به گروه خوش آمدی!",
    "farewell_text": "خداحافظ {name}",
    "auto_replies": {},
    "buttons": [
        {
            "text": "🌐 وب‌سایت رسمی",
            "url": WEBSITE_URL
        }
    ]
}

DEFAULT_DATA = {
    "groups": {},
    "admins": {},
    "warnings": {},
    "logs": [],
    "proxies": [],
    "customers": {},
    "tickets": {},
    "points": {},
    "seen": {},
    "stats": {
        "messages": 0,
        "blocked": 0,
        "warns": 0,
        "joins": 0,
        "tickets": 0
    },
    "settings": {
        "smart_security": True
    },
    "last_daily": ""
}


def clone_data(value):
    return json.loads(
        json.dumps(value, ensure_ascii=False)
    )


def load_data():
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)

        for key, value in DEFAULT_DATA.items():
            if key not in data:
                data[key] = clone_data(value)

        return data

    except (OSError, ValueError, TypeError):
        return clone_data(DEFAULT_DATA)


DATA = load_data()


def save_data():
    """Save data safely using a temporary file."""
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


def escape_html(value):
    value = str(value or "")
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def add_log(action, chat_id="", user_id="", detail=""):
    DATA["logs"].append({
        "time": datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        ),
        "action": str(action),
        "chat_id": str(chat_id),
        "user_id": str(user_id),
        "detail": str(detail)[:250]
    })

    DATA["logs"] = DATA["logs"][-800:]
    save_data()


def is_owner(user_id):
    return int(user_id or 0) == OWNER_ID


def is_admin(chat_id, user_id):
    if is_owner(user_id):
        return True

    admins = DATA["admins"].get(str(chat_id), [])
    return str(user_id) in admins


def get_group_settings(chat_id):
    key = str(chat_id)

    if key not in DATA["groups"]:
        DATA["groups"][key] = clone_data(DEFAULT_GROUP)

    settings = DATA["groups"][key]

    for name, value in DEFAULT_GROUP.items():
        if name not in settings:
            settings[name] = clone_data(value)

    return settings


# ---------------- MAIN PANEL ----------------

SECTIONS = {
    "security": "🛡 امنیت گروه",
    "members": "👥 مدیریت اعضا",
    "settings": "⚙️ تنظیمات گروه",
    "welcome": "👋 خوشامد و دکمه‌ها",
    "rules": "📜 قوانین و پاسخ خودکار",
    "font": "🔤 سازنده فونت",
    "proxy": "🌐 پنل پروکسی",
    "stats": "📊 آمار و گزارش",
    "customers": "💼 مشتریان و اشتراک",
    "tickets": "🎫 تیکت پشتیبانی",
    "ai": "🧠 هوش مصنوعی",
    "games": "🎮 بازی و امتیاز",
    "backup": "💾 پشتیبان‌گیری",
    "daily": "📅 گزارش روزانه",
    "smart": "🧩 امنیت هوشمند",
    "status": "🚀 وضعیت ربات"
}


def make_main_panel():
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    entries = list(SECTIONS.items())

    for index in range(0, len(entries), 2):
        pair = entries[index:index + 2]

        buttons = [
            types.InlineKeyboardButton(
                title,
                callback_data="panel:" + key
            )
            for key, title in pair
        ]

        keyboard.row(*buttons)

    keyboard.row(
        types.InlineKeyboardButton(
            "🌐 وب‌سایت",
            url=WEBSITE_URL
        ),
        types.InlineKeyboardButton(
            "📢 کانال",
            url=CHANNEL_URL
        )
    )

    return keyboard


def make_back_button():
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(
        types.InlineKeyboardButton(
            "⬅️ بازگشت به پنل",
            callback_data="panel:home"
        )
    )
    return keyboard


# ---------------- START COMMAND ----------------

@bot.message_handler(commands=["start", "panel", "help"])
def start_command(message):
    if (
        message.chat.type != "private"
        and not is_owner(message.from_user.id)
    ):
        bot.reply_to(
            message,
            "پنل مالک را در گفت‌وگوی خصوصی ربات باز کن."
        )
        return

    text = (
        f"🌈 <b>{BRAND} {VERSION}</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "پنل مدیریت یکپارچه\n\n"
        "🛡 امنیت گروه\n"
        "👥 مدیریت اعضا\n"
        "🔤 تبدیل فونت\n"
        "📊 گزارش و آمار\n"
        "🎫 پشتیبانی و تیکت\n"
        "🧠 هوش مصنوعی\n"
        "💾 پشتیبان‌گیری\n\n"
        "یکی از بخش‌ها را انتخاب کن."
    )

    bot.send_message(
        message.chat.id,
        text,
        reply_markup=make_main_panel()
    )


@bot.message_handler(commands=["id"])
def id_command(message):
    bot.reply_to(
        message,
        f"🆔 شناسه کاربر: "
        f"<code>{message.from_user.id}</code>\n"
        f"شناسه چت: <code>{message.chat.id}</code>"
    )


# بخش 2 را دقیقاً به انتهای همین فایل اضافه کن.

# ==================================================
# MASIH GUARD S1000+
# بخش 2 از 5: پنل دکمه‌ها و تنظیمات امنیت
# این بخش را زیر بخش اول main.py قرار بده
# ==================================================

def section_keyboard(section):
    keyboard = types.InlineKeyboardMarkup(row_width=1)

    if section == "security":
        buttons = [
            ("🔗 ضد لینک", "toggle:anti_link"),
            ("📢 ضد تبلیغ", "toggle:anti_ads"),
            ("🚫 ضد اسپم", "toggle:anti_spam"),
            ("🔁 ضد پیام تکراری", "toggle:anti_repeat"),
            ("↪️ ضد فوروارد", "toggle:anti_forward"),
            ("🖼 قفل رسانه", "toggle:media_lock"),
        ]

    elif section == "welcome":
        buttons = [
            ("👋 خوشامدگویی", "toggle:welcome_on"),
            ("👋 پیام خداحافظی", "toggle:farewell_on"),
            ("🔐 تأیید ورود اعضا", "toggle:join_approval"),
            ("✏️ تنظیم متن خوشامد", "ask:welcome_text"),
            ("✏️ تنظیم متن خداحافظی", "ask:farewell_text"),
        ]

    elif section == "rules":
        buttons = [
            ("📜 مشاهده قوانین", "show:rules"),
            ("✏️ تنظیم قوانین", "ask:rules"),
            ("💬 افزودن پاسخ خودکار", "ask:auto_reply"),
            ("🗑 حذف پاسخ خودکار", "ask:delete_reply"),
            ("🚫 افزودن کلمه ممنوع", "ask:bad_word"),
        ]

    elif section == "members":
        buttons = [
            ("⚠️ اخطار به عضو", "ask:warn"),
            ("🔇 سکوت عضو", "ask:mute"),
            ("🔊 برداشتن سکوت", "ask:unmute"),
            ("⛔ مسدود کردن عضو", "ask:ban"),
            ("✅ آزاد کردن عضو", "ask:unban"),
            ("👢 اخراج عضو", "ask:kick"),
        ]

    elif section == "font":
        buttons = [
            ("🔤 تبدیل متن به فونت", "ask:font"),
        ]

    elif section == "proxy":
        buttons = [
            ("➕ افزودن پروکسی", "ask:add_proxy"),
            ("📋 نمایش پروکسی‌ها", "show:proxies"),
            ("🗑 حذف پروکسی", "ask:delete_proxy"),
        ]

    elif section == "stats":
        buttons = [
            ("📊 آمار ربات", "show:stats"),
            ("🧾 گزارش فعالیت", "show:logs"),
        ]

    elif section == "customers":
        buttons = [
            ("➕ افزودن مشتری", "ask:add_customer"),
            ("📋 فهرست مشتریان", "show:customers"),
            ("🔎 جست‌وجوی مشتری", "ask:find_customer"),
        ]

    elif section == "tickets":
        buttons = [
            ("🎫 ثبت تیکت", "ask:ticket"),
            ("📋 تیکت‌های من", "show:tickets"),
        ]

    elif section == "ai":
        buttons = [
            ("🧠 پرسش از هوش مصنوعی", "ask:ai"),
        ]

    elif section == "games":
        buttons = [
            ("🎮 بازی حدس عدد", "game:guess"),
            ("🏆 امتیاز من", "show:points"),
        ]

    elif section == "backup":
        buttons = [
            ("💾 دریافت نسخه پشتیبان", "show:backup"),
        ]

    elif section == "daily":
        buttons = [
            ("📅 گزارش روزانه", "show:daily"),
        ]

    elif section == "smart":
        buttons = [
            ("🧩 امنیت هوشمند", "toggle:smart_security"),
        ]

    elif section == "status":
        buttons = [
            ("🚀 وضعیت ربات", "show:status"),
        ]

    elif section == "settings":
        buttons = [
            ("⚙️ تنظیم سقف اخطار", "ask:warn_limit"),
            ("📜 تنظیم قوانین", "ask:rules"),
        ]

    else:
        buttons = []

    for label, callback in buttons:
        keyboard.add(
            types.InlineKeyboardButton(
                label,
                callback_data=callback
            )
        )

    keyboard.add(
        types.InlineKeyboardButton(
            "⬅️ بازگشت به پنل اصلی",
            callback_data="panel:home"
        )
    )

    return keyboard


def send_section(chat_id, section, message_id=None):
    title = SECTIONS.get(section, "پنل مدیریت")

    text = (
        f"🌈 <b>{BRAND} {VERSION}</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"<b>{escape_html(title)}</b>\n\n"
        "یکی از گزینه‌های زیر را انتخاب کن."
    )

    keyboard = section_keyboard(section)

    if message_id is not None:
        try:
            bot.edit_message_text(
                text,
                chat_id,
                message_id,
                reply_markup=keyboard
            )
            return
        except Exception:
            pass

    bot.send_message(
        chat_id,
        text,
        reply_markup=keyboard
    )


def user_is_group_admin(chat_id, user_id):
    if is_owner(user_id):
        return True

    try:
        member = bot.get_chat_member(chat_id, user_id)
        return member.status in ("administrator", "creator")
    except Exception:
        return False


def toggle_group_setting(chat_id, setting_name):
    settings = get_group_settings(chat_id)

    if setting_name not in settings:
        return None

    if not isinstance(settings[setting_name], bool):
        return None

    settings[setting_name] = not settings[setting_name]
    save_data()

    return settings[setting_name]


@bot.callback_query_handler(func=lambda call: True)
def handle_panel_callbacks(call):
    try:
        data = call.data or ""
        user_id = call.from_user.id
        chat_id = call.message.chat.id if call.message else user_id

        if data == "panel:home":
            if call.message:
                bot.edit_message_text(
                    f"🌈 <b>{BRAND} {VERSION}</b>\n"
                    "━━━━━━━━━━━━━━━━━━\n"
                    "پنل مدیریت یکپارچه\n\n"
                    "یکی از بخش‌ها را انتخاب کن.",
                    chat_id,
                    call.message.message_id,
                    reply_markup=make_main_panel()
                )

            bot.answer_callback_query(call.id)
            return

        if data.startswith("panel:"):
            section = data.split(":", 1)[1]

            if section not in SECTIONS:
                bot.answer_callback_query(
                    call.id,
                    "این بخش شناخته نشد."
                )
                return

            send_section(
                chat_id,
                section,
                call.message.message_id if call.message else None
            )
            bot.answer_callback_query(call.id)
            return

        if data.startswith("toggle:"):
            setting_name = data.split(":", 1)[1]

            if setting_name == "smart_security":
                if not is_owner(user_id):
                    bot.answer_callback_query(
                        call.id,
                        "فقط مالک ربات می‌تواند این گزینه را تغییر دهد.",
                        show_alert=True
                    )
                    return

                current = DATA["settings"].get(
                    "smart_security", True
                )
                DATA["settings"]["smart_security"] = not current
                save_data()

                bot.answer_callback_query(
                    call.id,
                    "امنیت هوشمند " +
                    ("روشن شد." if not current else "خاموش شد.")
                )
                return

            if not is_owner(user_id):
                if not user_is_group_admin(chat_id, user_id):
                    bot.answer_callback_query(
                        call.id,
                        "برای تغییر تنظیمات باید مدیر گروه باشی.",
                        show_alert=True
                    )
                    return

            result = toggle_group_setting(
                chat_id,
                setting_name
            )

            if result is None:
                bot.answer_callback_query(
                    call.id,
                    "این تنظیم قابل تغییر نیست.",
                    show_alert=True
                )
                return

            bot.answer_callback_query(
                call.id,
                "فعال شد." if result else "غیرفعال شد."
            )

            section = "welcome" if setting_name in (
                "welcome_on",
                "farewell_on",
                "join_approval"
            ) else "security"

            send_section(
                chat_id,
                section,
                call.message.message_id if call.message else None
            )
            return

        if data.startswith("ask:"):
            action = data.split(":", 1)[1]

            if action in (
                "add_proxy",
                "delete_proxy",
                "add_customer",
                "find_customer",
                "delete_reply",
                "bad_word",
                "warn_limit"
            ) and not is_owner(user_id):
                bot.answer_callback_query(
                    call.id,
                    "این عملیات فقط برای مالک ربات است.",
                    show_alert=True
                )
                return

            WAITING[user_id] = {
                "action": action,
                "chat_id": chat_id
            }

            prompts = {
                "welcome_text": "متن خوشامدگویی را بفرست. می‌توانی از {name} استفاده کنی.",
                "farewell_text": "متن خداحافظی را بفرست. می‌توانی از {name} استفاده کنی.",
                "rules": "متن قوانین جدید را بفرست.",
                "auto_reply": "پاسخ خودکار را با این قالب بفرست:\nکلمه کلیدی | متن پاسخ",
                "delete_reply": "کلمه کلیدی پاسخ خودکار را برای حذف بفرست.",
                "bad_word": "کلمه ممنوع را بفرست.",
                "warn": "شناسه عددی عضو را بفرست.",
                "mute": "شناسه عددی عضو را بفرست.",
                "unmute": "شناسه عددی عضو را بفرست.",
                "ban": "شناسه عددی عضو را بفرست.",
                "unban": "شناسه عددی عضو را بفرست.",
                "kick": "شناسه عددی عضو را بفرست.",
                "font": "متنی را که می‌خواهی تغییر فونت بدهی بفرست.",
                "add_proxy": "لینک پروکسی را بفرست.",
                "delete_proxy": "شماره پروکسی موردنظر را بفرست.",
                "add_customer": "اطلاعات مشتری را با قالب زیر بفرست:\nشناسه | نام | توضیحات",
                "find_customer": "شناسه مشتری را بفرست.",
                "ticket": "پیام تیکت پشتیبانی را بفرست.",
                "ai": "سؤال خود را برای هوش مصنوعی بفرست.",
                "warn_limit": "حداکثر تعداد اخطار را به‌صورت عدد بفرست."
            }

            bot.answer_callback_query(call.id)

            bot.send_message(
                user_id,
                prompts.get(action, "اطلاعات موردنیاز را بفرست.")
            )
            return

        if data.startswith("show:"):
            action = data.split(":", 1)[1]
            bot.answer_callback_query(call.id)

            # پردازش نمایش اطلاعات در بخش‌های بعدی تکمیل می‌شود.
            WAITING[user_id] = {
                "action": "show_" + action,
                "chat_id": chat_id
            }

            bot.send_message(
                user_id,
                "درخواست ثبت شد؛ پردازش این بخش در کدهای بعدی تکمیل می‌شود."
            )
            return

        if data.startswith("game:"):
            bot.answer_callback_query(call.id)
            WAITING[user_id] = {
                "action": data,
                "chat_id": chat_id
            }
            bot.send_message(
                user_id,
                "بازی در بخش بعدی تکمیل می‌شود."
            )
            return

        bot.answer_callback_query(call.id, "گزینه ناشناخته است.")

    except Exception as error:
        print("Panel callback error:", repr(error))

        try:
            bot.answer_callback_query(
                call.id,
                "خطایی رخ داد؛ دوباره تلاش کن.",
                show_alert=True
            )
        except Exception:
            pass


# پایان بخش 2

# ==================================================
# MASIH GUARD S1000+
# بخش 3 از 5: امنیت گروه و پیام‌های خودکار
# ==================================================

def get_message_text(message):
    return (getattr(message, "text", None)
            or getattr(message, "caption", None)
            or "")


def log_block(chat_id, user_id, reason):
    DATA["stats"]["blocked"] += 1
    add_log("blocked", chat_id, user_id, reason)


def send_group_notice(chat_id, text):
    try:
        bot.send_message(
            chat_id,
            text,
            disable_web_page_preview=True
        )
    except Exception as error:
        print("Group notice error:", repr(error))


def delete_message_safely(message):
    try:
        bot.delete_message(
            message.chat.id,
            message.message_id
        )
        return True
    except Exception as error:
        print("Delete message error:", repr(error))
        return False


def warn_member(chat_id, user_id, reason="تخلف از قوانین"):
    key = f"{chat_id}:{user_id}"

    DATA["warnings"][key] = DATA["warnings"].get(key, 0) + 1
    count = DATA["warnings"][key]

    settings = get_group_settings(chat_id)
    limit = int(settings.get("warn_limit", 3) or 3)

    DATA["stats"]["warns"] += 1
    add_log("warning", chat_id, user_id, reason)
    save_data()

    try:
        bot.send_message(
            chat_id,
            f"⚠️ اخطار برای کاربر <code>{user_id}</code>\n"
            f"دلیل: {escape_html(reason)}\n"
            f"تعداد اخطار: {count}/{limit}"
        )
    except Exception as error:
        print("Warning message error:", repr(error))

    if count >= limit:
        try:
            bot.ban_chat_member(chat_id, user_id)
            send_group_notice(
                chat_id,
                f"⛔ کاربر {user_id} به‌دلیل رسیدن به سقف اخطار مسدود شد."
            )
            add_log("auto_ban", chat_id, user_id, reason)
            DATA["warnings"][key] = 0
            save_data()
        except Exception as error:
            print("Auto-ban error:", repr(error))


def message_has_link(text):
    if not text:
        return False

    patterns = [
        r"https?://",
        r"www\.",
        r"t\.me/",
        r"telegram\.me/",
        r"@[A-Za-z0-9_]{5,}"
    ]

    return any(
        re.search(pattern, text, re.IGNORECASE)
        for pattern in patterns
    )


def message_has_ad(text):
    if not text:
        return False

    ad_words = [
        "تبلیغ",
        "تبلیغات",
        "خرید ممبر",
        "فروش ممبر",
        "عضوگیری",
        "کسب درآمد تضمینی"
    ]

    lowered = text.casefold()

    return any(word.casefold() in lowered for word in ad_words)


def message_is_forwarded(message):
    if getattr(message, "forward_origin", None):
        return True

    if getattr(message, "forward_from", None):
        return True

    if getattr(message, "forward_from_chat", None):
        return True

    if getattr(message, "forward_date", None):
        return True

    return False


def message_has_media(message):
    media_fields = (
        "photo",
        "video",
        "audio",
        "voice",
        "document",
        "animation",
        "sticker",
        "video_note",
        "contact",
        "location"
    )

    return any(
        getattr(message, field, None)
        for field in media_fields
    )


def process_group_security(message):
    chat = message.chat
    user = message.from_user

    if not user:
        return False

    if chat.type not in ("group", "supergroup"):
        return False

    if is_owner(user.id):
        return False

    if user_is_group_admin(chat.id, user.id):
        return False

    settings = get_group_settings(chat.id)
    text = get_message_text(message)
    user_key = f"{chat.id}:{user.id}"

    reason = None

    if settings.get("media_lock") and message_has_media(message):
        reason = "ارسال رسانه در حالت قفل رسانه"

    elif (
        settings.get("anti_forward")
        and message_is_forwarded(message)
    ):
        reason = "ارسال پیام فورواردشده"

    elif settings.get("anti_link") and message_has_link(text):
        whitelist = settings.get("whitelist", [])
        if str(user.id) not in [str(x) for x in whitelist]:
            reason = "ارسال لینک"

    elif settings.get("anti_ads") and message_has_ad(text):
        reason = "ارسال تبلیغ"

    elif text and settings.get("bad_words"):
        lowered = text.casefold()

        for bad_word in settings["bad_words"]:
            if bad_word and str(bad_word).casefold() in lowered:
                reason = "استفاده از کلمه ممنوع"
                break

    if reason:
        deleted = delete_message_safely(message)

        if deleted:
            log_block(chat.id, user.id, reason)
            warn_member(chat.id, user.id, reason)

        return deleted

    if settings.get("anti_repeat") and text:
        previous = DATA["seen"].get(user_key, {})
        now = time.time()

        if (
            previous.get("text") == text
            and now - previous.get("time", 0) < 30
        ):
            deleted = delete_message_safely(message)

            if deleted:
                log_block(chat.id, user.id, "پیام تکراری")
                warn_member(chat.id, user.id, "پیام تکراری")

            return deleted

        DATA["seen"][user_key] = {
            "text": text,
            "time": now
        }

    if settings.get("anti_spam"):
        previous = DATA["seen"].get(user_key, {})
        now = time.time()

        times = previous.get("times", [])
        times = [
            item for item in times
            if now - item < 8
        ]
        times.append(now)

        DATA["seen"].setdefault(user_key, {})["times"] = times

        if len(times) >= 7:
            deleted = delete_message_safely(message)

            if deleted:
                log_block(chat.id, user.id, "ارسال پیام‌های پرتعداد")
                warn_member(chat.id, user.id, "ارسال پیام‌های پرتعداد")

            DATA["seen"][user_key]["times"] = []
            save_data()
            return deleted

    save_data()
    return False


@bot.message_handler(
    content_types=[
        "text", "photo", "video", "audio", "voice",
        "document", "sticker", "animation", "video_note",
        "contact", "location"
    ],
    func=lambda message: message.chat.type in ("group", "supergroup")
)
def group_message_handler(message):
    try:
        DATA["stats"]["messages"] += 1

        if process_group_security(message):
            return

        settings = get_group_settings(message.chat.id)
        text = get_message_text(message)

        if not text:
            save_data()
            return

        # پاسخ خودکار
        replies = settings.get("auto_replies", {})

        for keyword, reply in replies.items():
            if keyword and keyword.casefold() in text.casefold():
                bot.reply_to(message, str(reply))
                break

        save_data()

    except Exception as error:
        print("Group message handler error:", repr(error))


@bot.message_handler(
    content_types=["new_chat_members"],
    func=lambda message: message.chat.type in ("group", "supergroup")
)
def welcome_new_members(message):
    try:
        settings = get_group_settings(message.chat.id)

        if settings.get("join_approval"):
            # تأیید واقعی ورود باید توسط ربات ادمین و با دسترسی
            # مناسب مدیریت اعضا انجام شود؛ این بخش فقط ورود را ثبت می‌کند.
            add_log(
                "join_approval_requested",
                message.chat.id,
                "",
                "ورود عضو جدید؛ تأیید خودکار هنوز پیاده‌سازی نشده"
            )

        if settings.get("welcome_on"):
            for member in message.new_chat_members:
                name = escape_html(
                    member.first_name or "دوست عزیز"
                )

                welcome = str(
                    settings.get("welcome_text", "سلام {name}!")
                ).replace("{name}", name)

                try:
                    bot.send_message(
                        message.chat.id,
                        welcome
                    )
                except Exception as error:
                    print("Welcome error:", repr(error))

                DATA["stats"]["joins"] += 1
                add_log(
                    "new_member",
                    message.chat.id,
                    member.id,
                    "ورود به گروه"
                )

        save_data()

    except Exception as error:
        print("New member handler error:", repr(error))


@bot.message_handler(
    content_types=["left_chat_member"],
    func=lambda message: message.chat.type in ("group", "supergroup")
)
def farewell_member(message):
    try:
        settings = get_group_settings(message.chat.id)

        if settings.get("farewell_on") and message.left_chat_member:
            member = message.left_chat_member
            name = escape_html(
                member.first_name or "دوست ما"
            )

            farewell = str(
                settings.get("farewell_text", "خداحافظ {name}")
            ).replace("{name}", name)

            bot.send_message(
                message.chat.id,
                farewell
            )

            add_log(
                "member_left",
                message.chat.id,
                member.id,
                "خروج از گروه"
            )

        save_data()

    except Exception as error:
        print("Farewell handler error:", repr(error))


# پایان بخش 3

# ==================================================
# MASIH GUARD S1000+
# بخش 4 از 5: مدیریت، فونت، پروکسی، تیکت و هوش مصنوعی
# ==================================================

import io
import urllib.request
import urllib.error


# ---------- ابزار مدیریت اعضا ----------

def parse_chat_and_user(value, default_chat_id):
    """
    ورودی می‌تواند فقط شناسه عضو باشد یا:
    شناسه گروه | شناسه عضو
    """
    parts = [x.strip() for x in value.split("|")]

    if len(parts) == 1:
        return int(default_chat_id), int(parts[0])

    if len(parts) == 2:
        return int(parts[0]), int(parts[1])

    raise ValueError("قالب شناسه درست نیست.")


def moderate_member(action, chat_id, user_id):
    if action == "warn":
        warn_member(chat_id, user_id, "اخطار مدیر")
        return "⚠️ اخطار ثبت شد."

    if action == "ban":
        bot.ban_chat_member(chat_id, user_id)
        add_log("manual_ban", chat_id, user_id, "مسدودسازی مدیر")
        return "⛔ عضو مسدود شد."

    if action == "unban":
        bot.unban_chat_member(
            chat_id,
            user_id,
            only_if_banned=True
        )
        add_log("unban", chat_id, user_id, "رفع مسدودی")
        return "✅ مسدودی عضو برداشته شد."

    if action == "kick":
        bot.ban_chat_member(chat_id, user_id)
        bot.unban_chat_member(
            chat_id,
            user_id,
            only_if_banned=True
        )
        add_log("kick", chat_id, user_id, "اخراج توسط مدیر")
        return "👢 عضو از گروه اخراج شد."

    if action == "mute":
        bot.restrict_chat_member(
            chat_id,
            user_id,
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
        add_log("mute", chat_id, user_id, "سکوت توسط مدیر")
        return "🔇 عضو محدود شد."

    if action == "unmute":
        bot.restrict_chat_member(
            chat_id,
            user_id,
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
        add_log("unmute", chat_id, user_id, "رفع سکوت توسط مدیر")
        return "🔊 محدودیت عضو برداشته شد."

    raise ValueError("عملیات ناشناخته است.")


# ---------- تبدیل فونت ----------

FONT_MAPS = [
    str.maketrans(
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz",
        "𝔸𝔹ℂ𝔻𝔼𝔽𝔾ℍ𝕀𝕁𝕂𝕃𝕄ℕ𝕆ℙℚℝ𝕊𝕋𝕌𝕍𝕎𝕏𝕐ℤ"
        "𝕒𝕓𝕔𝕕𝕖𝕗𝕘𝕙𝕚𝕛𝕜𝕝𝕞𝕟𝕠𝕡𝕢𝕣𝕤𝕥𝕦𝕧𝕨𝕩𝕪𝕫"
    ),
    str.maketrans(
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz",
        "𝘈𝘉𝘊𝘋𝘌𝘍𝘎𝘏𝘐𝘑𝘒𝘓𝘔𝘕𝘖𝘗𝘘𝘙𝘚𝘛𝘜𝘝𝘞𝘟𝘠𝘡"
        "𝘢𝘣𝘤𝘥𝘦𝘧𝘨𝘩𝘪𝘫𝘬𝘭𝘮𝘯𝘰𝘱𝘲𝘳𝘴𝘵𝘶𝘷𝘸𝘹𝘺𝘻"
    ),
    str.maketrans(
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz",
        "ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺ"
        "ａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ"
    )
]


def convert_font(text, style=0):
    mapping = FONT_MAPS[style % len(FONT_MAPS)]
    return text.translate(mapping)


# ---------- پروکسی‌ها ----------

def valid_proxy_link(value):
    value = value.strip()

    return (
        value.startswith("https://t.me/proxy?")
        or value.startswith("http://t.me/proxy?")
        or value.startswith("tg://proxy?")
    )


def add_proxy(value, user_id):
    value = value.strip()

    if not valid_proxy_link(value):
        return False, "لینک باید از نوع t.me/proxy یا tg://proxy باشد."

    if value in DATA["proxies"]:
        return False, "این پروکسی قبلاً ثبت شده است."

    DATA["proxies"].append(value)
    save_data()
    add_log("proxy_added", "", user_id, value)

    return True, "✅ پروکسی ذخیره شد."


# ---------- مشتریان ----------

def add_customer(customer_id, name, details=""):
    DATA["customers"][str(customer_id)] = {
        "name": name.strip(),
        "details": details.strip(),
        "created": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

    save_data()
    add_log(
        "customer_added",
        "",
        customer_id,
        name
    )


# ---------- تیکت پشتیبانی ----------

def create_ticket(user_id, username, text):
    ticket_id = str(int(time.time() * 1000))

    DATA["tickets"][ticket_id] = {
        "user_id": int(user_id),
        "username": username or "",
        "text": text[:3500],
        "status": "open",
        "created": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

    DATA["stats"]["tickets"] += 1
    save_data()

    add_log(
        "ticket_created",
        "",
        user_id,
        "Ticket " + ticket_id
    )

    try:
        bot.send_message(
            OWNER_ID,
            "🎫 <b>تیکت جدید MASIH GUARD</b>\n"
            f"شناسه تیکت: <code>{ticket_id}</code>\n"
            f"کاربر: <code>{user_id}</code>\n"
            f"نام کاربری: @{escape_html(username or 'ندارد')}\n\n"
            f"{escape_html(text[:3500])}"
        )
    except Exception as error:
        print("Ticket forwarding error:", repr(error))

    return ticket_id


# ---------- هوش مصنوعی ----------

def ask_ai(question):
    if not AI_API_KEY:
        return (
            "⚠️ کلید هوش مصنوعی تنظیم نشده است.\n"
            "در تنظیمات میزبان، مقدار AI_API_KEY را وارد کن."
        )

    payload = {
        "model": AI_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are the helpful assistant inside MASIH GUARD. "
                    "Reply clearly and safely. "
                    "Unicode and Persian text must be preserved."
                )
            },
            {
                "role": "user",
                "content": question[:6000]
            }
        ],
        "temperature": 0.7
    }

    request = urllib.request.Request(
        AI_BASE_URL + "/chat/completions",
        data=json.dumps(
            payload,
            ensure_ascii=False
        ).encode("utf-8"),
        headers={
            "Authorization": "Bearer " + AI_API_KEY,
            "Content-Type": "application/json",
            "Accept": "application/json"
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=35
        ) as response:
            result = json.loads(
                response.read().decode("utf-8")
            )

        return result["choices"][0]["message"]["content"]

    except urllib.error.HTTPError as error:
        try:
            detail = error.read().decode(
                "utf-8",
                errors="replace"
            )[:500]
        except Exception:
            detail = str(error)

        print("AI HTTP error:", detail)
        return "⚠️ سرویس هوش مصنوعی خطا داد. کلید و مدل را بررسی کن."

    except Exception as error:
        print("AI request error:", repr(error))
        return "⚠️ ارتباط با هوش مصنوعی برقرار نشد. دوباره تلاش کن."


# ---------- آمار و نسخه پشتیبان ----------

def get_stats_text():
    return (
        f"📊 <b>آمار {BRAND}</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"💬 پیام‌های بررسی‌شده: {DATA['stats']['messages']}\n"
        f"🚫 پیام‌های حذف‌شده: {DATA['stats']['blocked']}\n"
        f"⚠️ اخطارها: {DATA['stats']['warns']}\n"
        f"👥 ورود اعضا: {DATA['stats']['joins']}\n"
        f"🎫 تیکت‌ها: {DATA['stats']['tickets']}\n"
        f"🌐 پروکسی‌ها: {len(DATA['proxies'])}\n"
        f"💼 مشتریان: {len(DATA['customers'])}"
    )


def send_backup(chat_id):
    if not is_owner(chat_id):
        bot.send_message(
            chat_id,
            "⛔ نسخه پشتیبان فقط برای مالک ربات است."
        )
        return

    content = json.dumps(
        DATA,
        ensure_ascii=False,
        indent=2
    ).encode("utf-8")

    file_obj = io.BytesIO(content)
    file_obj.name = "masih_guard_backup.json"

    bot.send_document(
        chat_id,
        file_obj,
        caption="💾 نسخه پشتیبان اطلاعات MASIH GUARD"
    )


# ---------- پردازش پیام‌های خصوصی و ورودی دکمه‌ها ----------

@bot.message_handler(
    content_types=["text"],
    func=lambda message: message.chat.type == "private"
)
def private_text_handler(message):
    user_id = message.from_user.id
    text = (message.text or "").strip()

    if text.startswith("/"):
        return

    pending = WAITING.get(user_id)

    if not pending:
        return

    action = pending.get("action", "")
    default_chat_id = pending.get("chat_id", user_id)

    try:
        # فقط مالک می‌تواند تنظیمات مالکیتی را اجرا کند.
        owner_only = (
            "add_proxy", "delete_proxy", "add_customer",
            "find_customer", "delete_reply", "bad_word",
            "warn_limit", "show_backup", "show_logs",
            "show_customers", "show_daily"
        )

        if action in owner_only and not is_owner(user_id):
            WAITING.pop(user_id, None)
            bot.send_message(
                user_id,
                "⛔ این عملیات فقط برای مالک ربات است."
            )
            return

        if action in ("font",):
            results = [
                "🔤 <b>نتیجه تبدیل متن</b>",
                escape_html(text),
                escape_html(convert_font(text, 0)),
                escape_html(convert_font(text, 1)),
                escape_html(convert_font(text, 2))
            ]

            bot.send_message(
                user_id,
                "\n\n".join(results)
            )

        elif action in ("welcome_text", "farewell_text", "rules"):
            settings = get_group_settings(default_chat_id)

            key = {
                "welcome_text": "welcome_text",
                "farewell_text": "farewell_text",
                "rules": "rules"
            }[action]

            settings[key] = text[:3000]
            save_data()

            bot.send_message(
                user_id,
                "✅ ذخیره شد."
            )

        elif action == "auto_reply":
            if "|" not in text:
                bot.send_message(
                    user_id,
                    "قالب صحیح:\nکلمه کلیدی | متن پاسخ"
                )
                return

            keyword, reply = [
                part.strip()
                for part in text.split("|", 1)
            ]

            if not keyword or not reply:
                bot.send_message(
                    user_id,
                    "کلمه کلیدی و متن پاسخ نباید خالی باشند."
                )
                return

            settings = get_group_settings(default_chat_id)
            settings["auto_replies"][keyword] = reply[:2000]
            save_data()

            bot.send_message(user_id, "✅ پاسخ خودکار ثبت شد.")

        elif action == "delete_reply":
            settings = get_group_settings(default_chat_id)
            existed = settings["auto_replies"].pop(text, None)
            save_data()

            bot.send_message(
                user_id,
                "🗑 پاسخ حذف شد." if existed is not None
                else "این کلمه کلیدی پیدا نشد."
            )

        elif action == "bad_word":
            settings = get_group_settings(default_chat_id)

            if text not in settings["bad_words"]:
                settings["bad_words"].append(text[:100])

            save_data()
            bot.send_message(user_id, "✅ کلمه ممنوع ثبت شد.")

        elif action == "warn_limit":
            limit = int(text)

            if not 1 <= limit <= 20:
                raise ValueError("عدد باید بین ۱ تا ۲۰ باشد.")

            settings = get_group_settings(default_chat_id)
            settings["warn_limit"] = limit
            save_data()

            bot.send_message(user_id, "✅ سقف اخطار ذخیره شد.")

        elif action in ("warn", "mute", "unmute", "ban", "unban", "kick"):
            target_chat, target_user = parse_chat_and_user(
                text,
                default_chat_id
            )

            if not is_owner(user_id):
                # اجرای مدیریت اعضا فقط با تأیید مدیر همان گروه مجاز است.
                if not user_is_group_admin(target_chat, user_id):
                    bot.send_message(
                        user_id,
                        "⛔ برای این عملیات باید مالک ربات یا مدیر همان گروه باشی."
                    )
                    return

            result = moderate_member(
                action,
                target_chat,
                target_user
            )

            bot.send_message(user_id, result)

        elif action == "add_proxy":
            success, result = add_proxy(text, user_id)
            bot.send_message(user_id, result)

        elif action == "delete_proxy":
            index = int(text) - 1

            if not 0 <= index < len(DATA["proxies"]):
                raise ValueError("شماره پروکسی معتبر نیست.")

            removed = DATA["proxies"].pop(index)
            save_data()
            add_log("proxy_deleted", "", user_id, removed)

            bot.send_message(user_id, "🗑 پروکسی حذف شد.")

        elif action == "add_customer":
            parts = [part.strip() for part in text.split("|", 2)]

            if len(parts) < 2:
                bot.send_message(
                    user_id,
                    "قالب صحیح:\nشناسه | نام | توضیحات"
                )
                return

            customer_id = parts[0]
            customer_name = parts[1]
            details = parts[2] if len(parts) > 2 else ""

            add_customer(customer_id, customer_name, details)
            bot.send_message(user_id, "✅ مشتری ثبت شد.")

        elif action == "find_customer":
            customer = DATA["customers"].get(text)

            if not customer:
                result = "مشتری پیدا نشد."
            else:
                result = (
                    f"💼 <b>{escape_html(customer['name'])}</b>\n"
                    f"شناسه: <code>{escape_html(text)}</code>\n"
                    f"توضیحات: {escape_html(customer['details'])}\n"
                    f"تاریخ ثبت: {escape_html(customer['created'])}"
                )

            bot.send_message(user_id, result)

        elif action == "ticket":
            ticket_id = create_ticket(
                user_id,
                message.from_user.username,
                text
            )

            bot.send_message(
                user_id,
                f"🎫 تیکت ثبت شد.\nشناسه: <code>{ticket_id}</code>"
            )

        elif action == "ai":
            bot.send_message(user_id, "🧠 در حال دریافت پاسخ...")

            answer = ask_ai(text)

            bot.send_message(
                user_id,
                escape_html(answer[:4000])
            )

        elif action == "show_stats":
            bot.send_message(user_id, get_stats_text())

        elif action == "show_status":
            bot.send_message(
                user_id,
                f"🚀 <b>{BRAND} {VERSION}</b>\n"
                "ربات در حال اجراست.\n"
                f"کلید هوش مصنوعی: {'تنظیم شده' if AI_API_KEY else 'تنظیم نشده'}"
            )

        elif action == "show_proxies":
            if not DATA["proxies"]:
                bot.send_message(user_id, "فهرست پروکسی‌ها خالی است.")
            else:
                lines = [
                    f"{i + 1}. {escape_html(proxy)}"
                    for i, proxy in enumerate(DATA["proxies"])
                ]

                bot.send_message(
                    user_id,
                    "🌐 <b>فهرست پروکسی‌ها</b>\n\n"
                    + "\n".join(lines)
                )

        elif action == "show_customers":
            if not DATA["customers"]:
                bot.send_message(user_id, "مشتری ثبت‌شده‌ای وجود ندارد.")
            else:
                lines = []

                for customer_id, customer in list(
                    DATA["customers"].items()
                )[:50]:
                    lines.append(
                        f"• {escape_html(customer['name'])} "
                        f"— <code>{escape_html(customer_id)}</code>"
                    )

                bot.send_message(
                    user_id,
                    "💼 <b>مشتریان</b>\n\n" + "\n".join(lines)
                )

        elif action == "show_logs":
            recent = DATA["logs"][-20:]

            if not recent:
                bot.send_message(user_id, "گزارشی ثبت نشده است.")
            else:
                lines = []

                for item in recent:
                    lines.append(
                        f"{escape_html(item['time'])} — "
                        f"{escape_html(item['action'])} — "
                        f"{escape_html(item['detail'])}"
                    )

                bot.send_message(
                    user_id,
                    "🧾 <b>آخرین گزارش‌ها</b>\n\n"
                    + "\n".join(lines)
                )

        elif action == "show_backup":
            send_backup(user_id)

        elif action == "show_daily":
            bot.send_message(
                user_id,
                get_stats_text()
                + "\n\nگزارش فعلی از شمارنده‌های ذخیره‌شده ساخته شده است."
            )

        elif action == "show_tickets":
            tickets = [
                (ticket_id, ticket)
                for ticket_id, ticket in DATA["tickets"].items()
                if ticket["user_id"] == user_id or is_owner(user_id)
            ]

            if not tickets:
                bot.send_message(user_id, "تیکتی ثبت نشده است.")
            else:
                lines = []

                for ticket_id, ticket in tickets[-15:]:
                    lines.append(
                        f"🎫 <code>{escape_html(ticket_id)}</code> "
                        f"— {escape_html(ticket['status'])}\n"
                        f"{escape_html(ticket['text'][:200])}"
                    )

                bot.send_message(
                    user_id,
                    "\n\n".join(lines)
                )

        elif action == "show_points":
            points = DATA["points"].get(str(user_id), 0)

            bot.send_message(
                user_id,
                f"🏆 امتیاز شما: {points}"
            )

        elif action == "game:guess":
            try:
                guess = int(text)
            except ValueError:
                bot.send_message(
                    user_id,
                    "یک عدد بین ۱ تا 5 بفرست."
                )
                return

            if not 1 <= guess <= 5:
                bot.send_message(
                    user_id,
                    "عدد باید بین ۱ تا ۵ باشد."
                )
                return

            answer = random.randint(1, 5)

            if guess == answer:
                DATA["points"][str(user_id)] = (
                    DATA["points"].get(str(user_id), 0) + 1
                )
                save_data()

                bot.send_message(
                    user_id,
                    f"🎉 درست حدس زدی! عدد {answer} بود.\n"
                    "🏆 یک امتیاز گرفتی."
                )
            else:
                bot.send_message(
                    user_id,
                    f"این بار نه! عدد درست {answer} بود."
                )

        else:
            bot.send_message(
                user_id,
                "این عملیات هنوز در نسخه فعلی پیاده‌سازی نشده است."
            )

        WAITING.pop(user_id, None)

    except (ValueError, TypeError) as error:
        bot.send_message(
            user_id,
            "⚠️ ورودی معتبر نیست.\n"
            + escape_html(str(error))
        )

    except Exception as error:
        print("Private action error:", repr(error))

        bot.send_message(
            user_id,
            "⚠️ انجام عملیات با خطا روبه‌رو شد. "
            "دسترسی ربات و اطلاعات واردشده را بررسی کن."
        )


# پایان بخش 4

# ============================================================
# PART 5 — MASIH GUARD S1000+ | AI ASSISTANT
# دستیار هوش مصنوعی فارسی
# ============================================================

import urllib.request
import urllib.error


AI_API_KEY = os.getenv("AI_API_KEY", "").strip()
AI_API_URL = os.getenv(
    "AI_API_URL",
    "https://api.openai.com/v1/chat/completions"
).strip()
AI_MODEL = os.getenv("AI_MODEL", "gpt-4o-mini").strip()


def masih_ai_request(question):
    """ارسال پرسش به سرویس هوش مصنوعی"""

    if not AI_API_KEY:
        return (
            "⚠️ کلید هوش مصنوعی تنظیم نشده است.\n\n"
            "در تنظیمات محیطی هاست، متغیر AI_API_KEY "
            "را با کلید معتبر خودت اضافه کن."
        )

    payload = {
        "model": AI_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "تو دستیار فارسی ربات MASIH GUARD هستی. "
                    "فارسی روان، دقیق و دوستانه پاسخ بده. "
                    "اگر پاسخ را نمی‌دانی، صادقانه بگو."
                )
            },
            {
                "role": "user",
                "content": question[:4000]
            }
        ],
        "temperature": 0.7,
        "max_tokens": 1200
    }

    request = urllib.request.Request(
        AI_API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": "Bearer " + AI_API_KEY,
            "Content-Type": "application/json"
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            result = json.loads(
                response.read().decode("utf-8")
            )

        answer = result["choices"][0]["message"]["content"]

        if isinstance(answer, str) and answer.strip():
            return answer.strip()

        return "⚠️ پاسخ معتبری از سرویس هوش مصنوعی دریافت نشد."

    except urllib.error.HTTPError as error:
        if error.code == 401:
            return "❌ کلید هوش مصنوعی معتبر نیست."
        if error.code == 429:
            return "⏳ محدودیت درخواست یا اعتبار سرویس را بررسی کن."
        return "❌ سرویس هوش مصنوعی خطای HTTP داد: " + str(error.code)

    except Exception:
        return "❌ ارتباط با هوش مصنوعی برقرار نشد؛ تنظیمات و اتصال هاست را بررسی کن."


@bot.message_handler(commands=["ai", "ask"])
def masih_ai_command(message):
    question = message.text or ""
    question = question.split(maxsplit=1)

    if len(question) < 2 or not question[1].strip():
        bot.reply_to(
            message,
            "🤖 دستیار هوش مصنوعی MASIH GUARD\n\n"
            "سؤالت را بعد از دستور بنویس:\n"
            "/ai سلام، خودت را معرفی کن"
        )
        return

    status = bot.reply_to(
        message,
        "🤖 در حال بررسی سؤال تو..."
    )

    answer = masih_ai_request(question[1].strip())

    # تقسیم پاسخ‌های طولانی برای محدودیت پیام تلگرام
    chunks = [
        answer[i:i + 4000]
        for i in range(0, len(answer), 4000)
    ]

    try:
        bot.edit_message_text(
            chunks[0],
            chat_id=status.chat.id,
            message_id=status.message_id
        )

        for chunk in chunks[1:]:
            bot.send_message(message.chat.id, chunk)

    except Exception:
        try:
            bot.send_message(message.chat.id, answer[:4000])
        except Exception:
            pass


# پایان بخش پنجم
