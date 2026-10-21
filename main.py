# -*- coding: utf-8 -*-
"""MASIH GUARD v30.0 | by Masih Hackring
Telegram group helper/moderation bot.

Environment variables:
  TELEGRAM_BOT_TOKEN (or BOT_TOKEN) - required
  OWNER_ID - Telegram numeric owner ID (default: 8620924698)
  AI_API_KEY - optional OpenRouter API key for AI replies
  AI_MODEL - optional OpenRouter model (default: openrouter/free)
  PORT - optional web health-check port (default: 8080)

Install requirements: pyTelegramBotAPI, requests, Flask
"""
import os
import re
import json
import time
import html
import random
import logging
import threading
from collections import defaultdict, deque
from datetime import datetime

import requests
import telebot
from telebot import types
from flask import Flask, jsonify

BOT_TOKEN = (os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN") or "").strip()
BOT_NAME = "MASIH GUARD"
VERSION = "30.0"
AUTHOR = "Masih Hackring"
OWNER_ID = int(os.getenv("OWNER_ID", "8620924698"))
PORT = int(os.getenv("PORT", "8080"))
DATA_FILE = os.getenv("DATA_FILE", "masih_guard_data.json")
AI_API_KEY = os.getenv("AI_API_KEY", "").strip()
AI_BASE_URL = os.getenv("AI_BASE_URL", "https://openrouter.ai/api/v1/chat/completions").strip()
AI_MODEL = os.getenv("AI_MODEL", "openrouter/free").strip()
CHANNEL_URL = os.getenv("CHANNEL_URL", "https://t.me/IRHACK_APP33")
CREATOR_URL = os.getenv("CREATOR_URL", "https://t.me/Ma3ih01")

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("masih_guard")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set. Add TELEGRAM_BOT_TOKEN or BOT_TOKEN in host environment variables.")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML", threaded=True, num_threads=8)
app = Flask(__name__)

DATA_LOCK = threading.RLock()
DEFAULT_SETTINGS = {
    "anti_link": True,
    "anti_spam": True,
    "anti_duplicate": True,
    "badword_filter": False,
    "welcome_enabled": True,
    "captcha_enabled": False,
    "lock_media": False,
    "max_messages": 6,
    "spam_window": 8,
    "max_warnings": 3,
    "mute_seconds": 60,
    "rules": "🌈 قوانین گروه:\n1) احترام به همه\n2) تبلیغات و لینک ممنوع مگر با اجازه مدیر\n3) اسپم و توهین ممنوع\n━━━ 🛡️ MASIH GUARD ━━━",
    "welcome_text": "سلام {name} به گروه: {group} خوش اومدی! 🍻💜\n🌈 جمع گرم و دوست‌داشتنی گروه منتظرته.\n━━━ 🛡️ MASIH GUARD 〰️ ━━━\n〰️ توسط: Masih Hackring",
    "bad_words": ["کص", "کسکش", "جنده"],
}
DATA = {"groups": {}, "warnings": {}, "muted": {}, "banned": {}, "stats": {"messages": 0, "blocked": 0, "welcomes": 0}}


def load_data():
    global DATA
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                DATA.update(loaded)
    except Exception as e:
        log.warning("Could not load data file: %s", e)


def save_data():
    try:
        with DATA_LOCK:
            tmp = DATA_FILE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(DATA, f, ensure_ascii=False, indent=2)
            os.replace(tmp, DATA_FILE)
    except Exception as e:
        log.warning("Could not save data file: %s", e)


def settings(chat_id):
    key = str(chat_id)
    with DATA_LOCK:
        if key not in DATA["groups"]:
            DATA["groups"][key] = dict(DEFAULT_SETTINGS)
        else:
            for k, v in DEFAULT_SETTINGS.items():
                DATA["groups"][key].setdefault(k, v)
        return DATA["groups"][key]


def display_name(user):
    name = " ".join(x for x in [getattr(user, "first_name", ""), getattr(user, "last_name", "")] if x).strip()
    return html.escape(name or getattr(user, "username", None) or str(getattr(user, "id", "کاربر")))


def mention(user):
    return f'<a href="tg://user?id={user.id}">{display_name(user)}</a>'


def is_owner(user_id):
    return int(user_id) == OWNER_ID


def is_admin(chat_id, user_id):
    if is_owner(user_id):
        return True
    try:
        member = bot.get_chat_member(chat_id, user_id)
        return member.status in ("administrator", "creator")
    except Exception:
        return False


def admin_required(message):
    if not message.from_user:
        return False
    if not is_admin(message.chat.id, message.from_user.id):
        bot.reply_to(message, "⛔ این دستور فقط برای مدیران گروه است.")
        return False
    return True


