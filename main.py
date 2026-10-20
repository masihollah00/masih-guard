# -*- coding: utf-8 -*-
"""
MASIH GUARD PRO — نسخه یکپارچه
نیازمندی: pyTelegramBotAPI
متغیرهای محیطی:
  TELEGRAM_BOT_TOKEN یا BOT_TOKEN = توکن ربات
  OWNER_ID = آیدی عددی مالک (اختیاری؛ پیش‌فرض نمونه زیر را تغییر دهید)
نکته: توکن را داخل این فایل ننویسید.
"""
import os
import re
import json
import time
import html
import logging
import threading
from collections import defaultdict, deque
from datetime import datetime

import telebot
from telebot import types

# -------------------- تنظیمات پایه --------------------
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID", "8620924698"))
DATA_FILE = os.getenv("DATA_FILE", "masih_guard_data.json")
BOT_NAME = "MASIH GUARD PRO"
VERSION = "2.0"

if not TOKEN:
    raise RuntimeError("توکن تنظیم نشده است؛ در بخش Environment متغیر BOT_TOKEN یا TELEGRAM_BOT_TOKEN را اضافه کن.")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
log = logging.getLogger("masih-guard")
bot = telebot.TeleBot(TOKEN, parse_mode="HTML", threaded=True)

db_lock = threading.RLock()
DEFAULTS = {
    "anti_link": True,
    "anti_spam": True,
    "anti_flood": True,
    "anti_forward": False,
    "anti_bot": True,
    "welcome": True,
    "goodbye": False,
    "lock_hashtags": False,
    "allowed_hashtags": [],
    "blocked_hashtags": [],
    "custom_hashtags": [],
    "bad_words": [],
    "rules": "۱) احترام به اعضا الزامی است.\\n۲) تبلیغات و اسپم ممنوع است.\\n۳) از قوانین گروه پیروی کنید.",
    "welcome_text": "سلام {name} عزیز، به گروه خوش اومدی 🌹",
    "goodbye_text": "خداحافظ {name} 👋",
    "warn_limit": 3,
    "log_chat_id": None,
    "locked_types": [],
    "stats": {"deleted": 0, "warnings": 0, "bans": 0, "joins": 0}
}
db = {"groups": {}, "users": {}, "licenses": {"approved": [], "revoked": []}}
message_times = defaultdict(lambda: deque(maxlen=8))
warns = defaultdict(int)
last_seen = {}
bot_username = None

def load_db():
    global db
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        if isinstance(loaded, dict):
            db.update(loaded)
    except FileNotFoundError:
        pass
    except Exception:
        log.exception("خواندن دیتابیس ناموفق بود")

def save_db():
    with db_lock:
        temp = DATA_FILE + ".tmp"
        try:
            with open(temp, "w", encoding="utf-8") as f:
                json.dump(db, f, ensure_ascii=False, indent=2)
            os.replace(temp, DATA_FILE)
        except Exception:
            log.exception("ذخیره دیتابیس ناموفق بود")

def group_settings(chat_id):
    key = str(chat_id)
    with db_lock:
        if key not in db["groups"]:
            db["groups"][key] = json.loads(json.dumps(DEFAULTS))
        else:
            for k, v in DEFAULTS.items():
                if k not in db["groups"][key]:
                    db["groups"][key][k] = json.loads(json.dumps(v))
            if not isinstance(db["groups"][key].get("stats"), dict):
                db["groups"][key]["stats"] = json.loads(json.dumps(DEFAULTS["stats"]))
        return db["groups"][key]

def is_owner(user_id):
    return bool(user_id and int(user_id) == OWNER_ID)

def is_group(chat):
    return chat and chat.type in ("group", "supergroup")

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
    return is_group(message.chat) and message.from_user and is_admin(message.chat.id, message.from_user.id)

def safe_name(user):
    name = user.first_name or "دوست"
    return html.escape(name)

def reply(message, text, **kwargs):
    try:
        return bot.reply_to(message, text, **kwargs)
    except Exception as exc:
        log.warning("ارسال پاسخ ناموفق: %s", exc)
        return None

def send_log(chat_id, text):
    s = group_settings(chat_id)
    target = s.get("log_chat_id")
    if target:
        try:
            bot.send_message(int(target), "📋 <b>گزارش MASIH GUARD PRO</b>\\n" + text)
        except Exception:
            pass

