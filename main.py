
# -*- coding: utf-8 -*-
# MASIH GUARD | Persian Telegram Group Manager
# Developer: Masih Mokhtari
# Library: pyTelegramBotAPI

import os
import re
import ast
import json
import time
import math
import html
import random
import string
import logging
import threading
from collections import defaultdict, deque
from datetime import datetime, timezone

import telebot
from telebot import types

# -------------------- CONFIG --------------------

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
DATA_FILE = "masih_guard_data.json"

if not TOKEN:
    raise RuntimeError(
        "متغیر TELEGRAM_BOT_TOKEN در تنظیمات هاست تنظیم نشده است."
    )

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s"
)
logger = logging.getLogger("MASIH_GUARD")

bot = telebot.TeleBot(TOKEN, parse_mode="HTML", threaded=True)

LOCK = threading.RLock()
GROUP_DATA = {}
WARNINGS = defaultdict(lambda: defaultdict(int))
USER_MESSAGES = defaultdict(deque)

DEFAULT_SETTINGS = {
    "anti_link": False,
    "anti_spam": False,
    "filter_words": False,
    "welcome": True,
    "goodbye": True,
    "welcome_text": "سلام {name} عزیز! به گروه خوش اومدی 🌈",
    "rules": "۱. احترام به اعضا الزامی است.\n۲. تبلیغات ممنوع است.\n۳. از ارسال پیام تکراری خودداری کنید.",
    "bad_words": [],
    "logs": []
}

# -------------------- STORAGE --------------------

def load_data():
    global GROUP_DATA, WARNINGS
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        GROUP_DATA = data.get("groups", {})
        WARNINGS.update(data.get("warnings", {}))
        logger.info("اطلاعات ذخیره‌شده بارگذاری شد.")
    except FileNotFoundError:
        logger.info("فایل ذخیره‌سازی جدید ساخته خواهد شد.")
    except Exception:
        logger.exception("خطا در خواندن اطلاعات ذخیره‌شده")