def target_from_message(message):
    if message.reply_to_message and message.reply_to_message.from_user:
        return message.reply_to_message.from_user
    parts = (message.text or "").split()
    if len(parts) >= 2 and parts[1].isdigit():
        try:
            return bot.get_chat_member(message.chat.id, int(parts[1])).user
        except Exception:
            return None
    return None


def main_panel():
    kb = types.InlineKeyboardMarkup(row_width=2)
    # Telegram controls actual button colors; rainbow emojis provide the seven-color look.
    kb.add(
        types.InlineKeyboardButton("🔴 مدیریت", callback_data="panel:manage"),
        types.InlineKeyboardButton("🟠 امنیت", callback_data="panel:security"),
        types.InlineKeyboardButton("🟡 قوانین", callback_data="panel:rules"),
        types.InlineKeyboardButton("🟢 راهنما", callback_data="panel:help"),
        types.InlineKeyboardButton("🔵 وضعیت", callback_data="panel:status"),
        types.InlineKeyboardButton("🟣 سازنده", callback_data="panel:creator"),
        types.InlineKeyboardButton("🌈 پنل هفت‌رنگ", callback_data="panel:rainbow"),
        types.InlineKeyboardButton("📢 کانال", url=CHANNEL_URL),
    )
    return kb


def panel_text():
    return (
        "🌈 <b>MASIH GUARD | نسخه 30.0</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "🛡️ ربات مدیریت و امنیت گروه\n"
        "🔴 مدیریت  🟠 امنیت  🟡 قوانین\n"
        "🟢 راهنما  🔵 وضعیت  🟣 سازنده\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "✦ سازنده: <b>Masih Hackring</b>\n"
        "برای فونت هر اسم یا متنی، بنویس: <code>فونت اسم دلخواه</code>\n"
        "برای پروکسی، بنویس: <code>پروکسی</code>"
    )


def send_long(chat_id, text, reply_to=None):
    # Telegram text messages have a 4096-character limit; split on line boundaries.
    chunks, current = [], ""
    for line in text.splitlines(True):
        if len(current) + len(line) > 3900:
            if current:
                chunks.append(current)
            current = ""
        current += line
    if current:
        chunks.append(current)
    for i, chunk in enumerate(chunks):
        bot.send_message(chat_id, chunk, reply_to_message_id=reply_to if i == 0 else None, disable_web_page_preview=True)

# ---------- 100 font styles ----------
_MATH_UPPER = {
    "bold": (0x1D400, 0x1D41A), "italic": (0x1D434, 0x1D44E),
    "bold_italic": (0x1D468, 0x1D482), "script": (0x1D49C, 0x1D4B6),
    "bold_script": (0x1D4D0, 0x1D4EA), "fraktur": (0x1D504, 0x1D51E),
    "double": (0x1D538, 0x1D552), "bold_fraktur": (0x1D56C, 0x1D586),
    "sans": (0x1D5A0, 0x1D5BA), "sans_bold": (0x1D5D4, 0x1D5EE),
    "sans_italic": (0x1D608, 0x1D622), "sans_bold_italic": (0x1D63C, 0x1D656),
    "mono": (0x1D670, 0x1D68A),
}
_MATH_LOWER = {
    "bold": (0x1D41A, 0x1D434), "italic": (0x1D44E, 0x1D468),
    "bold_italic": (0x1D482, 0x1D49C), "script": (0x1D4B6, 0x1D4D0),
    "bold_script": (0x1D4EA, 0x1D504), "fraktur": (0x1D51E, 0x1D538),
    "double": (0x1D552, 0x1D56C), "bold_fraktur": (0x1D586, 0x1D5A0),
    "sans": (0x1D5BA, 0x1D5D4), "sans_bold": (0x1D5EE, 0x1D608),
    "sans_italic": (0x1D622, 0x1D63C), "sans_bold_italic": (0x1D656, 0x1D670),
    "mono": (0x1D68A, 0x1D6A4),
}
_STYLE_NAMES = ["Bold", "Italic", "Bold Italic", "Script", "Bold Script", "Fraktur", "Double-struck", "Bold Fraktur", "Sans", "Sans Bold", "Sans Italic", "Sans Bold Italic", "Monospace"]