def stat(chat_id, key, amount=1):
    s = group_settings(chat_id)
    s.setdefault("stats", {}).setdefault(key, 0)
    s["stats"][key] += amount
    save_db()

def delete_message(message, reason):
    try:
        bot.delete_message(message.chat.id, message.message_id)
        stat(message.chat.id, "deleted")
        who = safe_name(message.from_user) if message.from_user else "کاربر"
        send_log(message.chat.id, f"🗑 پیام {who} حذف شد.\\nعلت: {html.escape(reason)}")
        return True
    except Exception as exc:
        log.info("حذف پیام ناموفق؛ ربات باید ادمین و مجوز حذف پیام داشته باشد: %s", exc)
        return False

def mention_user(user):
    name = html.escape(user.first_name or "کاربر")
    return f'<a href="tg://user?id={user.id}">{name}</a>'

def main_keyboard():
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("🛡 امنیت گروه", callback_data="panel:security"),
        types.InlineKeyboardButton("🏷 مدیریت هشتگ", callback_data="panel:hashtags"),
        types.InlineKeyboardButton("👥 اعضا و اخطارها", callback_data="panel:members"),
        types.InlineKeyboardButton("👋 خوشامدگویی", callback_data="panel:welcome"),
        types.InlineKeyboardButton("📜 قوانین گروه", callback_data="panel:rules"),
        types.InlineKeyboardButton("📊 آمار", callback_data="panel:stats"),
        types.InlineKeyboardButton("🧰 ابزارها", callback_data="panel:tools"),
        types.InlineKeyboardButton("⚙️ راهنما و تنظیمات", callback_data="panel:help"),
    )
    return kb

def back_keyboard():
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("⬅️ برگشت به پنل", callback_data="panel:home"))
    return kb

def toggle_keyboard(chat_id):
    s = group_settings(chat_id)
    labels = [
        ("anti_link", "🔗 ضدلینک"),
        ("anti_spam", "🚫 ضداسپم"),
        ("anti_flood", "🌊 ضدفلود"),
        ("anti_forward", "↪️ ضد فوروارد"),
        ("anti_bot", "🤖 ضدربات مزاحم"),
        ("lock_hashtags", "🏷 محدودیت هشتگ"),
        ("welcome", "👋 خوشامدگویی"),
        ("goodbye", "🚪 پیام خروج"),
    ]
    kb = types.InlineKeyboardMarkup(row_width=2)
    for key, label in labels:
        status = "✅" if s.get(key) else "❌"
        kb.add(types.InlineKeyboardButton(f"{label} {status}", callback_data=f"toggle:{key}"))
    kb.add(types.InlineKeyboardButton("⬅️ برگشت", callback_data="panel:home"))
    return kb

