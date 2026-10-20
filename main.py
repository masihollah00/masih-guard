# -*- coding: utf-8 -*-
"""
MASIH GUARD PRO - single-file Telegram group moderation bot
Requires: pyTelegramBotAPI>=4.20.0
Environment:
  TELEGRAM_BOT_TOKEN or BOT_TOKEN  (keep the token secret)
  OWNER_ID (optional; defaults to the owner's numeric ID supplied for this build)
"""
import os
import re
import json
import time
import random
import logging
import threading
from datetime import datetime, timezone

import telebot
from telebot import types

# ---------- Basic configuration ----------
BOT_TOKEN = (os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN") or "").strip()
OWNER_ID_RAW = (os.getenv("OWNER_ID") or "8620924698").strip()
if not BOT_TOKEN:
    raise RuntimeError(
        "توکن تنظیم نشده است؛ در Environment متغیر TELEGRAM_BOT_TOKEN یا BOT_TOKEN را تنظیم کنید."
    )
if not OWNER_ID_RAW.isdigit():
    raise RuntimeError("OWNER_ID باید فقط شامل رقم‌های شناسه عددی تلگرام مالک باشد.")
OWNER_ID = int(OWNER_ID_RAW)

DATA_FILE = os.getenv("DATA_FILE", "masih_guard_data.json")
LOG_FILE = os.getenv("LOG_FILE", "masih_guard.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[logging.StreamHandler()],
)
log = logging.getLogger("MASIH_GUARD")
bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML", threaded=True, num_threads=8)
lock = threading.RLock()

DEFAULTS = {
    "anti_link": True,
    "anti_spam": True,
    "anti_flood": True,
    "filter_words": True,
    "anti_forward": False,
    "anti_bot": True,
    "lock_media": False,
    "lock_stickers": False,
    "welcome": True,
    "goodbye": True,
    "rules": "۱) احترام به همه اعضا الزامی است.\n۲) تبلیغ و لینک بدون اجازه ممنوع است.\n۳) از ارسال اسپم و پیام‌های تکراری خودداری کنید.",
    "welcome_text": "سلام {name} عزیز، به {group} خوش اومدی! 🌟",
    "goodbye_text": "خداحافظ {name} 👋",
    "log_chat_id": 0,
    "warn_limit": 3,
    "bad_words": [],
    "admins": [],
    "warnings": {},
    "muted": [],
    "banned_words": [],
    "recent": {},
    "counts": {"messages": 0, "deleted": 0, "warnings": 0, "joins": 0},
}
DB = {"groups": {}, "approved": [], "users": {}}

def load_db():
    global DB
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                DB.update(loaded)
    except Exception as e:
        log.exception("Database load failed: %s", e)

def save_db():
    try:
        with lock:
            tmp = DATA_FILE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(DB, f, ensure_ascii=False, indent=2)
            os.replace(tmp, DATA_FILE)
    except Exception as e:
        log.exception("Database save failed: %s", e)

def settings(chat_id):
    key = str(chat_id)
    with lock:
        current = DB["groups"].setdefault(key, {})
        for k, v in DEFAULTS.items():
            if k not in current:
                current[k] = json.loads(json.dumps(v))
        return current

def is_owner(user_id):
    return bool(user_id and int(user_id) == OWNER_ID)

def is_group(chat):
    return chat and chat.type in ("group", "supergroup")

def is_approved(chat_id):
    # Groups are active by default; owner can revoke access with /revoke.
    return str(chat_id) not in DB.get("revoked", [])

def is_admin(chat_id, user_id):
    if not user_id:
        return False
    if is_owner(user_id):
        return True
    try:
        member = bot.get_chat_member(chat_id, user_id)
        return member.status in ("administrator", "creator")
    except Exception:
        return False

def can_manage(message):
    return is_owner(message.from_user.id) or (
        is_group(message.chat) and is_admin(message.chat.id, message.from_user.id)
    )

def mention(user):
    name = (user.first_name or "دوست").replace("<", "").replace(">", "")
    return f'<a href="tg://user?id={user.id}">{name}</a>'

def safe_text(value):
    return str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def send(chat_id, text, **kwargs):
    try:
        return bot.send_message(chat_id, text, disable_web_page_preview=True, **kwargs)
    except Exception as e:
        log.warning("send_message failed: %s", e)
        return None

def owner_only(message):
    if not is_owner(message.from_user.id):
        send(message.chat.id, "⛔ این دستور مخصوص مالک ربات است.")
        return False
    return True

def target_from_reply(message):
    if message.reply_to_message and message.reply_to_message.from_user:
        return message.reply_to_message.from_user
    return None

def target_id_from_command(message):
    parts = (message.text or "").split()
    if len(parts) > 1 and parts[1].lstrip("-").isdigit():
        return int(parts[1])
    return None

def group_only(message):
    if not is_group(message.chat):
        send(message.chat.id, "این دستور را داخل گروه استفاده کن.")
        return False
    return True

def action_log(chat_id, text):
    cfg = settings(chat_id)
    log_chat = cfg.get("log_chat_id", 0)
    if log_chat:
        send(log_chat, f"🧾 <b>گزارش MASIH GUARD</b>\n{text}")

def delete_message(message):
    try:
        bot.delete_message(message.chat.id, message.message_id)
        cfg = settings(message.chat.id)
        cfg["counts"]["deleted"] = cfg["counts"].get("deleted", 0) + 1
        save_db()
        return True
    except Exception as e:
        log.info("Could not delete message (bot may lack permission): %s", e)
        return False

def warn_user(chat_id, user, reason="قانون‌شکنی"):
    cfg = settings(chat_id)
    key = str(user.id)
    cfg["warnings"][key] = cfg["warnings"].get(key, 0) + 1
    cfg["counts"]["warnings"] = cfg["counts"].get("warnings", 0) + 1
    n = cfg["warnings"][key]
    save_db()
    send(chat_id, f"⚠️ {mention(user)} اخطار {n}/{cfg['warn_limit']}\nدلیل: {safe_text(reason)}")
    if n >= int(cfg["warn_limit"]):
        try:
            bot.ban_chat_member(chat_id, user.id, revoke_messages=False)
            send(chat_id, f"🚫 {mention(user)} به‌دلیل رسیدن به سقف اخطار بن شد.")
            action_log(chat_id, f"کاربر {user.id} پس از {n} اخطار بن شد.")
        except Exception:
            send(chat_id, "⚠️ سقف اخطار رسید، اما برای بن‌کردن باید ربات دسترسی محدودسازی اعضا داشته باشد.")

def main_keyboard(chat_id):
    kb = types.InlineKeyboardMarkup(row_width=2)
    buttons = [
        ("🛡 امنیت", "menu:security"),
        ("👥 اعضا", "menu:members"),
        ("👋 خوشامد", "menu:welcome"),
        ("📜 قوانین", "menu:rules"),
        ("🔒 قفل‌ها", "menu:locks"),
        ("📊 آمار", "menu:stats"),
        ("🧰 ابزارها", "menu:tools"),
        ("⚙️ تنظیمات", "menu:settings"),
        ("❓ راهنما", "menu:help"),
    ]
    for label, data in buttons:
        kb.add(types.InlineKeyboardButton(label, callback_data=data))
    return kb

def toggle_keyboard(chat_id, section):
    cfg = settings(chat_id)
    groups = {
        "security": [("anti_link","ضدلینک"),("anti_spam","ضداسپم"),("anti_flood","ضدفلود"),("filter_words","فیلتر کلمات"),("anti_forward","ضدفوروارد"),("anti_bot","ضدربات")],
        "welcome": [("welcome","خوشامدگویی"),("goodbye","پیام خداحافظی")],
        "locks": [("lock_media","قفل رسانه"),("lock_stickers","قفل استیکر")],
    }
    kb = types.InlineKeyboardMarkup(row_width=2)
    for key, label in groups.get(section, []):
        mark = "✅" if cfg.get(key) else "❌"
        kb.add(types.InlineKeyboardButton(f"{mark} {label}", callback_data=f"toggle:{key}"))
    kb.add(types.InlineKeyboardButton("⬅️ منوی اصلی", callback_data="menu:home"))
    return kb

def menu_text(chat_id, section):
    cfg = settings(chat_id)
    texts = {
        "home": "🛡 <b>پنل MASIH GUARD PRO</b>\nیک بخش را انتخاب کن:",
        "security": "🛡 <b>تنظیمات امنیتی</b>\nبرای روشن/خاموش کردن هر قابلیت دکمه‌اش را بزن.",
        "welcome": "👋 <b>خوشامدگویی</b>\nقابلیت‌ها را از دکمه‌های زیر کنترل کن.\nتغییر متن: /setwelcome متن",
        "locks": "🔒 <b>قفل‌ها</b>\nقفل رسانه و استیکر به مجوز حذف پیام نیاز دارد.",
        "rules": "📜 <b>قوانین گروه</b>\n" + safe_text(cfg.get("rules","")),
        "members": "👥 <b>مدیریت اعضا</b>\nروی پیام کاربر ریپلای کن و /warn یا /mute یا /ban یا /kick بزن.",
        "stats": "📊 <b>آمار گروه</b>\n" + "\n".join(f"• {safe_text(k)}: {v}" for k,v in cfg["counts"].items()),
        "tools": "🧰 <b>ابزارها</b>\n/id شناسه گروه\n/rules قوانین\n/calc 2+2 محاسبه ساده\n/dice تاس\n/coin شیر یا خط",
        "settings": "⚙️ <b>تنظیمات</b>\n/setwarnlimit عدد\n/setlog شناسه چت یا 0\n/addword کلمه\n/delword کلمه",
        "help": "❓ <b>راهنما</b>\n/panel پنل\n/rules قوانین\n/id شناسه چت\n/myid شناسه شما\n/report گزارش با ریپلای\nبرای حذف پیام و محدودسازی اعضا، ربات باید در گروه ادمین و دارای مجوز مربوطه باشد.",
    }
    return texts.get(section, texts["home"])

load_db()

# ---------- Start and owner tools ----------
@bot.message_handler(commands=["start"])
def cmd_start(message):
    if is_group(message.chat):
        send(message.chat.id, "سلام! 🛡️ MASIH GUARD PRO فعاله. برای پنل /panel را بزن.")
    else:
        send(message.chat.id,
             "سلام! 🛡️ به MASIH GUARD PRO خوش اومدی.\n"
             "شناسه شما: <code>%s</code>\n/panel برای پنل مالک." % message.from_user.id)

@bot.message_handler(commands=["myid"])
def cmd_myid(message):
    send(message.chat.id, f"🆔 شناسه عددی شما: <code>{message.from_user.id}</code>")

@bot.message_handler(commands=["id"])
def cmd_id(message):
    send(message.chat.id, f"🆔 شناسه این چت: <code>{message.chat.id}</code>")

@bot.message_handler(commands=["panel"])
def cmd_panel(message):
    if is_group(message.chat):
        if not can_manage(message):
            send(message.chat.id, "⛔ پنل فقط برای مالک یا مدیران گروه است.")
            return
        send(message.chat.id, menu_text(message.chat.id, "home"), reply_markup=main_keyboard(message.chat.id))
    elif is_owner(message.from_user.id):
        send(message.chat.id, "🛡 <b>پنل مالک MASIH GUARD PRO</b>\nبرای تنظیمات یک گروه، /id را داخل گروه بزن و سپس /panel را در گروه اجرا کن.")
    else:
        send(message.chat.id, "⛔ این پنل مخصوص مالک ربات است.")

@bot.message_handler(commands=["approve"])
def cmd_approve(message):
    if not owner_only(message):
        return
    parts = (message.text or "").split()
    if len(parts) < 2 or not parts[1].lstrip("-").isdigit():
        send(message.chat.id, "روش استفاده: /approve GROUP_ID")
        return
    gid = int(parts[1])
    DB.setdefault("revoked", [])
    DB["revoked"] = [x for x in DB["revoked"] if str(x) != str(gid)]
    save_db()
    send(message.chat.id, f"✅ گروه <code>{gid}</code> مجاز شد.")

@bot.message_handler(commands=["revoke"])
def cmd_revoke(message):
    if not owner_only(message):
        return
    parts = (message.text or "").split()
    if len(parts) < 2 or not parts[1].lstrip("-").isdigit():
        send(message.chat.id, "روش استفاده: /revoke GROUP_ID")
        return
    DB.setdefault("revoked", []).append(str(int(parts[1])))
    save_db()
    send(message.chat.id, f"⛔ گروه <code>{int(parts[1])}</code> غیرفعال شد.")

@bot.message_handler(commands=["licenses"])
def cmd_licenses(message):
    if owner_only(message):
        send(message.chat.id, "📋 گروه‌های غیرفعال‌شده:\n" + "\n".join(DB.get("revoked", [])) if DB.get("revoked") else "همه گروه‌ها به‌طور پیش‌فرض فعال هستند.")

# ---------- Group rules and settings ----------
@bot.message_handler(commands=["rules"])
def cmd_rules(message):
    if is_group(message.chat):
        send(message.chat.id, "📜 <b>قوانین گروه</b>\n" + safe_text(settings(message.chat.id)["rules"]))
    else:
        send(message.chat.id, "برای دیدن قوانین، این دستور را در گروه بزن.")

@bot.message_handler(commands=["setrules"])
def cmd_setrules(message):
    if not can_manage(message) or not group_only(message):
        return
    value = (message.text or "").partition(" ")[2].strip()
    if not value:
        send(message.chat.id, "روش استفاده: /setrules متن قوانین")
        return
    settings(message.chat.id)["rules"] = value
    save_db()
    send(message.chat.id, "✅ قوانین ذخیره شد.")

@bot.message_handler(commands=["setwelcome"])
def cmd_setwelcome(message):
    if not can_manage(message) or not group_only(message):
        return
    value = (message.text or "").partition(" ")[2].strip()
    if not value:
        send(message.chat.id, "روش استفاده: /setwelcome متن پیام")
        return
    settings(message.chat.id)["welcome_text"] = value
    save_db()
    send(message.chat.id, "✅ متن خوشامد ذخیره شد. متغیرها: {name} و {group}")

@bot.message_handler(commands=["setgoodbye"])
def cmd_setgoodbye(message):
    if not can_manage(message) or not group_only(message):
        return
    value = (message.text or "").partition(" ")[2].strip()
    if not value:
        send(message.chat.id, "روش استفاده: /setgoodbye متن پیام")
        return
    settings(message.chat.id)["goodbye_text"] = value
    save_db()
    send(message.chat.id, "✅ متن خداحافظی ذخیره شد.")

@bot.message_handler(commands=["setwarnlimit"])
def cmd_setwarnlimit(message):
    if not can_manage(message) or not group_only(message):
        return
    parts = (message.text or "").split()
    if len(parts) != 2 or not parts[1].isdigit() or not 1 <= int(parts[1]) <= 10:
        send(message.chat.id, "روش استفاده: /setwarnlimit عددی بین 1 تا 10")
        return
    settings(message.chat.id)["warn_limit"] = int(parts[1])
    save_db()
    send(message.chat.id, "✅ سقف اخطار ذخیره شد.")

@bot.message_handler(commands=["setlog"])
def cmd_setlog(message):
    if not can_manage(message) or not group_only(message):
        return
    parts = (message.text or "").split()
    if len(parts) != 2 or not parts[1].lstrip("-").isdigit():
        send(message.chat.id, "روش استفاده: /setlog CHAT_ID یا /setlog 0")
        return
    settings(message.chat.id)["log_chat_id"] = int(parts[1])
    save_db()
    send(message.chat.id, "✅ مقصد گزارش ذخیره شد.")

@bot.message_handler(commands=["addword"])
def cmd_addword(message):
    if not can_manage(message) or not group_only(message):
        return
    word = (message.text or "").partition(" ")[2].strip().lower()
    if not word:
        send(message.chat.id, "روش استفاده: /addword کلمه")
        return
    words = settings(message.chat.id)["bad_words"]
    if word not in words:
        words.append(word)
    save_db()
    send(message.chat.id, f"✅ کلمه «{safe_text(word)}» به فیلتر اضافه شد.")

@bot.message_handler(commands=["delword"])
def cmd_delword(message):
    if not can_manage(message) or not group_only(message):
        return
    word = (message.text or "").partition(" ")[2].strip().lower()
    cfg = settings(message.chat.id)
    cfg["bad_words"] = [w for w in cfg["bad_words"] if w != word]
    save_db()
    send(message.chat.id, "✅ اگر کلمه وجود داشت، حذف شد.")

@bot.message_handler(commands=["words"])
def cmd_words(message):
    if not can_manage(message) or not group_only(message):
        return
    words = settings(message.chat.id)["bad_words"]
    send(message.chat.id, "📃 کلمات فیلتر:\n" + ("\n".join(safe_text(w) for w in words) if words else "فهرست خالی است."))

# ---------- Moderation commands ----------
@bot.message_handler(commands=["warn"])
def cmd_warn(message):
    if not can_manage(message) or not group_only(message): return
    user = target_from_reply(message)
    if not user:
        send(message.chat.id, "برای اخطار، روی پیام کاربر ریپلای کن و /warn دلیل بنویس.")
        return
    if user.id == OWNER_ID or is_admin(message.chat.id, user.id):
        send(message.chat.id, "نمی‌توان به مالک یا مدیر گروه اخطار داد.")
        return
    reason = (message.text or "").partition(" ")[2].strip() or "قانون‌شکنی"
    warn_user(message.chat.id, user, reason)

@bot.message_handler(commands=["warnings"])
def cmd_warnings(message):
    if not group_only(message): return
    user = target_from_reply(message)
    uid = user.id if user else target_id_from_command(message)
    if not uid:
        send(message.chat.id, "روی پیام کاربر ریپلای کن یا /warnings USER_ID بزن.")
        return
    count = settings(message.chat.id)["warnings"].get(str(uid), 0)
    send(message.chat.id, f"⚠️ تعداد اخطارهای <code>{uid}</code>: {count}")

@bot.message_handler(commands=["resetwarn"])
def cmd_resetwarn(message):
    if not can_manage(message) or not group_only(message): return
    user = target_from_reply(message)
    uid = user.id if user else target_id_from_command(message)
    if not uid:
        send(message.chat.id, "روی پیام کاربر ریپلای کن یا /resetwarn USER_ID بزن.")
        return
    settings(message.chat.id)["warnings"].pop(str(uid), None)
    save_db()
    send(message.chat.id, f"✅ اخطارهای <code>{uid}</code> پاک شد.")

@bot.message_handler(commands=["ban", "kick"])
def cmd_ban_kick(message):
    if not can_manage(message) or not group_only(message): return
    user = target_from_reply(message)
    uid = user.id if user else target_id_from_command(message)
    if not uid:
        send(message.chat.id, "روی پیام کاربر ریپلای کن یا /ban USER_ID یا /kick USER_ID بزن.")
        return
    if uid == OWNER_ID or is_admin(message.chat.id, uid):
        send(message.chat.id, "نمی‌توان مالک یا مدیر گروه را حذف کرد.")
        return
    try:
        bot.ban_chat_member(message.chat.id, uid)
        if message.text.split()[0].split("@")[0] == "/kick":
            bot.unban_chat_member(message.chat.id, uid, only_if_banned=True)
            send(message.chat.id, f"👢 کاربر <code>{uid}</code> از گروه اخراج شد.")
        else:
            send(message.chat.id, f"🚫 کاربر <code>{uid}</code> بن شد.")
        action_log(message.chat.id, f"مدیریت عضو {uid}: {safe_text(message.text.split()[0])}")
    except Exception as e:
        send(message.chat.id, "❌ عملیات انجام نشد. ربات باید ادمین و دارای مجوز محدودسازی اعضا باشد.")
        log.info("ban/kick failed: %s", e)

@bot.message_handler(commands=["unban"])
def cmd_unban(message):
    if not can_manage(message) or not group_only(message): return
    uid = target_id_from_command(message)
    if not uid:
        send(message.chat.id, "روش استفاده: /unban USER_ID")
        return
    try:
        bot.unban_chat_member(message.chat.id, uid, only_if_banned=True)
        send(message.chat.id, f"✅ بن کاربر <code>{uid}</code> برداشته شد.")
    except Exception:
        send(message.chat.id, "❌ رفع بن انجام نشد؛ شناسه و دسترسی ربات را بررسی کن.")

@bot.message_handler(commands=["mute"])
def cmd_mute(message):
    if not can_manage(message) or not group_only(message): return
    user = target_from_reply(message)
    uid = user.id if user else target_id_from_command(message)
    if not uid:
        send(message.chat.id, "روی پیام کاربر ریپلای کن یا /mute USER_ID بزن.")
        return
    try:
        bot.restrict_chat_member(message.chat.id, uid, permissions=types.ChatPermissions(can_send_messages=False))
        cfg = settings(message.chat.id)
        if uid not in cfg["muted"]: cfg["muted"].append(uid)
        save_db()
        send(message.chat.id, f"🔇 کاربر <code>{uid}</code> سکوت شد.")
    except Exception:
        send(message.chat.id, "❌ سکوت انجام نشد؛ ربات باید ادمین و دارای مجوز محدودسازی اعضا باشد.")

@bot.message_handler(commands=["unmute"])
def cmd_unmute(message):
    if not can_manage(message) or not group_only(message): return
    user = target_from_reply(message)
    uid = user.id if user else target_id_from_command(message)
    if not uid:
        send(message.chat.id, "روی پیام کاربر ریپلای کن یا /unmute USER_ID بزن.")
        return
    try:
        bot.restrict_chat_member(message.chat.id, uid, permissions=types.ChatPermissions(
            can_send_messages=True, can_send_audios=True, can_send_documents=True,
            can_send_photos=True, can_send_videos=True, can_send_video_notes=True,
            can_send_voice_notes=True, can_send_polls=True, can_send_other_messages=True,
            can_add_web_page_previews=True
        ))
        cfg = settings(message.chat.id)
        cfg["muted"] = [x for x in cfg["muted"] if int(x) != uid]
        save_db()
        send(message.chat.id, f"🔊 سکوت کاربر <code>{uid}</code> برداشته شد.")
    except Exception:
        send(message.chat.id, "❌ رفع سکوت انجام نشد؛ مجوزهای ربات را بررسی کن.")

@bot.message_handler(commands=["purge"])
def cmd_purge(message):
    if not can_manage(message) or not group_only(message): return
    if not message.reply_to_message:
        send(message.chat.id, "روی اولین پیام از محدوده ریپلای کن و /purge بزن؛ فقط همان پیام حذف می‌شود.")
        return
    if delete_message(message.reply_to_message):
        delete_message(message)
        send(message.chat.id, "🧹 پیام حذف شد.")

@bot.message_handler(commands=["report"])
def cmd_report(message):
    user = target_from_reply(message)
    if not user:
        send(message.chat.id, "برای گزارش، روی پیام موردنظر ریپلای کن و /report بزن.")
        return
    cfg = settings(message.chat.id) if is_group(message.chat) else None
    owner_msg = f"🚨 <b>گزارش کاربر</b>\nچت: <code>{message.chat.id}</code>\nگزارش‌شده: <code>{user.id}</code>\nگزارش‌دهنده: <code>{message.from_user.id}</code>"
    send(OWNER_ID, owner_msg)
    if cfg and cfg.get("log_chat_id"):
        send(cfg["log_chat_id"], owner_msg)
    send(message.chat.id, "✅ گزارش برای مالک ارسال شد.")

@bot.message_handler(commands=["calc"])
def cmd_calc(message):
    expr = (message.text or "").partition(" ")[2].strip()
    if not expr or len(expr) > 60 or not re.fullmatch(r"[0-9+\-*/(). %]+", expr):
        send(message.chat.id, "روش استفاده: /calc 12*(3+2)\nفقط محاسبات عددی ساده مجاز است.")
        return
    try:
        # Safe arithmetic parser: permit only numbers/operators via a restricted AST.
        import ast, operator
        ops = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
               ast.Div: operator.truediv, ast.Mod: operator.mod, ast.USub: operator.neg,
               ast.UAdd: operator.pos}
        def ev(node):
            if isinstance(node, ast.Expression): return ev(node.body)
            if isinstance(node, ast.Constant) and isinstance(node.value, (int,float)): return node.value
            if isinstance(node, ast.BinOp) and type(node.op) in ops: return ops[type(node.op)](ev(node.left), ev(node.right))
            if isinstance(node, ast.UnaryOp) and type(node.op) in ops: return ops[type(node.op)](ev(node.operand))
            raise ValueError("invalid")
        result = ev(ast.parse(expr, mode="eval"))
        if abs(result) > 10**100: raise ValueError("too large")
        send(message.chat.id, f"🧮 نتیجه: <code>{result}</code>")
    except Exception:
        send(message.chat.id, "❌ عبارت ریاضی معتبر نیست.")

