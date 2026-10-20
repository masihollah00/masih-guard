# -*- coding: utf-8 -*-
"""
MASIH GUARD PRO — single-file Telegram group moderation bot
Required environment variables:
  BOT_TOKEN (or TELEGRAM_BOT_TOKEN)
Optional AI:
  AI_API_KEY, AI_BASE_URL, AI_MODEL
Optional:
  OWNER_ID (defaults to 8620924698), DATA_FILE
"""
import os
import re
import json
import time
import math
import random
import logging
import threading
import urllib.request
import urllib.error
from collections import defaultdict, deque
from datetime import datetime

import telebot
from telebot import types
from flask import Flask, jsonify

# -------------------- Configuration --------------------
BOT_TOKEN = os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN", "")
OWNER_ID = int(os.getenv("OWNER_ID", "8620924698"))
BOT_NAME = "MASIH GUARD PRO"
VERSION = "3.0"
DATA_FILE = os.getenv("DATA_FILE", "masih_guard_data.json")
AI_API_KEY = os.getenv("AI_API_KEY", "").strip()
AI_BASE_URL = os.getenv("AI_BASE_URL", "https://openrouter.ai/api/v1").strip().rstrip("/")
AI_MODEL = os.getenv("AI_MODEL", "").strip()
AI_TIMEOUT = 25

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN یا TELEGRAM_BOT_TOKEN در Environment تنظیم نشده است.")

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s | %(levelname)s | %(message)s"
)
log = logging.getLogger("masih_guard")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML", threaded=True, num_threads=8)
app = Flask(__name__)
START_TIME = time.time()

# -------------------- Persistent data --------------------
DATA_LOCK = threading.RLock()
DEFAULT_DATA = {
    "groups": {},
    "licenses": {},
    "bot_enabled": True,
}
data = {}

def load_data():
    global data
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        if not isinstance(loaded, dict):
            loaded = {}
        data = {**DEFAULT_DATA, **loaded}
        if not isinstance(data.get("groups"), dict):
            data["groups"] = {}
        if not isinstance(data.get("licenses"), dict):
            data["licenses"] = {}
    except FileNotFoundError:
        data = json.loads(json.dumps(DEFAULT_DATA))
    except Exception:
        log.exception("Could not read data file; starting with defaults")
        data = json.loads(json.dumps(DEFAULT_DATA))

def save_data():
    with DATA_LOCK:
        tmp = DATA_FILE + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, DATA_FILE)
        except Exception:
            log.exception("Could not save data")

def group_settings(chat_id):
    key = str(chat_id)
    with DATA_LOCK:
        groups = data.setdefault("groups", {})
        if key not in groups:
            groups[key] = {
                "antilink": True,
                "antispam": True,
                "antiforward": False,
                "welcome": True,
                "rules": "قوانین گروه هنوز تنظیم نشده است.",
                "badwords": [],
                "log_chat_id": None,
                "warnings": {},
                "muted_until": {},
            }
            save_data()
        settings = groups[key]
        defaults = {
            "antilink": True, "antispam": True, "antiforward": False,
            "welcome": True, "rules": "قوانین گروه هنوز تنظیم نشده است.",
            "badwords": [], "log_chat_id": None, "warnings": {}, "muted_until": {}
        }
        for k, v in defaults.items():
            settings.setdefault(k, v)
        return settings

load_data()

# -------------------- Helpers --------------------
def is_group(message):
    return bool(message.chat and message.chat.type in ("group", "supergroup"))

def is_admin(message):
    if not is_group(message):
        return False
    try:
        member = bot.get_chat_member(message.chat.id, message.from_user.id)
        return member.status in ("administrator", "creator")
    except Exception:
        return False

def is_owner(user_id):
    return int(user_id or 0) == OWNER_ID

def is_admin_or_owner(message):
    return is_owner(message.from_user.id) or is_admin(message)