def stylize_latin(text, style):
    upper = _MATH_UPPER.get(style)
    lower = _MATH_LOWER.get(style)
    out = []
    for ch in text:
        if "A" <= ch <= "Z" and upper:
            cp = upper[0] + ord(ch) - ord("A")
            # Unicode has a few historical holes in script/fraktur alphabets; fallback to original.
            try: out.append(chr(cp))
            except ValueError: out.append(ch)
        elif "a" <= ch <= "z" and lower:
            cp = lower[0] + ord(ch) - ord("a")
            try: out.append(chr(cp))
            except ValueError: out.append(ch)
        elif "0" <= ch <= "9" and style == "double":
            out.append(chr(0x1D7D8 + ord(ch) - ord("0")))
        elif "0" <= ch <= "9" and style in ("sans", "sans_bold", "mono"):
            base = {"sans": 0x1D7E2, "sans_bold": 0x1D7EC, "mono": 0x1D7F6}[style]
            out.append(chr(base + ord(ch) - ord("0")))
        else:
            out.append(ch)
    return "".join(out)


def font_variants(text):
    styles = list(_MATH_UPPER.keys())
    result = []
    # 13 mathematical alphabet styles
    for style in styles:
        result.append((style.replace("_", " ").title(), stylize_latin(text, style)))
    # Decorative variants that preserve the supplied text and work with Persian too.
    wrappers = [
        ("Neon", "✨ {x} ✨"), ("Stars", "★彡 {x} 彡★"), ("Crown", "♛ {x} ♛"),
        ("Diamond", "◇◆ {x} ◆◇"), ("Fire", "🔥 {x} 🔥"), ("Purple", "💜 {x} 💜"),
        ("Blue", "💙 {x} 💙"), ("Green", "💚 {x} 💚"), ("Red", "❤️ {x} ❤️"),
        ("Gold", "👑 {x} 👑"), ("Cyber", "⟦ {x} ⟧"), ("Box", "『 {x} 』"),
        ("Wave", "〰️ {x} 〰️"), ("Spark", "⋆｡°✩ {x} ✩°｡⋆"), ("Arrow", "➤ {x} ◀"),
        ("Moon", "☾ {x} ☽"), ("Flower", "❀ {x} ❀"), ("Heart", "ღ {x} ღ"),
        ("Music", "♫ {x} ♫"), ("Royal", "༺ {x} ༻"), ("Frame", "【 {x} 】"),
        ("Square", "▣ {x} ▣"), ("Circle", "◉ {x} ◉"), ("Cross", "✞ {x} ✞"),
        ("Butterfly", "ʚ♡ɞ {x} ʚ♡ɞ"), ("Cloud", "☁ {x} ☁"), ("Lightning", "ϟ {x} ϟ"),
        ("Pixel", "▓▒░ {x} ░▒▓"), ("Glitch", "≋ {x} ≋"), ("Minimal", "• {x} •"),
        ("Slash", "╱ {x} ╲"), ("Bracket", "⟪ {x} ⟫"), ("Flame", "♨ {x} ♨"),
        ("Gem", "💎 {x} 💎"), ("Angel", "୨୧ {x} ୨୧"), ("Devil", "𖤐 {x} 𖤐"),
        ("Leaf", "❦ {x} ❦"), ("Ribbon", "୨୧・{x}・୨୧"), ("Neon 2", "⫷ {x} ⫸"),
        ("Cyber 2", "⌁ {x} ⌁"), ("Royal 2", "♔ {x} ♔"), ("Stars 2", "✦✧ {x} ✧✦"),
        ("Cute", "૮₍ ˶ᵔ ᵕ ᵔ˶ ₎ა {x}"), ("Retro", "《 {x} 》"), ("Tech", "< {x} />"),
        ("Matrix", "▌│█║▌║▌ {x} ▌║▌║█│▌"), ("Line", "━━ {x} ━━"), ("Dots", "··· {x} ···"),
        ("Wave 2", "≈≈ {x} ≈≈"), ("Crown 2", "♕ {x} ♕"), ("Heart 2", "♡ {x} ♡"),
        ("Flower 2", "✿ {x} ✿"), ("Sparkle 2", "✧ {x} ✧"), ("Magic", "☄ {x} ☄"),
        ("Badge", "『★』{x}『★』"), ("Shield", "🛡️ {x} 🛡️"), ("Rainbow", "🌈 {x} 🌈"),
        ("Purple 2", "🟣〔{x}〕🟣"), ("Blue 2", "🔵〔{x}〕🔵"), ("Green 2", "🟢〔{x}〕🟢"),
        ("Yellow", "🟡〔{x}〕🟡"), ("Orange", "🟠〔{x}〕🟠"), ("Red 2", "🔴〔{x}〕🔴"),
        ("Square 2", "▰ {x} ▰"), ("Triangle", "△ {x} △"), ("Diamond 2", "◈ {x} ◈"),
        ("Vintage", "༒ {x} ༒"), ("Fancy", "꧁ {x} ꧂"), ("Fancy 2", "꧁༺ {x} ༻꧂"),
        ("Mystic", "𓆩 {x} 𓆪"), ("Space", "⭒ {x} ⭒"), ("Comet", "☄︎ {x} ☄︎"),
        ("Wave 3", "〜 {x} 〜"), ("Bracket 2", "〖 {x} 〗"), ("Frame 2", "╭─ {x} ─╮"),
        ("Frame 3", "╰─ {x} ─╯"), ("Star 3", "✪ {x} ✪"), ("Music 2", "♪ {x} ♪"),
        ("Love", "💞 {x} 💞"), ("Butterfly 2", "🦋 {x} 🦋"), ("Fox", "ᵔᴥᵔ {x}"),
        ("Cat", "ฅ^•ﻌ•^ฅ {x}"), ("Bear", "ʕ•ᴥ•ʔ {x}"), ("Sun", "☀ {x} ☀"),
        ("Moon 2", "☽⋆ {x} ⋆☾"), ("Cloud 2", "☁︎ {x} ☁︎"), ("Wave 4", "≋≋ {x} ≋≋"),
        ("Hash", "# {x} #"), ("Percent", "% {x} %"), ("At", "@ {x} @"),
        ("Dollar", "$ {x} $"), ("Ampersand", "& {x} &"), ("Plus", "✚ {x} ✚"),
        ("Infinity", "∞ {x} ∞"), ("Omega", "Ω {x} Ω"), ("Lambda", "Λ {x} Λ"),
        ("Terminal", "root@masih:~$ {x}"), ("Code", "[ {x} ]"), ("System", ":: {x} ::"),
        ("Glitch 2", "̷{x}̷"), ("Final", "༺🌈 {x} 🌈༻"),
    ]
    for name, fmt in wrappers:
        result.append((name, fmt.format(x=text)))
    # Always return exactly 100 copyable lines.
    return result[:100]