def panel_text(section, chat_id):
    s = group_settings(chat_id)
    if section == "home":
        return f"🛡 <b>{BOT_NAME}</b> v{VERSION}\\nپنل مدیریت گروه\\n\\nیکی از بخش‌های زیر را انتخاب کن:"
    if section == "security":
        return "🛡 <b>امنیت گروه</b>\\nبرای روشن یا خاموش کردن قابلیت‌ها روی دکمه‌ها بزن."
    if section == "hashtags":
        custom = s.get("custom_hashtags", [])
        allowed = s.get("allowed_hashtags", [])
        blocked = s.get("blocked_hashtags", [])
        return ("🏷 <b>مدیریت هشتگ</b>\\n"
                f"هشتگ‌های اختصاصی: {len(custom)}\\n"
                f"هشتگ‌های مجاز: {len(allowed)}\\n"
                f"هشتگ‌های ممنوع: {len(blocked)}\\n\\n"
                "دستورات: /addtag #هشتگ ، /deltag #هشتگ ، /tags ، /allowtag #هشتگ ، /blocktag #هشتگ")
    if section == "members":
        return "👥 <b>مدیریت اعضا</b>\\nدستورات: /warn (با ریپلای)، /warnings (با ریپلای)، /resetwarn (با ریپلای)، /mute، /unmute، /kick، /ban، /unban"
    if section == "welcome":
        return ("👋 <b>خوشامدگویی</b>\\n"
                f"وضعیت خوشامدگویی: {'روشن' if s.get('welcome') else 'خاموش'}\\n"
                f"متن فعلی: {html.escape(s.get('welcome_text',''))}\\n"
                "برای تغییر متن: /setwelcome متن جدید\\nبرای پیام خروج: /setgoodbye متن جدید")
    if section == "rules":
        return "📜 <b>قوانین گروه</b>\\n" + html.escape(s.get("rules", "قوانینی ثبت نشده"))
    if section == "stats":
        st = s.get("stats", {})
        return ("📊 <b>آمار گروه</b>\\n"
                f"پیام‌های حذف‌شده: {st.get('deleted', 0)}\\n"
                f"اخطارها: {st.get('warnings', 0)}\\n"
                f"مسدودسازی‌ها: {st.get('bans', 0)}\\n"
                f"عضویت‌ها: {st.get('joins', 0)}")
    if section == "tools":
        return "🧰 <b>ابزارها</b>\\n/calc 12*5 — محاسبه ساده\\n/dice — تاس\\n/coin — شیر یا خط\\n/myid — آیدی شما\\n/id — آیدی گروه/کاربر"
    return ("ℹ️ <b>راهنمای MASIH GUARD PRO</b>\\n"
            "/panel پنل مدیریت\\n/rules قوانین\\n/setrules متن — تنظیم قوانین\\n"
            "/addword کلمه — افزودن فیلتر\\n/delword کلمه — حذف فیلتر\\n/words فهرست کلمات\\n"
            "/addtag #tag — افزودن هشتگ اختصاصی\\n/deltag #tag — حذف هشتگ اختصاصی\\n"
            "/allowtag #tag — مجازکردن هشتگ\\n/blocktag #tag — ممنوع‌کردن هشتگ\\n/tags — فهرست هشتگ‌ها\\n"
            "برای کارکرد کامل مدیریت، ربات را ادمین گروه کن و مجوز حذف پیام/محدودکردن اعضا را بده.")

def section_keyboard(section, chat_id):
    if section == "security":
        return toggle_keyboard(chat_id)
    kb = types.InlineKeyboardMarkup(row_width=2)
    if section == "hashtags":
        kb.add(
            types.InlineKeyboardButton("📋 فهرست هشتگ‌ها", callback_data="hashtag:list"),
            types.InlineKeyboardButton("🔒 قفل هشتگ", callback_data="toggle:lock_hashtags"),
        )
    elif section == "welcome":
        kb.add(types.InlineKeyboardButton("👋 روشن/خاموش", callback_data="toggle:welcome"),
               types.InlineKeyboardButton("🚪 پیام خروج", callback_data="toggle:goodbye"))
    kb.add(types.InlineKeyboardButton("⬅️ برگشت به پنل", callback_data="panel:home"))
    return kb

# -------------------- فرمان‌های عمومی --------------------
@bot.message_handler(commands=["start", "help"])
def cmd_start(message):
    if is_group(message.chat):
        reply(message, f"سلام {safe_name(message.from_user)} 🌹\\nمن <b>{BOT_NAME}</b> هستم. برای پنل: /panel")
    else:
        bot.send_message(message.chat.id,
            f"💬 سلام {safe_name(message.from_user)} 🌹\\n"
            f"🛡 من <b>{BOT_NAME}</b> هستم؛ ربات مدیریت و امنیت گروه.\\n"
            "برای شروع من را به گروه اضافه کن و دسترسی ادمین بده.\\n"
            "دستور /help برای راهنما و /myid برای آیدی عددی.",
            reply_markup=main_keyboard())

@bot.message_handler(commands=["myid", "id"])
def cmd_id(message):
    user_id = message.from_user.id if message.from_user else "نامشخص"
    chat_id = message.chat.id
    reply(message, f"🆔 آیدی شما: <code>{user_id}</code>\\n🗂 آیدی گفتگو: <code>{chat_id}</code>")

@bot.message_handler(commands=["panel"])
def cmd_panel(message):
    if is_group(message.chat):
        if not can_manage(message):
            return reply(message, "⛔ فقط مدیران گروه می‌توانند پنل را باز کنند.")
        chat_id = message.chat.id
    else:
        chat_id = None
    text = panel_text("home", chat_id) if chat_id else f"🛡 <b>{BOT_NAME}</b>\\nبرای تنظیمات امنیتی، دستور /panel را داخل گروه بزن."
    bot.send_message(message.chat.id, text, reply_markup=main_keyboard())