def mention(user):
    name = (user.first_name or "کاربر").replace("<", "").replace(">", "")
    return f'<a href="tg://user?id={user.id}">{name}</a>'

def send_log(chat_id, text):
    try:
        s = group_settings(chat_id)
        log_chat_id = s.get("log_chat_id")
        if log_chat_id:
            bot.send_message(int(log_chat_id), text)
    except Exception:
        log.exception("Log message failed")

def safe_reply(message, text, **kwargs):
    try:
        return bot.reply_to(message, text, **kwargs)
    except Exception:
        log.exception("Could not send reply")
        return None

def extract_target_and_reason(message):
    parts = (message.text or "").split(maxsplit=1)
    reason = parts[1] if len(parts) > 1 else "بدون توضیح"
    if message.reply_to_message:
        return message.reply_to_message.from_user.id, reason
    if len(parts) > 1 and parts[1].split()[0].isdigit():
        target = int(parts[1].split()[0])
        rest = parts[1].split(maxsplit=1)
        return target, (rest[1] if len(rest) > 1 else "بدون توضیح")
    return None, reason

def require_admin(message):
    if not is_group(message):
        safe_reply(message, "این دستور را داخل گروه استفاده کن.")
        return False
    if not is_admin_or_owner(message):
        safe_reply(message, "⛔ فقط مدیران گروه می‌توانند از این دستور استفاده کنند.")
        return False
    return True

LINK_RE = re.compile(r"(?i)(https?://|www\.|t\.me/|telegram\.me/|discord\.gg/)")
def contains_link(text):
    return bool(LINK_RE.search(text or ""))

def normalized(text):
    return (text or "").casefold().replace("ي", "ی").replace("ك", "ک").strip()

def contains_badword(text, words):
    body = normalized(text)
    return any(normalized(w) and normalized(w) in body for w in words)

def warn_user(chat_id, user_id, reason="تخلف"):
    s = group_settings(chat_id)
    warnings = s.setdefault("warnings", {})
    key = str(user_id)
    warnings[key] = int(warnings.get(key, 0)) + 1
    count = warnings[key]
    save_data()
    try:
        if count >= 3:
            bot.restrict_chat_member(
                chat_id, user_id,
                until_date=int(time.time()) + 600,
                permissions=types.ChatPermissions(can_send_messages=False)
            )
            return count, True
    except Exception:
        log.exception("Auto mute after warnings failed")
    return count, False

def ai_answer(question, chat_title=""):
    if not AI_API_KEY or not AI_MODEL:
        return "🤖 قابلیت هوش مصنوعی هنوز فعال نشده. مدیر ربات باید AI_API_KEY و AI_MODEL را در Environment هاست تنظیم کند."
    url = AI_BASE_URL + "/chat/completions"
    payload = {
        "model": AI_MODEL,
        "messages": [
            {"role": "system", "content": "تو دستیار فارسی‌زبان MASIH GUARD PRO هستی. واضح، دوستانه و ایمن به فارسی جواب بده. اگر سؤال مبهم است، کوتاه سؤال روشن‌کننده بپرس."},
            {"role": "user", "content": question[:6000]}
        ],
        "temperature": 0.7,
        "max_tokens": 900
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": "Bearer " + AI_API_KEY,
            "Content-Type": "application/json",
            "HTTP-Referer": "https://masih-guard.local",
            "X-Title": BOT_NAME,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=AI_TIMEOUT) as response:
            result = json.loads(response.read().decode("utf-8"))
        answer = result["choices"][0]["message"]["content"]
        answer = str(answer).strip()
        return answer[:3900] if answer else "جواب خالی دریافت شد؛ دوباره امتحان کن."
    except urllib.error.HTTPError as e:
        details = ""
        try:
            details = e.read().decode("utf-8", errors="ignore")[:400]
        except Exception:
            pass
        log.warning("AI HTTP error %s: %s", e.code, details)
        return f"⚠️ اتصال هوش مصنوعی خطا داد (کد {e.code}). کلید، مدل و آدرس API را بررسی کن."
    except Exception:
        log.exception("AI request failed")
        return "⚠️ فعلاً اتصال هوش مصنوعی برقرار نشد؛ کمی بعد دوباره تلاش کن."

