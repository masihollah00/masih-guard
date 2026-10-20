# -*- coding: utf-8 -*-
"""
MASIH GUARD PRO — ربات مدیریت گروه تلگرام
نیازمندی‌ها:
  TELEGRAM_BOT_TOKEN = توکن ربات
  OWNER_ID = شناسه عددی تلگرام مالک
requirements.txt باید شامل pyTelegramBotAPI باشد.
"""
import os
import re
import json
import time
import html
import ast
import operator
import random
import logging
import threading
from pathlib import Path
from datetime import datetime, timezone

import telebot
from telebot import types

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("masih-guard")

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
OWNER_RAW = os.getenv("OWNER_ID", "").strip()
if not TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN تنظیم نشده است")
if not OWNER_RAW.isdigit():
    raise RuntimeError("OWNER_ID باید شناسه عددی تلگرام مالک باشد")
OWNER_ID = int(OWNER_RAW)

bot = telebot.TeleBot(TOKEN, parse_mode="HTML", threaded=True, num_threads=4)
DATA_PATH = Path("masih_guard_data.json")
LOCK = threading.RLock()
DATA = {"groups": {}, "licenses": {}, "reports": []}
warn_counts = {}
message_times = {}
duplicate_texts = {}
flood_strikes = {}

DEFAULTS = {
    "approved": False,
    "anti_link": True,
    "anti_spam": True,
    "anti_flood": True,
    "filter_words": True,
    "anti_forward": False,
    "anti_bot": True,
    "lock_media": False,
    "lock_stickers": False,
    "lock_forwards": False,
    "welcome": True,
    "goodbye": True,
    "rules": "۱) به همه احترام بگذارید.\n۲) تبلیغات و لینک بدون اجازه ممنوع است.\n۳) از اسپم خودداری کنید.",
    "welcome_text": "سلام {name}، به گروه خوش اومدی 🌟\nلطفاً قوانین گروه رو بخون.",
    "goodbye_text": "👋 {name} از گروه خارج شد.",
    "blocked_words": [],
    "warn_limit": 3,
    "log_chat_id": 0,
}