def handle_font_command(message, raw_text=None):
    text = (raw_text if raw_text is not None else (message.text or "")).strip()
    match = re.match(r"^(?:فونت|font)(?:\s+(.+))?$", text, flags=re.I | re.S)
    if not match or not match.group(1):
        bot.reply_to(message, "✍️ اسم یا متن رو بعد از کلمه فونت بنویس.\nمثال: <code>فونت Masih Hackring</code>")
        return True
    supplied = match.group(1).strip()
    if len(supplied) > 120:
        bot.reply_to(message, "⚠️ متن برای ساخت ۱۰۰ مدل خیلی طولانیه؛ لطفاً کوتاه‌ترش کن (حداکثر ۱۲۰ کاراکتر).")
        return True
    variants = font_variants(supplied)
    output = [f"🌈 <b>۱۰۰ مدل فونت برای:</b> {html.escape(supplied)}\n━━━━━━━━━━━━━━━━━━"]
    for i, (style, value) in enumerate(variants, 1):
        output.append(f"{i:02d}. {html.escape(value)}")
    output.append("\n✦ سازنده: <b>Masih Hackring</b>")
    send_long(message.chat.id, "\n".join(output), message.message_id)
    return True

# ---------- public Telegram proxy links ----------
def get_proxy_links():
    sources = [
        "https://raw.githubusercontent.com/ALIILAPRO/Telegram-Proxy/main/proxy.txt",
        "https://raw.githubusercontent.com/TelegramMessenger/Telegram-iOS/master/README.md",
    ]
    found = []
    patterns = [r"https?://t\.me/(?:proxy|socks)\?[A-Za-z0-9_=%&.+-]+", r"tg://proxy\?[A-Za-z0-9_=%&.+-]+"]
    for url in sources:
        try:
            r = requests.get(url, timeout=7, headers={"User-Agent": "MASIH-GUARD/30.0"})
            if r.ok:
                body = r.text
                for pat in patterns:
                    for link in re.findall(pat, body):
                        link = link.rstrip(".,);]}")
                        if link not in found:
                            found.append(link)
        except Exception as e:
            log.info("Proxy source unavailable: %s", e)
    return found[:10]


def handle_proxy(message):
    links = get_proxy_links()
    if not links:
        bot.reply_to(message, "⚠️ فعلاً نتونستم فهرست پروکسی رو از منبع عمومی دریافت کنم. چند دقیقه بعد دوباره «پروکسی» رو بفرست.")
        return
    lines = ["🌐 <b>فهرست پروکسی‌های عمومی تلگرام</b>", "━━━━━━━━━━━━━━━━━━"]
    lines.extend(f"{i}. {html.escape(link)}" for i, link in enumerate(links, 1))
    lines.append("\n⚠️ سرعت و پینگ این لینک‌ها از اینجا تست نشده و ممکنه بعضی‌ها از کار افتاده باشن. پروکسی ناشناس رو برای کارهای حساس با احتیاط استفاده کن.")
    lines.append("✦ <b>Masih Hackring</b>")
    send_long(message.chat.id, "\n".join(lines), message.message_id)