# -------------------- Web health endpoints --------------------
@app.get("/")
def home():
    return f"{BOT_NAME} is running"

@app.get("/health")
def health():
    return jsonify({
        "status": "ok",
        "bot": BOT_NAME,
        "version": VERSION,
        "uptime_seconds": int(time.time() - START_TIME),
        "ai_configured": bool(AI_API_KEY and AI_MODEL)
    })

# -------------------- Basic commands --------------------
@bot.message_handler(commands=["start", "help"])
def cmd_start(message):
    text = (
        f"🛡️ <b>{BOT_NAME} v{VERSION}</b>\n\n"
        "ربات مدیریت و امنیت گروه.\n\n"
        "دستورهای عمومی:\n"
        "/help — راهنما\n/about — درباره ربات\n/rules — قوانین گروه\n"
        "/ai پرسش — پرسیدن سؤال از هوش مصنوعی\n"
        "/ping — بررسی پاسخ‌گویی\n\n"
        "دستورهای مدیران:\n"
        "/antilink on|off — ضدلینک\n"
        "/antispam on|off — ضداسپم\n"
        "/antiforward on|off — جلوگیری از پیام فورواردی\n"
        "/welcome on|off — خوشامدگویی\n"
        "/setrules متن — تنظیم قوانین\n"
        "/addbad کلمه — افزودن کلمه به فیلتر\n"
        "/delbad کلمه — حذف کلمه از فیلتر\n"
        "/badlist — فهرست کلمات فیلتر\n"
        "/warn (روی پیام ریپلای کن) — اخطار\n"
        "/warnings (روی پیام ریپلای کن) — شمارش اخطار\n"
        "/resetwarn (روی پیام ریپلای کن) — پاک‌کردن اخطارها\n"
        "/mute (روی پیام ریپلای کن) — سکوت\n"
        "/unmute (روی پیام ریپلای کن) — رفع سکوت\n"
        "/ban (روی پیام ریپلای کن) — مسدودکردن\n"
        "/unban شناسه — رفع مسدودی\n"
        "/kick (روی پیام ریپلای کن) — اخراج\n"
        "/purge عدد — پاک‌کردن پیام‌های اخیر (با ریپلای)\n"
        "/setlog — تنظیم همین گروه به‌عنوان محل گزارش\n"
        "/stats — آمار ساده گروه\n\n"
        "برای کارکرد دستورهای مدیریتی، ربات باید مدیر گروه باشد."
    )
    safe_reply(message, text)

@bot.message_handler(commands=["about"])
def cmd_about(message):
    safe_reply(message, f"🛡️ <b>{BOT_NAME}</b>\nنسخه: {VERSION}\nسازنده: مسیح مختاری\nامنیت گروه + ابزارهای کاربردی + پاسخ‌گویی هوش مصنوعی (با تنظیم API).")

@bot.message_handler(commands=["ping"])
def cmd_ping(message):
    safe_reply(message, f"🏓 Pong!\n⏱️ {int(time.time() - START_TIME)} ثانیه از شروع این اجرا گذشته.")

@bot.message_handler(commands=["rules"])
def cmd_rules(message):
    if not is_group(message):
        safe_reply(message, "قوانین را داخل گروه ببین.")
        return
    safe_reply(message, "📜 <b>قوانین گروه</b>\n" + group_settings(message.chat.id)["rules"])

@bot.message_handler(commands=["setrules"])
def cmd_setrules(message):
    if not require_admin(message):
        return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        safe_reply(message, "روش استفاده: /setrules متن قوانین")
        return
    group_settings(message.chat.id)["rules"] = parts[1][:3500]
    save_data()
    safe_reply(message, "✅ قوانین ذخیره شد.")