def load_data():
    global DATA
    try:
        if DATA_PATH.exists():
            with DATA_PATH.open("r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                for key in ("groups", "licenses", "reports"):
                    if key in loaded:
                        DATA[key] = loaded[key]
    except Exception:
        log.exception("خطا در خواندن فایل تنظیمات")

def save_data():
    try:
        with LOCK:
            tmp = DATA_PATH.with_suffix(".tmp")
            with tmp.open("w", encoding="utf-8") as f:
                json.dump(DATA, f, ensure_ascii=False, indent=2)
            tmp.replace(DATA_PATH)
    except Exception:
        log.exception("خطا در ذخیره تنظیمات")

def settings(chat_id):
    with LOCK:
        item = DATA["groups"].setdefault(str(chat_id), {})
        for k, v in DEFAULTS.items():
            if k not in item:
                item[k] = list(v) if isinstance(v, list) else v
        return item

def group_chat(message):
    return message.chat.type in ("group", "supergroup")

def owner(user):
    return bool(user and user.id == OWNER_ID)

def admin(chat_id, user_id):
    try:
        return bot.get_chat_member(chat_id, user_id).status in ("administrator", "creator")
    except Exception:
        return False

def approved(chat_id):
    return bool(settings(chat_id).get("approved"))

def esc(value):
    return html.escape(str(value or ""))

def mention(user):
    return f'<a href="tg://user?id={user.id}">{esc(user.first_name or "کاربر")}</a>'

def reply(chat_id, text, **kwargs):
    try:
        return bot.send_message(chat_id, text, disable_web_page_preview=True, **kwargs)
    except Exception:
        log.exception("ارسال پیام ناموفق بود")
        return None

def can_manage(message):
    return bool(message.from_user and (owner(message.from_user) or admin(message.chat.id, message.from_user.id)))

def require_manage(message):
    if not group_chat(message):
        reply(message.chat.id, "این دستور را داخل گروه اجرا کن.")
        return False
    if not can_manage(message):
        reply(message.chat.id, "⛔ فقط مدیر گروه می‌تواند این دستور را اجرا کند.")
        return False
    if not approved(message.chat.id) and not owner(message.from_user):
        reply(message.chat.id, "⛔ گروه هنوز توسط مالک ربات تأیید نشده است.")
        return False
    return True

def log_action(chat_id, text):
    log.info("chat=%s %s", chat_id, re.sub(r"<[^>]+>", "", text))
    target = settings(chat_id).get("log_chat_id")
    if target:
        reply(int(target), "🧾 <b>گزارش گروه</b>\n" + text)

def target_from_reply(message):
    if message.reply_to_message and message.reply_to_message.from_user:
        return message.reply_to_message.from_user
    return None

def parse_duration(raw):
    match = re.fullmatch(r"(\d+)([mhd])", raw.lower())
    if not match:
        return 600
    number = min(int(match.group(1)), 365)
    return number * {"m": 60, "h": 3600, "d": 86400}[match.group(2)]

def main_keyboard():
    kb = types.InlineKeyboardMarkup(row_width=2)
    items = [
        ("🛡 امنیت گروه", "sec"),
        ("👥 مدیریت اعضا", "members"),
        ("👋 خوشامدگویی", "welcome"),
        ("📜 قوانین", "rules"),
        ("🔒 قفل‌ها", "locks"),
        ("📊 آمار", "stats"),
        ("🧰 ابزارها", "tools"),
        ("⚙️ تنظیمات", "settings"),
        ("❓ راهنما", "help"),
        ("ℹ️ درباره", "about"),
    ]
    for title, key in items:
        kb.add(types.InlineKeyboardButton(title, callback_data="menu:" + key))
    return kb

TOGGLES = {
    "sec": [
        ("anti_link", "🔗 ضد لینک"),
        ("anti_spam", "🚫 ضد اسپم"),
        ("anti_flood", "🌊 ضد فلود"),
        ("filter_words", "🤬 فیلتر کلمات"),
        ("anti_forward", "↪️ ضد فوروارد"),
        ("anti_bot", "🤖 ضد ربات"),
    ],
    "welcome": [("welcome", "👋 پیام ورود"), ("goodbye", "🚪 پیام خروج")],
    "locks": [
        ("lock_media", "🖼 قفل رسانه"),
        ("lock_stickers", "🎭 قفل استیکر"),
        ("lock_forwards", "↪️ قفل فوروارد"),
    ],
}

def toggle_keyboard(section, chat_id):
    s = settings(chat_id)
    kb = types.InlineKeyboardMarkup(row_width=1)
    for key, title in TOGGLES[section]:
        status = "روشن ✅" if s.get(key) else "خاموش ❌"
        kb.add(types.InlineKeyboardButton(f"{title}: {status}", callback_data=f"toggle:{key}"))
    kb.add(types.InlineKeyboardButton("⬅️ منوی اصلی", callback_data="menu:home"))
    return kb

def menu_content(section, chat_id):
    s = settings(chat_id)
    if section == "home":
        return "🛡 <b>پنل MASIH GUARD PRO</b>\nاز منوی زیر یک بخش را انتخاب کن:"
    if section == "sec":
        return "🛡 <b>امنیت گروه</b>\nبرای روشن یا خاموش کردن قابلیت‌ها دکمه‌ها را بزن."
    if section == "members":
        return ("👥 <b>مدیریت اعضا</b>\n"
                "روی پیام کاربر ریپلای کن و دستور را بفرست:\n"
                "/warn — اخطار\n/warnings — دیدن اخطارها\n/resetwarn — صفر کردن اخطارها\n"
                "/mute 10m — سکوت (مثل 30m، 2h، 1d)\n/unmute — رفع سکوت\n"
                "/ban — مسدودکردن\n/kick — اخراج\n/unban USER_ID — رفع مسدودی\n"
                "/purge — پاک‌کردن پیام‌ها با ریپلای")
    if section == "welcome":
        return "👋 <b>خوشامدگویی</b>\nاز دکمه‌ها وضعیت پیام ورود و خروج را عوض کن.\n/setwelcome متن {name}\n/setgoodbye متن {name}"
    if section == "rules":
        return "📜 <b>قوانین گروه</b>\n/rules — نمایش قوانین\n/setrules متن قوانین — تنظیم قوانین"
    if section == "locks":
        return "🔒 <b>قفل‌ها</b>\nقفل رسانه، استیکر و فوروارد را تغییر بده."
    if section == "stats":
        return (f"📊 <b>آمار گروه</b>\nشناسه: <code>{chat_id}</code>\n"
                f"تأیید مالک: {'بله ✅' if s['approved'] else 'خیر ❌'}\n"
                f"تعداد کلمات فیلتر: {len(s['blocked_words'])}")
    if section == "tools":
        return "🧰 <b>ابزارها</b>\n/id — شناسه‌ها\n/calc 2+2 — ماشین‌حساب\n/dice — تاس\n/coin — شیر یا خط\n/report متن — گزارش به مدیران"
    if section == "settings":
        return "⚙️ <b>تنظیمات</b>\nبرای دیدن شناسه گروه /id را بزن.\nمالک می‌تواند گروه را با /approve GROUP_ID فعال کند."
    if section == "help":
        return "❓ ربات را مدیر گروه کن و مجوز حذف پیام و محدودکردن اعضا را بده. همه قابلیت‌ها قبل از تأیید مالک فعال نمی‌شوند."
    return "ℹ️ <b>MASIH GUARD PRO</b>\nکدنویس: Masih Hackring ❤️"

@bot.message_handler(commands=["start", "help"])
def start_handler(message):
    if message.chat.type == "private":
        reply(message.chat.id,
              "سلام 🌟 من <b>MASIH GUARD PRO</b> هستم.\n"
              "من را به گروه اضافه کن و مدیرم کن.\n"
              "شناسه خودت: /myid\nشناسه گروه: /id\nپنل گروه: /panel")
    elif group_chat(message):
        if approved(message.chat.id):
            reply(message.chat.id, "سلام! برای بازکردن پنل /panel را بزن.")
        else:
            reply(message.chat.id, "⛔ این گروه هنوز توسط مالک ربات تأیید نشده است.")

@bot.message_handler(commands=["myid"])
def myid_handler(message):
    reply(message.chat.id, f"🆔 شناسه عددی شما: <code>{message.from_user.id}</code>")

@bot.message_handler(commands=["id"])
def id_handler(message):
    text = f"🆔 شناسه چت: <code>{message.chat.id}</code>"
    if message.from_user:
        text += f"\nشناسه شما: <code>{message.from_user.id}</code>"
    target = target_from_reply(message)
    if target:
        text += f"\nشناسه کاربر: <code>{target.id}</code>"
    reply(message.chat.id, text)

@bot.message_handler(commands=["panel"])
def panel_handler(message):
    if not group_chat(message):
        reply(message.chat.id, "پنل را داخل گروه باز کن.")
        return
    if not can_manage(message):
        reply(message.chat.id, "⛔ فقط مدیران گروه می‌توانند پنل را باز کنند.")
        return
    if not approved(message.chat.id) and not owner(message.from_user):
        reply(message.chat.id, "⛔ گروه تأیید نشده. شناسه گروه را با /id بگیر و به مالک ربات بده.")
        return
    reply(message.chat.id, menu_content("home", message.chat.id), reply_markup=main_keyboard())

@bot.callback_query_handler(func=lambda call: call.data.startswith("menu:"))
def menu_callback(call):
    try:
        chat_id = call.message.chat.id
        if not (owner(call.from_user) or admin(chat_id, call.from_user.id)):
            bot.answer_callback_query(call.id, "فقط مدیران گروه.", show_alert=True)
            return
        section = call.data.split(":", 1)[1]
        if section == "home":
            text, markup = menu_content("home", chat_id), main_keyboard()
        elif section in TOGGLES:
            text, markup = menu_content(section, chat_id), toggle_keyboard(section, chat_id)
        else:
            text = menu_content(section, chat_id)
            markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("⬅️ منوی اصلی", callback_data="menu:home"))
        bot.edit_message_text(text, chat_id, call.message.message_id, reply_markup=markup, disable_web_page_preview=True)
        bot.answer_callback_query(call.id)
    except Exception:
        log.exception("menu callback error")
        try:
            bot.answer_callback_query(call.id, "خطا؛ دوباره امتحان کن.")
        except Exception:
            pass