# ---------- moderation ----------
def mute_user(chat_id, user_id, seconds):
    until = int(time.time()) + max(30, min(int(seconds), 2_592_000))
    permissions = types.ChatPermissions(can_send_messages=False, can_send_audios=False, can_send_documents=False,
        can_send_photos=False, can_send_videos=False, can_send_video_notes=False, can_send_voice_notes=False,
        can_send_polls=False, can_send_other_messages=False, can_add_web_page_previews=False)
    bot.restrict_chat_member(chat_id, user_id, permissions, until_date=until)
    DATA["muted"][f"{chat_id}:{user_id}"] = until
    save_data()


def unmute_user(chat_id, user_id):
    permissions = types.ChatPermissions(can_send_messages=True, can_send_audios=True, can_send_documents=True,
        can_send_photos=True, can_send_videos=True, can_send_video_notes=True, can_send_voice_notes=True,
        can_send_polls=True, can_send_other_messages=True, can_add_web_page_previews=True)
    bot.restrict_chat_member(chat_id, user_id, permissions)
    DATA["muted"].pop(f"{chat_id}:{user_id}", None)
    save_data()


def ban_user(chat_id, user_id):
    bot.ban_chat_member(chat_id, user_id)
    DATA["banned"][f"{chat_id}:{user_id}"] = int(time.time())
    save_data()


def moderation_notice(message, user, status, reason=None):
    if "تبچی" in status:
        state = "سکوت در گروه"
    elif "مسدود" in status:
        state = "مسدود شد"
    else:
        state = status
    text = f"〰️ کاربر {display_name(user)} {status}\n🎖 وضعیت کاربر : {state}"
    if reason:
        text += f"\n📝 دلیل: {html.escape(reason)}"
    text += "\n━━━ 💢 MASIH GUARD 〰️ ━━━\n〰️ توسط : Masih Hackring"
    bot.send_message(message.chat.id, text, reply_to_message_id=message.message_id)


def add_warning(chat_id, user_id):
    key = f"{chat_id}:{user_id}"
    DATA["warnings"][key] = int(DATA["warnings"].get(key, 0)) + 1
    save_data()
    return DATA["warnings"][key]


def try_delete(message):
    try:
        bot.delete_message(message.chat.id, message.message_id)
        return True
    except Exception:
        return False

@bot.message_handler(commands=["start", "panel"])
def start(message):
    bot.send_message(message.chat.id, panel_text(), reply_markup=main_panel(), disable_web_page_preview=True)

@bot.message_handler(commands=["about"])
def about(message):
    bot.reply_to(message, f"🌈 <b>{BOT_NAME} v{VERSION}</b>\n🛡️ ابزار مدیریت گروه، ضداسپم و خوشامدگویی\n✦ سازنده: <b>{AUTHOR}</b>\n📨 ارتباط: @{CREATOR_URL.rsplit('/', 1)[-1]}")

@bot.message_handler(commands=["help"])
def help_command(message):
    txt = (
        "🌈 <b>راهنمای MASIH GUARD v30.0</b>\n━━━━━━━━━━━━━━━━━━\n"
        "• <code>/panel</code> پنل اصلی\n• <code>/rules</code> دیدن قوانین\n• <code>/setrules متن</code> تنظیم قوانین (مدیر)\n"
        "• <code>/antilink on|off</code> ضدلینک (مدیر)\n• <code>/antispam on|off</code> ضداسپم (مدیر)\n"
        "• <code>/warn</code> اخطار به کاربر (روی پیامش ریپلای کن)\n• <code>/mute 60</code> سکوت (ریپلای؛ ثانیه اختیاری)\n"
        "• <code>/unmute</code> رفع سکوت (ریپلای)\n• <code>/ban</code> مسدودکردن (ریپلای)\n• <code>/unban شناسه</code> رفع مسدودی\n"
        "• <code>/kick</code> اخراج (ریپلای)\n• <code>/purge</code> پاک‌کردن پیام انتخاب‌شده و پیام‌های بعد از آن در حد دسترسی تلگرام\n"
        "• <code>فونت متن</code> ساخت ۱۰۰ مدل نوشتار\n• <code>پروکسی</code> دریافت فهرست پروکسی عمومی\n"
        "━━━━━━━━━━━━━━━━━━\n⚠️ دستورهای مدیریتی نیاز به دسترسی مدیر ربات دارند."
    )
    bot.reply_to(message, txt)