def setting_command(name, label):
    def handler(message):
        if not require_admin(message):
            return
        parts = (message.text or "").split()
        if len(parts) != 2 or parts[1].lower() not in ("on", "off"):
            safe_reply(message, f"روش استفاده: /{name} on یا /{name} off")
            return
        group_settings(message.chat.id)[name] = parts[1].lower() == "on"
        save_data()
        safe_reply(message, f"✅ {label}: {'روشن' if parts[1].lower() == 'on' else 'خاموش'}")
    handler.__name__ = "cmd_" + name
    return handler

bot.message_handler(commands=["antilink"])(setting_command("antilink", "ضدلینک"))
bot.message_handler(commands=["antispam"])(setting_command("antispam", "ضداسپم"))
bot.message_handler(commands=["antiforward"])(setting_command("antiforward", "ضدفوروارد"))
bot.message_handler(commands=["welcome"])(setting_command("welcome", "خوشامدگویی"))

@bot.message_handler(commands=["addbad"])
def cmd_addbad(message):
    if not require_admin(message):
        return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        safe_reply(message, "روش استفاده: /addbad کلمه")
        return
    words = group_settings(message.chat.id).setdefault("badwords", [])
    word = parts[1].strip()[:100]
    if normalized(word) not in [normalized(w) for w in words]:
        words.append(word)
        save_data()
    safe_reply(message, f"✅ کلمه «{word}» به فیلتر اضافه شد.")

@bot.message_handler(commands=["delbad"])
def cmd_delbad(message):
    if not require_admin(message):
        return
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        safe_reply(message, "روش استفاده: /delbad کلمه")
        return
    s = group_settings(message.chat.id)
    s["badwords"] = [w for w in s.get("badwords", []) if normalized(w) != normalized(parts[1])]
    save_data()
    safe_reply(message, "✅ اگر کلمه در فهرست بود، حذف شد.")

@bot.message_handler(commands=["badlist"])
def cmd_badlist(message):
    if not require_admin(message):
        return
    words = group_settings(message.chat.id).get("badwords", [])
    safe_reply(message, "📋 کلمات فیلتر:\n" + ("\n".join("• " + w for w in words) if words else "فهرست خالی است."))

@bot.message_handler(commands=["warn"])
def cmd_warn(message):
    if not require_admin(message):
        return
    if not message.reply_to_message:
        safe_reply(message, "برای اخطار، روی پیام کاربر ریپلای کن و /warn بزن.")
        return
    target = message.reply_to_message.from_user
    if target.is_bot:
        safe_reply(message, "به ربات‌ها اخطار نمی‌دهم.")
        return
    count, muted = warn_user(message.chat.id, target.id, "اخطار مدیر")
    safe_reply(message, f"⚠️ {mention(target)} اخطار گرفت. تعداد: {count}/3" + ("\n🔇 به‌دلیل رسیدن به ۳ اخطار، ۱۰ دقیقه سکوت شد." if muted else ""))

@bot.message_handler(commands=["warnings"])
def cmd_warnings(message):
    if not is_group(message):
        return
    target = message.reply_to_message.from_user if message.reply_to_message else message.from_user
    count = group_settings(message.chat.id).get("warnings", {}).get(str(target.id), 0)
    safe_reply(message, f"⚠️ تعداد اخطارهای {mention(target)}: {count}")

@bot.message_handler(commands=["resetwarn"])
def cmd_resetwarn(message):
    if not require_admin(message):
        return
    if not message.reply_to_message:
        safe_reply(message, "روی پیام کاربر ریپلای کن و /resetwarn بزن.")
        return
    target = message.reply_to_message.from_user
    group_settings(message.chat.id).setdefault("warnings", {}).pop(str(target.id), None)
    save_data()
    safe_reply(message, f"✅ اخطارهای {mention(target)} پاک شد.")