@bot.message_handler(commands=["dice"])
def cmd_dice(message):
    send(message.chat.id, f"🎲 نتیجه تاس: {random.randint(1,6)}")

@bot.message_handler(commands=["coin"])
def cmd_coin(message):
    send(message.chat.id, f"🪙 نتیجه: {random.choice(['شیر','خط'])}")

# ---------- Menu callbacks ----------
@bot.callback_query_handler(func=lambda call: True)
def callback_router(call):
    try:
        if not call.message or not is_group(call.message.chat):
            bot.answer_callback_query(call.id, "این منو را داخل گروه باز کن.")
            return
        chat_id = call.message.chat.id
        if not is_admin(chat_id, call.from_user.id):
            bot.answer_callback_query(call.id, "فقط مالک یا مدیران گروه اجازه دارند.", show_alert=True)
            return
        data = call.data or ""
        if data.startswith("menu:"):
            section = data.split(":",1)[1]
            if section in ("security","welcome","locks"):
                bot.edit_message_text(menu_text(chat_id, section), chat_id, call.message.message_id,
                                      reply_markup=toggle_keyboard(chat_id, section))
            else:
                bot.edit_message_text(menu_text(chat_id, section), chat_id, call.message.message_id,
                                      reply_markup=main_keyboard(chat_id))
        elif data.startswith("toggle:"):
            key = data.split(":",1)[1]
            if key in DEFAULTS and isinstance(DEFAULTS[key], bool):
                cfg = settings(chat_id)
                cfg[key] = not cfg.get(key, False)
                save_db()
                section = "security" if key in ("anti_link","anti_spam","anti_flood","filter_words","anti_forward","anti_bot") else ("welcome" if key in ("welcome","goodbye") else "locks")
                bot.edit_message_text(menu_text(chat_id, section), chat_id, call.message.message_id,
                                      reply_markup=toggle_keyboard(chat_id, section))
        bot.answer_callback_query(call.id)
    except Exception as e:
        log.info("callback error: %s", e)
        try: bot.answer_callback_query(call.id, "خطا؛ دوباره تلاش کن.")
        except Exception: pass