@bot.message_handler(commands=["rules"])
def rules_command(message):
    bot.reply_to(message, settings(message.chat.id)["rules"])

@bot.message_handler(commands=["setrules"])
def setrules_command(message):
    if not admin_required(message): return
    text = (message.text or "").partition(" ")[2].strip()
    if not text:
        bot.reply_to(message, "نمونه: <code>/setrules احترام به همه و ممنوعیت تبلیغات</code>")
        return
    settings(message.chat.id)["rules"] = text
    save_data()
    bot.reply_to(message, "✅ قوانین گروه ذخیره شد.")

@bot.message_handler(commands=["antilink", "antispam", "antiduplicate", "badwords", "welcome", "lockmedia"])
def toggle_command(message):
    if not admin_required(message): return
    cmd = message.text.split()[0].split("@")[0].lstrip("/")
    value = (message.text or "").split()
    if len(value) < 2 or value[1].lower() not in ("on", "off"):
        bot.reply_to(message, f"استفاده: <code>/{cmd} on</code> یا <code>/{cmd} off</code>")
        return
    key_map = {"antilink": "anti_link", "antispam": "anti_spam", "antiduplicate": "anti_duplicate", "badwords": "badword_filter", "welcome": "welcome_enabled", "lockmedia": "lock_media"}
    key = key_map[cmd]
    settings(message.chat.id)[key] = value[1].lower() == "on"
    save_data()
    bot.reply_to(message, f"✅ {cmd}: {'روشن' if settings(message.chat.id)[key] else 'خاموش'} شد.")

@bot.message_handler(commands=["warn", "mute", "unmute", "ban", "unban", "kick"])
def moderation_command(message):
    if not admin_required(message): return
    cmd = message.text.split()[0].split("@")[0].lstrip("/")
    target = target_from_message(message)
    if cmd == "unban" and not target:
        parts = (message.text or "").split()
        if len(parts) > 1 and parts[1].isdigit():
            try:
                bot.unban_chat_member(message.chat.id, int(parts[1]), only_if_banned=True)
                DATA["banned"].pop(f"{message.chat.id}:{parts[1]}", None)
                save_data()
                bot.reply_to(message, "✅ مسدودی کاربر برداشته شد.")
            except Exception as e: bot.reply_to(message, f"❌ انجام نشد: {html.escape(str(e)[:250])}")
        else: bot.reply_to(message, "روی پیام کاربر ریپلای کن یا شناسه عددی بده: <code>/unban 123456</code>")
        return
    if not target:
        bot.reply_to(message, "⚠️ روی پیام کاربر ریپلای کن و دستور رو بفرست.")
        return
    if target.id == OWNER_ID or target.id == message.from_user.id:
        bot.reply_to(message, "⛔ این کاربر رو نمی‌تونم با این دستور مدیریت کنم.")
        return
    try:
        if cmd == "warn":
            count = add_warning(message.chat.id, target.id)
            limit = int(settings(message.chat.id)["max_warnings"])
            bot.reply_to(message, f"⚠️ به {mention(target)} اخطار داده شد. ({count}/{limit})")
            if count >= limit:
                mute_user(message.chat.id, target.id, int(settings(message.chat.id)["mute_seconds"]))
                DATA["warnings"][f"{message.chat.id}:{target.id}"] = 0
                save_data()
                bot.send_message(message.chat.id, f"🔇 {mention(target)} به دلیل دریافت چند اخطار، موقتاً ساکت شد.")
        elif cmd == "mute":
            parts = (message.text or "").split()
            secs = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else int(settings(message.chat.id)["mute_seconds"])
            mute_user(message.chat.id, target.id, secs)
            moderation_notice(message, target, "در لیست تبچی بود !")
        elif cmd == "unmute":
            unmute_user(message.chat.id, target.id)
            bot.reply_to(message, f"🔊 سکوت {mention(target)} برداشته شد.")
        elif cmd == "ban":
            ban_user(message.chat.id, target.id)
            moderation_notice(message, target, "در لیست مسدودها شد !", "تخلف از قوانین گروه")
        elif cmd == "kick":
            bot.ban_chat_member(message.chat.id, target.id)
            bot.unban_chat_member(message.chat.id, target.id, only_if_banned=True)
            bot.reply_to(message, f"👢 {mention(target)} از گروه اخراج شد.")
    except Exception as e:
        bot.reply_to(message, f"❌ انجام نشد. بررسی کن ربات مدیر و دسترسی لازم رو داشته باشه.\n<code>{html.escape(str(e)[:300])}</code>")