def save_data():
    with LOCK:
        try:
            payload = {
                "groups": GROUP_DATA,
                "warnings": dict(WARNINGS)
            }
            temp = DATA_FILE + ".tmp"
            with open(temp, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            os.replace(temp, DATA_FILE)
        except Exception:
            logger.exception("خطا در ذخیره اطلاعات")

def settings(chat_id):
    key = str(chat_id)
    with LOCK:
        if key not in GROUP_DATA:
            GROUP_DATA[key] = dict(DEFAULT_SETTINGS)
        else:
            for k, v in DEFAULT_SETTINGS.items():
                GROUP_DATA[key].setdefault(k, v.copy() if isinstance(v, list) else v)
        return GROUP_DATA[key]

def log_action(chat_id, text):
    s = settings(chat_id)
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    s["logs"].append(f"{stamp} | {text}")
    s["logs"] = s["logs"][-100:]
    save_data()

def safe_text(value):
    return html.escape(str(value or ""))

def is_group(message):
    return message.chat.type in ("group", "supergroup")

def is_admin(chat_id, user_id):
    try:
        member = bot.get_chat_member(chat_id, user_id)
        return member.status in ("administrator", "creator")
    except Exception:
        return False

def is_owner(message):
    return is_admin(message.chat.id, message.from_user.id)

def reply(message, text, **kwargs):
    try:
        return bot.reply_to(message, text, **kwargs)
    except Exception:
        logger.exception("خطا در ارسال پاسخ")
        return None

def require_group_admin(message):
    if not is_group(message):
        reply(message, "❌ این دستور فقط داخل گروه قابل استفاده است.")
        return False
    if not is_owner(message):
        reply(message, "⛔ فقط مدیران گروه اجازه استفاده از این دستور را دارند.")
        return False
    return True

# -------------------- MAIN MENU --------------------

def main_menu():
    kb = types.InlineKeyboardMarkup(row_width=2)
    buttons = [
        ("🛡️ امنیت گروه", "security"),
        ("🔨 مدیریت اعضا", "moderation"),
        ("👋 خوشامدگویی", "welcome"),
        ("📜 قوانین گروه", "rules"),
        ("📋 گزارش‌ها", "logs"),
        ("🧰 ابزارها", "tools"),
        ("⚙️ تنظیمات", "settings"),
        ("📊 وضعیت ربات", "status"),
        ("❓ راهنما", "help"),
        ("👨‍💻 درباره سازنده", "about"),
    ]
    for label, data in buttons:
        kb.add(types.InlineKeyboardButton(label, callback_data=data))
    return kb

def section_menu(section, chat_id=None):
    kb = types.InlineKeyboardMarkup(row_width=1)

    if section == "security":
        s = settings(chat_id) if chat_id is not None else DEFAULT_SETTINGS
        items = [
            ("لینک‌یاب: " + ("روشن 🟢" if s["anti_link"] else "خاموش 🔴"), "toggle:anti_link"),
            ("ضداسپم: " + ("روشن 🟢" if s["anti_spam"] else "خاموش 🔴"), "toggle:anti_spam"),
            ("فیلتر کلمات: " + ("روشن 🟢" if s["filter_words"] else "خاموش 🔴"), "toggle:filter_words"),
        ]
    elif section == "welcome":
        s = settings(chat_id) if chat_id is not None else DEFAULT_SETTINGS
        items = [
            ("خوشامدگویی: " + ("روشن 🟢" if s["welcome"] else "خاموش 🔴"), "toggle:welcome"),
            ("خداحافظی: " + ("روشن 🟢" if s["goodbye"] else "خاموش 🔴"), "toggle:goodbye"),
        ]
    else:
        items = []

    for label, data in items:
        kb.add(types.InlineKeyboardButton(label, callback_data=data))
    kb.add(types.InlineKeyboardButton("🔙 منوی اصلی", callback_data="home"))
    return kb

@bot.message_handler(commands=["start", "help"])
def start_command(message):
    text = (
        "🛡️ <b>به MASIH GUARD خوش اومدی!</b>\n\n"
        "ربات مدیریت و ابزارهای گروه با منوی فارسی.\n\n"
        "برای باز کردن پنل، دستور /panel رو بزن.\n"
        "برای دیدن دستورات، /commands رو بزن.\n\n"
        "👨‍💻 سازنده: <b>مسیح مختاری | Masih Hackring</b>"
    )
    bot.send_message(message.chat.id, text, reply_markup=main_menu())

@bot.message_handler(commands=["panel", "menu"])
def panel_command(message):
    bot.send_message(
        message.chat.id,
        "🌈 <b>پنل مدیریت MASIH GUARD</b>\nیک بخش رو انتخاب کن:",
        reply_markup=main_menu()
    )

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    try:
        data = call.data
        chat_id = call.message.chat.id

        if data == "home":
            bot.edit_message_text(
                "🌈 <b>پنل MASIH GUARD</b>\nیک بخش رو انتخاب کن:",
                chat_id, call.message.message_id,
                reply_markup=main_menu()
            )

        elif data in ("security", "welcome"):
            titles = {
                "security": "🛡️ تنظیمات امنیت گروه",
                "welcome": "👋 تنظیمات خوشامدگویی"
            }
            bot.edit_message_text(
                titles[data] + "\n\nبرای تغییر وضعیت روی گزینه موردنظر بزن.",
                chat_id, call.message.message_id,
                reply_markup=section_menu(data, chat_id)
            )

        elif data.startswith("toggle:"):
            if call.message.chat.type not in ("group", "supergroup"):
                bot.answer_callback_query(
                    call.id,
                    "این گزینه را از داخل گروه باز کن.",
                    show_alert=True
                )
                return

            if not is_admin(chat_id, call.from_user.id):
                bot.answer_callback_query(
                    call.id,
                    "فقط مدیر گروه می‌تواند تنظیمات را تغییر دهد.",
                    show_alert=True
                )
                return

            key = data.split(":", 1)[1]
            if key not in DEFAULT_SETTINGS:
                bot.answer_callback_query(call.id, "گزینه نامعتبر است.")
                return

            s = settings(chat_id)
            s[key] = not bool(s[key])
            save_data()
            log_action(chat_id, f"تغییر تنظیم {key} توسط {call.from_user.id}")

            section = "welcome" if key in ("welcome", "goodbye") else "security"
            bot.edit_message_text(
                "⚙️ تنظیمات به‌روزرسانی شد.",
                chat_id, call.message.message_id,
                reply_markup=section_menu(section, chat_id)
            )

        elif data == "moderation":
            text = (
                "🔨 <b>مدیریت اعضا</b>\n\n"
                "/warn — اخطار\n"
                "/warnings — مشاهده اخطارها\n"
                "/mute 10 — سکوت ۱۰ دقیقه‌ای\n"
                "/unmute — برداشتن سکوت\n"
                "/ban — مسدود کردن\n"
                "/unban — رفع مسدودیت\n"
                "/kick — اخراج عضو\n"
                "/purge 10 — حذف پیام‌ها\n\n"
                "برای اعمال دستورات، به پیام عضو پاسخ بده."
            )
            bot.edit_message_text(
                text, chat_id, call.message.message_id,
                reply_markup=back_menu()
            )

        elif data == "rules":
            text = (
                "📜 <b>قوانین گروه</b>\n\n"
                "برای دیدن قوانین: /rules\n"
                "برای تنظیم قوانین: /setrules متن قوانین\n"
                "برای تنظیم، باید مدیر گروه باشی."
            )
            bot.edit_message_text(
                text, chat_id, call.message.message_id,
                reply_markup=back_menu()
            )

        elif data == "logs":
            logs = settings(chat_id)["logs"][-10:]
            text = "📋 <b>آخرین گزارش‌ها</b>\n\n" + (
                "\n".join(safe_text(x) for x in logs) if logs else "هنوز گزارشی ثبت نشده."
            )
            bot.edit_message_text(
                text, chat_id, call.message.message_id,
                reply_markup=back_menu()
            )

        elif data == "tools":
            text = (
                "🧰 <b>ابزارهای ربات</b>\n\n"
                "/id — شناسه چت و کاربر\n"
                "/calc 2+2 — ماشین‌حساب\n"
                "/dice — تاس\n"
                "/fancy Hello — متن فانتزی انگلیسی\n"
                "/poll | سؤال | گزینه ۱ | گزینه ۲ — نظرسنجی\n"
                "/commands — فهرست دستورات"
            )
            bot.edit_message_text(
                text, chat_id, call.message.message_id,
                reply_markup=back_menu()
            )

        elif data == "settings":
            text = (
                "⚙️ <b>تنظیمات</b>\n\n"
                "برای امنیت و خوشامدگویی، از منوهای مربوطه استفاده کن.\n"
                "تنظیمات هر گروه جداگانه ذخیره می‌شوند."
            )
            bot.edit_message_text(
                text, chat_id, call.message.message_id,
                reply_markup=back_menu()
            )

        elif data == "status":
            me = bot.get_me()
            bot.edit_message_text(
                f"📊 <b>وضعیت ربات</b>\n\n"
                f"نام: {safe_text(me.first_name)}\n"
                f"شناسه: <code>{me.id}</code>\n"
                f"وضعیت: فعال 🟢\n"
                f"گروه‌های دارای تنظیمات: {len(GROUP_DATA)}",
                chat_id, call.message.message_id,
                reply_markup=back_menu()
            )

        elif data == "help":
            bot.edit_message_text(
                "❓ <b>راهنما</b>\n\n"
                "۱. ربات را به گروه اضافه کن.\n"
                "۲. برای حذف لینک‌ها و مدیریت اعضا، دسترسی مدیر بده.\n"
                "۳. دستور /panel را اجرا کن.\n"
                "۴. تنظیمات امنیتی به‌صورت پیش‌فرض خاموش‌اند.\n\n"
                "دستورات بیشتر: /commands",
                chat_id, call.message.message_id,
                reply_markup=back_menu()
            )

        elif data == "about":
            bot.edit_message_text(
                "👨‍💻 <b>MASIH GUARD</b>\n\n"
                "ساخته‌شده توسط مسیح مختاری\n"
                "<b>Masih Hackring</b>\n\n"
                "🛡️ مدیریت گروه | ابزارهای کاربردی | تنظیمات فارسی",
                chat_id, call.message.message_id,
                reply_markup=back_menu()
            )

        bot.answer_callback_query(call.id)

    except Exception:
        logger.exception("خطا در پنل")
        try:
            bot.answer_callback_query(call.id, "خطا رخ داد؛ دوباره امتحان کن.")
        except Exception:
            pass

def back_menu():
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🔙 منوی اصلی", callback_data="home"))
    return kb

@bot.message_handler(commands=["commands"])
def commands_list(message):
    bot.reply_to(
        message,
        "📚 <b>فهرست دستورات</b>\n\n"
        "/panel — پنل\n"
        "/id — شناسه‌ها\n"
        "/rules — قوانین\n"
        "/setrules متن — تنظیم قوانین\n"
        "/setwelcome متن — تنظیم خوشامدگویی\n"
        "/addword کلمه — افزودن کلمه فیلتر\n"
        "/delword کلمه — حذف کلمه فیلتر\n"
        "/words — فهرست کلمات فیلتر\n"
        "/warn — اخطار به عضو با پاسخ به پیام\n"
        "/warnings — تعداد اخطار عضو\n"
        "/mute 10 — سکوت به دقیقه\n"
        "/unmute — رفع سکوت\n"
        "/ban — مسدودسازی\n"
        "/unban شناسه — رفع مسدودیت\n"
        "/kick — اخراج\n"
        "/purge 10 — حذف پیام‌های اخیر\n"
        "/calc 2+2 — ماشین‌حساب\n"
        "/dice — تاس\n"
        "/fancy Hello — متن فانتزی\n"
        "/poll | سؤال | گزینه۱ | گزینه۲ — نظرسنجی"
    )

# -------------------- RULES & WELCOME --------------------

@bot.message_handler(commands=["rules"])
def show_rules(message):
    s = settings(message.chat.id)
    bot.reply_to(message, "📜 <b>قوانین گروه</b>\n\n" + safe_text(s["rules"]))

@bot.message_handler(commands=["setrules"])
def set_rules(message):
    if not require_group_admin(message):
        return
    value = message.text.partition(" ")[2].strip()
    if not value:
        reply(message, "نمونه: /setrules احترام به همه الزامی است.")
        return
    settings(message.chat.id)["rules"] = value[:3500]
    save_data()
    log_action(message.chat.id, "قوانین گروه تغییر کرد")
    reply(message, "✅ قوانین گروه ذخیره شد.")

@bot.message_handler(commands=["setwelcome"])
def set_welcome(message):
    if not require_group_admin(message):
        return
    value = message.text.partition(" ")[2].strip()
    if not value:
        reply(message, "نمونه: /setwelcome سلام {name} به گروه خوش اومدی!")
        return
    settings(message.chat.id)["welcome_text"] = value[:1000]
    save_data()
    reply(message, "✅ متن خوشامدگویی ذخیره شد.\nبرای نام عضو از {name} استفاده کن.")

@bot.message_handler(content_types=["new_chat_members"])
def welcome_members(message):
    s = settings(message.chat.id)
    if not s["welcome"]:
        return
    for user in message.new_chat_members:
        if user.is_bot:
            continue
        name = safe_text(user.first_name or "دوست عزیز")
        template = str(s["welcome_text"])
        template = template.replace("{name}", name)
        template = template.replace("{group}", safe_text(message.chat.title))
        bot.send_message(message.chat.id, "👋 " + template)

@bot.message_handler(content_types=["left_chat_member"])
def goodbye_member(message):
    s = settings(message.chat.id)
    if s["goodbye"]:
        name = safe_text(message.left_chat_member.first_name)
        bot.send_message(message.chat.id, f"👋 خداحافظ {name}!")

# -------------------- FILTER SETTINGS --------------------

@bot.message_handler(commands=["addword"])
def add_word(message):
    if not require_group_admin(message):
        return
    word = message.text.partition(" ")[2].strip().lower()
    if not word:
        reply(message, "نمونه: /addword کلمه")
        return
    s = settings(message.chat.id)
    if word not in s["bad_words"]:
        s["bad_words"].append(word[:100])
        save_data()
    reply(message, "✅ کلمه به فهرست فیلتر اضافه شد.")

@bot.message_handler(commands=["delword"])
def delete_word(message):
    if not require_group_admin(message):
        return
    word = message.text.partition(" ")[2].strip().lower()
    s = settings(message.chat.id)
    if word in s["bad_words"]:
        s["bad_words"].remove(word)
        save_data()
        reply(message, "✅ کلمه حذف شد.")
    else:
        reply(message, "این کلمه در فهرست نیست.")

@bot.message_handler(commands=["words"])
def list_words(message):
    s = settings(message.chat.id)
    words = s["bad_words"]
    reply(
        message,
        "📃 <b>کلمات فیلترشده</b>\n\n" +
        ("\n".join("• " + safe_text(w) for w in words) if words else "فهرست خالی است.")
    )

# -------------------- MODERATION --------------------

def target_from_reply(message):
    if not message.reply_to_message:
        reply(message, "❗ برای استفاده، به پیام عضو موردنظر پاسخ بده.")
        return None
    target = message.reply_to_message.from_user
    if not target or target.is_bot:
        reply(message, "❌ این عضو قابل مدیریت نیست.")
        return None
    if target.id == message.from_user.id:
        reply(message, "❌ نمی‌توانی این دستور را روی خودت اجرا کنی.")
        return None
    if is_admin(message.chat.id, target.id):
        reply(message, "⛔ نمی‌توان مدیر گروه را با این دستور مدیریت کرد.")
        return None
    return target

@bot.message_handler(commands=["warn"])
def warn_user(message):
    if not require_group_admin(message):
        return
    target = target_from_reply(message)
    if not target:
        return
    key = str(message.chat.id)
    WARNINGS[key][str(target.id)] += 1
    count = WARNINGS[key][str(target.id)]
    save_data()
    log_action(message.chat.id, f"اخطار به {target.id}؛ تعداد {count}")
    reply(message, f"⚠️ به <a href='tg://user?id={target.id}'>{safe_text(target.first_name)}</a> اخطار داده شد.\nتعداد اخطار: {count}")

@bot.message_handler(commands=["warnings"])
def show_warnings(message):
    if not is_group(message):
        reply(message, "این دستور را در گروه اجرا کن.")
        return
    target = message.reply_to_message.from_user if message.reply_to_message else message.from_user
    count = WARNINGS[str(message.chat.id)][str(target.id)]
    reply(message, f"⚠️ تعداد اخطارهای {safe_text(target.first_name)}: {count}")

@bot.message_handler(commands=["mute"])
def mute_user(message):
    if not require_group_admin(message):
        return
    target = target_from_reply(message)
    if not target:
        return
    parts = message.text.split()
    try:
        minutes = int(parts[1]) if len(parts) > 1 else 10
        minutes = max(1, min(minutes, 10080))
    except ValueError:
        reply(message, "زمان باید عدد باشد. نمونه: /mute 10")
        return
    try:
        until = int(time.time()) + minutes * 60
        bot.restrict_chat_member(
            message.chat.id,
            target.id,
            until_date=until,
            permissions=types.ChatPermissions(can_send_messages=False)
        )
        log_action(message.chat.id, f"سکوت {target.id} برای {minutes} دقیقه")
        reply(message, f"🔇 {safe_text(target.first_name)} به مدت {minutes} دقیقه سکوت شد.")
    except Exception as e:
        logger.exception("خطا در سکوت عضو")
        reply(message, "❌ انجام نشد. مطمئن شو ربات مدیر و دارای دسترسی محدودکردن اعضاست.")

@bot.message_handler(commands=["unmute"])
def unmute_user(message):
    if not require_group_admin(message):
        return
    target = target_from_reply(message)
    if not target:
        return
    try:
        bot.restrict_chat_member(
            message.chat.id,
            target.id,
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
        reply(message, f"🔊 سکوت {safe_text(target.first_name)} برداشته شد.")
        log_action(message.chat.id, f"رفع سکوت {target.id}")
    except Exception:
        logger.exception("خطا در رفع سکوت")
        reply(message, "❌ خطا. دسترسی‌های مدیر ربات را بررسی کن.")

@bot.message_handler(commands=["ban"])
def ban_user(message):
    if not require_group_admin(message):
        return
    target = target_from_reply(message)
    if not target:
        return
    try:
        bot.ban_chat_member(message.chat.id, target.id)
        log_action(message.chat.id, f"مسدودسازی {target.id}")
        reply(message, f"⛔ {safe_text(target.first_name)} از گروه مسدود شد.")
    except Exception:
        logger.exception("خطا در مسدودسازی")
        reply(message, "❌ مسدودسازی انجام نشد؛ دسترسی ربات را بررسی کن.")

@bot.message_handler(commands=["kick"])
def kick_user(message):
    if not require_group_admin(message):
        return
    target = target_from_reply(message)
    if not target:
        return
    try:
        bot.ban_chat_member(message.chat.id, target.id)
        bot.unban_chat_member(message.chat.id, target.id)
        log_action(message.chat.id, f"اخراج {target.id}")
        reply(message, f"👢 {safe_text(target.first_name)} از گروه اخراج شد.")
    except Exception:
        logger.exception("خطا در اخراج")
        reply(message, "❌ اخراج انجام نشد؛ دسترسی ربات را بررسی کن.")

@bot.message_handler(commands=["unban"])
def unban_user(message):
    if not require_group_admin(message):
        return
    parts = message.text.split()
    try:
        user_id = int(parts[1]) if len(parts) > 1 else None
    except ValueError:
        user_id = None
    if user_id is None:
        reply(message, "نمونه: /unban 123456789")
        return
    try:
        bot.unban_chat_member(message.chat.id, user_id, only_if_banned=True)
        log_action(message.chat.id, f"رفع مسدودیت {user_id}")
        reply(message, "✅ مسدودیت کاربر برداشته شد.")
    except Exception:
        logger.exception("خطا در رفع مسدودیت")
        reply(message, "❌ انجام نشد؛ شناسه و دسترسی ربات را بررسی کن.")

@bot.message_handler(commands=["purge"])
def purge_messages(message):
    if not require_group_admin(message):
        return
    try:
        amount = int(message.text.split()[1]) if len(message.text.split()) > 1 else 10
        amount = max(1, min(amount, 100))
    except ValueError:
        reply(message, "نمونه: /purge 10")
        return
    if not message.reply_to_message:
        reply(message, "به اولین پیامی که می‌خواهی پاک شود پاسخ بده و /purge 10 را اجرا کن.")
        return
    start_id = message.reply_to_message.message_id
    deleted = 0
    for msg_id in range(start_id, min(start_id + amount, start_id + 100)):
        try:
            bot.delete_message(message.chat.id, msg_id)
            deleted += 1
        except Exception:
            pass
    try:
        bot.delete_message(message.chat.id, message.message_id)
    except Exception:
        pass
    log_action(message.chat.id, f"پاک‌سازی {deleted} پیام")
    bot.send_message(message.chat.id, f"🧹 تعداد {deleted} پیام حذف شد.")

# -------------------- TOOLS --------------------

@bot.message_handler(commands=["id"])
def id_command(message):
    user = message.from_user
    text = (
        "🆔 <b>اطلاعات شناسه</b>\n\n"
        f"شناسه چت: <code>{message.chat.id}</code>\n"
        f"شناسه شما: <code>{user.id}</code>\n"
        f"نام: {safe_text(user.first_name)}"
    )
    if message.reply_to_message:
        target = message.reply_to_message.from_user
        text += f"\nشناسه عضو پاسخ‌داده‌شده: <code>{target.id}</code>"
    reply(message, text)

# Calculator allows only arithmetic operations, not arbitrary Python code.
def safe_calculate(expression):
    if len(expression) > 100:
        raise ValueError("عبارت بیش از حد طولانی است.")
    tree = ast.parse(expression, mode="eval")
    allowed_bin = (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow)
    allowed_unary = (ast.UAdd, ast.USub)

    def evaluate(node):
        if isinstance(node, ast.Expression):
            return evaluate(node.body)
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            if abs(node.value) > 10**12:
                raise ValueError("عدد بیش از حد بزرگ است.")
            return node.value
        if isinstance(node, ast.BinOp) and isinstance(node.op, allowed_bin):
            left, right = evaluate(node.left), evaluate(node.right)
            if isinstance(node.op, ast.Pow) and abs(right) > 10:
                raise ValueError("توان بیش از حد بزرگ است.")
            result = {
                ast.Add: lambda: left + right,
                ast.Sub: lambda: left - right,
                ast.Mult: lambda: left * right,
                ast.Div: lambda: left / right,
                ast.FloorDiv: lambda: left // right,
                ast.Mod: lambda: left % right,
                ast.Pow: lambda: left ** right
            }[type(node.op)]()
            if abs(result) > 10**100:
                raise ValueError("نتیجه بیش از حد بزرگ است.")
            return result
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, allowed_unary):
            value = evaluate(node.operand)
            return value if isinstance(node.op, ast.UAdd) else -value
        raise ValueError("عبارت نامعتبر است.")
    return evaluate(tree)

@bot.message_handler(commands=["calc"])
def calc_command(message):
    expression = message.text.partition(" ")[2].strip()
    if not expression:
        reply(message, "نمونه: /calc 12*(5+3)")
        return
    try:
        result = safe_calculate(expression)
        reply(message, f"🧮 نتیجه: <code>{safe_text(result)}</code>")
    except Exception:
        reply(message, "❌ عبارت ریاضی معتبر نیست یا محاسبه ممکن نیست.")

@bot.message_handler(commands=["dice"])
def dice_command(message):
    bot.send_dice(message.chat.id, emoji="🎲")

FANCY_SOURCE = string.ascii_lowercase + string.ascii_uppercase
FANCY_TARGET = (
    "𝕒𝕓𝕔𝕕𝕖𝕗𝕘𝕙𝕚𝕛𝕜𝕝𝕞𝕟𝕠𝕡𝕢𝕣𝕤𝕥𝕦𝕧𝕨𝕩𝕪𝕫"
    "𝔸𝔹ℂ𝔻𝔼𝔽𝔾ℍ𝕀𝕁𝕂𝕃𝕄ℕ𝕆ℙℚℝ𝕊𝕋𝕌𝕍𝕎𝕏𝕐ℤ"
)
FANCY_MAP = dict(zip(FANCY_SOURCE, FANCY_TARGET))

@bot.message_handler(commands=["fancy"])
def fancy_command(message):
    value = message.text.partition(" ")[2].strip()
    if not value:
        reply(message, "نمونه: /fancy Hello Masih")
        return
    result = "".join(FANCY_MAP.get(c, c) for c in value)
    reply(message, "✨ " + safe_text(result))

@bot.message_handler(commands=["poll"])
def poll_command(message):
    parts = [p.strip() for p in message.text.split("|")]
    if len(parts) < 4:
        reply(message, "نمونه:\n/poll | بهترین رنگ؟ | آبی | قرمز")
        return
    question = parts[1][:250]
    options = parts[2:12]
    if len(options) < 2 or any(not x for x in options):
        reply(message, "حداقل دو گزینه غیرخالی بنویس.")
        return
    try:
        bot.send_poll(
            message.chat.id,
            question,
            options,
            is_anonymous=True
        )
    except Exception:
        logger.exception("خطا در ساخت نظرسنجی")
        reply(message, "❌ ساخت نظرسنجی انجام نشد.")

# -------------------- MESSAGE SECURITY --------------------

LINK_PATTERN = re.compile(
    r"(https?://|www\.|t\.me/|telegram\.me/|(?:^|\s)@[A-Za-z0-9_]{5,})",
    re.IGNORECASE
)

@bot.message_handler(
    content_types=[
        "text", "photo", "video", "document", "animation",
        "audio", "voice", "sticker", "video_note"
    ]
)
def inspect_message(message):
    if not is_group(message) or not message.from_user:
        return

    # Commands are handled by their dedicated handlers.
    if message.content_type == "text" and message.text and message.text.startswith("/"):
        return

    chat_id = message.chat.id
    user_id = message.from_user.id
    s = settings(chat_id)

    # Never moderate group administrators.
    if is_admin(chat_id, user_id):
        return

    text_value = message.text or message.caption or ""

    if s["anti_link"] and LINK_PATTERN.search(text_value):
        try:
            bot.delete_message(chat_id, message.message_id)
            bot.send_message(chat_id, "🔗 ارسال لینک در این گروه مجاز نیست.")
            log_action(chat_id, f"حذف لینک از {user_id}")
        except Exception:
            logger.exception("حذف لینک ناموفق بود")
        return

    if s["filter_words"] and text_value:
        lowered = text_value.lower()
        if any(word and word.lower() in lowered for word in s["bad_words"]):
            try:
                bot.delete_message(chat_id, message.message_id)
                log_action(chat_id, f"حذف پیام دارای کلمه فیلتر از {user_id}")
            except Exception:
                logger.exception("حذف پیام فیلترشده ناموفق بود")
            return

    if s["anti_spam"]:
        now = time.time()
        key = (chat_id, user_id)
        q = USER_MESSAGES[key]
        q.append(now)
        while q and now - q[0] > 8:
            q.popleft()
        if len(q) >= 7:
            try:
                bot.delete_message(chat_id, message.message_id)
                log_action(chat_id, f"پیام مشکوک به اسپم از {user_id}")
            except Exception:
                logger.exception("حذف پیام اسپم ناموفق بود")

# -------------------- START --------------------

def main():
    load_data()
    logger.info("Starting MASIH GUARD")
    while True:
        try:
            bot.remove_webhook()
            bot.infinity_polling(
                skip_pending=True,
                timeout=30,
                long_polling_timeout=25
            )
        except KeyboardInterrupt:
            logger.info("Bot stopped manually")
            break
        except Exception:
            logger.exception("Polling failed; retrying in 5 seconds")
            time.sleep(5)

if __name__ == "__main__":
    main()