# ---------- New members ----------
@bot.message_handler(content_types=["new_chat_members"])
def on_new_members(message):
    cfg = settings(message.chat.id)
    for user in message.new_chat_members:
        cfg["counts"]["joins"] = cfg["counts"].get("joins", 0) + 1
        if user.is_bot and cfg.get("anti_bot", True) and not is_owner(message.from_user.id):
            try:
                bot.ban_chat_member(message.chat.id, user.id)
                send(message.chat.id, "⛔ افزودن ربات جدید مجاز نیست.")
            except Exception:
                pass
            continue
        if cfg.get("welcome", True):
            template = cfg.get("welcome_text", DEFAULTS["welcome_text"])
            text = template.replace("{name}", mention(user)).replace("{group}", safe_text(message.chat.title or "گروه"))
            send(message.chat.id, text)
    save_db()

@bot.message_handler(content_types=["left_chat_member"])
def on_left_member(message):
    cfg = settings(message.chat.id)
    user = message.left_chat_member
    if cfg.get("goodbye", True) and user:
        text = cfg.get("goodbye_text", DEFAULTS["goodbye_text"]).replace("{name}", safe_text(user.first_name or "دوست"))
        send(message.chat.id, text)

# ---------- Main moderation filter ----------
URL_RE = re.compile(r"(https?://|www\.|t\.me/|telegram\.me/|discord\.gg/)", re.I)