@bot.callback_query_handler(func=lambda call: call.data.startswith("toggle:"))
def toggle_callback(call):
    chat_id = call.message.chat.id
    if not (owner(call.from_user) or admin(chat_id, call.from_user.id)):
        bot.answer_callback_query(call.id, "فقط مدیران گروه.", show_alert=True)
        return
    if not approved(chat_id) and not owner(call.from_user):
        bot.answer_callback_query(call.id, "گروه تأیید نشده.", show_alert=True)
        return
    key = call.data.split(":", 1)[1]
    section = next((sec for sec, entries in TOGGLES.items() if key in [x[0] for x in entries]), None)
    if not section:
        bot.answer_callback_query(call.id, "تنظیم نامعتبر.")
        return
    s = settings(chat_id)
    s[key] = not bool(s.get(key))
    save_data()
    try:
        bot.edit_message_text(menu_content(section, chat_id), chat_id, call.message.message_id,
                              reply_markup=toggle_keyboard(section, chat_id), disable_web_page_preview=True)
    except Exception:
        pass
    bot.answer_callback_query(call.id, "ذخیره شد ✅")

@bot.message_handler(commands=["approve", "revoke", "licenses"])
def license_handler(message):
    if not owner(message.from_user):
        reply(message.chat.id, "⛔ فقط مالک ربات اجازه دارد.")
        return
    parts = (message.text or "").split()
    cmd = parts[0].split("@")[0]
    if cmd == "/licenses":
        ids = list(DATA["licenses"])
        reply(message.chat.id, "📋 گروه‌های تأییدشده:\n" + ("\n".join(f"<code>{x}</code>" for x in ids) if ids else "هیچ گروهی تأیید نشده."))
        return
    if len(parts) < 2 or not re.fullmatch(r"-?\d+", parts[1]):
        reply(message.chat.id, "شناسه گروه را با /id داخل گروه بگیر.\nاستفاده: /approve GROUP_ID یا /revoke GROUP_ID")
        return
    gid = str(int(parts[1]))
    if cmd == "/approve":
        settings(int(gid))["approved"] = True
        DATA["licenses"][gid] = {"approved_at": datetime.now(timezone.utc).isoformat(), "owner": OWNER_ID}
        save_data()
        reply(message.chat.id, f"✅ گروه <code>{gid}</code> تأیید شد.")
    else:
        if gid in DATA["groups"]:
            DATA["groups"][gid]["approved"] = False
        DATA["licenses"].pop(gid, None)
        save_data()
        reply(message.chat.id, f"🚫 دسترسی گروه <code>{gid}</code> لغو شد.")

