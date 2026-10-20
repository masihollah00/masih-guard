
import os
import re
import json
import time
import logging
import threading
from collections import defaultdict, deque
from datetime import datetime

import telebot
from telebot import types

# ==================================================
# MASIH GUARD - Persian Telegram Group Manager
# ==================================================

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()

if not TOKEN:
    raise RuntimeError("متغیر TELEGRAM_BOT_TOKEN در تنظیمات هاست تنظیم نشده است.")

bot = telebot.TeleBot(TOKEN, parse_mode="HTML")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s"
)
log = logging.getLogger("MASIH_GUARD")

DATA_FILE = "masih_guard_data.json"
LOCK = threading.RLock()

DEFAULT_SETTINGS = {
    "anti_link": False,
    "anti_spam": False,
    "filter_words": False,
    "welcome": True,
    "goodbye": False,
    "rules": "لطفاً به اعضا احترام بگذارید و قوانین گروه را رعایت کنید.",
    "words": [],
    "warnings": {}
}

def load_data():
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}

data = load_data()

def save_data():
    with LOCK:
        temp = DATA_FILE + ".tmp"
        with open(temp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(temp, DATA_FILE)

def settings(chat_id):
    key = str(chat_id)
    with LOCK:
        if key not in data:
            data[key] = dict(DEFAULT_SETTINGS)
        else:
            for k, v in DEFAULT_SETTINGS.items():
                data[key].setdefault(k, v)
        return data[key]

def is_group(chat):
    return chat.type in ("group", "supergroup")

def is_admin(chat_id, user_id):
    try:
        member = bot.get_chat_member(chat_id, user_id)
        return member.status in ("administrator", "creator")
    except Exception:
        log.exception("Could not check administrator status")
        return False

def is_owner_or_admin(message):
    return (
        message.from_user is not None
        and is_admin(message.chat.id, message.from_user.id)
    )

def safe_delete(message):
    try:
        bot.delete_message(message.chat.id, message.message_id)
        return True
    except Exception:
        log.exception("Could not delete message")
        return False

def say(chat_id, text, **kwargs):
    try:
        return bot.send_message(chat_id, text, **kwargs)
    except Exception:
        log.exception("Could not send message")
        return None

def main_menu(chat_id):
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.row(
        types.InlineKeyboardButton("🛡 امنیت گروه", callback_data="menu_security"),
        types.InlineKeyboardButton("👋 خوشامدگویی", callback_data="menu_welcome")
    )
    kb.row(
        types.InlineKeyboardButton("📜 قوانین", callback_data="menu_rules"),
        types.InlineKeyboardButton("📊 وضعیت", callback_data="menu_status")
    )
    kb.row(
        types.InlineKeyboardButton("🧰 ابزارها", callback_data="menu_tools"),
        types.InlineKeyboardButton("ℹ️ راهنما", callback_data="menu_help")
    )
    return kb

def security_menu(chat_id):
    s = settings(chat_id)
    kb = types.InlineKeyboardMarkup(row_width=1)
    for key, label in (
        ("anti_link", "🔗 ضدلینک"),
        ("anti_spam", "🚫 ضداسپم"),
        ("filter_words", "🤬 فیلتر کلمات")
    ):
        state = "روشن ✅" if s[key] else "خاموش ❌"
        kb.add(types.InlineKeyboardButton(
            f"{label}: {state}", callback_data=f"toggle_{key}"
        ))
    kb.add(types.InlineKeyboardButton("⬅️ منوی اصلی", callback_data="menu_home"))
    return kb

def welcome_menu(chat_id):
    s = settings(chat_id)
    kb = types.InlineKeyboardMarkup(row_width=1)
    for key, label in (
        ("welcome", "👋 خوشامدگویی"),
        ("goodbye", "🚪 پیام خروج")
    ):
        state = "روشن ✅" if s[key] else "خاموش ❌"
        kb.add(types.InlineKeyboardButton(
            f"{label}: {state}", callback_data=f"toggle_{key}"
        ))
    kb.add(types.InlineKeyboardButton("⬅️ منوی اصلی", callback_data="menu_home"))
    return kb

def edit_panel(call, text, markup):
    try:
        bot.edit_message_text(
            text, call.message.chat.id, call.message.message_id,
            reply_markup=markup
        )
    except Exception:
        try:
            bot.answer_callback_query(call.id, "پنل به‌روز شد.")
        except Exception:
            pass

@bot.message_handler(commands=["start", "help"])
def start(message):
    if is_group(message.chat):
        text = (
            "🛡 <b>MASIH GUARD</b>\n"
            "مدیریت و محافظت گروه به زبان فارسی\n\n"
            "برای بازکردن پنل مدیریتی، دستور /panel را بفرست."
        )
    else:
        text = (
            "🛡 <b>MASIH GUARD</b>\n\n"
            "من ربات مدیریت گروه هستم.\n"
            "برای استفاده، مرا به گروه اضافه کن و دسترسی‌های لازم را بده.\n"
            "دستورات: /help"
        )
    bot.reply_to(message, text)

@bot.message_handler(commands=["panel"])
def panel(message):
    if not is_group(message.chat):
        bot.reply_to(message, "پنل را داخل گروه باز کن.")
        return
    if not is_owner_or_admin(message):
        bot.reply_to(message, "⛔ فقط مدیران گروه می‌توانند پنل را باز کنند.")
        return
    bot.reply_to(
        message,
        "🛡 <b>پنل مدیریت MASIH GUARD</b>\nیک بخش را انتخاب کن:",
        reply_markup=main_menu(message.chat.id)
    )

@bot.callback_query_handler(func=lambda call: True)
def callbacks(call):
    msg = call.message
    if not msg or not is_group(msg.chat):
        bot.answer_callback_query(call.id, "این پنل را داخل گروه باز کن.")
        return

    chat_id = msg.chat.id
    user_id = call.from_user.id

    if not is_admin(chat_id, user_id):
        bot.answer_callback_query(
            call.id, "⛔ فقط مدیران گروه اجازهٔ تغییر تنظیمات را دارند.",
            show_alert=True
        )
        return

    s = settings(chat_id)
    action = call.data or ""

    if action == "menu_home":
        edit_panel(call, "🛡 <b>پنل مدیریت</b>\nیک بخش را انتخاب کن:", main_menu(chat_id))

    elif action == "menu_security":
        edit_panel(call, "🛡 <b>امنیت گروه</b>\nبرای تغییر وضعیت، روی گزینه بزن:", security_menu(chat_id))

    elif action == "menu_welcome":
        edit_panel(call, "👋 <b>تنظیمات ورود و خروج</b>", welcome_menu(chat_id))

    elif action == "menu_rules":
        rules = s["rules"]
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("⬅️ منوی اصلی", callback_data="menu_home"))
        edit_panel(call, "📜 <b>قوانین فعلی گروه</b>\n\n" + rules, kb)

    elif action == "menu_status":
        text = (
            "📊 <b>وضعیت امنیت گروه</b>\n\n"
            f"🔗 ضدلینک: {'روشن' if s['anti_link'] else 'خاموش'}\n"
            f"🚫 ضداسپم: {'روشن' if s['anti_spam'] else 'خاموش'}\n"
            f"🤬 فیلتر کلمات: {'روشن' if s['filter_words'] else 'خاموش'}\n"
            f"👋 خوشامدگویی: {'روشن' if s['welcome'] else 'خاموش'}\n"
            f"🚪 پیام خروج: {'روشن' if s['goodbye'] else 'خاموش'}\n"
            f"📚 تعداد کلمات فیلتر: {len(s['words'])}"
        )
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("⬅️ منوی اصلی", callback_data="menu_home"))
        edit_panel(call, text, kb)

    elif action == "menu_tools":
        text = (
            "🧰 <b>ابزارها</b>\n\n"
            "/id - شناسهٔ کاربر و گروه\n"
            "/calc 12*5 - محاسبه\n"
            "/rules - مشاهدهٔ قوانین\n"
            "/words - فهرست کلمات فیلتر"
        )
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("⬅️ منوی اصلی", callback_data="menu_home"))
        edit_panel(call, text, kb)

    elif action == "menu_help":
        text = (
            "ℹ️ <b>راهنمای مدیریت</b>\n\n"
            "/panel - پنل\n"
            "/setrules متن قوانین - تنظیم قوانین\n"
            "/addword کلمه - افزودن کلمه به فیلتر\n"
            "/delword کلمه - حذف کلمه از فیلتر\n"
            "/warn با ریپلای - اخطار\n"
            "/warnings با ریپلای - شمارش اخطارها\n"
            "/mute دقیقه با ریپلای - سکوت\n"
            "/unmute با ریپلای - رفع سکوت\n"
            "/kick با ریپلای - اخراج\n"
            "/ban با ریپلای - مسدودکردن\n"
            "/unban شناسه - رفع مسدودی\n"
            "/purge تعداد - حذف پیام‌های اخیر"
        )
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("⬅️ منوی اصلی", callback_data="menu_home"))
        edit_panel(call, text, kb)

    elif action.startswith("toggle_"):
        key = action[len("toggle_"):]
        if key not in ("anti_link", "anti_spam", "filter_words", "welcome", "goodbye"):
            bot.answer_callback_query(call.id, "گزینه نامعتبر است.")
            return
        s[key] = not s[key]
        save_data()
        bot.answer_callback_query(call.id, "تنظیم ذخیره شد.")
        if key in ("anti_link", "anti_spam", "filter_words"):
            edit_panel(call, "🛡 <b>امنیت گروه</b>", security_menu(chat_id))
        else:
            edit_panel(call, "👋 <b>تنظیمات ورود و خروج</b>", welcome_menu(chat_id))
        return

    else:
        bot.answer_callback_query(call.id, "گزینه ناشناخته است.")
        return

    bot.answer_callback_query(call.id)

