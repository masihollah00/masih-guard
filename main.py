# -*- coding: utf-8 -*-
"""MASIH GUARD S1000+ - single-file Telegram group guard bot."""
import os
import re
import json
import time
import random
import threading
import traceback
import urllib.request
import urllib.error
from datetime import datetime, date

import telebot
from telebot import types

# ==================== CONFIG ====================
BOT_TOKEN = (os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
OWNER_ID = int(os.getenv("OWNER_ID", "8620924698"))
DATA_FILE = os.getenv("DATA_FILE", "masih_guard_data.json")
AI_API_KEY = os.getenv("AI_API_KEY", "").strip()
# Use an OpenAI-compatible endpoint. Override AI_API_URL if your provider differs.
AI_API_URL = os.getenv("AI_API_URL", "https://api.openai.com/v1/chat/completions").strip()
AI_MODEL = os.getenv("AI_MODEL", "gpt-4o-mini").strip()
WEBSITE_URL = os.getenv("WEBSITE_URL", "https://neon-portfolio-7vhj.onrender.com").strip()
BRAND = "MASIH GUARD"
VERSION = "S1000+"
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN تنظیم نشده است. آن را در Environment Variables هاست اضافه کن.")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML", threaded=True, num_threads=4)
LOCK = threading.RLock()
WAITING = {}

# ==================== DATA ====================
DEFAULT_GROUP = {
    "anti_link": True, "anti_ads": True, "anti_spam": True, "anti_repeat": True,
    "anti_forward": False, "media_lock": False, "welcome_on": True,
    "farewell_on": False, "join_approval": False, "bad_words": [], "whitelist": [],
    "warn_limit": 3, "rules": "هنوز قانونی ثبت نشده است.",
    "welcome_text": "سلام {name}، به گروه خوش آمدی 🌟",
    "farewell_text": "{name} از گروه خارج شد.", "auto_replies": {}
}
DEFAULT_DATA = {
    "groups": {}, "warnings": {}, "logs": [], "proxies": [], "customers": [],
    "tickets": [], "points": {}, "seen": {},
    "stats": {"messages": 0, "blocked": 0, "warns": 0, "joins": 0, "tickets": 0},
    "settings": {"smart_security": True}, "last_daily": {}
}

def clone(obj):
    return json.loads(json.dumps(obj, ensure_ascii=False))

def load_data():
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            saved = json.load(f)
        data = clone(DEFAULT_DATA)
        if isinstance(saved, dict):
            for k, v in saved.items():
                if k == "stats" and isinstance(v, dict): data["stats"].update(v)
                elif k == "settings" and isinstance(v, dict): data["settings"].update(v)
                elif k in data and isinstance(v, type(data[k])): data[k] = v
        return data
    except (OSError, ValueError, TypeError):
        return clone(DEFAULT_DATA)

DATA = load_data()

def save_data():
    with LOCK:
        tmp = DATA_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(DATA, f, ensure_ascii=False, indent=2)
        os.replace(tmp, DATA_FILE)