@bot.message_handler(commands=["setrules", "setwelcome", "setgoodbye"])
def set_text_handler(message):
    if not require_manage(message):
        return
    cmd = message.text.split()[0].split("@")[0]
    value = message.text.partition(" ")[2].strip()
    if not value:
        reply(message.chat.id, "بعد از دستور متن موردنظر را بنویس. برای خوشامد از {name} استفاده کن.")
        return
    s = settings(message.chat.id)
    key = {"/setrules": "rules", "/setwelcome": "welcome_text", "/setgoodbye": "goodbye_text"}[cmd]
    s[key] = value[:3500 if key == "rules" else 1000]
    save_data()
    reply(message.chat.id, "✅ متن ذخیره شد.")

@bot.message_handler(commands=["addword", "delword", "words"])
def word_handler(message):
    if not require_manage(message):
        return
    s = settings(message.chat.id)
    cmd = message.text.split()[0].split("@")[0]
    value = message.text.partition(" ")[2].strip()
    if cmd == "/words":
        reply(message.chat.id, "🧹 کلمات فیلترشده:\n" + (", ".join(esc(w) for w in s["blocked_words"]) if s["blocked_words"] else "فهرست خالی است."))
    elif not value:
        reply(message.chat.id, "بعد از دستور یک کلمه بنویس.")
    elif cmd == "/addword":
        if value.lower() not in [w.lower() for w in s["blocked_words"]]:
            s["blocked_words"].append(value[:80])
        save_data()
        reply(message.chat.id, "✅ کلمه اضافه شد.")
    else:
        s["blocked_words"] = [w for w in s["blocked_words"] if w.lower() != value.lower()]
        save_data()
        reply(message.chat.id, "✅ کلمه حذف شد.")

@bot.message_handler(commands=["rules"])
def rules_handler(message):
    reply(message.chat.id, "📜 <b>قوانین گروه</b>\n" + esc(settings(message.chat.id)["rules"]))