@bot.callback_query_handler(func=lambda call: True)
def callbacks(call):
    try:
        data = call.data or ""
        if data.startswith("panel:"):
            section = data.split(":", 1)[1]
            chat_id = call.message.chat.id if is_group(call.message.chat) else None
            if chat_id and not is_admin(chat_id, call.from_user.id):
                return bot.answer_callback_query(call.id, "فقط مدیران گروه دسترسی دارند.", show_alert=True)
            if section == "home":
                text, markup = panel_text("home", chat_id), main_keyboard()
            else:
                text = panel_text(section, chat_id or call.message.chat.id)
                markup = section_keyboard(section, chat_id or call.message.chat.id)
            bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                                  reply_markup=markup, parse_mode="HTML")
            bot.answer_callback_query(call.id)
            return
        if data.startswith("toggle:"):
            key = data.split(":", 1)[1]
            chat_id = call.message.chat.id
            if not is_group(call.message.chat) or not is_admin(chat_id, call.from_user.id):
                return bot.answer_callback_query(call.id, "فقط مدیران گروه دسترسی دارند.", show_alert=True)
            s = group_settings(chat_id)
            if key not in DEFAULTS or not isinstance(DEFAULTS[key], bool):
                return bot.answer_callback_query(call.id, "گزینه نامعتبر است.", show_alert=True)
            s[key] = not s.get(key, False)
            save_db()
            bot.edit_message_text(panel_text("security", chat_id), chat_id, call.message.message_id,
                                  reply_markup=toggle_keyboard(chat_id), parse_mode="HTML")
            bot.answer_callback_query(call.id, "تنظیم ذخیره شد.")
            return
        if data == "hashtag:list":
            chat_id = call.message.chat.id
            if not is_group(call.message.chat) or not is_admin(chat_id, call.from_user.id):
                return bot.answer_callback_query(call.id, "فقط مدیران گروه دسترسی دارند.", show_alert=True)
            s = group_settings(chat_id)
            text = ("🏷 <b>فهرست هشتگ‌ها</b>\\nاختصاصی: " + html.escape(", ".join(s["custom_hashtags"]) or "ندارد")
                    + "\\nمجاز: " + html.escape(", ".join(s["allowed_hashtags"]) or "ندارد")
                    + "\\nممنوع: " + html.escape(", ".join(s["blocked_hashtags"]) or "ندارد"))
            bot.answer_callback_query(call.id)
            bot.send_message(chat_id, text, reply_markup=back_keyboard())
            return
        bot.answer_callback_query(call.id)
    except Exception:
        log.exception("خطای callback")

def require_group_admin(message):
    if not is_group(message.chat):
        reply(message, "این دستور را داخل گروه اجرا کن.")
        return False
    if not can_manage(message):
        reply(message, "⛔ فقط مدیران گروه اجازه این کار را دارند.")
        return False
    return True

def arg_text(message):
    return (message.text or "").partition(" ")[2].strip()

def normalize_tag(raw):
    tag = raw.strip()
    if not tag:
        return None
    if not tag.startswith("#"):
        tag = "#" + tag
    if not re.fullmatch(r"#[A-Za-z0-9_\u0600-\u06FF]{1,64}", tag):
        return None
    return tag

def tag_command(message, field, action):
    if not require_group_admin(message):
        return
    raw = arg_text(message)
    tag = normalize_tag(raw)
    if not tag:
        return reply(message, "فرمت هشتگ درست نیست. نمونه: <code>/addtag #اخبار</code>")
    s = group_settings(message.chat.id)
    items = s.setdefault(field, [])
    if action == "add":
        if tag in items:
            return reply(message, "این هشتگ از قبل در فهرست هست.")
        items.append(tag)
        save_db()
        reply(message, f"✅ هشتگ {html.escape(tag)} اضافه شد.")
    else:
        if tag not in items:
            return reply(message, "این هشتگ در این فهرست پیدا نشد.")
        items.remove(tag)
        save_db()
        reply(message, f"✅ هشتگ {html.escape(tag)} حذف شد.")

@bot.message_handler(commands=["addtag"])
def cmd_addtag(m): tag_command(m, "custom_hashtags", "add")
@bot.message_handler(commands=["deltag"])
def cmd_deltag(m): tag_command(m, "custom_hashtags", "del")
@bot.message_handler(commands=["allowtag"])
def cmd_allowtag(m): tag_command(m, "allowed_hashtags", "add")
@bot.message_handler(commands=["unallowtag"])
def cmd_unallowtag(m): tag_command(m, "allowed_hashtags", "del")
@bot.message_handler(commands=["blocktag"])
def cmd_blocktag(m): tag_command(m, "blocked_hashtags", "add")
@bot.message_handler(commands=["unblocktag"])
def cmd_unblocktag(m): tag_command(m, "blocked_hashtags", "del")