@bot.message_handler(commands=["rules"])
def rules(message):
    s = settings(message.chat.id)
    bot.reply_to(message, "📜 <b>قوانین گروه</b>\n\n" + s["rules"])

@bot.message_handler(commands=["setrules"])
def set_rules(message):
    if not is_group(message.chat) or not is_owner_or_admin(message):
        bot.reply_to(message, "⛔ این دستور مخصوص مدیران گروه است.")
        return
    value = (message.text or "").partition(" ")[2].strip()
    if not value:
        bot.reply_to(message, "استفاده: /setrules متن قوانین")
        return
    settings(message.chat.id)["rules"] = value[:3500]
    save_data()
    bot.reply_to(message, "✅ قوانین گروه ذخیره شد.")

@bot.message_handler(commands=["addword"])
def add_word(message):
    if not is_group(message.chat) or not is_owner_or_admin(message):
        bot.reply_to(message, "⛔ این دستور مخصوص مدیران گروه است.")
        return
    word = (message.text or "").partition(" ")[2].strip().lower()
    if not word:
        bot.reply_to(message, "استفاده: /addword کلمه")
        return
    s = settings(message.chat.id)
    if word not in s["words"]:
        s["words"].append(word[:100])
        save_data()
    bot.reply_to(message, "✅ کلمه به فهرست فیلتر اضافه شد.")