@bot.message_handler(func=lambda m: bool(m and is_group(m.chat)), content_types=[
    "text","photo","video","document","audio","voice","video_note","sticker","animation",
    "contact","location","venue","poll"
])
def moderate_message(message):
    if not is_group(message.chat) or not message.from_user:
        return
    if message.from_user.is_bot or is_admin(message.chat.id, message.from_user.id):
        return
    cfg = settings(message.chat.id)
    if not is_approved(message.chat.id):
        return
    cfg["counts"]["messages"] = cfg["counts"].get("messages", 0) + 1
    text = message.text or message.caption or ""
    delete_reason = None

    if cfg.get("lock_media") and message.content_type in ("photo","video","document","audio","voice","video_note","animation"):
        delete_reason = "ارسال رسانه در این گروه قفل است."
    elif cfg.get("lock_stickers") and message.content_type == "sticker":
        delete_reason = "ارسال استیکر در این گروه قفل است."
    elif cfg.get("anti_forward") and (getattr(message, "forward_origin", None) or getattr(message, "forward_from", None) or getattr(message, "forward_from_chat", None)):
        delete_reason = "ارسال پیام فورواردی مجاز نیست."
    elif cfg.get("anti_link") and text and URL_RE.search(text):
        delete_reason = "ارسال لینک مجاز نیست."
    elif cfg.get("filter_words") and text and any(w and w.lower() in text.lower() for w in cfg.get("bad_words", [])):
        delete_reason = "پیام شامل کلمه فیلترشده است."

    now = time.time()
    if not delete_reason and cfg.get("anti_flood"):
        key = f"{message.chat.id}:{message.from_user.id}"
        recent = cfg.setdefault("recent", {})
        timestamps = [t for t in recent.get(key, []) if now - t < 8]
        timestamps.append(now)
        recent[key] = timestamps
        if len(timestamps) > 6:
            delete_reason = "ارسال پیام‌های پشت‌سرهم (فلود) مجاز نیست."
        # Keep memory bounded.
        if len(recent) > 1000:
            cfg["recent"] = {k:v for k,v in recent.items() if v and now-v[-1] < 60}

    if not delete_reason and cfg.get("anti_spam") and text:
        normalized = re.sub(r"\s+", " ", text.strip().lower())
        key = f"{message.chat.id}:{message.from_user.id}"
        recent = cfg.setdefault("recent", {})
        same = [t for t in recent.get("same:"+key, []) if now-t[0] < 30]
        same.append((now, normalized))
        recent["same:"+key] = same[-6:]
        if len(same) >= 4 and len({item[1] for item in same[-4:]}) == 1:
            delete_reason = "ارسال پیام تکراری (اسپم) مجاز نیست."

    if delete_reason:
        if delete_message(message):
            send(message.chat.id, f"⚠️ {mention(message.from_user)} پیام حذف شد.\nدلیل: {safe_text(delete_reason)}")
            action_log(message.chat.id, f"پیام کاربر {message.from_user.id} حذف شد؛ دلیل: {safe_text(delete_reason)}")
    save_db()

@bot.message_handler(func=lambda m: True, content_types=["text"])
def fallback(message):
    # Private owner messages get a lightweight status response; do not echo secrets.
    if message.chat.type == "private" and is_owner(message.from_user.id):
        if (message.text or "").strip().lower() in ("وضعیت", "status"):
            send(message.chat.id, "✅ ربات در حال اجراست.\nشناسه مالک تأیید شد.\nتوکن از متغیر محیطی خوانده می‌شود.")
        return

def run():
    log.info("MASIH GUARD PRO started; owner_id=%s", OWNER_ID)
    while True:
        try:
            bot.infinity_polling(skip_pending=True, timeout=30, long_polling_timeout=25)
        except Exception as e:
            log.exception("Polling stopped; retrying in 5 seconds: %s", e)
            time.sleep(5)

if __name__ == "__main__":
    run()