@bot.message_handler(commands=["tags"])
def cmd_tags(message):
    if not is_group(message.chat):
        return reply(message, "این دستور را داخل گروه اجرا کن.")
    s = group_settings(message.chat.id)
    reply(message, "🏷 <b>مدیریت هشتگ‌ها</b>\\n"
          "اختصاصی: " + html.escape(", ".join(s["custom_hashtags"]) or "ندارد") + "\\n"
          "مجاز: " + html.escape(", ".join(s["allowed_hashtags"]) or "ندارد") + "\\n"
          "ممنوع: " + html.escape(", ".join(s["blocked_hashtags"]) or "ندارد"))

@bot.message_handler(commands=["lockhashtags", "unlockhashtags"])
def cmd_lockhashtags(message):
    if not require_group_admin(message): return
    s = group_settings(message.chat.id)
    s["lock_hashtags"] = message.text.startswith("/lockhashtags")
    save_db()
    reply(message, "🏷 محدودیت هشتگ روشن شد." if s["lock_hashtags"] else "🏷 محدودیت هشتگ خاموش شد.")

@bot.message_handler(commands=["setrules"])
def cmd_setrules(message):
    if not require_group_admin(message): return
    text = arg_text(message)
    if not text: return reply(message, "متن قوانین را بعد از دستور بنویس.")
    group_settings(message.chat.id)["rules"] = text[:3500]
    save_db()
    reply(message, "✅ قوانین گروه ذخیره شد.")

@bot.message_handler(commands=["rules"])
def cmd_rules(message):
    s = group_settings(message.chat.id) if is_group(message.chat) else DEFAULTS
    reply(message, "📜 <b>قوانین گروه</b>\\n" + html.escape(s.get("rules", DEFAULTS["rules"])))

@bot.message_handler(commands=["setwelcome", "setgoodbye"])
def cmd_set_messages(message):
    if not require_group_admin(message): return
    text = arg_text(message)
    if not text: return reply(message, "متن پیام را بعد از دستور بنویس. متغیر {name} نام عضو را نشان می‌دهد.")
    key = "welcome_text" if message.text.split()[0].startswith("/setwelcome") else "goodbye_text"
    group_settings(message.chat.id)[key] = text[:1000]
    save_db()
    reply(message, "✅ متن ذخیره شد. متغیر {name} برای نام عضو قابل استفاده است.")

@bot.message_handler(commands=["setwarnlimit"])
def cmd_warnlimit(message):
    if not require_group_admin(message): return
    try:
        n = int(arg_text(message))
        if n < 1 or n > 20: raise ValueError
    except ValueError:
        return reply(message, "عدد بین ۱ تا ۲۰ وارد کن؛ مثال: /setwarnlimit 3")
    group_settings(message.chat.id)["warn_limit"] = n
    save_db()
    reply(message, f"✅ سقف اخطار روی {n} تنظیم شد.")

@bot.message_handler(commands=["addword", "delword", "words"])
def cmd_words(message):
    if not require_group_admin(message): return
    s = group_settings(message.chat.id)
    cmd = message.text.split()[0].split("@")[0]
    raw = arg_text(message)
    if cmd == "/words":
        return reply(message, "🧹 <b>کلمات فیلتر</b>\\n" + html.escape(", ".join(s["bad_words"]) or "فهرست خالی است"))
    if not raw: return reply(message, "بعد از دستور یک کلمه بنویس.")
    if cmd == "/addword":
        if raw.lower() not in [x.lower() for x in s["bad_words"]]:
            s["bad_words"].append(raw[:80])
        reply(message, f"✅ «{html.escape(raw[:80])}» به فیلتر اضافه شد.")
    else:
        s["bad_words"] = [x for x in s["bad_words"] if x.lower() != raw.lower()]
        reply(message, f"✅ درخواست حذف «{html.escape(raw[:80])}» انجام شد.")
    save_db()

# -------------------- مدیریت اعضا --------------------
def target_from_reply(message):
    if message.reply_to_message and message.reply_to_message.from_user:
        return message.reply_to_message.from_user
    return None