@bot.message_handler(commands=["warn", "warnings", "resetwarn", "mute", "unmute", "ban", "kick", "unban", "purge", "setwarnlimit"])
def moderation_handler(message):
    if not require_manage(message):
        return
    cmd = message.text.split()[0].split("@")[0]
    s = settings(message.chat.id)
    if cmd == "/unban":
        parts = message.text.split()
        if len(parts) < 2 or not parts[1].isdigit():
            reply(message.chat.id, "استفاده: /unban USER_ID")
            return
        try:
            bot.unban_chat_member(message.chat.id, int(parts[1]), only_if_banned=True)
            reply(message.chat.id, "✅ مسدودی برداشته شد.")
        except Exception as e:
            reply(message.chat.id, "❌ انجام نشد: " + esc(str(e)[:160]))
        return
    if cmd == "/setwarnlimit":
        parts = message.text.split()
        if len(parts) < 2 or not parts[1].isdigit() or not 1 <= int(parts[1]) <= 10:
            reply(message.chat.id, "استفاده: /setwarnlimit 3 (بین ۱ تا ۱۰)")
            return
        s["warn_limit"] = int(parts[1]); save_data()
        reply(message.chat.id, "✅ حد اخطار ذخیره شد.")
        return
    if cmd == "/purge":
        if not message.reply_to_message:
            reply(message.chat.id, "روی اولین پیام ریپلای کن و /purge بزن.")
            return
        count = 0
        for mid in range(message.reply_to_message.message_id, message.message_id + 1):
            try:
                bot.delete_message(message.chat.id, mid); count += 1
            except Exception:
                pass
        reply(message.chat.id, f"🧹 تعداد پیام‌های پاک‌شده: {count}")
        return
    target = target_from_reply(message)
    if not target:
        reply(message.chat.id, "روی پیام کاربر ریپلای کن و دوباره دستور را بفرست.")
        return
    if target.id in (message.from_user.id, OWNER_ID):
        reply(message.chat.id, "⚠️ این کار روی خودت یا مالک ربات انجام نمی‌شود.")
        return
    key = (message.chat.id, target.id)
    if cmd == "/warnings":
        reply(message.chat.id, f"⚠️ اخطارهای {mention(target)}: <b>{warn_counts.get(key, 0)}</b>")
    elif cmd == "/resetwarn":
        warn_counts[key] = 0
        reply(message.chat.id, "✅ اخطارها صفر شد.")
    elif cmd == "/warn":
        warn_counts[key] = warn_counts.get(key, 0) + 1
        count = warn_counts[key]
        reply(message.chat.id, f"⚠️ {mention(target)} اخطار گرفت ({count}/{s['warn_limit']}).")
        if count >= int(s["warn_limit"]):
            try:
                bot.ban_chat_member(message.chat.id, target.id)
                bot.unban_chat_member(message.chat.id, target.id, only_if_banned=True)
                warn_counts[key] = 0
                reply(message.chat.id, f"🚪 {mention(target)} به دلیل رسیدن به حد اخطار اخراج شد.")
            except Exception:
                reply(message.chat.id, "⚠️ ربات اجازه اخراج ندارد.")
    elif cmd == "/mute":
        parts = message.text.split()
        duration = parse_duration(parts[1]) if len(parts) > 1 else 600
        try:
            perms = types.ChatPermissions(can_send_messages=False, can_send_audios=False,
                can_send_documents=False, can_send_photos=False, can_send_videos=False,
                can_send_video_notes=False, can_send_voice_notes=False, can_send_polls=False,
                can_send_other_messages=False, can_add_web_page_previews=False)
            bot.restrict_chat_member(message.chat.id, target.id, until_date=int(time.time()) + duration, permissions=perms)
            reply(message.chat.id, f"🔇 {mention(target)} سکوت شد.")
        except Exception as e:
            reply(message.chat.id, "❌ سکوت انجام نشد: " + esc(str(e)[:160]))
    elif cmd == "/unmute":
        try:
            perms = types.ChatPermissions(can_send_messages=True, can_send_audios=True,
                can_send_documents=True, can_send_photos=True, can_send_videos=True,
                can_send_video_notes=True, can_send_voice_notes=True, can_send_polls=True,
                can_send_other_messages=True, can_add_web_page_previews=True)
            bot.restrict_chat_member(message.chat.id, target.id, permissions=perms)
            reply(message.chat.id, f"🔊 سکوت {mention(target)} برداشته شد.")
        except Exception as e:
            reply(message.chat.id, "❌ انجام نشد: " + esc(str(e)[:160]))
    elif cmd in ("/ban", "/kick"):
        try:
            bot.ban_chat_member(message.chat.id, target.id)
            if cmd == "/kick":
                bot.unban_chat_member(message.chat.id, target.id, only_if_banned=True)
            reply(message.chat.id, f"🚫 {mention(target)} {'مسدود شد' if cmd == '/ban' else 'اخراج شد'}.")
        except Exception as e:
            reply(message.chat.id, "❌ انجام نشد: " + esc(str(e)[:160]))
    log_action(message.chat.id, f"دستور {esc(cmd)} توسط {mention(message.from_user)} برای {mention(target)} اجرا شد.")