@bot.message_handler(commands=["delword"])
def del_word(message):
    if not is_group(message.chat) or not is_owner_or_admin(message):
        bot.reply_to(message, "⛔ این دستور مخصوص مدیران گروه است.")
        return
    word = (message.text or "").partition(" ")[2].strip().lower()
    s = settings(message.chat.id)
    if word in s["words"]:
        s["words"].remove(word)
        save_data()
        bot.reply_to(message, "✅ کلمه حذف شد.")
    else:
        bot.reply_to(message, "این کلمه در فهرست نبود.")

@bot.message_handler(commands=["words"])
def list_words(message):
    if not is_group(message.chat) or not is_owner_or_admin(message):
        bot.reply_to(message, "⛔ این دستور مخصوص مدیران گروه است.")
        return
    words = settings(message.chat.id)["words"]
    bot.reply_to(message, "📚 کلمات فیلتر:\n" + ("\n".join(words) if words else "فهرست خالی است."))

def replied_target(message):
    if not message.reply_to_message:
        return None
    target = message.reply_to_message.from_user
    if not target or target.is_bot:
        return None
    if is_admin(message.chat.id, target.id):
        return None
    return target

@bot.message_handler(commands=["warn"])
def warn(message):
    if not is_group(message.chat) or not is_owner_or_admin(message):
        bot.reply_to(message, "⛔ فقط مدیران گروه.")
        return
    target = replied_target(message)
    if not target:
        bot.reply_to(message, "برای اخطار، روی پیام عضو ریپلای کن. به مدیران اخطار داده نمی‌شود.")
        return
    s = settings(message.chat.id)
    key = str(target.id)
    s["warnings"][key] = int(s["warnings"].get(key, 0)) + 1
    save_data()
    bot.reply_to(message, f"⚠️ اخطار برای {target.first_name} ثبت شد. تعداد: {s['warnings'][key]}")

@bot.message_handler(commands=["warnings"])
def warnings_cmd(message):
    if not is_group(message.chat) or not is_owner_or_admin(message):
        bot.reply_to(message, "⛔ فقط مدیران گروه.")
        return
    target = replied_target(message)
    if not target:
        bot.reply_to(message, "روی پیام عضو ریپلای کن.")
        return
    count = settings(message.chat.id)["warnings"].get(str(target.id), 0)
    bot.reply_to(message, f"⚠️ تعداد اخطارهای این عضو: {count}")