@bot.message_handler(commands=["warn", "warnings", "resetwarn"])
def cmd_warns(message):
    if not require_group_admin(message): return
    target = target_from_reply(message)
    if not target: return reply(message, "برای این دستور روی پیام کاربر ریپلای کن.")
    key = (message.chat.id, target.id)
    cmd = message.text.split()[0].split("@")[0]
    if cmd == "/resetwarn":
        warns[key] = 0
        reply(message, f"✅ اخطارهای {mention_user(target)} پاک شد.")
        return
    if cmd == "/warnings":
        return reply(message, f"⚠️ {mention_user(target)} تعداد اخطارها: {warns[key]}")
    if is_admin(message.chat.id, target.id):
        return reply(message, "مدیران گروه را اخطار نمی‌دهم.")
    warns[key] += 1
    stat(message.chat.id, "warnings")
    s = group_settings(message.chat.id)
    count = warns[key]
    reply(message, f"⚠️ اخطار {count}/{s['warn_limit']} برای {mention_user(target)}")
    send_log(message.chat.id, f"⚠️ اخطار برای {mention_user(target)} توسط {mention_user(message.from_user)}")
    if count >= int(s.get("warn_limit", 3)):
        try:
            bot.ban_chat_member(message.chat.id, target.id, until_date=int(time.time()) + 60)
            bot.unban_chat_member(message.chat.id, target.id, only_if_banned=True)
            warns[key] = 0
            reply(message, f"🔇 {mention_user(target)} پس از رسیدن به سقف اخطار، یک دقیقه محدود شد.")
        except Exception:
            reply(message, "به سقف اخطار رسید؛ اما برای محدودکردن عضو، دسترسی ربات را بررسی کن.")

@bot.message_handler(commands=["ban", "kick", "mute", "unmute", "unban"])
def cmd_member_action(message):
    if not require_group_admin(message): return
    target = target_from_reply(message)
    if not target:
        return reply(message, "روی پیام کاربر ریپلای کن و دوباره دستور را بفرست.")
    if is_admin(message.chat.id, target.id):
        return reply(message, "⛔ این عملیات روی مدیر گروه انجام نمی‌شود.")
    cmd = message.text.split()[0].split("@")[0]
    try:
        if cmd == "/ban":
            bot.ban_chat_member(message.chat.id, target.id)
            stat(message.chat.id, "bans")
            result = "🚫 کاربر مسدود شد."
        elif cmd == "/kick":
            bot.ban_chat_member(message.chat.id, target.id)
            bot.unban_chat_member(message.chat.id, target.id, only_if_banned=True)
            result = "👢 کاربر از گروه اخراج شد."
        elif cmd == "/unban":
            bot.unban_chat_member(message.chat.id, target.id, only_if_banned=True)
            result = "✅ مسدودیت کاربر برداشته شد."
        elif cmd == "/mute":
            bot.restrict_chat_member(message.chat.id, target.id,
                permissions=types.ChatPermissions(can_send_messages=False))
            result = "🔇 کاربر محدود شد."
        else:
            bot.restrict_chat_member(message.chat.id, target.id,
                permissions=types.ChatPermissions(can_send_messages=True, can_send_media_messages=True,
                    can_send_polls=True, can_send_other_messages=True, can_add_web_page_previews=True))
            result = "🔊 محدودیت کاربر برداشته شد."
        reply(message, result)
        send_log(message.chat.id, f"{html.escape(cmd)} برای {mention_user(target)} توسط {mention_user(message.from_user)}")
    except Exception as exc:
        log.info("عملیات عضو ناموفق: %s", exc)
        reply(message, "❌ عملیات انجام نشد. ادمین‌بودن ربات و دسترسی محدودکردن اعضا را بررسی کن.")

@bot.message_handler(commands=["purge"])
def cmd_purge(message):
    if not require_group_admin(message): return
    if not message.reply_to_message:
        return reply(message, "روی اولین پیامی که می‌خواهی پاک شود ریپلای کن و /purge بزن.")
    start_id = message.reply_to_message.message_id
    end_id = message.message_id
    if end_id - start_id > 100:
        return reply(message, "برای جلوگیری از پاکسازی ناخواسته، هر بار حداکثر ۱۰۰ پیام.")
    deleted = 0
    for mid in range(start_id, end_id + 1):
        try:
            bot.delete_message(message.chat.id, mid)
            deleted += 1
        except Exception:
            pass
    try:
        bot.send_message(message.chat.id, f"🧹 پاکسازی انجام شد؛ {deleted} پیام حذف شد.")
    except Exception:
        pass