def safe_calculate(expression):
    allowed_ops = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
                   ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv,
                   ast.Mod: operator.mod, ast.Pow: operator.pow, ast.USub: operator.neg,
                   ast.UAdd: operator.pos}
    def walk(node):
        if isinstance(node, ast.Expression):
            return walk(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in allowed_ops:
            left, right = walk(node.left), walk(node.right)
            if isinstance(node.op, ast.Pow) and abs(right) > 8:
                raise ValueError("توان خیلی بزرگ است")
            result = allowed_ops[type(node.op)](left, right)
            if abs(result) > 10**15:
                raise ValueError("عدد بیش از حد بزرگ است")
            return result
        if isinstance(node, ast.UnaryOp) and type(node.op) in allowed_ops:
            return allowed_ops[type(node.op)](walk(node.operand))
        raise ValueError("عبارت نامعتبر است")
    tree = ast.parse(expression, mode="eval")
    return walk(tree)

@bot.message_handler(commands=["calc", "dice", "coin"])
def tools_handler(message):
    cmd = message.text.split()[0].split("@")[0]
    if cmd == "/dice":
        reply(message.chat.id, f"🎲 نتیجه تاس: <b>{random.randint(1, 6)}</b>")
    elif cmd == "/coin":
        reply(message.chat.id, "🪙 نتیجه: <b>" + random.choice(["شیر", "خط"]) + "</b>")
    else:
        expr = message.text.partition(" ")[2].strip()
        if not expr or len(expr) > 100:
            reply(message.chat.id, "استفاده: /calc 12*(3+4)")
            return
        try:
            result = safe_calculate(expr)
            reply(message.chat.id, f"🧮 نتیجه: <code>{esc(result)}</code>")
        except Exception:
            reply(message.chat.id, "❌ عبارت ریاضی معتبر نیست.")

@bot.message_handler(commands=["report"])
def report_handler(message):
    text = message.text.partition(" ")[2].strip()
    if not text and message.reply_to_message:
        text = (message.reply_to_message.text or message.reply_to_message.caption or "پیام گزارش‌شده")
    if not text:
        reply(message.chat.id, "استفاده: /report متن گزارش یا روی پیام ریپلای کن.")
        return
    record = {"chat_id": message.chat.id, "from_id": message.from_user.id,
              "text": text[:800], "time": datetime.now(timezone.utc).isoformat()}
    DATA["reports"].append(record)
    DATA["reports"] = DATA["reports"][-100:]
    save_data()
    delivered = 0
    try:
        admins = bot.get_chat_administrators(message.chat.id)
        for member in admins:
            if member.user.id != message.from_user.id:
                reply(member.user.id, f"🚨 <b>گزارش جدید</b>\nگروه: <code>{message.chat.id}</code>\nاز: {mention(message.from_user)}\n{esc(text[:800])}")
                delivered += 1
    except Exception:
        pass
    reply(message.chat.id, "✅ گزارش ثبت شد." if delivered else "✅ گزارش ثبت شد؛ برای ارسال مستقیم به مدیران، باید قبلاً ربات را در خصوصی شروع کرده باشند.")

@bot.message_handler(commands=["setlog"])
def setlog_handler(message):
    if not require_manage(message):
        return
    parts = message.text.split()
    if len(parts) < 2 or not re.fullmatch(r"-?\d+", parts[1]):
        reply(message.chat.id, "استفاده: /setlog CHAT_ID یا /setlog 0 برای خاموش‌کردن")
        return
    settings(message.chat.id)["log_chat_id"] = int(parts[1])
    save_data()
    reply(message.chat.id, "✅ مقصد گزارش ذخیره شد.")

@bot.message_handler(content_types=["new_chat_members"])
def new_members_handler(message):
    s = settings(message.chat.id)
    for member in message.new_chat_members:
        if member.id == bot.get_me().id:
            reply(message.chat.id, "سلام! من را مدیر کن، سپس مالک ربات باید گروه را تأیید کند. برای شناسه گروه /id را بزن.")
            continue
        if s["welcome"] and approved(message.chat.id):
            text = s["welcome_text"].replace("{name}", safe_name(member))
            reply(message.chat.id, text)
        if s["anti_bot"] and approved(message.chat.id) and getattr(member, "is_bot", False):
            try:
                bot.ban_chat_member(message.chat.id, member.id)
                reply(message.chat.id, "🤖 ورود ربات جدید مسدود شد.")
            except Exception:
                pass

@bot.message_handler(content_types=["left_chat_member"])
def left_member_handler(message):
    s = settings(message.chat.id)
    member = message.left_chat_member
    if s["goodbye"] and approved(message.chat.id) and member.id != bot.get_me().id:
        reply(message.chat.id, s["goodbye_text"].replace("{name}", safe_name(member)))

@bot.message_handler(content_types=["text", "photo", "video", "document", "audio", "voice", "sticker", "animation", "video_note"])
def moderation_filter(message):
    if not group_chat(message) or not message.from_user or message.from_user.is_bot:
        return
    chat_id, user_id = message.chat.id, message.from_user.id
    if not approved(chat_id) or admin(chat_id, user_id) or owner(message.from_user):
        return
    s = settings(chat_id)
    text = message.text or message.caption or ""
    now = time.time()
    key = (chat_id, user_id)
    times = message_times.setdefault(key, [])
    times[:] = [t for t in times if now - t < 8]
    times.append(now)
    if s["anti_flood"] and len(times) > 6:
        try:
            bot.delete_message(chat_id, message.message_id)
            flood_strikes[key] = flood_strikes.get(key, 0) + 1
            if flood_strikes[key] >= 3:
                bot.restrict_chat_member(chat_id, user_id, until_date=int(now) + 300,
                    permissions=types.ChatPermissions(can_send_messages=False))
                flood_strikes[key] = 0
            else:
                reply(chat_id, f"🌊 {mention(message.from_user)} لطفاً پشت‌سرهم پیام نفرست.")
        except Exception:
            pass
        return
    if s["anti_spam"] and text:
        old = duplicate_texts.get(key)
        if old and old[0] == text.lower() and now - old[1] < 12:
            try:
                bot.delete_message(chat_id, message.message_id)
                reply(chat_id, f"🚫 {mention(message.from_user)} از ارسال پیام تکراری خودداری کن.")
            except Exception:
                pass
            return
        duplicate_texts[key] = (text.lower(), now)
    if s["anti_link"] and re.search(r"(https?://|www\.|t\.me/|telegram\.me/|@\w{4,})", text, re.I):
        try:
            bot.delete_message(chat_id, message.message_id)
            reply(chat_id, f"🔗 {mention(message.from_user)} ارسال لینک در این گروه مجاز نیست.")
            log_action(chat_id, f"لینک از {mention(message.from_user)} حذف شد.")
        except Exception:
            pass
        return
    if s["anti_forward"] and getattr(message, "forward_origin", None):
        try:
            bot.delete_message(chat_id, message.message_id)
            return
        except Exception:
            pass
    if s["lock_forwards"] and getattr(message, "forward_origin", None):
        try:
            bot.delete_message(chat_id, message.message_id)
            return
        except Exception:
            pass
    if s["lock_media"] and message.content_type in ("photo", "video", "document", "audio", "voice", "animation", "video_note"):
        try:
            bot.delete_message(chat_id, message.message_id)
            return
        except Exception:
            pass
    if s["lock_stickers"] and message.content_type == "sticker":
        try:
            bot.delete_message(chat_id, message.message_id)
            return
        except Exception:
            pass
    if s["filter_words"] and text:
        lowered = text.casefold()
        if any(word.casefold() in lowered for word in s["blocked_words"] if word):
            try:
                bot.delete_message(chat_id, message.message_id)
                reply(chat_id, f"🤬 {mention(message.from_user)} این پیام با فیلتر گروه سازگار نیست.")
            except Exception:
                pass

load_data()
save_data()
log.info("MASIH GUARD PRO is starting")
try:
    bot.infinity_polling(skip_pending=True, timeout=30, long_polling_timeout=25)
except KeyboardInterrupt:
    log.info("Bot stopped manually")
except Exception:
    log.exception("Bot stopped because of an error")
    raise