@bot.message_handler(commands=["mute"])
def cmd_mute(message):
    if not require_admin(message):
        return
    target_id, reason = extract_target_and_reason(message)
    if not target_id:
        safe_reply(message, "روی پیام کاربر ریپلای کن و /mute بزن؛ یا /mute شناسه")
        return
    try:
        bot.restrict_chat_member(message.chat.id, target_id, until_date=int(time.time()) + 600,
                                 permissions=types.ChatPermissions(can_send_messages=False))
        safe_reply(message, f"🔇 کاربر برای ۱۰ دقیقه سکوت شد.\nدلیل: {reason}")
        send_log(message.chat.id, f"🔇 MUTE | chat={message.chat.id} user={target_id} by={message.from_user.id} reason={reason}")
    except Exception as e:
        safe_reply(message, f"❌ سکوت انجام نشد. بررسی کن ربات مدیر و دارای دسترسی محدودکردن اعضا باشد.\n{str(e)[:250]}")

@bot.message_handler(commands=["unmute"])
def cmd_unmute(message):
    if not require_admin(message):
        return
    target_id, _ = extract_target_and_reason(message)
    if not target_id:
        safe_reply(message, "روی پیام کاربر ریپلای کن و /unmute بزن؛ یا /unmute شناسه")
        return
    try:
        bot.restrict_chat_member(message.chat.id, target_id,
                                 permissions=types.ChatPermissions(
                                     can_send_messages=True, can_send_audios=True,
                                     can_send_documents=True, can_send_photos=True,
                                     can_send_videos=True, can_send_video_notes=True,
                                     can_send_voice_notes=True, can_send_polls=True,
                                     can_send_other_messages=True, can_add_web_page_previews=True
                                 ))
        safe_reply(message, "🔊 سکوت کاربر برداشته شد.")
    except Exception as e:
        safe_reply(message, f"❌ رفع سکوت انجام نشد: {str(e)[:250]}")

@bot.message_handler(commands=["ban", "kick"])
def cmd_ban_kick(message):
    if not require_admin(message):
        return
    cmd = (message.text or "").split()[0].split("@")[0].lower()
    target_id, reason = extract_target_and_reason(message)
    if not target_id:
        safe_reply(message, "روی پیام کاربر ریپلای کن و دستور را بزن؛ یا شناسه را وارد کن.")
        return
    try:
        bot.ban_chat_member(message.chat.id, target_id)
        if cmd == "/kick":
            bot.unban_chat_member(message.chat.id, target_id, only_if_banned=True)
            safe_reply(message, f"👢 کاربر از گروه اخراج شد.\nدلیل: {reason}")
        else:
            safe_reply(message, f"⛔ کاربر مسدود شد.\nدلیل: {reason}")
        send_log(message.chat.id, f"{cmd.upper()} | chat={message.chat.id} user={target_id} by={message.from_user.id} reason={reason}")
    except Exception as e:
        safe_reply(message, f"❌ عملیات انجام نشد. دسترسی مدیر ربات را بررسی کن.\n{str(e)[:250]}")

@bot.message_handler(commands=["unban"])
def cmd_unban(message):
    if not require_admin(message):
        return
    parts = (message.text or "").split()
    if len(parts) < 2 or not parts[1].lstrip("-").isdigit():
        safe_reply(message, "روش استفاده: /unban شناسه_عددی_کاربر")
        return
    try:
        bot.unban_chat_member(message.chat.id, int(parts[1]), only_if_banned=True)
        safe_reply(message, "✅ مسدودی کاربر برداشته شد.")
    except Exception as e:
        safe_reply(message, f"❌ رفع مسدودی انجام نشد: {str(e)[:250]}")