@bot.message_handler(commands=["setlog"])
def cmd_setlog(message):
    if not require_group_admin(message): return
    raw = arg_text(message)
    if raw.lower() in ("off", "خاموش", "0"):
        group_settings(message.chat.id)["log_chat_id"] = None
        save_db()
        return reply(message, "گزارش‌گیری خاموش شد.")
    try:
        target = int(raw)
    except ValueError:
        return reply(message, "آیدی عددی گروه گزارش را بده یا /setlog off بزن.")
    group_settings(message.chat.id)["log_chat_id"] = target
    save_db()
    reply(message, "✅ مقصد گزارش ذخیره شد. ربات باید در آن گفتگو اجازه ارسال پیام داشته باشد.")

@bot.message_handler(commands=["report"])
def cmd_report(message):
    if not is_group(message.chat): return
    target = target_from_reply(message)
    if not target: return reply(message, "برای گزارش، روی پیام موردنظر ریپلای کن و /report بزن.")
    s = group_settings(message.chat.id)
    send_log(message.chat.id, f"🚨 گزارش از {mention_user(message.from_user)} درباره {mention_user(target)}")
    reply(message, "✅ گزارش برای مدیران ثبت شد.")

@bot.message_handler(commands=["approve", "revoke", "licenses"])
def cmd_licenses(message):
    if not is_owner(message.from_user.id):
        return reply(message, "⛔ این دستور فقط برای مالک ربات است.")
    cmd = message.text.split()[0].split("@")[0]
    raw = arg_text(message)
    if cmd == "/licenses":
        approved = db["licenses"].get("approved", [])
        revoked = db["licenses"].get("revoked", [])
        return reply(message, "🔑 <b>وضعیت دسترسی</b>\\nتأییدشده: " + html.escape(", ".join(map(str, approved)) or "ندارد") +
                     "\\nلغوشده: " + html.escape(", ".join(map(str, revoked)) or "ندارد"))
    try:
        chat_id = int(raw)
    except ValueError:
        return reply(message, "آیدی عددی گروه را بعد از دستور وارد کن.")
    approved = db["licenses"].setdefault("approved", [])
    revoked = db["licenses"].setdefault("revoked", [])
    if cmd == "/approve":
        if chat_id not in approved: approved.append(chat_id)
        if chat_id in revoked: revoked.remove(chat_id)
        reply(message, f"✅ دسترسی گروه <code>{chat_id}</code> ثبت شد.")
    else:
        if chat_id in approved: approved.remove(chat_id)
        if chat_id not in revoked: revoked.append(chat_id)
        reply(message, f"⛔ دسترسی گروه <code>{chat_id}</code> لغو شد.")
    save_db()

# -------------------- ابزارهای سرگرمی و محاسبه --------------------
@bot.message_handler(commands=["dice"])
def cmd_dice(message):
    import random
    bot.send_dice(message.chat.id, emoji="🎲")

@bot.message_handler(commands=["coin"])
def cmd_coin(message):
    import random
    reply(message, "🪙 نتیجه: " + ("شیر" if random.choice((0, 1)) else "خط"))

@bot.message_handler(commands=["calc"])
def cmd_calc(message):
    expr = arg_text(message)
    if not expr or len(expr) > 80 or not re.fullmatch(r"[0-9+*/().% \-]+", expr):
        return reply(message, "مثال: <code>/calc (12+5)*3</code>\\nفقط محاسبات عددی ساده مجاز است.")
    try:
        # فقط اعداد و عملگرهای ریاضی ساده اجازه دارند؛ builtins غیرفعال است.
        value = eval(expr, {"__builtins__": {}}, {})
        if isinstance(value, (int, float)) and abs(value) < 10**15:
            reply(message, f"🧮 نتیجه: <code>{value}</code>")
        else:
            reply(message, "نتیجه خارج از محدوده است.")
    except Exception:
        reply(message, "عبارت ریاضی نامعتبر است.")