@bot.message_handler(commands=["purge"])
def purge_command(message):
    if not admin_required(message): return
    if not message.reply_to_message:
        bot.reply_to(message, "برای پاک‌کردن پیام، روی همون پیام ریپلای کن و /purge بفرست.")
        return
    try:
        bot.delete_message(message.chat.id, message.reply_to_message.message_id)
        bot.delete_message(message.chat.id, message.message_id)
    except Exception as e:
        bot.reply_to(message, f"❌ پاک‌کردن پیام انجام نشد؛ دسترسی حذف پیام رو بررسی کن.\n<code>{html.escape(str(e)[:200])}</code>")

@bot.callback_query_handler(func=lambda call: call.data.startswith("panel:"))
def panel_callbacks(call):
    key = call.data.split(":", 1)[1]
    chat_id = call.message.chat.id if call.message else call.from_user.id
    if key == "manage":
        text = "🔴 <b>مدیریت گروه</b>\nروی پیام کاربر ریپلای کن: /warn، /mute 60، /unmute، /ban یا /kick\nبرای رفع مسدودی: /unban شناسه"
    elif key == "security":
        text = "🟠 <b>امنیت</b>\n/antilink on|off\n/antispam on|off\n/antiduplicate on|off\n/badwords on|off\n/welcome on|off\n/lockmedia on|off"
    elif key == "rules":
        text = settings(chat_id)["rules"]
    elif key == "help":
        text = "🟢 برای راهنمای کامل دستور /help رو بفرست.\nفونت: <code>فونت اسم دلخواه</code>\nپروکسی: <code>پروکسی</code>"
    elif key == "status":
        st = DATA.get("stats", {})
        text = f"🔵 <b>وضعیت ربات</b>\nنسخه: {VERSION}\nپیام‌های بررسی‌شده: {st.get('messages', 0)}\nموارد مسدودشده: {st.get('blocked', 0)}\nخوشامدها: {st.get('welcomes', 0)}"
    elif key == "creator":
        text = f"🟣 سازنده: <b>{AUTHOR}</b>\nارتباط: {html.escape(CREATOR_URL)}"
    else:
        text = "🌈 <b>MASIH GUARD | پنل هفت‌رنگ</b>\n🔴 مدیریت 🟠 امنیت 🟡 قوانین 🟢 راهنما 🔵 وضعیت 🟣 سازنده\n✦ by Masih Hackring"
    try:
        bot.answer_callback_query(call.id)
        bot.send_message(chat_id, text, reply_markup=main_panel() if key == "rainbow" else None, disable_web_page_preview=True)
    except Exception as e:
        log.warning("Callback failed: %s", e)

# Private messages: commands are handled above; font/proxy commands must work in private too.
@bot.message_handler(func=lambda m: m.chat.type == "private" and bool(m.text) and not m.text.startswith("/"), content_types=["text"])
def private_text(message):
    text = message.text.strip()
    if re.match(r"^(?:فونت|font)(?:\s|$)", text, re.I):
        handle_font_command(message, text)
        return
    if re.fullmatch(r"پروکسی|proxy", text, re.I):
        handle_proxy(message)
        return
    if AI_API_KEY:
        try:
            r = requests.post(AI_BASE_URL, headers={"Authorization": f"Bearer {AI_API_KEY}", "Content-Type": "application/json", "HTTP-Referer": "https://t.me/", "X-Title": BOT_NAME}, json={"model": AI_MODEL, "messages": [{"role": "system", "content": "تو دستیار فارسی‌زبان مودب MASIH GUARD هستی. پاسخ کوتاه و امن بده."}, {"role": "user", "content": text}]}, timeout=25)
            if r.ok:
                answer = r.json()["choices"][0]["message"]["content"].strip()
                send_long(message.chat.id, html.escape(answer), message.message_id)
                return
        except Exception as e:
            log.warning("AI request failed: %s", e)
    bot.reply_to(message, "سلام! 🌈 برای امکانات، /help رو بزن. برای فونت هر اسم یا متن بنویس «فونت اسم دلخواه» و برای فهرست پروکسی بنویس «پروکسی».")

# Group welcome and moderation filter. Commands are handled by command handlers above.
message_times = defaultdict(deque)
last_messages = {}