@bot.message_handler(commands=["mute"])
def mute(message):
    if not is_group(message.chat) or not is_owner_or_admin(message):
        bot.reply_to(message, "⛔ فقط مدیران گروه.")
        return
    target = replied_target(message)
    if not target:
        bot.reply_to(message, "روی پیام عضو ریپلای کن و بنویس: /mute 10")
        return
    parts = (message.text or "").split()
    try:
        minutes = int(parts[1]) if len(parts) > 1 else 10
        if not 1 <= minutes <= 10080:
            raise ValueError
    except ValueError:
        bot.reply_to(message, "مدت باید بین ۱ تا ۱۰۰۸۰ دقیقه باشد.")
        return
    try:
        bot.restrict_chat_member(
            message.chat.id, target.id,
            permissions=types.ChatPermissions(can_send_messages=False),
            until_date=int(time.time() + minutes * 60)
        )
        bot.reply_to(message, f"🔇 {target.first_name} به مدت {minutes} دقیقه ساکت شد.")
    except Exception:
        log.exception("Mute failed")
        bot.reply_to(message, "❌ سکوت انجام نشد؛ دسترسی Restrict Members ربات را بررسی کن.")

@bot.message_handler(commands=["unmute"])
def unmute(message):
    if not is_group(message.chat) or not is_owner_or_admin(message):
        bot.reply_to(message, "⛔ فقط مدیران گروه.")
        return
    target = replied_target(message)
    if not target:
        bot.reply_to(message, "روی پیام عضو ریپلای کن.")
        return
    try:
        bot.restrict_chat_member(
            message.chat.id, target.id,
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
        bot.reply_to(message, "🔊 محدودیت ارسال پیام برداشته شد.")
    except Exception:
        log.exception("Unmute failed")
        bot.reply_to(message, "❌ رفع سکوت انجام نشد؛ دسترسی‌های ربات را بررسی کن.")

@bot.message_handler(commands=["ban", "kick"])
def ban_kick(message):
    if not is_group(message.chat) or not is_owner_or_admin(message):
        bot.reply_to(message, "⛔ فقط مدیران گروه.")
        return
    target = replied_target(message)
    if not target:
        bot.reply_to(message, "روی پیام عضو ریپلای کن.")
        return
    try:
        bot.ban_chat_member(message.chat.id, target.id)
        if message.text.startswith("/kick"):
            bot.unban_chat_member(message.chat.id, target.id)
            bot.reply_to(message, "👢 عضو از گروه اخراج شد.")
        else:
            bot.reply_to(message, "⛔ عضو مسدود شد.")
    except Exception:
        log.exception("Ban/kick failed")
        bot.reply_to(message, "❌ عملیات انجام نشد؛ دسترسی Ban Users ربات را بررسی کن.")

@bot.message_handler(commands=["unban"])
def unban(message):
    if not is_group(message.chat) or not is_owner_or_admin(message):
        bot.reply_to(message, "⛔ فقط مدیران گروه.")
        return
    parts = (message.text or "").split()
    if len(parts) < 2 or not parts[1].lstrip("-").isdigit():
        bot.reply_to(message, "استفاده: /unban شناسه_عددی")
        return
    try:
        bot.unban_chat_member(message.chat.id, int(parts[1]))
        bot.reply_to(message, "✅ مسدودی برداشته شد.")
    except Exception:
        log.exception("Unban failed")
        bot.reply_to(message, "❌ رفع مسدودی انجام نشد.")

@bot.message_handler(commands=["id"])
def get_id(message):
    text = f"🆔 شناسهٔ گروه: <code>{message.chat.id}</code>"
    if message.from_user:
        text += f"\nشناسهٔ شما: <code>{message.from_user.id}</code>"
    if message.reply_to_message and message.reply_to_message.from_user:
        text += f"\nشناسهٔ عضو: <code>{message.reply_to_message.from_user.id}</code>"
    bot.reply_to(message, text)

@bot.message_handler(commands=["calc"])
def calc(message):
    expr = (message.text or "").partition(" ")[2].strip()
    if not expr or len(expr) > 80 or not re.fullmatch(r"[0-9+\-*/(). %]+", expr):
        bot.reply_to(message, "استفاده: /calc 12*(5+2)")
        return
    try:
        # Arithmetic-only evaluator; no Python names or function calls.
        result = eval(expr, {"__builtins__": {}}, {})
        if isinstance(result, (int, float)) and abs(result) < 10**100:
            bot.reply_to(message, f"🧮 نتیجه: <code>{result}</code>")
        else:
            bot.reply_to(message, "نتیجه خارج از محدوده است.")
    except Exception:
        bot.reply_to(message, "عبارت ریاضی معتبر نیست.")

@bot.message_handler(commands=["purge"])
def purge(message):
    if not is_group(message.chat) or not is_owner_or_admin(message):
        bot.reply_to(message, "⛔ فقط مدیران گروه.")
        return
    try:
        count = int((message.text or "").split()[1])
        if not 1 <= count <= 100:
            raise ValueError
    except (ValueError, IndexError):
        bot.reply_to(message, "استفاده: /purge 20 (حداکثر ۱۰۰ پیام)")
        return
    if not message.reply_to_message:
        bot.reply_to(message, "روی اولین پیامی که می‌خواهی پاک شود ریپلای کن.")
        return
    start_id = message.reply_to_message.message_id
    end_id = message.message_id
    deleted = 0
    for mid in range(start_id, min(end_id, start_id + count)):
        try:
            bot.delete_message(message.chat.id, mid)
            deleted += 1
        except Exception:
            pass
    try:
        bot.delete_message(message.chat.id, message.message_id)
    except Exception:
        pass
    say(message.chat.id, f"🧹 تعداد پیام‌های حذف‌شده: {deleted}")

# --------------------------------------------------
# Anti-link / anti-spam / word filter
# --------------------------------------------------

LINK_RE = re.compile(
    r"(?i)(?:https?://|www\.|t\.me/|telegram\.me/|"
    r"telegram\.dog/|(?:[a-z0-9-]+\.)+(?:com|net|org|info|biz|io|me|ir|de|co|app|xyz)\b)"
)

spam_times = defaultdict(deque)
SPAM_LIMIT = 7
SPAM_WINDOW = 8

def get_message_text(message):
    return (message.text or message.caption or "").strip()

def has_link(message, text):
    if LINK_RE.search(text):
        return True
    entities = (
        getattr(message, "entities", None)
        or getattr(message, "caption_entities", None)
        or []
    )
    return any(
        getattr(entity, "type", "") in ("url", "text_link")
        for entity in entities
    )

@bot.message_handler(
    content_types=[
        "text", "photo", "video", "document", "audio",
        "voice", "video_note", "animation", "sticker"
    ]
)
def inspect_message(message):
    if not is_group(message.chat) or not message.from_user:
        return

    # Never moderate group administrators or the bot itself.
    if message.from_user.is_bot or is_admin(message.chat.id, message.from_user.id):
        return

    s = settings(message.chat.id)
    text = get_message_text(message)
    user_key = (message.chat.id, message.from_user.id)

    if s["anti_link"] and text and has_link(message, text):
        if safe_delete(message):
            say(message.chat.id, "🔗 ارسال لینک در این گروه مجاز نیست.")
        return

    if s["filter_words"] and text:
        lowered = text.casefold()
        words = s["words"]
        if any(word.casefold() in lowered for word in words if word):
            if safe_delete(message):
                say(message.chat.id, "🤬 پیام به‌دلیل داشتن کلمهٔ فیلترشده حذف شد.")
            return

    if s["anti_spam"]:
        now = time.monotonic()
        queue = spam_times[user_key]
        queue.append(now)
        while queue and now - queue[0] > SPAM_WINDOW:
            queue.popleft()
        if len(queue) >= SPAM_LIMIT:
            if safe_delete(message):
                say(message.chat.id, "🚫 لطفاً پشت‌سرهم پیام نفرست.")
            queue.clear()

# --------------------------------------------------
# Welcome / goodbye
# --------------------------------------------------

@bot.message_handler(content_types=["new_chat_members"])
def new_members(message):
    s = settings(message.chat.id)
    if not s["welcome"]:
        return
    for member in message.new_chat_members:
        if member.id == bot.get_me().id:
            continue
        name = member.first_name or "دوست عزیز"
        say(message.chat.id, f"👋 خوش آمدی {name}!\nلطفاً قوانین گروه را رعایت کن.")

@bot.message_handler(content_types=["left_chat_member"])
def left_member(message):
    s = settings(message.chat.id)
    if s["goodbye"] and message.left_chat_member:
        say(message.chat.id, "🚪 یکی از اعضا گروه را ترک کرد.")

# --------------------------------------------------
# Start
# --------------------------------------------------

def main():
    log.info("Starting MASIH GUARD")
    while True:
        try:
            bot.infinity_polling(
                skip_pending=True,
                timeout=30,
                long_polling_timeout=30
            )
        except Exception:
            log.exception("Polling stopped; retrying in 5 seconds")
            time.sleep(5)

if __name__ == "__main__":
    main()