# -------------------- ورود/خروج و فیلتر پیام‌ها --------------------
@bot.message_handler(content_types=["new_chat_members"])
def on_join(message):
    if not is_group(message.chat): return
    s = group_settings(message.chat.id)
    for user in message.new_chat_members:
        if user.is_bot and s.get("anti_bot") and not is_owner(user.id):
            try:
                bot.kick_chat_member(message.chat.id, user.id)
                continue
            except Exception:
                pass
        stat(message.chat.id, "joins")
        if s.get("welcome"):
            text = s.get("welcome_text", DEFAULTS["welcome_text"]).replace("{name}", safe_name(user))
            try: bot.send_message(message.chat.id, text, parse_mode="HTML")
            except Exception: pass

@bot.message_handler(content_types=["left_chat_member"])
def on_leave(message):
    if not is_group(message.chat): return
    s = group_settings(message.chat.id)
    user = message.left_chat_member
    if s.get("goodbye") and user:
        text = s.get("goodbye_text", DEFAULTS["goodbye_text"]).replace("{name}", safe_name(user))
        try: bot.send_message(message.chat.id, text, parse_mode="HTML")
        except Exception: pass

URL_RE = re.compile(r"(?i)(https?://|www\\.|t\\.me/|telegram\\.me/|discord\\.gg/|@[A-Za-z][A-Za-z0-9_]{4,})")
HASHTAG_RE = re.compile(r"#[A-Za-z0-9_\\u0600-\\u06FF]+")

@bot.message_handler(content_types=[
    "text", "photo", "video", "animation", "document", "audio", "voice",
    "video_note", "sticker", "contact", "location", "venue", "poll"
])
def moderate_message(message):
    if not is_group(message.chat) or not message.from_user:
        return
    if message.from_user.is_bot and message.from_user.id != getattr(bot, "id", None):
        s = group_settings(message.chat.id)
        if s.get("anti_bot") and not is_admin(message.chat.id, message.from_user.id):
            delete_message(message, "ربات مزاحم")
            return
    if is_admin(message.chat.id, message.from_user.id):
        return
    s = group_settings(message.chat.id)
    text_content = message.text or message.caption or ""
    now = time.time()
    key = (message.chat.id, message.from_user.id)
    message_times[key].append(now)
    # فلود: بیش از 6 پیام در 8 ثانیه
    if s.get("anti_flood") and len(message_times[key]) >= 6 and now - message_times[key][0] <= 8:
        delete_message(message, "ارسال پیام‌های پیاپی")
        return
    # ضداسپم: متن‌های تکراری پشت‌سرهم
    last = last_seen.get(key)
    if s.get("anti_spam") and text_content and last and last[0] == text_content and now - last[1] < 20:
        delete_message(message, "پیام تکراری")
        return
    if text_content:
        last_seen[key] = (text_content, now)
    if s.get("anti_link") and URL_RE.search(text_content):
        delete_message(message, "ارسال لینک یا شناسه تبلیغاتی")
        return
    lower = text_content.lower()
    if any(word.lower() in lower for word in s.get("bad_words", [])):
        delete_message(message, "کلمه فیلترشده")
        return
    hashtags = HASHTAG_RE.findall(text_content)
    if hashtags:
        normalized = [x.lower() for x in hashtags]
        blocked = [x.lower() for x in s.get("blocked_hashtags", [])]
        if any(tag in blocked for tag in normalized):
            delete_message(message, "هشتگ ممنوع")
            return
        allowed = [x.lower() for x in s.get("allowed_hashtags", [])]
        if s.get("lock_hashtags") and allowed and any(tag not in allowed for tag in normalized):
            delete_message(message, "هشتگ در فهرست مجاز نیست")
            return
    if s.get("anti_forward") and getattr(message, "forward_origin", None):
        delete_message(message, "پیام فورواردشده")
        return
    locked = s.get("locked_types", [])
    if message.content_type in locked:
        delete_message(message, "نوع محتوای قفل‌شده")
        return

# -------------------- راه‌اندازی --------------------
load_db()

def startup():
    global bot_username
    try:
        me = bot.get_me()
        bot_username = me.username
        log.info("%s @%s started; owner=%s", BOT_NAME, bot_username, OWNER_ID)
    except Exception:
        log.exception("اتصال اولیه به تلگرام ناموفق بود")

if __name__ == "__main__":
    startup()
    log.info("Polling started")
    bot.infinity_polling(skip_pending=True, timeout=30, long_polling_timeout=30)
