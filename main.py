# -*- coding: utf-8 -*-
"""MASIH GUARD S1000+ - نسخه یکپارچه و فارسی
پیش‌نیاز: pip install pyTelegramBotAPI requests
متغیرهای محیطی: BOT_TOKEN (ضروری), OWNER_ID (اختیاری), AI_API_KEY (اختیاری)
توجه: این فایل نسخه مستقل و پایه است؛ قبل از جایگزینی نسخه اصلی، از آن نسخه پشتیبان بگیرید.
"""
import os
import re
import json
import time
import random
import threading
from datetime import datetime, timedelta

import telebot
from telebot import types

BOT_TOKEN = (os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
OWNER_ID = int(os.getenv("OWNER_ID", "8620924698"))
DATA_FILE = os.getenv("DATA_FILE", "masih_guard_data.json")
AI_API_KEY = os.getenv("AI_API_KEY", "").strip()
AI_BASE_URL = os.getenv("AI_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
AI_MODEL = os.getenv("AI_MODEL", "openai/gpt-4o-mini").strip()
BRAND = "MASIH GUARD S1000+"

if not BOT_TOKEN:
    raise RuntimeError("توکن ربات تنظیم نشده است؛ متغیر محیطی BOT_TOKEN را در هاست وارد کن.")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML", threaded=True, num_threads=4)
LOCK = threading.RLock()
WAITING = {}
DEFAULT_GROUP = {
    "anti_link": True, "anti_spam": True, "anti_repeat": True, "anti_forward": False,
    "welcome_on": True, "farewell_on": False, "bad_words": [], "warn_limit": 3,
    "rules": "احترام به اعضا الزامی است.", "welcome_text": "سلام {name}، به گروه خوش آمدی!",
    "farewell_text": "خداحافظ {name}", "auto_replies": {}, "muted": [],
    "blocked_words": [], "media_lock": False
}
DEFAULT_DATA = {
    "groups": {}, "warnings": {}, "users": {}, "subscriptions": {}, "purchase_requests": {},
    "transactions": {}, "wallets": {}, "last_daily": {}, "referrals": {}, "tickets": {},
    "logs": [], "settings": {"daily_reward": 10, "referral_reward": 5},
    "proxies": [], "customers": {}, "points": {}, "last_luck": {}
}

def now_text():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def esc(value):
    from html import escape
    return escape(str(value or ""), quote=False)

def load_data():
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            saved = json.load(f)
        data = dict(DEFAULT_DATA)
        data.update(saved if isinstance(saved, dict) else {})
        for k, v in DEFAULT_DATA.items():
            if k not in data:
                data[k] = v.copy() if isinstance(v, (dict, list)) else v
        return data
    except (OSError, ValueError, TypeError):
        return json.loads(json.dumps(DEFAULT_DATA, ensure_ascii=False))

DATA = load_data()

def save_data():
    with LOCK:
        tmp = DATA_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(DATA, f, ensure_ascii=False, indent=2)
        os.replace(tmp, DATA_FILE)

def is_owner(uid):
    return int(uid or 0) == OWNER_ID

def group_cfg(chat_id):
    key = str(chat_id)
    if key not in DATA["groups"]:
        DATA["groups"][key] = json.loads(json.dumps(DEFAULT_GROUP, ensure_ascii=False))
    else:
        for k, v in DEFAULT_GROUP.items():
            DATA["groups"][key].setdefault(k, v.copy() if isinstance(v, (list, dict)) else v)
    return DATA["groups"][key]

def log(action, chat_id="", user_id="", detail=""):
    DATA["logs"].append({"time": now_text(), "action": action, "chat_id": str(chat_id),
                         "user_id": str(user_id), "detail": str(detail)[:300]})
    DATA["logs"] = DATA["logs"][-1000:]
    save_data()

def user_keyboard():
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.row(types.InlineKeyboardButton("💎 کیف پول", callback_data="u:wallet"),
           types.InlineKeyboardButton("🎁 پاداش روزانه", callback_data="u:daily"))
    kb.row(types.InlineKeyboardButton("🛒 خرید اشتراک الماسی", callback_data="u:diamondshop"))
    kb.row(types.InlineKeyboardButton("💳 خرید اشتراک پولی", callback_data="u:paidshop"))
    kb.row(types.InlineKeyboardButton("🎫 پشتیبانی", callback_data="u:ticket"),
           types.InlineKeyboardButton("🧠 هوش مصنوعی", callback_data="u:ai"))
    kb.row(types.InlineKeyboardButton("🔤 تبدیل فونت", callback_data="u:font"),
           types.InlineKeyboardButton("📊 آمار", callback_data="u:stats"))
    return kb

PAID_PACKAGES = {
    30: {"price": 40000, "label": "۳۰ روزه"},
    60: {"price": 80000, "label": "۶۰ روزه"},
    90: {"price": 135000, "label": "۹۰ روزه"},
}

def paid_keyboard():
    kb = types.InlineKeyboardMarkup(row_width=1)
    for days, p in PAID_PACKAGES.items():
        kb.add(types.InlineKeyboardButton(
            f"💳 {p['label']} — {p['price']:,} تومان", callback_data=f"paidbuy:{days}"))
    kb.add(types.InlineKeyboardButton("⬅️ بازگشت", callback_data="u:home"))
    return kb

def owner_request_keyboard(order_id):
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.row(types.InlineKeyboardButton("✅ تأیید پرداخت", callback_data=f"paidapprove:{order_id}"),
           types.InlineKeyboardButton("❌ رد درخواست", callback_data=f"paidreject:{order_id}"))
    return kb

def wallet(uid):
    return int(DATA["wallets"].get(str(uid), 0))

def change_wallet(uid, amount, reason):
    key = str(uid)
    DATA["wallets"][key] = wallet(uid) + int(amount)
    DATA["transactions"].setdefault(key, []).append(
        {"amount": int(amount), "reason": reason, "time": now_text()})
    save_data()

def subscription_expiry(uid):
    return DATA["subscriptions"].get(str(uid), {}).get("expires", "ندارد")

def activate_subscription(uid, days):
    now = datetime.now()
    old = DATA["subscriptions"].get(str(uid), {}).get("expires", "")
    try:
        base = datetime.strptime(old, "%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        base = now
    if base < now:
        base = now
    expiry = (base + timedelta(days=int(days))).strftime("%Y-%m-%d %H:%M:%S")
    DATA["subscriptions"][str(uid)] = {"expires": expiry, "source": "paid", "updated": now_text()}
    save_data()
    return expiry

def owner_only_private(call):
    return is_owner(call.from_user.id) and call.message and call.message.chat.type == "private" and call.message.chat.id == call.from_user.id

def main_menu_text():
    return (
        "🛡️ <b>به MASIH GUARD خوش آمدی</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "🤖 ربات مدیریت گروه و ابزارهای کاربردی\n\n"
        "🧹 ضداسپم و ضدلینک\n"
        "👋 خوشامد و خداحافظی\n"
        "⚠️ اخطار، سکوت، اخراج و مسدودسازی\n"
        "📜 قوانین و پاسخ خودکار\n"
        "💎 کیف پول و اشتراک\n"
        "🎫 پشتیبانی و 🧠 هوش مصنوعی\n\n"
        "برای تنظیمات گروه، ربات را مدیر گروه کن و دسترسی‌های لازم را بده."
    )

def admin_keyboard():
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.row(types.InlineKeyboardButton("🛡️ ضدلینک", callback_data="cfg:anti_link"),
           types.InlineKeyboardButton("🧹 ضداسپم", callback_data="cfg:anti_spam"))
    kb.row(types.InlineKeyboardButton("👋 خوشامد", callback_data="cfg:welcome_on"),
           types.InlineKeyboardButton("🚪 خداحافظی", callback_data="cfg:farewell_on"))
    kb.row(types.InlineKeyboardButton("📜 تنظیم قوانین", callback_data="set:rules"),
           types.InlineKeyboardButton("💬 پاسخ خودکار", callback_data="set:reply"))
    kb.row(types.InlineKeyboardButton("📊 گزارش", callback_data="admin:stats"),
           types.InlineKeyboardButton("🧾 گزارش‌ها", callback_data="admin:logs"))
    return kb

@bot.message_handler(commands=["start", "help"])
def start(message):
    uid = message.from_user.id
    if message.chat.type != "private":
        bot.reply_to(message, "برای استفاده از منو، وارد گفت‌وگوی خصوصی ربات شو.")
        return
    bot.send_message(uid, main_menu_text(), reply_markup=user_keyboard())

@bot.message_handler(commands=["panel"])
def panel(message):
    if not is_owner(message.from_user.id):
        bot.reply_to(message, "⛔ این بخش فقط برای مالک ربات است.")
        return
    bot.send_message(message.chat.id, "👑 <b>پنل مالک</b>\nاز دکمه‌ها استفاده کن.", reply_markup=admin_keyboard())

@bot.message_handler(commands=["id"])
def show_id(message):
    bot.reply_to(message, f"🆔 شناسه کاربر: <code>{message.from_user.id}</code>\nشناسه گروه: <code>{message.chat.id}</code>")

@bot.message_handler(commands=["warn", "mute", "unmute", "ban", "unban", "kick", "pin", "purge"])
def admin_commands(message):
    if message.chat.type not in ("group", "supergroup"):
        bot.reply_to(message, "این فرمان فقط داخل گروه استفاده می‌شود.")
        return
    try:
        member = bot.get_chat_member(message.chat.id, message.from_user.id)
        if member.status not in ("administrator", "creator"):
            bot.reply_to(message, "⛔ فقط مدیر گروه می‌تواند از این فرمان استفاده کند.")
            return
    except Exception:
        bot.reply_to(message, "دسترسی مدیر گروه بررسی نشد؛ ربات باید مدیر باشد.")
        return
    cmd = message.text.split()[0].split("@")[0].lower()
    target = message.reply_to_message.from_user if message.reply_to_message else None
    if cmd == "/purge":
        if not message.reply_to_message:
            bot.reply_to(message, "برای پاک‌سازی، به پیام موردنظر ریپلای کن.")
            return
        deleted = 0
        try:
            for mid in range(message.reply_to_message.message_id, message.message_id + 1):
                bot.delete_message(message.chat.id, mid)
                deleted += 1
        except Exception:
            pass
        bot.send_message(message.chat.id, f"🧹 پاک‌سازی انجام شد؛ تعداد حذف موفق: {deleted}")
        return
    if cmd == "/pin":
        if not message.reply_to_message:
            bot.reply_to(message, "برای سنجاق، به پیام موردنظر ریپلای کن.")
            return
        try:
            bot.pin_chat_message(message.chat.id, message.reply_to_message.message_id)
            bot.reply_to(message, "📌 پیام سنجاق شد.")
        except Exception:
            bot.reply_to(message, "سنجاق پیام ناموفق بود؛ دسترسی ربات را بررسی کن.")
        return
    if not target:
        bot.reply_to(message, "برای این فرمان باید به پیام کاربر ریپلای کنی.")
        return
    if target.id == OWNER_ID or target.id == message.from_user.id:
        bot.reply_to(message, "این عملیات روی مالک یا خود مدیر اجرا نمی‌شود.")
        return
    try:
        if cmd == "/warn":
            key = f"{message.chat.id}:{target.id}"
            count = int(DATA["warnings"].get(key, 0)) + 1
            DATA["warnings"][key] = count
            save_data()
            limit = int(group_cfg(message.chat.id).get("warn_limit", 3))
            if count >= limit:
                bot.restrict_chat_member(message.chat.id, target.id, until_date=int(time.time()) + 600,
                    permissions=types.ChatPermissions(can_send_messages=False))
                DATA["warnings"][key] = 0
                save_data()
                bot.reply_to(message, f"⚠️ اخطار به حد نصاب رسید؛ {esc(target.first_name)} برای ۱۰ دقیقه سکوت شد.")
            else:
                bot.reply_to(message, f"⚠️ اخطار {count}/{limit} برای {esc(target.first_name)} ثبت شد.")
        elif cmd == "/mute":
            bot.restrict_chat_member(message.chat.id, target.id, until_date=int(time.time()) + 3600,
                permissions=types.ChatPermissions(can_send_messages=False))
            bot.reply_to(message, "🔇 کاربر برای یک ساعت سکوت شد.")
        elif cmd == "/unmute":
            bot.restrict_chat_member(message.chat.id, target.id, permissions=types.ChatPermissions(
                can_send_messages=True, can_send_audios=True, can_send_documents=True, can_send_photos=True,
                can_send_videos=True, can_send_video_notes=True, can_send_voice_notes=True,
                can_send_polls=True, can_send_other_messages=True, can_add_web_page_previews=True))
            bot.reply_to(message, "🔊 سکوت کاربر برداشته شد.")
        elif cmd == "/ban":
            bot.ban_chat_member(message.chat.id, target.id)
            bot.reply_to(message, "⛔ کاربر مسدود شد.")
        elif cmd == "/unban":
            bot.unban_chat_member(message.chat.id, target.id, only_if_banned=True)
            bot.reply_to(message, "✅ مسدودیت کاربر برداشته شد.")
        elif cmd == "/kick":
            bot.ban_chat_member(message.chat.id, target.id)
            bot.unban_chat_member(message.chat.id, target.id, only_if_banned=True)
            bot.reply_to(message, "👢 کاربر از گروه اخراج شد.")
        log(cmd[1:], message.chat.id, target.id, "فرمان مدیر")
    except Exception as exc:
        bot.reply_to(message, "❌ عملیات انجام نشد؛ دسترسی‌های ربات و وضعیت کاربر را بررسی کن.")
        print("Moderation error:", repr(exc))

@bot.message_handler(content_types=["new_chat_members"])
def welcome(message):
    cfg = group_cfg(message.chat.id)
    if not cfg.get("welcome_on", True):
        return
    for member in message.new_chat_members:
        if member.id == bot.get_me().id:
            continue
        try:
            text = cfg.get("welcome_text", "سلام {name}، به گروه خوش آمدی!").replace("{name}", esc(member.first_name))
            bot.send_message(message.chat.id, "👋 " + text)
            log("join", message.chat.id, member.id, "عضو جدید")
        except Exception as exc:
            print("Welcome error:", repr(exc))

@bot.message_handler(content_types=["left_chat_member"])
def farewell(message):
    cfg = group_cfg(message.chat.id)
    if cfg.get("farewell_on", False):
        try:
            text = cfg.get("farewell_text", "خداحافظ {name}").replace("{name}", esc(message.left_chat_member.first_name))
            bot.send_message(message.chat.id, "🚪 " + text)
        except Exception:
            pass

@bot.message_handler(content_types=["text", "photo", "video", "document", "animation", "voice", "audio", "sticker"])
def group_guard(message):
    if message.chat.type not in ("group", "supergroup") or not message.from_user:
        return
    if message.from_user.is_bot:
        return
    cfg = group_cfg(message.chat.id)
    text = message.text or message.caption or ""
    try:
        member = bot.get_chat_member(message.chat.id, message.from_user.id)
        if member.status in ("administrator", "creator"):
            return
    except Exception:
        pass
    blocked = None
    if cfg.get("anti_link", True) and re.search(r"(https?://|t\.me/|telegram\.me/|www\.)", text, re.I):
        blocked = "لینک"
    if not blocked and cfg.get("anti_spam", True) and len(text) > 700:
        blocked = "پیام بسیار طولانی"
    if not blocked:
        for word in cfg.get("bad_words", []):
            if word and word.casefold() in text.casefold():
                blocked = "واژه ممنوع"
                break
    if blocked:
        try:
            bot.delete_message(message.chat.id, message.message_id)
            log("blocked", message.chat.id, message.from_user.id, blocked)
            bot.send_message(message.chat.id, f"🛡️ پیام {esc(message.from_user.first_name)} به دلیل {blocked} حذف شد.")
        except Exception as exc:
            print("Guard error:", repr(exc))
        return
    if text:
        key = f"{message.chat.id}:{message.from_user.id}"
        last = DATA.setdefault("last_messages", {}).get(key, "")
        if cfg.get("anti_repeat", True) and text.strip() and text.strip() == last:
            try:
                bot.delete_message(message.chat.id, message.message_id)
            except Exception:
                pass
            return
        DATA.setdefault("last_messages", {})[key] = text.strip()[:1000]
        for trigger, answer in cfg.get("auto_replies", {}).items():
            if trigger.casefold() in text.casefold():
                bot.reply_to(message, str(answer)[:3500])
                break
        save_data()

@bot.message_handler(func=lambda m: m.chat.type == "private", content_types=["text"])
def private_text(message):
    uid = message.from_user.id
    state = WAITING.get(uid)
    if not state:
        return
    action = state.get("action")
    text = (message.text or "").strip()
    if action == "ticket":
        ticket_id = str(int(time.time() * 1000))
        DATA["tickets"][ticket_id] = {"user_id": uid, "text": text, "status": "open", "created": now_text()}
        save_data()
        WAITING.pop(uid, None)
        bot.send_message(uid, "✅ تیکتت ثبت شد.")
        try:
            bot.send_message(OWNER_ID, f"🎫 <b>تیکت جدید</b>\nشناسه: <code>{ticket_id}</code>\nکاربر: <code>{uid}</code>\n\n{esc(text)}")
        except Exception:
            pass
    elif action == "font":
        WAITING.pop(uid, None)
        variants = [
            ("✨ ستاره‌ای", f"✦ {text} ✦"), ("👑 سلطنتی", f"꧁ {text} ꧂"),
            ("💜 قلبی", f"♡ {text} ♡"), ("⚡ برقی", f"⚡ {text} ⚡"),
            ("🌙 ماه", f"☾ {text} ☽"), ("🖤 تیره", f"༒ {text} ༒"),
            ("🌈 رنگین", f"🌈 {text} 🌈"), ("【کادری】", f"【 {text} 】")
        ]
        bot.send_message(uid, "\n".join(f"{i+1}. {name}: {esc(value)}" for i, (name, value) in enumerate(variants)))
    elif action == "ai":
        WAITING.pop(uid, None)
        if not AI_API_KEY:
            bot.send_message(uid, "🧠 هوش مصنوعی تنظیم نشده است. مالک باید متغیر AI_API_KEY را در هاست قرار دهد.")
            return
        try:
            import requests
            response = requests.post(AI_BASE_URL + "/chat/completions",
                headers={"Authorization": "Bearer " + AI_API_KEY, "Content-Type": "application/json"},
                json={"model": AI_MODEL, "messages":[
                    {"role":"system","content":"به فارسی روان و ایمن پاسخ بده."},
                    {"role":"user","content":text}], "temperature":0.6},
                timeout=35)
            response.raise_for_status()
            answer = response.json()["choices"][0]["message"]["content"]
            bot.send_message(uid, esc(answer[:4000]))
        except Exception as exc:
            print("AI error:", repr(exc))
            bot.send_message(uid, "❌ پاسخ هوش مصنوعی دریافت نشد؛ کلید و تنظیمات API را بررسی کن.")
    elif action == "rules":
        group_id = state.get("group_id")
        if not is_owner(uid):
            WAITING.pop(uid, None)
            return
        group_cfg(group_id)["rules"] = text
        save_data()
        WAITING.pop(uid, None)
        bot.send_message(uid, "✅ قوانین ذخیره شد.")
    elif action == "reply":
        group_id = state.get("group_id")
        if not is_owner(uid):
            WAITING.pop(uid, None)
            return
        if "|" not in text:
            bot.send_message(uid, "قالب درست: کلمه کلیدی | پاسخ")
            return
        trigger, answer = [x.strip() for x in text.split("|", 1)]
        group_cfg(group_id)["auto_replies"][trigger] = answer
        save_data()
        WAITING.pop(uid, None)
        bot.send_message(uid, "✅ پاسخ خودکار ذخیره شد.")

@bot.callback_query_handler(func=lambda c: True)
def callbacks(call):
    uid = call.from_user.id
    data = call.data or ""
    try:
        if data.startswith("u:"):
            if not call.message or call.message.chat.type != "private":
                bot.answer_callback_query(call.id, "این گزینه فقط در پیوی ربات است.", show_alert=True)
                return
            if data == "u:home":
                bot.answer_callback_query(call.id)
                bot.send_message(uid, main_menu_text(), reply_markup=user_keyboard())
            elif data == "u:wallet":
                bot.answer_callback_query(call.id)
                bot.send_message(uid, f"💎 موجودی: {wallet(uid)} الماس\n⭐ اعتبار اشتراک: {esc(subscription_expiry(uid))}")
            elif data == "u:daily":
                today = datetime.now().strftime("%Y-%m-%d")
                if DATA["last_daily"].get(str(uid)) == today:
                    answer = "⏳ پاداش امروز را قبلاً گرفته‌ای."
                else:
                    amount = int(DATA["settings"].get("daily_reward", 10))
                    DATA["last_daily"][str(uid)] = today
                    change_wallet(uid, amount, "پاداش روزانه")
                    answer = f"🎁 {amount} الماس گرفتی!"
                save_data()
                bot.answer_callback_query(call.id)
                bot.send_message(uid, answer)
            elif data == "u:paidshop":
                bot.answer_callback_query(call.id)
                bot.send_message(uid,
                    "💳 <b>اشتراک پولی</b>\n۳۰ روز: ۴۰٬۰۰۰ تومان\n۶۰ روز: ۸۰٬۰۰۰ تومان\n۹۰ روز: ۱۳۵٬۰۰۰ تومان\n\n"
                    "پس از انتخاب بسته، درخواست برای مالک ارسال می‌شود. اطلاعات پرداخت را با مالک هماهنگ کن.",
                    reply_markup=paid_keyboard())
            elif data == "u:diamondshop":
                kb = types.InlineKeyboardMarkup()
                kb.add(types.InlineKeyboardButton("💎 ۱۵ الماس / ۴۰ روز", callback_data="diamondbuy:15:40"))
                kb.add(types.InlineKeyboardButton("💎 ۳۰ الماس / ۸۰ روز", callback_data="diamondbuy:30:80"))
                bot.answer_callback_query(call.id)
                bot.send_message(uid, "🛒 فروشگاه اشتراک الماسی\nانتخاب کن:", reply_markup=kb)
            elif data == "u:ticket":
                WAITING[uid] = {"action": "ticket"}
                bot.answer_callback_query(call.id)
                bot.send_message(uid, "🎫 متن تیکت را بفرست.")
            elif data == "u:ai":
                WAITING[uid] = {"action": "ai"}
                bot.answer_callback_query(call.id)
                bot.send_message(uid, "🧠 پرسشت را بفرست.")
            elif data == "u:font":
                WAITING[uid] = {"action": "font"}
                bot.answer_callback_query(call.id)
                bot.send_message(uid, "🔤 متن را بفرست تا چند سبک تزئینی بسازم.")
            elif data == "u:stats":
                bot.answer_callback_query(call.id)
                bot.send_message(uid, f"📊 گزارش کلی\nکاربران ثبت‌شده: {len(DATA['wallets'])}\nتیکت‌ها: {len(DATA['tickets'])}\nدرخواست‌های خرید: {len(DATA['purchase_requests'])}")
            return

        if data.startswith("paidbuy:"):
            if not call.message or call.message.chat.type != "private":
                bot.answer_callback_query(call.id, "فقط در پیوی ربات.", show_alert=True)
                return
            days = int(data.split(":")[1])
            package = PAID_PACKAGES.get(days)
            if not package:
                bot.answer_callback_query(call.id, "بسته معتبر نیست.", show_alert=True)
                return
            order_id = f"{int(time.time() * 1000)}-{uid}"
            request = {"id": order_id, "user_id": uid, "days": days, "price": package["price"],
                       "status": "pending", "created": now_text()}
            DATA["purchase_requests"][order_id] = request
            save_data()
            try:
                profile = bot.get_chat(uid)
                buyer_name = " ".join(x for x in [profile.first_name or "", profile.last_name or ""] if x)
                username = "@" + profile.username if profile.username else "ندارد"
            except Exception:
                buyer_name, username = "نامشخص", "نامشخص"
            bot.send_message(OWNER_ID,
                "💳 <b>درخواست خرید اشتراک</b>\n━━━━━━━━━━━━━━━━━━\n"
                f"🧾 کد: <code>{esc(order_id)}</code>\n👤 نام: {esc(buyer_name)}\n🔗 نام کاربری: {esc(username)}\n"
                f"🆔 شناسه: <code>{uid}</code>\n⭐ بسته: {package['label']}\n💰 مبلغ: <b>{package['price']:,} تومان</b>\n"
                f"🕒 {esc(request['created'])}\n\n⚠️ فقط بعد از بررسی واقعی پرداخت تأیید کن.",
                reply_markup=owner_request_keyboard(order_id))
            bot.answer_callback_query(call.id, "درخواست برای مالک فرستاده شد.")
            bot.send_message(uid, "✅ درخواست به مالک ارسال شد. برای اطلاعات پرداخت با مالک هماهنگ کن؛ فعال‌سازی بعد از تأیید دستی است.")
            return

        if data.startswith(("paidapprove:", "paidreject:")):
            if not owner_only_private(call):
                bot.answer_callback_query(call.id, "فقط مالک می‌تواند این کار را انجام دهد.", show_alert=True)
                return
            action, order_id = data.split(":", 1)
            request = DATA["purchase_requests"].get(order_id)
            if not request or request.get("status") != "pending":
                bot.answer_callback_query(call.id, "درخواست معتبر یا در انتظار بررسی نیست.", show_alert=True)
                return
            buyer_id, days = int(request["user_id"]), int(request["days"])
            if action == "paidapprove":
                expiry = activate_subscription(buyer_id, days)
                request["status"] = "approved"
                request["reviewed"] = now_text()
                request["reviewed_by"] = uid
                request["expires"] = expiry
                save_data()
                bot.send_message(buyer_id, f"✅ پرداخت تأیید شد!\n⭐ اشتراک {days} روزه فعال شد.\n📅 اعتبار تا: {esc(expiry)}")
                bot.answer_callback_query(call.id, "اشتراک فعال شد.")
            else:
                request["status"] = "rejected"
                request["reviewed"] = now_text()
                request["reviewed_by"] = uid
                save_data()
                bot.send_message(buyer_id, "❌ درخواست تأیید نشد؛ اگر پرداخت کرده‌ای با مالک هماهنگ کن.")
                bot.answer_callback_query(call.id, "درخواست رد شد.")
            try:
                bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
            except Exception:
                pass
            return

        if data.startswith("diamondbuy:"):
            _, diamonds, days = data.split(":")
            diamonds, days = int(diamonds), int(days)
            if wallet(uid) < diamonds:
                bot.answer_callback_query(call.id, "الماس کافی نیست.", show_alert=True)
                return
            change_wallet(uid, -diamonds, f"خرید اشتراک {days} روزه")
            expiry = activate_subscription(uid, days)
            bot.answer_callback_query(call.id, "اشتراک الماسی فعال شد.")
            bot.send_message(uid, f"⭐ اشتراک {days} روزه فعال شد تا {esc(expiry)}")
            return

        if data.startswith("cfg:"):
            if not owner_only_private(call):
                bot.answer_callback_query(call.id, "فقط مالک مجاز است.", show_alert=True)
                return
            setting = data.split(":", 1)[1]
            WAITING[uid] = {"action": "toggle", "setting": setting}
            bot.answer_callback_query(call.id)
            bot.send_message(uid, "🆔 شناسه گروه را بفرست تا این تنظیم را تغییر بدهم.")
            return

        if data.startswith("set:"):
            if not owner_only_private(call):
                bot.answer_callback_query(call.id, "فقط مالک مجاز است.", show_alert=True)
                return
            action = data.split(":", 1)[1]
            WAITING[uid] = {"action": action + "_group"}
            bot.answer_callback_query(call.id)
            bot.send_message(uid, "🆔 شناسه گروه را بفرست.")
            return

        if data == "admin:stats":
            if not owner_only_private(call):
                bot.answer_callback_query(call.id, "فقط مالک مجاز است.", show_alert=True)
                return
            bot.answer_callback_query(call.id)
            bot.send_message(uid, f"📊 پیام‌های ثبت‌شده: {len(DATA['logs'])}\nگروه‌های شناخته‌شده: {len(DATA['groups'])}")
            return
        if data == "admin:logs":
            if not owner_only_private(call):
                bot.answer_callback_query(call.id, "فقط مالک مجاز است.", show_alert=True)
                return
            rows = DATA["logs"][-15:]
            bot.answer_callback_query(call.id)
            bot.send_message(uid, "🧾 گزارش‌ها\n" + ("\n".join(
                f"• {esc(x['time'])} | {esc(x['action'])} | گروه {esc(x['chat_id'])} | کاربر {esc(x['user_id'])}"
                for x in rows) if rows else "گزارشی ثبت نشده است."))
            return
        bot.answer_callback_query(call.id, "گزینه ناشناخته است.")
    except Exception as exc:
        print("Callback error:", repr(exc))
        try:
            bot.answer_callback_query(call.id, "خطا رخ داد؛ دوباره تلاش کن.", show_alert=True)
        except Exception:
            pass

def run():
    print(BRAND + " starting...")
    while True:
        try:
            bot.infinity_polling(skip_pending=True, timeout=30, long_polling_timeout=30)
        except Exception as exc:
            print("Polling error:", repr(exc))
            time.sleep(5)

if __name__ == "__main__":
    run()