def esc(value):
    s = str(value if value is not None else "")
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def add_log(text):
    with LOCK:
        DATA["logs"].append({"time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "text": str(text)[:500]})
        DATA["logs"] = DATA["logs"][-200:]
        save_data()

def is_owner(user_id):
    return int(user_id or 0) == OWNER_ID

def is_group(chat):
    return bool(chat and chat.type in ("group", "supergroup"))

def get_group_settings(chat_id):
    key = str(chat_id)
    with LOCK:
        if key not in DATA["groups"]:
            DATA["groups"][key] = clone(DEFAULT_GROUP)
            save_data()
        else:
            for k, v in DEFAULT_GROUP.items():
                DATA["groups"][key].setdefault(k, clone(v))
        return DATA["groups"][key]

def user_is_group_admin(chat_id, user_id):
    if is_owner(user_id): return True
    try:
        member = bot.get_chat_member(chat_id, user_id)
        return member.status in ("administrator", "creator")
    except Exception:
        return False

def mention(user):
    name = esc(getattr(user, "first_name", None) or "کاربر")
    return f'<a href="tg://user?id={user.id}">{name}</a>'

def safe_send(chat_id, text, **kwargs):
    try:
        return bot.send_message(chat_id, text, **kwargs)
    except Exception as e:
        print("send_message error:", e)
        return None

# ==================== MAIN PANEL ====================
SECTIONS = [
    ("🛡️ امنیت گروه", "security"), ("👥 مدیریت اعضا", "members"),
    ("⚙️ تنظیمات", "settings"), ("👋 خوشامد/خداحافظی", "welcome"),
    ("📜 قوانین", "rules"), ("🔤 تبدیل فونت", "font"),
    ("🌐 پروکسی‌ها", "proxy"), ("📊 آمار و گزارش", "stats"),
    ("🧾 مشتریان", "customers"), ("🎫 تیکت پشتیبانی", "tickets"),
    ("🤖 هوش مصنوعی", "ai"), ("🎮 بازی و امتیاز", "games"),
    ("💾 پشتیبان‌گیری", "backup"), ("🎁 امتیاز روزانه", "daily"),
    ("🧠 امنیت هوشمند", "smart"), ("🌐 وب‌سایت", "website"), ("📡 وضعیت ربات", "status"),
]

def main_panel():
    kb = types.InlineKeyboardMarkup(row_width=2)
    for i in range(0, len(SECTIONS), 2):
        row = [types.InlineKeyboardButton(SECTIONS[i][0], callback_data="panel:" + SECTIONS[i][1])]
        if i + 1 < len(SECTIONS): row.append(types.InlineKeyboardButton(SECTIONS[i+1][0], callback_data="panel:" + SECTIONS[i+1][1]))
        kb.row(*row)
    kb.add(types.InlineKeyboardButton("🌐 سایت رسمی", url=WEBSITE_URL))
    return kb

def back_kb():
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("⬅️ بازگشت به پنل", callback_data="panel:home"))
    return kb

def section_kb(section, chat_id=None):
    kb = types.InlineKeyboardMarkup(row_width=2)
    if section == "security":
        settings = get_group_settings(chat_id) if chat_id else DEFAULT_GROUP
        for key, label in [("anti_link","ضدلینک"),("anti_ads","ضدتبلیغ"),("anti_spam","ضداسپم"),("anti_repeat","ضدتکرار"),("anti_forward","ضدفوروارد"),("media_lock","قفل رسانه")]:
            kb.add(types.InlineKeyboardButton(("✅ " if settings.get(key) else "❌ ")+label, callback_data="toggle:"+key))
    elif section == "welcome":
        s = get_group_settings(chat_id) if chat_id else DEFAULT_GROUP
        for key,label in [("welcome_on","خوشامدگویی"),("farewell_on","خداحافظی"),("join_approval","تأیید ورود")]:
            kb.add(types.InlineKeyboardButton(("✅ " if s.get(key) else "❌ ")+label, callback_data="toggle:"+key))
        kb.add(types.InlineKeyboardButton("✍️ متن خوشامد", callback_data="ask:welcome_text"), types.InlineKeyboardButton("✍️ متن خداحافظی", callback_data="ask:farewell_text"))
    elif section == "rules":
        kb.add(types.InlineKeyboardButton("📜 دیدن قوانین", callback_data="show:rules"), types.InlineKeyboardButton("✍️ تنظیم قوانین", callback_data="ask:rules"))
        kb.add(types.InlineKeyboardButton("➕ پاسخ خودکار", callback_data="ask:auto_reply"), types.InlineKeyboardButton("➖ حذف پاسخ", callback_data="ask:delete_reply"))
        kb.add(types.InlineKeyboardButton("🚫 افزودن کلمه ممنوع", callback_data="ask:bad_word"))
    elif section == "members":
        for action,label in [("warn","اخطار"),("mute","سکوت"),("unmute","رفع سکوت"),("ban","مسدودکردن"),("unban","رفع مسدودی"),("kick","اخراج")]:
            kb.add(types.InlineKeyboardButton(label, callback_data="ask:"+action))
    elif section == "settings":
        kb.add(types.InlineKeyboardButton("🔢 تعداد اخطار تا مسدودی", callback_data="ask:warn_limit"))
    elif section == "font": kb.add(types.InlineKeyboardButton("🔤 تبدیل متن به فونت فانتزی", callback_data="ask:font"))
    elif section == "proxy":
        kb.add(types.InlineKeyboardButton("➕ افزودن پروکسی", callback_data="ask:add_proxy"), types.InlineKeyboardButton("📋 نمایش پروکسی‌ها", callback_data="show:proxies"), types.InlineKeyboardButton("🗑 حذف پروکسی", callback_data="ask:delete_proxy"))
    elif section == "stats":
        kb.add(types.InlineKeyboardButton("📊 آمار", callback_data="show:stats"), types.InlineKeyboardButton("🧾 گزارش اخیر", callback_data="show:logs"))
    elif section == "customers":
        kb.add(types.InlineKeyboardButton("➕ ثبت مشتری", callback_data="ask:add_customer"), types.InlineKeyboardButton("📋 فهرست مشتریان", callback_data="show:customers"), types.InlineKeyboardButton("🔎 جستجوی مشتری", callback_data="ask:find_customer"))
    elif section == "tickets": kb.add(types.InlineKeyboardButton("🎫 ارسال تیکت", callback_data="ask:ticket"), types.InlineKeyboardButton("📋 تیکت‌ها", callback_data="show:tickets"))
    elif section == "ai": kb.add(types.InlineKeyboardButton("🤖 پرسش از هوش مصنوعی", callback_data="ask:ai"))
    elif section == "games": kb.add(types.InlineKeyboardButton("🎲 حدس عدد ۱ تا ۵", callback_data="game:guess"), types.InlineKeyboardButton("🏆 امتیاز من", callback_data="show:points"))
    elif section == "backup": kb.add(types.InlineKeyboardButton("💾 دریافت پشتیبان", callback_data="backup:now"))
    elif section == "daily": kb.add(types.InlineKeyboardButton("🎁 امتیاز روزانه", callback_data="daily:claim"))
    elif section == "smart":
        active = DATA["settings"].get("smart_security", True)
        kb.add(types.InlineKeyboardButton(("✅ روشن" if active else "❌ خاموش"), callback_data="toggle:smart_security"))
    elif section == "website": kb.add(types.InlineKeyboardButton("🌐 بازکردن وب‌سایت", url=WEBSITE_URL))
    elif section == "status": kb.add(types.InlineKeyboardButton("📡 بررسی وضعیت", callback_data="show:status"))
    kb.add(types.InlineKeyboardButton("⬅️ بازگشت", callback_data="panel:home"))
    return kb

def send_section(chat_id, section, user_id=None):
    titles = dict(SECTIONS)
    if section == "home":
        safe_send(chat_id, f"🛡️ <b>{BRAND} {VERSION}</b>\nپنل مدیریت ربات", reply_markup=main_panel())
        return
    if section in ("security","welcome") and chat_id > 0:
        # Group settings should be edited from the group itself; private panel cannot guess target group.
        safe_send(chat_id, "برای تغییر تنظیمات گروه، دستور /panel را داخل همان گروه بفرست و دکمه‌ها را آنجا بزن.", reply_markup=back_kb())
        return
    safe_send(chat_id, f"<b>{esc(titles.get(section, section))}</b>\nیکی از گزینه‌ها را انتخاب کن:", reply_markup=section_kb(section, chat_id if chat_id < 0 else None))

@bot.message_handler(commands=["start", "panel", "help"])
def start_command(message):
    if message.chat.type == "private" and not is_owner(message.from_user.id):
        safe_send(message.chat.id, "سلام! برای امکانات مدیریتی، فقط مالک ربات دسترسی دارد.")
        return
    safe_send(message.chat.id, f"🛡️ <b>{BRAND} {VERSION}</b>\nربات مدیریت و امنیت گروه\n\nبرای تنظیمات گروه، دستور /panel را داخل گروه اجرا کن.", reply_markup=main_panel())

@bot.message_handler(commands=["id"])
def id_command(message):
    safe_send(message.chat.id, f"🆔 Chat ID: <code>{message.chat.id}</code>\nUser ID: <code>{message.from_user.id}</code>")

# ==================== FONT + AI ====================
FONT_MAPS = [
    str.maketrans("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ", "𝐚𝐛𝐜𝐝𝐞𝐟𝐠𝐡𝐢𝐣𝐤𝐥𝐦𝐧𝐨𝐩𝐪𝐫𝐬𝐭𝐮𝐯𝐰𝐱𝐲𝐳𝐀𝐁𝐂𝐃𝐄𝐅𝐆𝐇𝐈𝐉𝐊𝐋𝐌𝐍𝐎𝐏𝐐𝐑𝐒𝐓𝐔𝐕𝐖𝐗𝐘𝐙"),
    str.maketrans("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ", "𝘢𝘣𝘤𝘥𝘦𝘧𝘨𝘩𝘪𝘫𝘬𝘭𝘮𝘯𝘰𝘱𝘲𝘳𝘴𝘵𝘶𝘷𝘸𝘹𝘺𝘻𝘈𝘉𝘊𝘋𝘌𝘍𝘎𝘏𝘐𝘑𝘒𝘓𝘔𝘕𝘖𝘗𝘘𝘙𝘚𝘛𝘜𝘝𝘞𝘟𝘠𝘡"),
    str.maketrans("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ", "ａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺ")
]
def convert_font(text, style=0):
    return text.translate(FONT_MAPS[style % len(FONT_MAPS)])

def ask_ai(question):
    if not AI_API_KEY:
        return "⚠️ کلید هوش مصنوعی تنظیم نشده. در هاست متغیر AI_API_KEY را اضافه کن؛ برای تعیین سرویس، AI_API_URL و AI_MODEL هم باید مطابق ارائه‌دهنده باشند. بقیه امکانات ربات مستقل کار می‌کنند."
    payload = json.dumps({"model": AI_MODEL, "messages": [{"role":"system","content":"تو دستیار فارسی‌زبان MASIH GUARD هستی. پاسخ‌ها مفید، محترمانه و ایمن باشند."},{"role":"user","content":question}], "temperature":0.7}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(AI_API_URL, data=payload, headers={"Content-Type":"application/json","Authorization":"Bearer " + AI_API_KEY}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=35) as response:
            data = json.loads(response.read().decode("utf-8"))
        return data.get("choices", [{}])[0].get("message", {}).get("content", "پاسخی دریافت نشد.").strip()
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "ignore")[:300]
        return f"خطای سرویس هوش مصنوعی ({e.code}). آدرس و مدل را بررسی کن.\n{esc(detail)}"
    except Exception as e:
        return "ارتباط با سرویس هوش مصنوعی برقرار نشد: " + esc(e)

@bot.message_handler(commands=["ai", "ask"])
def ai_command(message):
    question = re.sub(r"^/(ai|ask)(@\w+)?\s*", "", message.text or "", flags=re.I).strip()
    if not question:
        WAITING[message.from_user.id] = {"action":"ai", "chat_id":message.chat.id}
        safe_send(message.chat.id, "سؤالت را در پیام بعدی بفرست.")
        return
    safe_send(message.chat.id, "🤖 " + esc(ask_ai(question))[:4000])

# ==================== MODERATION + SECURITY ====================
def delete_safely(message):
    try: bot.delete_message(message.chat.id, message.message_id)
    except Exception: pass

def warn_member(chat_id, user, reason):
    key = f"{chat_id}:{user.id}"
    DATA["warnings"][key] = DATA["warnings"].get(key, 0) + 1
    DATA["stats"]["warns"] += 1
    count = DATA["warnings"][key]
    settings = get_group_settings(chat_id)
    add_log(f"warn {user.id} in {chat_id}: {reason} ({count})")
    if count >= int(settings.get("warn_limit", 3)):
        try:
            bot.ban_chat_member(chat_id, user.id)
            safe_send(chat_id, f"⛔ {mention(user)} به دلیل رسیدن به سقف اخطارها مسدود شد.")
            DATA["warnings"][key] = 0
        except Exception:
            safe_send(chat_id, f"⚠️ {mention(user)} اخطار {count}/{settings.get('warn_limit',3)} دریافت کرد. برای مسدودی، ربات باید مجوز مدیر داشته باشد.")
    else:
        safe_send(chat_id, f"⚠️ {mention(user)} اخطار {count}/{settings.get('warn_limit',3)} دریافت کرد. دلیل: {esc(reason)}")
    save_data()

def is_forwarded(message):
    return bool(getattr(message, "forward_origin", None) or getattr(message, "forward_from", None) or getattr(message, "forward_from_chat", None))

def message_text(message):
    return (getattr(message, "text", None) or getattr(message, "caption", None) or "").strip()

def security_check(message):
    if not is_group(message.chat) or not message.from_user or message.from_user.is_bot: return False
    settings = get_group_settings(message.chat.id)
    if user_is_group_admin(message.chat.id, message.from_user.id): return False
    text = message_text(message)
    reason = None
    if settings.get("media_lock") and (message.photo or message.video or message.document or message.audio or message.voice or message.sticker or message.animation): reason = "ارسال رسانه ممنوع است"
    elif settings.get("anti_forward") and is_forwarded(message): reason = "ارسال فوروارد ممنوع است"
    elif settings.get("anti_link") and re.search(r"https?://|www\.|t\.me/|telegram\.me/", text, re.I):
        allowed = any(link.lower() in text.lower() for link in settings.get("whitelist", []))
        if not allowed: reason = "ارسال لینک ممنوع است"
    elif settings.get("anti_ads") and re.search(r"تبلیغ|تبليغ|خرید و فروش|فالوور|عضوگیری|تبلیغات", text, re.I): reason = "تبلیغات ممنوع است"
    elif any(word.lower() in text.lower() for word in settings.get("bad_words", []) if word): reason = "استفاده از کلمه ممنوع"
    if reason:
        delete_safely(message)
        DATA["stats"]["blocked"] += 1
        warn_member(message.chat.id, message.from_user, reason)
        save_data()
        return True
    # Repeat/spam detection is intentionally conservative to reduce false positives.
    user_key = f"{message.chat.id}:{message.from_user.id}"
    now = time.time(); previous = DATA["seen"].get(user_key, {})
    if settings.get("anti_repeat") and text and previous.get("text") == text and now - previous.get("time", 0) < 30:
        delete_safely(message); DATA["stats"]["blocked"] += 1; warn_member(message.chat.id, message.from_user, "پیام تکراری"); return True
    recent = previous.get("times", [])
    recent = [t for t in recent if now - t < 8] + [now]
    DATA["seen"][user_key] = {"text":text, "time":now, "times":recent}
    if settings.get("anti_spam") and len(recent) >= 7:
        delete_safely(message); DATA["stats"]["blocked"] += 1; warn_member(message.chat.id, message.from_user, "ارسال بیش از حد پیام"); save_data(); return True
    save_data()
    return False

@bot.message_handler(content_types=["new_chat_members"])
def welcome_new_members(message):
    settings = get_group_settings(message.chat.id)
    for user in message.new_chat_members:
        DATA["stats"]["joins"] += 1
        if settings.get("welcome_on"):
            text = settings.get("welcome_text", DEFAULT_GROUP["welcome_text"]).replace("{name}", mention(user))
            safe_send(message.chat.id, text)
    save_data()

@bot.message_handler(content_types=["left_chat_member"])
def farewell_member(message):
    settings = get_group_settings(message.chat.id)
    user = message.left_chat_member
    if settings.get("farewell_on") and user:
        safe_send(message.chat.id, settings.get("farewell_text", DEFAULT_GROUP["farewell_text"]).replace("{name}", esc(user.first_name or "کاربر")))

@bot.message_handler(content_types=["photo", "video", "document", "audio", "voice", "sticker", "animation", "video_note"])
def media_security_handler(message):
    if is_group(message.chat):
        DATA["stats"]["messages"] += 1
        security_check(message)
        save_data()

# ==================== CUSTOMER / TICKET / BACKUP ====================
def make_backup():
    save_data()
    return DATA_FILE

def stats_text():
    s = DATA["stats"]
    return ("📊 <b>آمار MASIH GUARD</b>\n"
            f"پیام‌های بررسی‌شده: {s.get('messages',0)}\n"
            f"پیام‌های مسدودشده: {s.get('blocked',0)}\n"
            f"اخطارها: {s.get('warns',0)}\n"
            f"ورود اعضا: {s.get('joins',0)}\n"
            f"تیکت‌ها: {s.get('tickets',0)}")

def add_ticket(user, text):
    ticket = {"id": int(time.time()), "user_id": user.id, "name": user.first_name or "کاربر", "text": text[:2000], "time": datetime.now().isoformat(timespec="seconds"), "status":"open"}
    DATA["tickets"].append(ticket); DATA["stats"]["tickets"] += 1; save_data()
    safe_send(OWNER_ID, f"🎫 <b>تیکت جدید</b>\nاز: {esc(ticket['name'])} (<code>{user.id}</code>)\nمتن: {esc(text[:3000])}")
    return ticket["id"]

# ==================== CALLBACKS ====================
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    try:
        user_id = call.from_user.id; chat_id = call.message.chat.id if call.message else user_id
        data = call.data or ""
        if chat_id > 0 and not is_owner(user_id):
            bot.answer_callback_query(call.id, "این پنل فقط برای مالک ربات است.", show_alert=True); return
        if data in ("panel:home", "panel:main"):
            bot.answer_callback_query(call.id); safe_send(chat_id, f"🛡️ <b>{BRAND} {VERSION}</b>", reply_markup=main_panel()); return
        if data.startswith("panel:"):
            section = data.split(":",1)[1]
            bot.answer_callback_query(call.id)
            if section in ("security", "welcome") and not is_group(call.message.chat):
                safe_send(chat_id, "برای تنظیم امنیت یا خوشامدگویی، /panel را داخل گروه بفرست و از همان‌جا انتخاب کن.", reply_markup=back_kb()); return
            safe_send(chat_id, f"<b>{esc(dict(SECTIONS).get(section, section))}</b>", reply_markup=section_kb(section, chat_id if is_group(call.message.chat) else None)); return
        if data.startswith("toggle:"):
            key = data.split(":",1)[1]
            if key == "smart_security":
                if not is_owner(user_id): bot.answer_callback_query(call.id, "فقط مالک اجازه دارد.", show_alert=True); return
                DATA["settings"][key] = not DATA["settings"].get(key, True); save_data()
                bot.answer_callback_query(call.id, "تنظیم ذخیره شد."); safe_send(chat_id, "امنیت هوشمند: " + ("روشن ✅" if DATA["settings"][key] else "خاموش ❌"), reply_markup=back_kb()); return
            if not is_group(call.message.chat): bot.answer_callback_query(call.id, "این گزینه را داخل گروه اجرا کن.", show_alert=True); return
            if not user_is_group_admin(chat_id, user_id): bot.answer_callback_query(call.id, "فقط مدیر گروه می‌تواند تغییر دهد.", show_alert=True); return
            settings = get_group_settings(chat_id); settings[key] = not settings.get(key, False); save_data()
            bot.answer_callback_query(call.id, "ذخیره شد.")
            safe_send(chat_id, f"{key}: {'روشن ✅' if settings[key] else 'خاموش ❌'}", reply_markup=section_kb("security" if key in ("anti_link","anti_ads","anti_spam","anti_repeat","anti_forward","media_lock") else "welcome", chat_id)); return
        if data.startswith("ask:"):
            action = data.split(":",1)[1]
            if action not in ("ai", "font", "ticket") and not is_owner(user_id) and not (is_group(call.message.chat) and user_is_group_admin(chat_id,user_id)):
                bot.answer_callback_query(call.id, "اجازه نداری.", show_alert=True); return
            WAITING[user_id] = {"action":action, "chat_id":chat_id}
            prompts = {"welcome_text":"متن خوشامد را بفرست. از {name} برای نام استفاده کن.","farewell_text":"متن خداحافظی را بفرست. از {name} برای نام استفاده کن.","rules":"قوانین جدید را بفرست.","auto_reply":"در یک خط بنویس: کلمه | پاسخ","delete_reply":"کلمه‌ای که پاسخ خودکارش حذف شود را بفرست.","bad_word":"کلمه ممنوع را بفرست.","warn_limit":"عدد اخطار تا مسدودی را بفرست (۱ تا ۱۰).","font":"متن موردنظر را بفرست؛ خروجی سه سبک دارد.","add_proxy":"لینک پروکسی تلگرام را بفرست.","delete_proxy":"شماره پروکسی برای حذف را بفرست.","add_customer":"نام مشتری | توضیحات را بفرست.","find_customer":"نام یا شناسه مشتری را بفرست.","ticket":"متن تیکت را بفرست.","ai":"سؤالت را برای هوش مصنوعی بفرست.","warn":"شناسه کاربر | شناسه گروه | دلیل (اختیاری)","mute":"شناسه کاربر | شناسه گروه | دقیقه","unmute":"شناسه کاربر | شناسه گروه","ban":"شناسه کاربر | شناسه گروه","unban":"شناسه کاربر | شناسه گروه","kick":"شناسه کاربر | شناسه گروه"}
            bot.answer_callback_query(call.id); safe_send(chat_id, prompts.get(action, "مقدار را بفرست.")); return
        if data.startswith("show:"):
            what = data.split(":",1)[1]
            if what == "stats": out = stats_text()
            elif what == "logs": out = "🧾 <b>آخرین گزارش‌ها</b>\n" + "\n".join(esc(x.get("time"))+" — "+esc(x.get("text")) for x in DATA["logs"][-15:])
            elif what == "rules": out = "📜 " + esc(get_group_settings(chat_id).get("rules", DEFAULT_GROUP["rules"])) if is_group(call.message.chat) else "قوانین را داخل گروه مشاهده کن."
            elif what == "proxies": out = "🌐 <b>پروکسی‌ها</b>\n" + ("\n".join(f"{i+1}. {esc(p)}" for i,p in enumerate(DATA["proxies"])) or "هنوز پروکسی ثبت نشده.")
            elif what == "customers": out = "🧾 <b>مشتریان</b>\n" + ("\n".join(f"{i+1}. {esc(c.get('name'))}: {esc(c.get('notes',''))}" for i,c in enumerate(DATA["customers"][-30:])) or "فهرست خالی است.")
            elif what == "tickets": out = "🎫 <b>تیکت‌ها</b>\n" + ("\n".join(f"#{t['id']} — {esc(t['name'])}: {esc(t['status'])}" for t in DATA["tickets"][-20:]) or "تیکتی وجود ندارد.")
            elif what == "points": out = f"🏆 امتیاز شما: {DATA['points'].get(str(user_id),0)}"
            elif what == "status": out = f"📡 <b>وضعیت ربات</b>\nنسخه: {VERSION}\nهوش مصنوعی: {'تنظیم شده' if AI_API_KEY else 'بدون کلید'}\nگروه‌های ذخیره‌شده: {len(DATA['groups'])}\nزمان سرور: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            else: out = "موردی پیدا نشد."
            bot.answer_callback_query(call.id); safe_send(chat_id, out, reply_markup=back_kb()); return
        if data == "backup:now":
            if not is_owner(user_id): bot.answer_callback_query(call.id,"فقط مالک.",show_alert=True); return
            save_data()
            with open(DATA_FILE,"rb") as f: bot.send_document(chat_id, f, caption="💾 پشتیبان اطلاعات ربات")
            bot.answer_callback_query(call.id); return
        if data == "daily:claim":
            today = date.today().isoformat()
            if DATA["last_daily"].get(str(user_id)) == today: bot.answer_callback_query(call.id,"امروز امتیازت را گرفته‌ای.",show_alert=True); return
            DATA["last_daily"][str(user_id)] = today; DATA["points"][str(user_id)] = DATA["points"].get(str(user_id),0)+5; save_data()
            bot.answer_callback_query(call.id,"۵ امتیاز دریافت شد!"); safe_send(chat_id,"🎁 ۵ امتیاز روزانه گرفتی!",reply_markup=back_kb()); return
        if data == "game:guess":
            WAITING[user_id] = {"action":"guess", "chat_id":chat_id, "number":random.randint(1,5)}
            bot.answer_callback_query(call.id); safe_send(chat_id,"یک عدد بین ۱ تا ۵ بفرست."); return
        bot.answer_callback_query(call.id, "گزینه شناخته نشد.")
    except Exception as e:
        print("callback error:", traceback.format_exc())
        try: bot.answer_callback_query(call.id, "خطایی رخ داد.", show_alert=True)
        except Exception: pass

# ==================== PRIVATE / WAITING INPUT ====================
@bot.message_handler(content_types=["text"])
def text_handler(message):
    if message.text and message.text.startswith("/"):
        return
    user_id = message.from_user.id
    pending = WAITING.get(user_id)
    if is_group(message.chat) and not pending:
        DATA["stats"]["messages"] += 1
        if security_check(message): return
        settings = get_group_settings(message.chat.id)
        text_lower = (message.text or "").strip().lower()
        for key, reply in settings.get("auto_replies", {}).items():
            if key.lower() == text_lower:
                safe_send(message.chat.id, reply); break
        save_data(); return
    if not pending:
        return
    action = pending.get("action"); target_chat = pending.get("chat_id", message.chat.id); text = (message.text or "").strip()
    if action not in ("ai", "font", "ticket", "guess") and not is_owner(user_id) and not (is_group(message.chat) and user_is_group_admin(message.chat.id, user_id)):
        safe_send(message.chat.id, "⛔ فقط مالک ربات می‌تواند این کار را انجام دهد."); WAITING.pop(user_id,None); return
    try:
        if action == "ai": out = ask_ai(text); safe_send(message.chat.id, "🤖 " + esc(out)[:4000])
        elif action == "font":
            out = "🔤 <b>سه مدل فونت</b>\n\n" + esc(convert_font(text,0)) + "\n\n" + esc(convert_font(text,1)) + "\n\n" + esc(convert_font(text,2))
            safe_send(message.chat.id, out)
        elif action == "ticket":
            tid = add_ticket(message.from_user, text); safe_send(message.chat.id, f"✅ تیکت #{tid} برای پشتیبانی ارسال شد.")
        elif action == "rules":
            settings = get_group_settings(target_chat) if target_chat < 0 else None
            if settings is None: safe_send(message.chat.id,"برای تنظیم قوانین، داخل گروه /panel را بزن و از همان گروه اقدام کن.")
            else: settings["rules"] = text[:3000]; save_data(); safe_send(message.chat.id,"✅ قوانین ذخیره شد.")
        elif action in ("welcome_text","farewell_text"):
            if target_chat >= 0: safe_send(message.chat.id,"این تنظیم باید از پنل داخل گروه انجام شود.")
            else: get_group_settings(target_chat)[action] = text[:1000]; save_data(); safe_send(message.chat.id,"✅ متن ذخیره شد.")
        elif action == "auto_reply":
            if "|" not in text: safe_send(message.chat.id,"فرمت درست: کلمه | پاسخ")
            elif target_chat >= 0: safe_send(message.chat.id,"برای افزودن پاسخ، پنل را در گروه باز کن.")
            else:
                key, reply = [x.strip() for x in text.split("|",1)]; get_group_settings(target_chat)["auto_replies"][key] = reply[:1000]; save_data(); safe_send(message.chat.id,"✅ پاسخ خودکار ذخیره شد.")
        elif action == "delete_reply":
            if target_chat < 0: get_group_settings(target_chat)["auto_replies"].pop(text,None); save_data()
            safe_send(message.chat.id,"اگر این کلمه وجود داشت، پاسخ خودکار حذف شد.")
        elif action == "bad_word":
            if target_chat < 0:
                arr = get_group_settings(target_chat)["bad_words"]
                if text not in arr: arr.append(text[:100]); save_data()
                safe_send(message.chat.id,"✅ کلمه به فهرست ممنوع اضافه شد.")
            else: safe_send(message.chat.id,"برای تنظیم کلمات ممنوع، از پنل داخل گروه استفاده کن.")
        elif action == "warn_limit":
            n = int(text)
            if not 1 <= n <= 10: raise ValueError()
            if target_chat < 0: get_group_settings(target_chat)["warn_limit"] = n; save_data(); safe_send(message.chat.id,"✅ سقف اخطار ذخیره شد.")
            else: safe_send(message.chat.id,"این تنظیم را از پنل داخل گروه انجام بده.")
        elif action == "add_proxy":
            if not re.match(r"^(https?://t\.me/proxy\?|tg://proxy\?)", text, re.I): safe_send(message.chat.id,"لینک باید از نوع t.me/proxy یا tg://proxy باشد.")
            else: DATA["proxies"].append(text); save_data(); safe_send(message.chat.id,"✅ پروکسی ذخیره شد.")
        elif action == "delete_proxy":
            idx = int(text)-1
            if idx < 0 or idx >= len(DATA["proxies"]): safe_send(message.chat.id,"شماره پروکسی معتبر نیست.")
            else: DATA["proxies"].pop(idx); save_data(); safe_send(message.chat.id,"🗑 پروکسی حذف شد.")
        elif action == "add_customer":
            parts = text.split("|",1); DATA["customers"].append({"name":parts[0].strip()[:100],"notes":parts[1].strip()[:500] if len(parts)>1 else "","created":datetime.now().isoformat(timespec="seconds")}); save_data(); safe_send(message.chat.id,"✅ مشتری ثبت شد.")
        elif action == "find_customer":
            found = [c for c in DATA["customers"] if text.lower() in c.get("name","").lower() or text.lower() in c.get("notes","").lower()]
            safe_send(message.chat.id, "\n".join(f"{esc(c['name'])}: {esc(c.get('notes',''))}" for c in found[:20]) or "مشتری پیدا نشد.")
        elif action == "guess":
            guess = int(text); number = pending.get("number",0)
            if guess == number: DATA["points"][str(user_id)] = DATA["points"].get(str(user_id),0)+3; save_data(); safe_send(message.chat.id,"🎉 درست حدس زدی! ۳ امتیاز گرفتی.")
            else: safe_send(message.chat.id,f"این بار نه! عدد درست {number} بود.")
        elif action in ("warn","mute","unmute","ban","unban","kick"):
            bits = [x.strip() for x in text.split("|")]
            if len(bits) < 2: safe_send(message.chat.id,"فرمت: شناسه کاربر | شناسه گروه | دلیل/دقیقه (اختیاری)")
            else:
                uid = int(bits[0]); cid = int(bits[1]); extra = bits[2] if len(bits)>2 else ""
                if action == "warn": warn_member(cid, type("U",(),{"id":uid,"first_name":str(uid)})(), extra or "اخطار مدیر")
                elif action == "ban": bot.ban_chat_member(cid,uid)
                elif action == "unban": bot.unban_chat_member(cid,uid,only_if_banned=True)
                elif action == "kick": bot.ban_chat_member(cid,uid); bot.unban_chat_member(cid,uid,only_if_banned=True)
                elif action == "mute":
                    minutes = max(1,min(int(extra or "10"),10080)); until = int(time.time()) + minutes*60
                    bot.restrict_chat_member(cid,uid,until_date=until,permissions=types.ChatPermissions(can_send_messages=False,can_send_media_messages=False,can_send_polls=False,can_send_other_messages=False,can_add_web_page_previews=False))
                elif action == "unmute": bot.restrict_chat_member(cid,uid,permissions=types.ChatPermissions(can_send_messages=True,can_send_media_messages=True,can_send_polls=True,can_send_other_messages=True,can_add_web_page_previews=True))
                safe_send(message.chat.id,"✅ عملیات مدیریتی ارسال شد؛ اگر خطایی نبود انجام شده است.")
        else: safe_send(message.chat.id,"این عملیات هنوز تنظیم نشده است.")
    except ValueError:
        safe_send(message.chat.id,"⚠️ مقدار واردشده معتبر نیست؛ دوباره بررسی کن.")
    except Exception as e:
        print("input handler error:", traceback.format_exc())
        safe_send(message.chat.id,"❌ عملیات انجام نشد. مطمئن شو ربات مجوز لازم را دارد و اطلاعات درست است.")
    finally:
        WAITING.pop(user_id, None)

# ==================== POLLING ====================
if __name__ == "__main__":
    print(f"{BRAND} {VERSION} starting...")
    try:
        bot.infinity_polling(skip_pending=True, timeout=30, long_polling_timeout=25)
    except KeyboardInterrupt:
        print("Stopped by user")
    except Exception:
        traceback.print_exc()
        raise