@bot.message_handler(commands=["purge"])
def cmd_purge(message):
    if not require_admin(message):
        return
    if not message.reply_to_message:
        safe_reply(message, "روی اولین پیام موردنظر ریپلای کن و /purge تعداد بزن.")
        return
    parts = (message.text or "").split()
    amount = 10
    if len(parts) > 1 and parts[1].isdigit():
        amount = max(1, min(100, int(parts[1])))
    start_id = message.reply_to_message.message_id
    deleted = 0
    for mid in range(start_id, start_id + amount):
        try:
            bot.delete_message(message.chat.id, mid)
            deleted += 1
        except Exception:
            pass
    try:
        bot.delete_message(message.chat.id, message.message_id)
    except Exception:
        pass
    safe_reply(message, f"🧹 {deleted} پیام پاک شد.")

@bot.message_handler(commands=["setlog"])
def cmd_setlog(message):
    if not require_admin(message):
        return
    group_settings(message.chat.id)["log_chat_id"] = message.chat.id
    save_data()
    safe_reply(message, "✅ گزارش‌های مدیریتی در همین گروه ثبت می‌شوند.")

@bot.message_handler(commands=["stats"])
def cmd_stats(message):
    if not is_group(message):
        safe_reply(message, "این دستور برای گروه است.")
        return
    s = group_settings(message.chat.id)
    try:
        count = bot.get_chat_member_count(message.chat.id)
    except Exception:
        count = "نامشخص"
    safe_reply(message, f"📊 <b>آمار گروه</b>\n👥 اعضا: {count}\n🔗 ضدلینک: {'روشن' if s['antilink'] else 'خاموش'}\n🚫 ضداسپم: {'روشن' if s['antispam'] else 'خاموش'}\n👋 خوشامد: {'روشن' if s['welcome'] else 'خاموش'}\n🧾 کلمات فیلتر: {len(s.get('badwords', []))}")

@bot.message_handler(commands=["ai"])
def cmd_ai(message):
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        safe_reply(message, "روش استفاده: /ai سؤال خودت را بنویس")
        return
    status = safe_reply(message, "🤖 دارم فکر می‌کنم...")
    answer = ai_answer(parts[1], message.chat.title if message.chat else "")
    try:
        if status:
            bot.edit_message_text(answer, message.chat.id, status.message_id)
        else:
            safe_reply(message, answer)
    except Exception:
        safe_reply(message, answer)

# -------------------- Welcome / moderation --------------------
@bot.message_handler(content_types=["new_chat_members"])
def new_members(message):
    if not is_group(message):
        return
    s = group_settings(message.chat.id)
    if not s.get("welcome", True):
        return
    for member in message.new_chat_members:
        if member.id == bot.get_me().id:
            safe_reply(message, f"سلام! من <b>{BOT_NAME}</b> هستم.\nبرای دیدن دستورها /help را بزن.")
        else:
            safe_reply(message, f"👋 خوش اومدی {mention(member)}!\nلطفاً قوانین گروه رو با /rules بخون.")

@bot.message_handler(content_types=["left_chat_member"])
def left_member(message):
    try:
        if is_group(message) and group_settings(message.chat.id).get("welcome", True):
            safe_reply(message, "👋 یکی از اعضا گروه را ترک کرد.")
    except Exception:
        log.exception("Goodbye handler failed")

# In-memory anti-flood tracking
recent_messages = defaultdict(lambda: deque(maxlen=8))
last_duplicate = {}