@bot.message_handler(content_types=["new_chat_members"])
def welcome_members(message):
    cfg = settings(message.chat.id)
    if not cfg.get("welcome_enabled", True):
        return
    for user in message.new_chat_members or []:
        if user.id == bot.get_me().id:
            continue
        name = display_name(user)
        group = html.escape(message.chat.title or "گروه")
        template = cfg.get("welcome_text", DEFAULT_SETTINGS["welcome_text"])
        try:
            out = template.format(name=name, group=group)
        except Exception:
            out = f"سلام {name} به گروه: {group} خوش اومدی! 🍻💜\n━━━ 🛡️ MASIH GUARD ━━━\n〰️ توسط: Masih Hackring"
        bot.send_message(message.chat.id, out, disable_web_page_preview=True)
        DATA["stats"]["welcomes"] = DATA["stats"].get("welcomes", 0) + 1
    save_data()

@bot.message_handler(content_types=["text", "photo", "video", "document", "animation", "audio", "voice", "video_note", "sticker"])
def group_moderation(message):
    if message.chat.type not in ("group", "supergroup") or not message.from_user:
        return
    if message.from_user.is_bot or is_admin(message.chat.id, message.from_user.id):
        return
    text = message.text or message.caption or ""
    cfg = settings(message.chat.id)
    DATA["stats"]["messages"] = DATA["stats"].get("messages", 0) + 1

    # Commands and direct font/proxy triggers in groups.
    if text and re.match(r"^(?:فونت|font)(?:\s|$)", text.strip(), re.I):
        handle_font_command(message, text.strip())
        return
    if text and re.fullmatch(r"پروکسی|proxy", text.strip(), re.I):
        handle_proxy(message)
        return

    # Anti-spam: rapid repeated messages are muted and reported using the requested format.
    now = time.time()
    uid_key = f"{message.chat.id}:{message.from_user.id}"
    q = message_times[uid_key]
    q.append(now)
    window = int(cfg.get("spam_window", 8))
    while q and now - q[0] > window:
        q.popleft()
    normalized = re.sub(r"\s+", " ", text).strip().lower()
    repeated = normalized and last_messages.get(uid_key) == normalized
    last_messages[uid_key] = normalized
    spam = cfg.get("anti_spam", True) and len(q) > int(cfg.get("max_messages", 6))
    duplicate = cfg.get("anti_duplicate", True) and repeated and len(normalized) > 3
    link = cfg.get("anti_link", True) and bool(re.search(r"(?:https?://|www\.|t\.me/|telegram\.me/)", text, re.I))
    badword = cfg.get("badword_filter", False) and any(w in text.lower() for w in cfg.get("bad_words", []))
    media_locked = cfg.get("lock_media", False) and message.content_type in ("photo", "video", "document", "animation", "audio", "voice", "video_note", "sticker")

    if spam or duplicate:
        try:
            try_delete(message)
            mute_user(message.chat.id, message.from_user.id, int(cfg.get("mute_seconds", 60)))
            DATA["stats"]["blocked"] = DATA["stats"].get("blocked", 0) + 1
            save_data()
            # This report is triggered by spam/repeated-message rules; it does not claim to identify every tabchi account.
            bot.send_message(message.chat.id,
                f"〰️ کاربر {display_name(message.from_user)} در لیست تبچی بود !\n"
                "🎖 وضعیت کاربر : سکوت در گروه\n"
                "━━━ 💢 MASIH GUARD 〰️ ━━━\n〰️ توسط : Masih Hackring")
        except Exception as e:
            log.warning("Anti-spam action failed: %s", e)
        return
    if link or badword or media_locked:
        try:
            if try_delete(message):
                DATA["stats"]["blocked"] = DATA["stats"].get("blocked", 0) + 1
                save_data()
                reason = "ارسال لینک" if link else "کلمات ممنوعه" if badword else "ارسال رسانه در حالت قفل"
                bot.send_message(message.chat.id, f"⚠️ {mention(message.from_user)} پیام حذف شد.\n📝 دلیل: {reason}\n━━━ 💢 MASIH GUARD 〰️ ━━━")
        except Exception as e:
            log.warning("Filter action failed: %s", e)

@app.get("/")
def home():
    return f"{BOT_NAME} v{VERSION} is running | by {AUTHOR}", 200

@app.get("/health")
def health():
    return jsonify({"ok": True, "bot": BOT_NAME, "version": VERSION}), 200


def run_web():
    app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False)


def run_bot():
    while True:
        try:
            log.info("Starting %s v%s", BOT_NAME, VERSION)
            try:
                bot.remove_webhook()
            except Exception:
                pass
            bot.infinity_polling(skip_pending=True, timeout=30, long_polling_timeout=25, allowed_updates=["message", "callback_query"])
        except Exception as e:
            log.exception("Polling stopped: %s", e)
            time.sleep(5)

load_data()
threading.Thread(target=run_web, daemon=True).start()
run_bot()