@bot.message_handler(func=lambda m: bool(m and m.text and not (m.text or "").startswith("/")), content_types=["text"])
def moderate_text(message):
    if not is_group(message) or not data.get("bot_enabled", True):
        return
    if not message.from_user or message.from_user.is_bot:
        return
    if is_admin(message) or is_owner(message.from_user.id):
        return
    s = group_settings(message.chat.id)
    text_body = message.text or ""
    reason = None

    if s.get("antilink", True) and contains_link(text_body):
        reason = "ارسال لینک"
    elif contains_badword(text_body, s.get("badwords", [])):
        reason = "کلمه فیلترشده"
    elif s.get("antiforward", False) and getattr(message, "forward_origin", None):
        reason = "پیام فورواردی"
    elif s.get("antispam", True):
        key = (message.chat.id, message.from_user.id)
        now = time.time()
        q = recent_messages[key]
        q.append(now)
        if len(q) >= 6 and q[-1] - q[0] < 7:
            reason = "ارسال پیام‌های پیاپی"
        dupkey = (message.chat.id, message.from_user.id)
        old = last_duplicate.get(dupkey)
        if old and old[0] == normalized(text_body) and now - old[1] < 15:
            reason = "تکرار پیام"
        last_duplicate[dupkey] = (normalized(text_body), now)

    if reason:
        try:
            bot.delete_message(message.chat.id, message.message_id)
        except Exception:
            log.info("Could not delete offending message in %s", message.chat.id)
        count, muted = warn_user(message.chat.id, message.from_user.id, reason)
        safe_reply(message, f"⚠️ {mention(message.from_user)} پیام حذف شد: {reason}.\nاخطار: {count}/3" + ("\n🔇 سکوت ۱۰ دقیقه‌ای فعال شد." if muted else ""))
        send_log(message.chat.id, f"MODERATION | chat={message.chat.id} user={message.from_user.id} reason={reason} warnings={count}")

# -------------------- Utility commands --------------------
@bot.message_handler(commands=["coin"])
def cmd_coin(message):
    safe_reply(message, random.choice(["🪙 شیر", "🪙 خط"]))

@bot.message_handler(commands=["dice"])
def cmd_dice(message):
    safe_reply(message, f"🎲 عدد تو: {random.randint(1, 6)}")

@bot.message_handler(commands=["calc"])
def cmd_calc(message):
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        safe_reply(message, "روش استفاده: /calc 12*(3+4)")
        return
    expr = parts[1].strip()
    if len(expr) > 100 or not re.fullmatch(r"[0-9+\-*/(). %]+", expr):
        safe_reply(message, "❌ فقط محاسبات ساده عددی مجاز است.")
        return
    try:
        # Safe arithmetic parser: no names, calls, attributes or other Python syntax.
        import ast
        tree = ast.parse(expr, mode="eval")
        allowed = (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant, ast.Add, ast.Sub,
                   ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow, ast.USub, ast.UAdd)
        if any(not isinstance(node, allowed) for node in ast.walk(tree)):
            raise ValueError("unsupported")
        result = eval(compile(tree, "<calc>", "eval"), {"__builtins__": {}}, {})
        if isinstance(result, (int, float)) and math.isfinite(result):
            safe_reply(message, f"🧮 جواب: <code>{result}</code>")
        else:
            safe_reply(message, "❌ نتیجه معتبر نیست.")
    except Exception:
        safe_reply(message, "❌ عبارت ریاضی معتبر نیست.")

# -------------------- Callback panel --------------------
@bot.message_handler(commands=["panel"])
def cmd_panel(message):
    if not is_admin_or_owner(message):
        safe_reply(message, "⛔ پنل فقط برای مدیر گروه یا مالک ربات است.")
        return
    if not is_group(message):
        safe_reply(message, "پنل را داخل گروه باز کن.")
        return
    s = group_settings(message.chat.id)
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton(f"ضدلینک: {'روشن' if s['antilink'] else 'خاموش'}", callback_data="toggle:antilink"),
        types.InlineKeyboardButton(f"ضداسپم: {'روشن' if s['antispam'] else 'خاموش'}", callback_data="toggle:antispam"),
        types.InlineKeyboardButton(f"فوروارد: {'روشن' if s['antiforward'] else 'خاموش'}", callback_data="toggle:antiforward"),
        types.InlineKeyboardButton(f"خوشامد: {'روشن' if s['welcome'] else 'خاموش'}", callback_data="toggle:welcome"),
    )
    kb.add(types.InlineKeyboardButton("📊 آمار", callback_data="panel:stats"),
           types.InlineKeyboardButton("📜 قوانین", callback_data="panel:rules"))
    safe_reply(message, "🎛️ <b>پنل مدیریت MASIH GUARD PRO</b>\nبرای تغییر وضعیت، دکمه را بزن:", reply_markup=kb)

@bot.callback_query_handler(func=lambda call: bool(call.data and (call.data.startswith("toggle:") or call.data.startswith("panel:"))))
def panel_callback(call):
    try:
        chat_id = call.message.chat.id
        member = bot.get_chat_member(chat_id, call.from_user.id)
        if member.status not in ("administrator", "creator") and not is_owner(call.from_user.id):
            bot.answer_callback_query(call.id, "فقط مدیران اجازه دارند.", show_alert=True)
            return
        s = group_settings(chat_id)
        if call.data.startswith("toggle:"):
            key = call.data.split(":", 1)[1]
            if key not in ("antilink", "antispam", "antiforward", "welcome"):
                bot.answer_callback_query(call.id, "گزینه نامعتبر است.")
                return
            s[key] = not s.get(key, False)
            save_data()
            bot.answer_callback_query(call.id, "تنظیم ذخیره شد.")
            # Refresh panel buttons by editing the original message.
            kb = types.InlineKeyboardMarkup(row_width=2)
            kb.add(
                types.InlineKeyboardButton(f"ضدلینک: {'روشن' if s['antilink'] else 'خاموش'}", callback_data="toggle:antilink"),
                types.InlineKeyboardButton(f"ضداسپم: {'روشن' if s['antispam'] else 'خاموش'}", callback_data="toggle:antispam"),
                types.InlineKeyboardButton(f"فوروارد: {'روشن' if s['antiforward'] else 'خاموش'}", callback_data="toggle:antiforward"),
                types.InlineKeyboardButton(f"خوشامد: {'روشن' if s['welcome'] else 'خاموش'}", callback_data="toggle:welcome"),
            )
            kb.add(types.InlineKeyboardButton("📊 آمار", callback_data="panel:stats"),
                   types.InlineKeyboardButton("📜 قوانین", callback_data="panel:rules"))
            bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=kb)
        elif call.data == "panel:rules":
            bot.answer_callback_query(call.id)
            bot.send_message(chat_id, "📜 قوانین:\n" + s["rules"])
        elif call.data == "panel:stats":
            bot.answer_callback_query(call.id)
            bot.send_message(chat_id, f"📊 ضدلینک: {s['antilink']}\nضداسپم: {s['antispam']}\nکلمات فیلتر: {len(s.get('badwords', []))}")
    except Exception:
        log.exception("Panel callback failed")
        try:
            bot.answer_callback_query(call.id, "خطا رخ داد؛ دوباره تلاش کن.")
        except Exception:
            pass

# -------------------- Startup and reconnect --------------------
def run_web():
    port = int(os.getenv("PORT", "8080"))
    app.run(host="0.0.0.0", port=port, use_reloader=False)

def run_bot_forever():
    delay = 3
    while True:
        try:
            log.info("Starting %s v%s", BOT_NAME, VERSION)
            try:
                bot.remove_webhook(drop_pending_updates=False)
            except Exception:
                log.exception("Could not remove webhook (continuing)")
            bot.infinity_polling(timeout=30, long_polling_timeout=25, skip_pending=False)
            delay = 3
        except KeyboardInterrupt:
            log.info("Stopped by keyboard")
            break
        except Exception:
            log.exception("Polling stopped unexpectedly; reconnecting in %s seconds", delay)
            time.sleep(delay)
            delay = min(delay * 2, 60)

if __name__ == "__main__":
    threading.Thread(target=run_web, daemon=True).start()
    run_bot_forever()
