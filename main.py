
# -*- coding: utf-8 -*-
"""مدیریت گروه | 𝑴𝒂𝒔𝒊𝒉 𝑯𝒂𝒄𝒌𝒆𝒓𝒊𝒏𝒈 — single-file Telegram group management bot."""
import os, re, json, time, random, threading, io, urllib.request, urllib.error, html, socket, shutil
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, quote
from datetime import datetime, date
try:
    from zoneinfo import ZoneInfo
except ImportError:  # Python < 3.9 fallback
    ZoneInfo = None
import telebot
from telebot import types

# ---------------- Configuration ----------------
# FadeHost uses TELEGRAM_BOT_TOKEN; prefer it so a stale BOT_TOKEN cannot override it.
BOT_TOKEN = (os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("BOT_TOKEN") or "").strip()
OWNER_ID = int(os.getenv("OWNER_ID", "8620924698"))
DATA_FILE = os.getenv("DATA_FILE", "masih_guard_data.json")
AI_API_KEY = os.getenv("AI_API_KEY", "").strip()
AI_BASE_URL = os.getenv("AI_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
AI_MODEL = os.getenv("AI_MODEL", "openai/gpt-4o-mini").strip()
CARD_NUMBER = os.getenv("CARD_NUMBER", "").strip()
CARD_HOLDER = os.getenv("CARD_HOLDER", "").strip()
WEBSITE_URL = os.getenv("WEBSITE_URL", "https://masihollah00.github.io/neon-portfolio/").strip()
CHANNEL_URL = os.getenv("CHANNEL_URL", "https://t.me/IRHACK_APP33").strip()
OWNER_CONTACT_URL = os.getenv("OWNER_CONTACT_URL", "https://t.me/Ma3ih01").strip()
BRAND, VERSION = "مدیریت گروه | 𝑴𝒂𝒔𝒊𝒉 𝑯𝒂𝒄𝒌𝒆𝒓𝒊𝒏𝒈", "نسخهٔ پیشرفته"
TIMEZONE_NAME = os.getenv("TIMEZONE", "Asia/Tehran").strip() or "Asia/Tehran"
if not BOT_TOKEN:
    raise RuntimeError(
        "توکن ربات تنظیم نشده است؛ در Environment هاست متغیر TELEGRAM_BOT_TOKEN را با توکن کامل BotFather پر کن."
    )
if ":" not in BOT_TOKEN:
    raise RuntimeError(
        "قالب توکن ربات معتبر نیست؛ مقدار TELEGRAM_BOT_TOKEN در Environment باید توکن کامل BotFather و شامل ':' باشد. مقدار توکن در لاگ چاپ نمی‌شود."
    )

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML", threaded=True, num_threads=4)


def safe_reply_to(message, text, *args, **kwargs):
    """Reply normally; if Telegram says the source message is no longer replyable, send a regular message instead."""
    try:
        return bot.reply_to(message, text, *args, **kwargs)
    except Exception as reply_error:
        error_text = str(reply_error).casefold()
        if "message to be replied not found" not in error_text and "reply message not found" not in error_text:
            raise
        try:
            return bot.send_message(message.chat.id, text, *args, **kwargs)
        except Exception as send_error:
            print("Safe reply fallback failed:", repr(send_error))
            raise
LOCK = threading.RLock()
GROUP_ADMIN_CACHE = {}  # (chat_id, user_id) -> (monotonic expiry, bool)
FORCE_JOIN_CACHE = {}  # (chat_id, user_id) -> (monotonic expiry, missing channel rows)
ENTRY_GATE_NOTICE_CACHE = {}  # (chat_id, user_id) -> monotonic expiry
GROUP_ADMIN_CACHE_TTL = 15
WAITING, GAMES, PANEL_CURRENT, PANEL_HISTORY = {}, {}, {}, {}
GAME_CYCLES = {}
BOT_USERNAME = ""
BOT_ID = 0
STARTED_AT = time.time()

DEFAULT_GROUP = {
    "anti_link": True, "anti_ads": True, "anti_tapchi": True, "anti_spam": True, "anti_repeat": True, "anti_raid_on": False, "raid_mode_until": 0,
    "anti_forward": False, "media_lock": False, "lock_mentions": False, "lock_hashtags": False, "lock_usernames": False, "welcome_on": True,
    "farewell_on": False, "join_approval": False, "bad_words": [], "whitelist": [],
    "force_join_on": False, "force_join_channels": [], "force_add_on": False, "force_add_count": 3, "force_add_credits": {}, "invite_links": [],
    "warn_limit": 3, "lock_photos": False, "lock_videos": False, "lock_files": False,
    "lock_stickers": False, "lock_voice": False, "lock_video_notes": False,
    "rules": "احترام به اعضا الزامی است.",
    "welcome_text": "سلام {name}، به گروه خوش آمدی!", "farewell_text": "خداحافظ {name}",
    "auto_replies": {}, "custom_commands": {}, "phone_filter": False,
    "smart_security": True, "quiet_hours_on": False, "quiet_start": "23:00", "quiet_end": "07:00",
    "welcome_image": "", "welcome_delete_seconds": 0, "captcha_on": False, "notes": {}
}
DEFAULT_DATA = {
    "groups": {}, "warnings": {}, "logs": [], "proxies": [], "customers": {}, "moderation_lists": {}, "message_history": {},
    "tickets": {}, "points": {}, "seen": {}, "stats": {"messages": 0, "blocked": 0,
    "warns": 0, "joins": 0, "tickets": 0, "start_commands": 0, "users_started": 0},
    "settings": {"smart_security": True},
    "bot_settings": {
        "public_features": "", "channel_url": "https://t.me/IRHACK_APP33",
        "website_url": "https://neon-portfolio-7vhj.onrender.com",
        "referral_reward_toman": 5000,
        "subscription_packages": [[30, 40000], [60, 80000], [90, 120000]]
    },
    "users": {}, "referrals": {}, "subscriptions": {}, "transactions": {}, "captchas": {}, "join_times": {}, "force_add_credits": {}, "force_invite_links": {}, "tapchi_violations": {},
    "subscription_requests": {}, "payout_requests": {},
    "last_daily": {}, "group_licenses": {}, "join_requests": {}, "group_requests": {},
    "group_stats": {}, "active_members": {}, "activity_stats": {}, "manager_roles": {}, "bot_admins": {}
}

def clone(obj): return json.loads(json.dumps(obj, ensure_ascii=False))
def esc(value): return html.escape(str(value or ""), quote=False)
def local_now():
    """Consistent timezone-aware clock for welcome messages and audit timestamps."""
    if ZoneInfo:
        try:
            return datetime.now(ZoneInfo(TIMEZONE_NAME))
        except Exception:
            pass
    return datetime.now().astimezone()

def persian_digits(value):
    return str(value).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))

def now_text(): return local_now().strftime("%Y-%m-%d %H:%M:%S")
def today(): return local_now().date().isoformat()

def load_data():
    """Load persistent data; preserve a damaged file for manual recovery instead of overwriting it."""
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("The root of the data file must be a JSON object")
    except FileNotFoundError:
        data = clone(DEFAULT_DATA)
    except (OSError, ValueError, TypeError) as load_error:
        # Never silently discard a broken JSON file: preserve a timestamped copy first.
        try:
            if os.path.isfile(DATA_FILE) and os.path.getsize(DATA_FILE) <= 25 * 1024 * 1024:
                stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
                corrupt_copy = f"{DATA_FILE}.corrupt-{stamp}.bak"
                shutil.copy2(DATA_FILE, corrupt_copy)
                print(f"WARNING: invalid data file preserved as {corrupt_copy}: {load_error!r}")
            else:
                print(f"WARNING: could not preserve invalid data file: {load_error!r}")
        except Exception as backup_error:
            print("WARNING: failed to preserve invalid data file:", repr(backup_error))
        data = clone(DEFAULT_DATA)
    for k, v in DEFAULT_DATA.items():
        if k not in data: data[k] = clone(v)
    for k, v in DEFAULT_DATA["stats"].items(): data["stats"].setdefault(k, v)
    for k, v in DEFAULT_DATA["settings"].items(): data["settings"].setdefault(k, v)
    data.setdefault("group_licenses", {})
    data.setdefault("join_requests", {})
    data.setdefault("group_requests", {})
    data.setdefault("moderation_lists", {})
    data.setdefault("message_history", {})
    data.setdefault("group_requests", {})
    data.setdefault("group_stats", {})
    data.setdefault("active_members", {})
    data.setdefault("manager_roles", {})
    data.setdefault("bot_admins", {})
    data.setdefault("subscription_requests", {})
    data.setdefault("payout_requests", {})
    # Migration away from the retired diamond economy. Old diamond balances and
    # histories are deliberately discarded instead of being misrepresented as Toman.
    if isinstance(data.get("users"), dict):
        for _user in data["users"].values():
            if isinstance(_user, dict):
                _user.pop("diamonds", None)
                _user.setdefault("wallet_toman", 0)
                _user.pop("last_daily", None)
                _user.pop("last_luck", None)
    if isinstance(data.get("transactions"), dict):
        # Clear only legacy diamond rows once; preserve new Toman transaction history.
        for _key, _rows in list(data["transactions"].items()):
            if isinstance(_rows, list) and any(isinstance(_row, dict) and "amount_toman" not in _row for _row in _rows):
                data["transactions"][_key] = []
    for k, v in DEFAULT_DATA.items():
        if isinstance(v, dict) and not isinstance(data.get(k), dict): data[k] = clone(v)
        if isinstance(v, list) and not isinstance(data.get(k), list): data[k] = clone(v)
    return data

DATA = load_data()

def save_data():
    """Atomically persist bot state so interrupted writes do not truncate the main JSON file."""
    with LOCK:
        parent = os.path.dirname(os.path.abspath(DATA_FILE))
        os.makedirs(parent, exist_ok=True)
        tmp = DATA_FILE + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(DATA, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, DATA_FILE)
        except Exception:
            try:
                if os.path.exists(tmp):
                    os.remove(tmp)
            except OSError:
                pass
            raise

def add_log(action, chat_id="", user_id="", detail=""):
    with LOCK:
        DATA["logs"].append({"time": now_text(), "action": str(action), "chat_id": str(chat_id),
                             "user_id": str(user_id), "detail": str(detail)[:250]})
        DATA["logs"] = DATA["logs"][-800:]
        save_data()

def is_owner(uid): return int(uid or 0) == OWNER_ID

def is_bot_admin(uid):
    """Delegated sales admins can activate group licenses, but never own the bot."""
    if is_owner(uid):
        return True
    return str(int(uid or 0)) in DATA.setdefault("bot_admins", {})

def ensure_user(uid, username="", first_name=""):
    key = str(int(uid))
    with LOCK:
        user = DATA["users"].setdefault(key, {"wallet_toman": 0, "username": "", "first_name": "", "joined": now_text()})
        # Remove legacy currency fields on every access as a final migration guard.
        user.pop("diamonds", None)
        user.setdefault("wallet_toman", 0)
        if username: user["username"] = username
        if first_name: user["first_name"] = first_name
        DATA["transactions"].setdefault(key, [])
    return user

def wallet(uid):
    return max(0, int(ensure_user(uid).get("wallet_toman", 0)))

def transaction(uid, amount_toman, reason):
    key = str(int(uid))
    amount_toman = int(amount_toman)
    with LOCK:
        user = ensure_user(uid)
        new_balance = int(user.get("wallet_toman", 0)) + amount_toman
        if new_balance < 0: return False
        user["wallet_toman"] = new_balance
        history = DATA["transactions"].setdefault(key, [])
        history.append({"time": now_text(), "amount_toman": amount_toman,
                        "reason": str(reason)[:120], "balance_toman": new_balance})
        DATA["transactions"][key] = history[-100:]
        save_data()
    return True

def get_group_settings(chat_id):
    key = str(chat_id)
    if key not in DATA["groups"]: DATA["groups"][key] = clone(DEFAULT_GROUP)
    settings = DATA["groups"][key]
    for k, v in DEFAULT_GROUP.items(): settings.setdefault(k, clone(v))
    # Core onboarding behavior: welcome messages cannot be disabled from panel or old data.
    settings["welcome_on"] = True
    return settings

def group_license_status(chat_id):
    """Return (active, license_record); a license can be permanent or time-limited."""
    record = DATA.setdefault("group_licenses", {}).get(str(chat_id), {})
    if not record or not record.get("approved", False):
        return False, record
    expires = str(record.get("expires", "") or "").strip()
    if not expires:
        return True, record
    try:
        active = datetime.strptime(expires, "%Y-%m-%d %H:%M:%S") > datetime.now()
    except ValueError:
        active = False
    return active, record

def is_group_licensed(chat_id):
    return group_license_status(chat_id)[0]

def support_contact_markup():
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("📩 ارتباط با پشتیبان نصب", url=f"tg://user?id={OWNER_ID}"))
    return kb

def group_install_message(chat_id, title="این گروه"):
    return ("🛡️ <b>فعال‌سازی MASIH GUARD</b>\n━━━━━━━━━━━━━━━━━━\n"
            f"برای استفاده از امکانات مدیریتی در «{esc(title)}»، باید مجوز نصب از پشتیبانی دریافت شود.\n\n"
            "📩 برای بررسی و فعال‌سازی، با پشتیبان ربات ارتباط بگیرید.")

def bot_settings():
    """Return normalized Toman settings without overwriting valid owner configuration."""
    settings = DATA.setdefault("bot_settings", clone(DEFAULT_DATA["bot_settings"]))
    # Remove retired economy keys, but preserve valid current Toman settings.
    for retired_key in ("daily_reward", "luck_max", "referral_reward", "shop_packages"):
        settings.pop(retired_key, None)
    for key, value in DEFAULT_DATA["bot_settings"].items():
        settings.setdefault(key, clone(value))
    settings.setdefault("referral_reward_toman", 5000)
    # Validate packages defensively. The previous implementation reset this list on
    # every call, silently discarding any customized packages from persistent data.
    packages = settings.get("subscription_packages")
    normalized_packages = []
    if isinstance(packages, list):
        for row in packages[:20]:
            if not isinstance(row, (list, tuple)) or len(row) != 2:
                continue
            try:
                days, price = int(row[0]), int(row[1])
            except (TypeError, ValueError, OverflowError):
                continue
            if 1 <= days <= 3650 and 0 <= price <= 2_000_000_000:
                pair = [days, price]
                if pair not in normalized_packages:
                    normalized_packages.append(pair)
    if not normalized_packages:
        normalized_packages = clone(DEFAULT_DATA["bot_settings"]["subscription_packages"])
    settings["subscription_packages"] = normalized_packages
    try:
        reward = int(settings.get("referral_reward_toman", 5000))
    except (TypeError, ValueError, OverflowError):
        reward = 5000
    settings["referral_reward_toman"] = min(100_000_000, max(0, reward))
    return settings

def start_welcome_text(user):
    """Compact but broad, honest feature catalogue for the private /start screen."""
    raw_name = " ".join(x for x in [getattr(user, "first_name", ""), getattr(user, "last_name", "")] if x).strip() or "دوست عزیز"
    mention = f'<a href="tg://user?id={int(user.id)}">{esc(raw_name)}</a>'
    custom = str(bot_settings().get("public_features", "") or "").strip()
    if custom:
        marker = "__MASIH_CLICKABLE_USER_MENTION__"
        safe_custom = esc(custom.replace("{name}", marker)).replace(marker, mention)
        return safe_custom + "\n\n" + PUBLIC_FEATURES + "\n\n📚 فرمان‌ها: /help"
    return (
        f"👋 سلام {mention}؛ خوش اومدی!\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🛡️ <b>مدیریت گروه | 𝑴𝒂𝒔𝒊𝒉 𝑯𝒂𝒄𝒌𝒆𝒓𝒊𝒏𝒈</b>\n"
        "<i>امنیت، مدیریت هوشمند و ابزارهای کاربردی تلگرام</i>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🔐 <b>امنیت گروه:</b> ضدلینک، ضدتبلیغ، ضداسپم، ضدتکرار، کنترل فوروارد و رسانه، فیلتر شماره و کلمات، کپچا و ضدیورش؛ فعال‌سازی تابع تنظیمات و دسترسی‌های تلگرام است.\n"
        "👥 <b>مدیریت اعضا:</b> اخطار، سکوت/رفع سکوت، بن/رفع بن، اخراج، اطلاعات کاربر، شناسه و مقام، شمارش دعوت، سنجاق/لغو سنجاق و حذف پیام.\n"
        "👋 <b>ورود و خروج:</b> خوشامد و خداحافظی قابل‌تنظیم، قوانین، جوین اجباری کانال، اد اجباری با لینک دعوت اختصاصی و کنترل ضدیورش.\n"
        "🧰 <b>مدیریت و تنظیمات:</b> پنل گروه، تنظیمات امنیت، فیلتر کلمات، یادداشت‌ها، پاسخ خودکار، ساعت سکوت، لینک گروه، پاک‌سازی پیام‌های اخیر و گزارش آماری.\n"
        "📊 <b>آمار:</b> اطلاعات گروه و اعضا، آمار فعالیت ۲۴ ساعته، کاربران فعال، مدیران و گزارش قابل‌خروجی در بخش‌های پشتیبانی‌شده.\n"
        "🧪 <b>ابزارهای کاربردی:</b> تاریخ و ساعت، اکو متن، بررسی فایل از نظر نوع/اندازه و اطلاعات هش؛ این بررسی به‌تنهایی اسکن ضدویروس نیست.\n"
        "🧠 <b>هوش مصنوعی:</b> راهنمایی و پاسخ به سؤال‌ها؛ امکانات وابسته به کلید API فقط در صورت تنظیم سرویس فعال‌اند.\n"
        "🎨 <b>ابزارهای جانبی:</b> فونت‌های متنی، بازی‌ها، جدول امتیازها، تیکت پشتیبانی و فهرست پروکسی‌های ذخیره‌شده.\n"
        "💳 <b>حساب و خدمات:</b> کیف پول تومانی، تاریخچه تراکنش، اشتراک، دعوت دوستان، درخواست برداشت و پنل پشتیبانی. پرداخت/برداشت تابع بررسی و تنظیمات موجود است.\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "⚡ <b>شروع سریع</b>\n"
        "/help راهنمای کامل | /panel پنل | /profile پروفایل و کیف پول | /stats آمار | /id شناسه | /ping پاسخ‌گویی | /health سلامت | /ai سؤال | /game بازی‌ها | /top امتیازها | /cancel لغو\n"
        "👥 <b>در گروه:</b> «پنل»، «راهنما»، «قوانین»، «آمار» یا /mylink (در صورت فعال بودن اد اجباری). برای اقدام روی عضو، فرمان مدیریتی را روی پیام او ریپلای کن.\n"
        "🔒 فرمان‌های مدیریتی فقط با مجوز لازم اجرا می‌شوند؛ امکانات خارجی یا وابسته به دسترسی ممکن است نیاز به تنظیم جداگانه داشته باشند.\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "👇 از منوی زیر بخش موردنظرت را انتخاب کن."
    )


def group_start_guide(chat_title="گروه"):
    return (
        f"🛡️ <b>مدیریت گروه | 𝑴𝒂𝒔𝒊𝒉 𝑯𝒂𝒄𝒌𝒆𝒓𝒊𝒏𝒈</b>\n"
        f"📍 راهنمای سریع: {esc(chat_title or 'گروه')}\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🔐 <b>امنیت:</b> ضدلینک، ضدتبلیغ، ضداسپم/تکرار، کنترل فوروارد و رسانه، فیلتر کلمات/شماره، کپچا و ضدیورش (طبق تنظیمات فعال).\n"
        "👥 <b>اعضا:</b> اخطار، سکوت/رفع سکوت، اخراج، بن/رفع بن، اطلاعات و شناسه، شمارش دعوت، سنجاق/لغو سنجاق و حذف پیام.\n"
        "👋 <b>ورود:</b> خوشامد/خداحافظی، قوانین، جوین اجباری کانال و اد اجباری با لینک اختصاصی.\n"
        "⚙️ <b>مدیریت:</b> پنل و تنظیمات، فیلتر کلمات، یادداشت، پاسخ خودکار، ساعت سکوت، لینک گروه و پاک‌سازی پیام‌های اخیر.\n"
        "📊 <b>آمار:</b> /groupinfo /members /admins /activity /stats24 /topactive /exportstats\n"
        "🧰 <b>ابزارها:</b> /time /date /echo متن /id /ping /help\n"
        "👮 <b>فرمان‌های عضو</b> (روی پیام او ریپلای کن): /warn /mute /unmute /kick /ban /unban /delete /pin /unpin\n"
        "🛠️ <b>تنظیم مدیر:</b> /setrules /setwelcome /setfarewell /filteradd /filterdel /filterlist /noteadd /notedel /setquiet /cleanlast\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "📢 اگر جوین اجباری فعال است، عضو کانال‌های تعیین‌شده شو و عضویت را بررسی کن. برای لینک دعوت در حالت اد اجباری از /mylink استفاده کن.\n"
        "⚠️ ربات باید مدیر گروه باشد و مجوز لازم را داشته باشد؛ اقدام مدیریتی فقط برای مدیر مجاز همان گروه انجام می‌شود. برای فهرست کامل‌تر: /help"
    )


def public_features_text():
    custom = str(bot_settings().get("public_features", "") or "").strip()
    return esc(custom) if custom else PUBLIC_FEATURES

def configured_url(key, fallback):
    value = str(bot_settings().get(key, "") or fallback).strip()
    return value if value.startswith(("https://", "http://")) else fallback


def get_game_url():
    """Resolve the browser-game URL without accidentally creating /game/game."""
    explicit = (os.getenv("WEB_GAME_URL") or "").strip()
    if explicit:
        # WEB_GAME_URL may be either the bot site's root or a direct game URL.
        # Preserve a deliberate non-root path; only add /game to a root URL.
        explicit = explicit.rstrip("/")
        if not explicit.lower().startswith("https://"):
            return ""
        parsed = urlparse(explicit)
        path = (parsed.path or "").rstrip("/")
        if not path:
            return explicit + "/game"
        return explicit if path.lower().endswith("/game") else explicit

    base = (os.getenv("PUBLIC_BASE_URL") or os.getenv("PUBLIC_URL") or
            os.getenv("APP_URL") or os.getenv("FADEHOST_PUBLIC_URL") or
            os.getenv("SERVICE_URL") or os.getenv("RENDER_EXTERNAL_URL") or "").strip().rstrip("/")
    if not base:
        # Some hosts expose a bare public domain rather than a fully-qualified URL.
        bare_domain = (os.getenv("RAILWAY_PUBLIC_DOMAIN") or
                       os.getenv("KOYEB_PUBLIC_DOMAIN") or "").strip().strip("/")
        if bare_domain:
            base = bare_domain if "://" in bare_domain else "https://" + bare_domain
    if base.startswith("https://"):
        return base + "/game"
    return ""

def group_admin_status(chat_id, user_id):
    """Return True/False for a confirmed role, or None if Telegram lookup failed.

    A short cache avoids one Telegram API request for every group message. The
    unknown state is kept separate so security filters do not punish an admin
    merely because Telegram is temporarily unreachable.
    """
    if not user_id:
        return False
    key = (int(chat_id), int(user_id))
    now = time.monotonic()
    cached = GROUP_ADMIN_CACHE.get(key)
    if cached and cached[0] > now:
        return cached[1]
    try:
        member = bot.get_chat_member(key[0], key[1])
        result = getattr(member, "status", "") in ("administrator", "creator")
        GROUP_ADMIN_CACHE[key] = (now + GROUP_ADMIN_CACHE_TTL, result)
        if len(GROUP_ADMIN_CACHE) > 10000:
            for cache_key, (expiry, _) in list(GROUP_ADMIN_CACHE.items()):
                if expiry <= now:
                    GROUP_ADMIN_CACHE.pop(cache_key, None)
            if len(GROUP_ADMIN_CACHE) > 12000:
                GROUP_ADMIN_CACHE.clear()
        return result
    except Exception:
        # Do not cache failures: permissions may become available on the next check.
        return None

def is_group_admin(chat_id, user_id):
    """Require confirmed Telegram admin/creator status in this exact group."""
    return group_admin_status(chat_id, user_id) is True

def bot_has_group_permission(chat_id, permission):
    """Check the bot's current Telegram permission before enabling dependent features."""
    try:
        me = bot.get_me()
        member = bot.get_chat_member(chat_id, me.id)
        status = getattr(member, "status", "")
        if status == "creator":
            return True
        if status != "administrator":
            return False
        return bool(getattr(member, permission, False))
    except Exception:
        return False

# ---------------- Menus ----------------
SECTIONS = {
    "security":"🛡 امنیت گروه", "members":"👥 مدیریت اعضا", "settings":"⚙️ تنظیمات گروه",
    "welcome":"👋 خوشامد و خداحافظی", "rules":"📜 قوانین و پاسخ خودکار",
    "referrals":"👥 کیف پول تومانی و اشتراک",
    "stats":"📊 آمار و گزارش", "customers":"💼 مشتریان و اشتراک",
    "tickets":"🎫 تیکت پشتیبانی", "ai":"🧠 هوش مصنوعی",
    "backup":"💾 پشتیبان‌گیری", "daily":"📅 گزارش روزانه",
    "smart":"🧩 امنیت هوشمند", "status":"🚀 وضعیت ربات",
    "bot_settings":"🎛️ تنظیمات عمومی ربات", "licenses":"🛡️ مجوز نصب گروه‌ها", "full_control":"🎛️ کنترل کامل ربات", "admins":"👮 مدیریت ادمین‌های ربات"
}

PUBLIC_FEATURES = (
    "🌌 <b>مدیریت گروه | 𝑴𝒂𝒔𝒊𝒉 𝑯𝒂𝒄𝒌𝒆𝒓𝒊𝒏𝒈</b>\n"
    "<i>امنیت گروه، مدیریت هوشمند و ابزارهای کاربردی تلگرام</i>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "🛡️ <b>امنیت:</b> ضدلینک، ضدتبلیغ، ضداسپم، ضدتکرار، کنترل فوروارد و رسانه، فیلتر شماره، کپچا و ضدیورش.\n"
    "👥 <b>مدیریت اعضا:</b> اخطار، سکوت/رفع سکوت، بن/رفع بن، اخراج، گزارش، سنجاق و پاک‌سازی پیام‌ها.\n"
    "👋 <b>ورود و خروج:</b> خوشامد و خداحافظی، متن و تصویر خوشامد، تأیید ورود و قوانین گروه.\n"
    "⚙️ <b>ابزار مدیریت:</b> پاسخ خودکار، فرمان اختصاصی، یادداشت، اطلاعیه، آمار و گزارش فعالیت.\n"
    "🧠 <b>دستیار هوشمند:</b> راهنمای امکانات و کمک به فرمان‌های پشتیبانی‌شده؛ اجرای مدیریت با بررسی دسترسی.\n"
    "🎨 <b>ابزارهای جانبی:</b> فونت‌های متنی، پروکسی‌های ذخیره‌شده، تیکت پشتیبانی و بازی‌ها.\n"
    "💳 <b>حساب کاربری:</b> کیف پول تومانی، تراکنش‌ها، دعوت دوستان، درخواست برداشت و بسته‌های اشتراک.\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "📌 <b>نکته:</b> فعال بودن هر قابلیت به تنظیمات، مجوز نصب و دسترسی‌های تلگرام بستگی دارد. پاداش دعوت و اشتراک طبق تنظیمات فعلی و پس از بررسی مربوطه ثبت می‌شوند.\n"
    "👇 برای ادامه، یکی از گزینه‌های منو را انتخاب کن."
)

def public_keyboard():
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.row(types.InlineKeyboardButton("💳 کیف پول تومانی", callback_data="user:wallet"),
           types.InlineKeyboardButton("🛒 خرید اشتراک", callback_data="user:shop"))
    kb.row(types.InlineKeyboardButton("👥 زیرمجموعه‌گیری", callback_data="user:referrals"),
           types.InlineKeyboardButton("🧾 تراکنش‌ها", callback_data="user:transactions"))
    kb.row(types.InlineKeyboardButton("💸 درخواست برداشت از کیف پول", callback_data="user:payout"))
    kb.row(types.InlineKeyboardButton("🎫 پشتیبانی", callback_data="user:ticket"),
           types.InlineKeyboardButton("🧠 هوش مصنوعی", callback_data="user:ai"))
    kb.row(types.InlineKeyboardButton("👨‍💻 پیام به سازنده", url=OWNER_CONTACT_URL),
           types.InlineKeyboardButton("🌐 وب‌سایت", url=configured_url("website_url", WEBSITE_URL)))
    return kb

def owner_start_keyboard():
    """Private start menu with a direct, owner-only management entry."""
    kb = public_keyboard()
    if kb.keyboard and kb.keyboard[-1]:
        kb.keyboard.append([types.InlineKeyboardButton("👑 پنل مدیریت مالک", callback_data="panel:home")])
    return kb

def main_keyboard():
    kb = types.InlineKeyboardMarkup(row_width=2)
    palette = ["🔴", "🟠", "🟡", "🟢", "🔵", "🟣", "🌈"]
    items = list(SECTIONS.items())
    for i in range(0, len(items), 2):
        row = []
        for j, (key, title) in enumerate(items[i:i+2]):
            row.append(types.InlineKeyboardButton(f'{palette[(i+j) % len(palette)]} {title}',
                                                   callback_data='panel:'+key))
        kb.row(*row)
    kb.row(types.InlineKeyboardButton("🌐 وب‌سایت رسمی", url=configured_url("website_url", WEBSITE_URL)))
    kb.row(types.InlineKeyboardButton("👨‍💻 پیام به سازنده", url=OWNER_CONTACT_URL))
    return kb

def section_keyboard(section):
    kb = types.InlineKeyboardMarkup(row_width=1)
    choices = {
      "security":[("🔗 قفل لینک","toggle:anti_link"),("📢 ضد تبلیغ","toggle:anti_ads"),("🚫 قفل تبچی","toggle:anti_tapchi"),("🚫 ضد اسپم","toggle:anti_spam"),("🔁 ضد پیام تکراری","toggle:anti_repeat"),("↪️ ضد فوروارد","toggle:anti_forward"),("🖼 قفل رسانه","toggle:media_lock"),("🔗 قفل لینک و نام کاربری","toggle:anti_link"),("📵 فیلتر شماره تماس","toggle:phone_filter"),("🖼 قفل عکس","toggle:lock_photos"),("🎞 قفل فیلم","toggle:lock_videos"),("📁 قفل فایل","toggle:lock_files"),("🎭 قفل استیکر و گیف","toggle:lock_stickers"),("🎙 قفل پیام صوتی","toggle:lock_voice"),("⭕ قفل ویدئوی گرد","toggle:lock_video_notes"),("📂 فهرست کاربران مجاز","show:whitelist"),("➕ افزودن کاربر مجاز","ask:add_whitelist"),("➖ حذف کاربر مجاز","ask:remove_whitelist"),
      ("🧠 امنیت هوشمند این گروه","toggle:group_smart_security"),("🚨 ضد یورش ورود","toggle:anti_raid_on"),("🌙 ساعت سکوت شبانه","ask:quiet_hours"),("🆔 شناسه و تنظیمات گروه","ask:group_settings")],
      "welcome":[("👋 پیام خداحافظی","toggle:farewell_on"),("🛂 تأیید خودکار ورود","toggle:join_approval"),("📢 تنظیم جوین اجباری","ask:force_join"),("➕ تنظیم اد اجباری","ask:force_add"),("✏️ تنظیم متن خوشامد","ask:welcome_text"),("✏️ تنظیم متن خداحافظی","ask:farewell_text"),
      ("🖼 تنظیم تصویر خوشامد","ask:welcome_image"),("🗑 زمان حذف خوشامد","ask:welcome_delete_seconds"),("🔐 تأیید عضو جدید (کپچا)","toggle:captcha_on")],
      "rules":[("📜 مشاهده قوانین","show:rules"),("✏️ تنظیم قوانین","ask:rules"),("💬 افزودن پاسخ خودکار","ask:auto_reply"),("🗑 حذف پاسخ خودکار","ask:delete_reply"),("🚫 افزودن کلمه ممنوع","ask:bad_word"),("🧩 افزودن فرمان اختصاصی","ask:add_custom_command"),("🗑 حذف فرمان اختصاصی","ask:delete_custom_command"),("📝 افزودن یادداشت","ask:add_note"),("🗑 حذف یادداشت","ask:delete_note"),("📋 فهرست یادداشت‌ها","show:notes"),("📣 ارسال اطلاعیه","ask:announcement")],
      "members":[(x, "ask:"+a) for x,a in [("⚠️ اخطار عضو","warn"),("🔇 سکوت عضو","mute"),("🔊 رفع سکوت","unmute"),("⛔ مسدودسازی","ban"),("✅ رفع مسدودی","unban"),("👢 اخراج عضو","kick"), ("🧹 پاک‌کردن اخطارها","clear_warnings"), ("📋 فهرست مسدودها","show:ban_list"), ("🔇 فهرست ساکت‌ها","show:mute_list"), ("🔎 اطلاعات عضو","ask:member_info")]],
      "settings":[("⚙️ تنظیم سقف اخطار","ask:warn_limit"),("📜 تنظیم قوانین","ask:rules")],
      "referrals":[("💳 آمار کیف پول تومانی","show:wallet_stats"),("👥 آمار دعوت‌ها","show:referral_stats"),("🛒 درخواست‌های اشتراک","show:subscription_requests"),("💸 درخواست‌های برداشت","show:payout_requests"),("➕ تنظیم موجودی کیف پول","ask:wallet_adjust"),("📦 بسته‌های اشتراک","show:shop")],
      "stats":[("📊 آمار ربات","show:stats"),("🧾 گزارش فعالیت","show:logs"),("📈 آمار یک گروه","ask:group_stats"),("📅 گزارش روزانه","show:daily"),("📅 گزارش هفتگی","show:weekly_report"),("🛡 وضعیت امنیت","show:security_status"),("💳 فروش و تمدید اشتراک","show:subscription_sales"),("🔎 جست‌وجوی گزارش‌ها","ask:search_logs")],
      "customers":[("➕ افزودن مشتری","ask:add_customer"),("📋 فهرست مشتریان","show:customers"),("🔎 جست‌وجوی مشتری","ask:find_customer")],
      "tickets":[("🎫 ثبت تیکت","ask:ticket"),("📋 تیکت‌ها","show:tickets")],
      "ai":[("🧠 پرسش از هوش مصنوعی","ask:ai")],
      "backup":[("💾 دریافت نسخه پشتیبان","show:backup")],
      "daily":[("📅 گزارش روزانه","show:daily")],
      "smart":[("🧩 روشن/خاموش امنیت هوشمند","toggle:smart_security")],
      "status":[("🚀 وضعیت ربات","show:status")],
      "licenses":[("➕ فعال‌سازی مجوز گروه","ask:activate_group"),("🗓 تمدید مجوز گروه","ask:extend_group"),("⛔ لغو مجوز گروه","ask:revoke_group"),("📋 فهرست گروه‌های مجاز","show:group_licenses"),("📨 درخواست‌های نصب","show:group_requests")],
      "full_control":[
        ("🔗 قفل لینک","toggle:anti_link"),("📢 قفل تبلیغات","toggle:anti_ads"),("🚫 قفل تبچی","toggle:anti_tapchi"),
        ("🚫 قفل اسپم","toggle:anti_spam"),("🔁 قفل پیام تکراری","toggle:anti_repeat"),
        ("↪️ قفل فوروارد","toggle:anti_forward"),("🖼 قفل همه رسانه‌ها","toggle:media_lock"),
        ("🏷 قفل تگ/منشن","toggle:lock_mentions"),("#️⃣ قفل هشتگ","toggle:lock_hashtags"),
        ("👤 قفل نام‌کاربری (@)","toggle:lock_usernames"),
        ("🖼 قفل عکس","toggle:lock_photos"),("🎞 قفل فیلم","toggle:lock_videos"),
        ("📁 قفل فایل","toggle:lock_files"),("🎭 قفل استیکر/گیف","toggle:lock_stickers"),
        ("🎙 قفل ویس","toggle:lock_voice"),("⭕ قفل ویدئوی گرد","toggle:lock_video_notes"),
        ("📵 فیلتر شماره تماس","toggle:phone_filter"),("🧠 امنیت هوشمند گروه","toggle:group_smart_security"),
        ("🌙 خداحافظی","toggle:farewell_on"),("🔐 کپچا","toggle:captcha_on"),("🚨 ضد یورش","toggle:anti_raid_on"),
        ("🛂 تأیید ورود","toggle:join_approval"),("🌙 تنظیم ساعت سکوت","ask:quiet_hours"),
        ("⚙️ سقف اخطار","ask:warn_limit"),("📜 تنظیم قوانین","ask:rules"),
        ("🆔 نمایش تنظیمات یک گروه","ask:group_settings")
      ],
      "admins":[
        ("➕ ثبت ادمین با @username","ask:register_bot_admin"),
        ("➖ حذف ادمین با @username","ask:remove_bot_admin"),
        ("📋 فهرست ادمین‌های ثبت‌شده","show:bot_admins")
      ],
      "bot_settings":[
        ("🎛️ کنترل کامل ربات (همه تنظیمات)","panel:full_control"),
        ("📝 متن معرفی /start","ask:public_features"),
        ("📢 تغییر لینک کانال","ask:channel_url"),
        ("🌐 تغییر لینک وب‌سایت","ask:website_url"),
        ("👥 تنظیم پاداش دعوت (تومان)","ask:referral_reward_toman"),
        ("🛒 تنظیم بسته‌های اشتراک","ask:subscription_packages"),
        ("🌐 نمایش فهرست پروکسی‌ها","show:proxies"),
        ("➕ افزودن پروکسی تلگرام","ask:add_proxy"),
        ("➖ حذف پروکسی با شماره","ask:delete_proxy"),
        ("📋 مشاهده تنظیمات فعلی","show:bot_settings")
      ]
    }
    for label, data in choices.get(section, []):
        kb.add(types.InlineKeyboardButton(label, callback_data=data))
    kb.row(types.InlineKeyboardButton("🏠 صفحهٔ اصلی پنل", callback_data="panel:home"),
           types.InlineKeyboardButton("⬅️ بازگشت", callback_data="panel:back"))
    return kb


GROUP_PANEL_PAGES = {}

GROUP_PANEL_SECTIONS = {
    "security": {
        "title": "🛡 امنیت و ضداسپم",
        "toggles": [
            ("🔗 قفل لینک", "anti_link"), ("📢 ضد تبلیغ", "anti_ads"),
            ("🚫 قفل تبچی", "anti_tapchi"), ("🚫 ضد اسپم", "anti_spam"), ("🔁 ضد تکرار", "anti_repeat"),
            ("↪️ ضد فوروارد", "anti_forward"), ("🧠 امنیت هوشمند", "smart_security"),
            ("🚨 ضد یورش", "anti_raid_on"), ("🔐 کپچا", "captcha_on"),
        ],
        "asks": [("⚙️ سقف اخطار", "warn_limit"), ("🌙 ساعت سکوت", "quiet_hours")],
    },
    "locks": {
        "title": "🔒 قفل محتوا",
        "toggles": [
            ("🖼 همه رسانه‌ها", "media_lock"), ("🏷 تگ و منشن", "lock_mentions"),
            ("#️⃣ هشتگ", "lock_hashtags"), ("👤 نام‌کاربری", "lock_usernames"),
            ("📵 شماره تماس", "phone_filter"), ("🖼 عکس", "lock_photos"),
            ("🎞 ویدئو", "lock_videos"), ("📁 فایل", "lock_files"),
            ("🎭 استیکر و گیف", "lock_stickers"), ("🎙 ویس", "lock_voice"),
            ("⭕ ویدئوی گرد", "lock_video_notes"),
        ],
        "asks": [],
    },
    "welcome": {
        "title": "👋 ورود، خوشامد و قوانین",
        "toggles": [
            ("🚪 پیام خداحافظی", "farewell_on"),
            ("🛂 تأیید ورود", "join_approval"),
        ],
        "asks": [
            ("✏️ متن خوشامد", "welcome_text"), ("✏️ متن خداحافظی", "farewell_text"),
            ("📜 تنظیم قوانین", "rules"), ("🖼 تصویر خوشامد", "welcome_image"),
            ("🧹 زمان حذف خوشامد", "welcome_delete_seconds"),
        ],
    },
    "entry": {
        "title": "📢 جوین و اد اجباری",
        "toggles": [],
        "asks": [],
    },
    "automation": {
        "title": "🤖 پاسخ‌ها و ابزارهای خودکار",
        "toggles": [],
        "asks": [
            ("💬 افزودن پاسخ خودکار", "auto_reply"), ("🧹 حذف پاسخ خودکار", "delete_reply"),
            ("🚫 افزودن کلمه ممنوع", "bad_word"), ("🌙 تنظیم ساعت سکوت", "quiet_hours"),
            ("➕ فرمان سفارشی", "add_custom_command"), ("➖ حذف فرمان سفارشی", "delete_custom_command"),
            ("📝 افزودن یادداشت", "add_note"), ("🗑 حذف یادداشت", "delete_note"),
        ],
    },
    "overview": {
        "title": "📊 آمار و وضعیت",
        "toggles": [],
        "asks": [],
    },
    "help": {
        "title": "📚 راهنما",
        "toggles": [],
        "asks": [],
    },
}

def group_panel_keyboard(chat_id, user_id=None, section="home"):
    """Paginated group panel; admin actions are displayed only to confirmed group admins."""
    settings = get_group_settings(chat_id)
    can_manage = bool(user_id is not None and is_group_admin(chat_id, user_id))
    kb = types.InlineKeyboardMarkup(row_width=2)
    if section == "home":
        rows = [
            ("🛡 امنیت و ضداسپم", "security"), ("🔒 قفل محتوا", "locks"),
            ("👋 ورود و خوشامد", "welcome"), ("📢 جوین و اد اجباری", "entry"),
            ("🤖 پاسخ‌ها و خودکار", "automation"), ("📊 آمار و وضعیت", "overview"),
            ("📚 راهنمای کامل", "help"),
        ]
        for label, page in rows:
            kb.add(types.InlineKeyboardButton(label, callback_data=f"gpanel:page:{page}"))
    elif section in GROUP_PANEL_SECTIONS:
        cfg = GROUP_PANEL_SECTIONS[section]
        for label, key in cfg.get("toggles", []):
            enabled = bool(settings.get(key, False))
            status = "🟢" if enabled else "⚪"
            callback = f"gpanel:toggle:{key}" if can_manage else "gpanel:locked"
            kb.add(types.InlineKeyboardButton(f"{status} {label}", callback_data=callback))
        if section == "entry":
            kb.row(
                types.InlineKeyboardButton(
                    ("🟢" if settings.get("force_join_on") else "⚪") + " تنظیم جوین اجباری",
                    callback_data="gpanel:configure_force_join" if can_manage else "gpanel:locked"),
                types.InlineKeyboardButton(
                    ("🟢" if settings.get("force_add_on") else "⚪") + " تنظیم اد اجباری",
                    callback_data="gpanel:configure_force_add" if can_manage else "gpanel:locked"))
            kb.add(types.InlineKeyboardButton("🔗 دریافت لینک دعوت اختصاصی", callback_data="gpanel:mylink"))
        for label, action in cfg.get("asks", []):
            kb.add(types.InlineKeyboardButton(label, callback_data=f"gpanel:ask:{action}" if can_manage else "gpanel:locked"))
        if section == "overview":
            kb.row(types.InlineKeyboardButton("📊 آمار گروه", callback_data="gpanel:stats"),
                   types.InlineKeyboardButton("⚙️ وضعیت تنظیمات", callback_data="gpanel:settings"))
            kb.add(types.InlineKeyboardButton("🎮 بازی‌ها", callback_data="gpanel:games"))
        if section == "help":
            kb.add(types.InlineKeyboardButton("📖 راهنمای فرمان‌ها", callback_data="gpanel:commands"))
            kb.add(types.InlineKeyboardButton("🧪 بررسی سلامت ربات", callback_data="gpanel:health"))
    kb.row(types.InlineKeyboardButton("🏠 صفحه اصلی", callback_data="gpanel:page:home"),
           types.InlineKeyboardButton("🔄 تازه‌سازی", callback_data="gpanel:refresh"))
    return kb

def send_group_panel(chat_id, message_id=None, user_id=None, section="home"):
    can_manage = bool(user_id is not None and is_group_admin(chat_id, user_id))
    settings = get_group_settings(chat_id)
    if section not in {"home", *GROUP_PANEL_SECTIONS.keys()}:
        section = "home"
    GROUP_PANEL_PAGES[(int(chat_id), int(message_id or 0))] = section
    if section == "home":
        heading = "🏠 صفحه اصلی پنل"
        intro = ("این پنل چندصفحه‌ای است؛ از دسته‌بندی‌ها وارد شو.\n"
                 "هر گزینهٔ مدیریتی فقط پس از بررسی مجوز مدیر اجرا می‌شود.")
    else:
        heading = GROUP_PANEL_SECTIONS[section]["title"]
        intro = "تنظیمات این بخش را از دکمه‌های زیر مدیریت کن."
    status = (f"📢 جوین اجباری: {'روشن' if settings.get('force_join_on') else 'خاموش'} | "
              f"➕ اد اجباری: {'روشن (' + str(settings.get('force_add_count', 3)) + ')' if settings.get('force_add_on') else 'خاموش'}\n")
    text = ("🛡️ <b>مدیریت گروه | 𝑴𝒂𝒔𝒊𝒉 𝑯𝒂𝒄𝒌𝒆𝒓𝒊𝒏𝒈 — پنل مدیریت گروه</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"<b>{esc(heading)}</b>\n{intro}\n\n{status}"
            f"📜 مجوز گروه: {'🟢 فعال' if is_group_licensed(chat_id) else '🟠 غیرفعال؛ بعضی عملیات حفاظتی اجرا نمی‌شوند'}\n"
            f"👤 دسترسی شما: {'🛠 مدیر گروه' if can_manage else '👁 مشاهده‌گر؛ کنترل‌های مدیریتی قفل هستند'}")
    markup = group_panel_keyboard(chat_id, user_id, section)
    if message_id is not None:
        try:
            bot.edit_message_text(text, chat_id, message_id, reply_markup=markup)
            GROUP_PANEL_PAGES[(int(chat_id), int(message_id))] = section
            return
        except Exception as e:
            if "message is not modified" in str(e).lower():
                return
    sent = bot.send_message(chat_id, text, reply_markup=markup)
    GROUP_PANEL_PAGES[(int(chat_id), int(sent.message_id))] = section

def send_panel(chat_id, section="home", message_id=None, user_id=None):
    # The menu can be viewed by anyone in private chat; every privileged callback is owner-gated.
    if user_id is not None and int(chat_id) != int(user_id):
        try: bot.send_message(user_id, "🔐 این پنل فقط در گفت‌وگوی خصوصی ربات نمایش داده می‌شود.")
        except Exception: pass
        return
    if user_id is not None: PANEL_CURRENT[user_id] = section
    if section == "home":
        text = f"🌈 <b>{BRAND} {VERSION}</b>\n━━━━━━━━━━━━━━━━━━\n👑 پنل مدیریت اختصاصی مالک\n\nیکی از بخش‌ها را انتخاب کن."
        kb = main_keyboard()
    else:
        text = f"🌈 <b>{BRAND} {VERSION}</b>\n━━━━━━━━━━━━━━━━━━\n<b>{esc(SECTIONS.get(section, 'پنل مدیریت'))}</b>\n\nتنظیمات را انتخاب کن."
        kb = section_keyboard(section)
    if message_id is not None:
        try:
            bot.edit_message_text(text, chat_id, message_id, reply_markup=kb)
            return
        except Exception as e:
            if "message is not modified" in str(e).lower(): return
            print("Panel edit error:", repr(e))
    bot.send_message(chat_id, text, reply_markup=kb)

# ---------------- Font/proxy/referrals/rewards ----------------
# 50 free font styles. Latin letters use Unicode variants where available;
# decorative wrappers keep Persian/Arabic text readable too.
_LATIN = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
def _range_map(upper_start, lower_start=None, upper_count=26, lower_count=26):
    src, dst = _LATIN, []
    if upper_start is not None:
        dst.extend(chr(upper_start+i) for i in range(26))
    else:
        dst.extend("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    if lower_start is not None:
        dst.extend(chr(lower_start+i) for i in range(26))
    else:
        dst.extend("abcdefghijklmnopqrstuvwxyz")
    return str.maketrans(src, "".join(dst))

FONT_MAPS = [
 str.maketrans(_LATIN, "𝔸𝔹ℂ𝔻𝔼𝔽𝔾ℍ𝕀𝕁𝕂𝕃𝕄ℕ𝕆ℙℚℝ𝕊𝕋𝕌𝕍𝕎𝕏𝕐ℤ𝕒𝕓𝕔𝕕𝕖𝕗𝕘𝕙𝕚𝕛𝕜𝕝𝕞𝕟𝕠𝕡𝕢𝕣𝕤𝕥𝕦𝕧𝕨𝕩𝕪𝕫"),
 str.maketrans(_LATIN, "𝘈𝘉𝘊𝘋𝘌𝘍𝘎𝘏𝘐𝘑𝘒𝘓𝘔𝘕𝘖𝘗𝘘𝘙𝘚𝘛𝘜𝘝𝘞𝘟𝘠𝘡𝘢𝘣𝘤𝘥𝘦𝘧𝘨𝘩𝘪𝘫𝘬𝘭𝘮𝘯𝘰𝘱𝘲𝘳𝘴𝘵𝘶𝘷𝘸𝘹𝘺𝘻"),
 str.maketrans(_LATIN, "ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ"),
 _range_map(0x1D400,0x1D41A), # bold
 _range_map(0x1D434,0x1D44E), # italic
 _range_map(0x1D468,0x1D482), # bold italic
 _range_map(0x1D49C,0x1D4B6), # script
 _range_map(0x1D4D0,0x1D4EA), # bold script
 _range_map(0x1D504,0x1D51E), # fraktur
 _range_map(0x1D56C,0x1D586), # bold fraktur
 _range_map(0x1D538,0x1D552), # double-struck
 _range_map(0x1D5A0,0x1D5BA), # sans
 _range_map(0x1D5D4,0x1D5EE), # sans bold
 _range_map(0x1D608,0x1D622), # sans italic
 _range_map(0x1D63C,0x1D656), # sans bold italic
 _range_map(0x1D670,0x1D68A), # monospace
 str.maketrans(_LATIN, "ⒶⒷⒸⒹⒺⒻⒼⒽⒾⒿⓀⓁⓂⓃⓄⓅⓆⓇⓈⓉⓊⓋⓌⓍⓎⓏⓐⓑⓒⓓⓔⓕⓖⓗⓘⓙⓚⓛⓜⓝⓞⓟⓠⓡⓢⓣⓤⓥⓦⓧⓨⓩ"),
 str.maketrans(_LATIN, "🄰🄱🄲🄳🄴🄵🄶🄷🄸🄹🄺🄻🄼🄽🄾🄿🅀🅁🅂🅃🅄🅅🅆🅇🅈🅉abcdefghijklmnopqrstuvwxyz"),
]
FONT_NAMES = [
 "دوبل‌استراک", "ایتالیک", "فول‌ویدث", "بولد", "ایتالیک کلاسیک", "بولد ایتالیک", "اسکریپت", "اسکریپت بولد", "فرکتور", "فرکتور بولد", "دوبل‌لاین", "سن‌سریف", "سن‌سریف بولد", "سن‌سریف ایتالیک", "سن‌سریف بولد ایتالیک", "مونو‌اسپیس", "دایره‌ای", "کادر مربع"
]
FONT_WRAPPERS = [
 ("✨ ستاره‌ای", "✦ {} ✦"), ("🌟 درخشان", "🌟 {} 🌟"), ("💜 قلبی", "💜 {} 💜"), ("🖤 تیره", "🖤 {} 🖤"),
 ("⚡ برقی", "⚡ {} ⚡"), ("🔥 آتشی", "🔥 {} 🔥"), ("🌈 رنگین‌کمانی", "🌈 {} 🌈"), ("👑 سلطنتی", "♛ {} ♛"),
 ("༺ سلطنتی ۲", "༺ {} ༻"), ("꧁ فانتزی", "꧁ {} ꧂"), ("『 کادری ۱ 』", "『 {} 』"), ("【 کادری ۲ 】", "【 {} 】"),
 ("《 کادری ۳ 》", "《 {} 》"), ("〈 کادری ۴ 〉", "〈 {} 〉"), ("• نقطه‌ای", "• {} •"), ("⋆ ستاره‌ای ۲", "⋆｡ {} ｡⋆"),
 ("♡ قلب توخالی", "♡ {} ♡"), ("ღ قلبی ۲", "ღ {} ღ"), ("ツ ژاپنی", "ツ {} ツ"), ("メ ژاپنی ۲", "メ {} メ"),
 ("〆 ژاپنی ۳", "〆 {} 〆"), ("彡 سایه‌ای", "彡 {} 彡"), ("乂 ضربدری", "乂 {} 乂"), ("× ضربدری ۲", "× {} ×"),
 ("➳ پیکانی", "➳ {} ➳"), ("➤ پیکانی ۲", "➤ {} ➤"), ("☯ نمادین", "☯ {} ☯"), ("☾ ماه", "☾ {} ☽"),
 ("༄ تزئینی", "༄ {} ༄"), ("𓆩 قاب ۱", "𓆩 {} 𓆪"), ("⫷ قاب ۲", "⫷ {} ⫸"), ("༒ تاریک", "༒ {} ༒")
]


EXTRA_FONT_WRAPPERS = [
    ("نئونی", "✧ {} ✧"),
    ("الماسی", "◇ {} ◇"),
    ("شاهانه", "♛ {} ♛"),
    ("ستارهٔ دنباله‌دار", "☄ {} ☄"),
    ("خورشیدی", "☀ {} ☀"),
    ("ماه‌تاب", "☾ {} ☽"),
    ("برگی", "❧ {} ❧"),
    ("گل‌دار", "❀ {} ❀"),
    ("گل رز", "🌹 {} 🌹"),
    ("شعله", "♨ {} ♨"),
    ("موجی", "≈ {} ≈"),
    ("کریستالی", "◈ {} ◈"),
    ("هندسی", "◆ {} ◆"),
    ("کمانی", "⌁ {} ⌁"),
    ("خطی", "═ {} ═"),
    ("دوخطی", "╬ {} ╬"),
    ("کلاسیک", "❖ {} ❖"),
    ("نقش‌دار", "۞ {} ۞"),
    ("ستارهٔ هشت‌پر", "✵ {} ✵"),
    ("ستارهٔ چهارپر", "✣ {} ✣"),
    ("قاب پررنگ", "【 {} 】"),
    ("قاب زاویه‌ای", "⟪ {} ⟫"),
    ("قاب دوبل", "《 {} 》"),
    ("قاب مثلثی", "⟬ {} ⟭"),
    ("قاب موج", "≋ {} ≋"),
    ("خط‌چین", "┄ {} ┄"),
    ("خط‌بلند", "━━ {} ━━"),
    ("کادر گوشه‌دار", "┏ {} ┓"),
    ("کادر پایین", "┗ {} ┛"),
    ("شطرنجی", "▣ {} ▣"),
    ("چهارگوش", "▪ {} ▪"),
    ("لوزی", "♦ {} ♦"),
    ("دایرهٔ توپر", "● {} ●"),
    ("دایرهٔ توخالی", "○ {} ○"),
    ("مثلثی", "▲ {} ▲"),
    ("پیکان‌دار", "➳ {} ➳"),
    ("بال‌دار", "༺ {} ༻"),
    ("افسانه‌ای", "𓆩 {} 𓆪"),
    ("تاریک ۲", "☠ {} ☠"),
    ("جادویی", "⋆｡ {} ｡⋆"),
    ("قلب قرمز", "❤️ {} ❤️"),
    ("قلب آبی", "💙 {} 💙"),
    ("قلب سبز", "💚 {} 💚"),
    ("قلب زرد", "💛 {} 💛"),
    ("قلب بنفش", "💜 {} 💜"),
    ("درخشش", "💫 {} 💫"),
    ("ستاره رنگی", "🌟 {} 🌟"),
    ("تاج و تخت", "♕ {} ♕"),
    ("شمشیر", "⚔ {} ⚔"),
    ("شیر و خورشید", "🦁 {} 🦁"),
]


def font_variants(text):
    """Return up to 200 distinct decorative styles; Persian is decorated rather than remapped."""
    variants=[]
    has_persian = bool(re.search(r"[\u0600-\u06ff]", text))
    for i, mapping in enumerate(FONT_MAPS):
        name = FONT_NAMES[i] if i < len(FONT_NAMES) else f"سبک {i+1}"
        converted = text.translate(mapping)
        if has_persian and i < len(FONT_WRAPPERS):
            wrapper_name, wrapper = FONT_WRAPPERS[i]
            converted = wrapper.format(converted)
            name = f"{name} + {wrapper_name}"
        variants.append((name, converted))
    for name, wrapper in FONT_WRAPPERS + EXTRA_FONT_WRAPPERS:
        variants.append((name, wrapper.format(text)))
    # Build 100 additional combinations so there are actually 200 results, not just a label.
    outer = ["✦ {} ✦", "꧁ {} ꧂", "『 {} 』", "【 {} 】", "༺ {} ༻", "⚡ {} ⚡", "𓆩 {} 𓆪", "♛ {} ♛", "彡 {} 彡", "★彡 {} 彡★"]
    inner = ["♡ {} ♡", "✧ {} ✧", "☾ {} ☽", "◇ {} ◇", "༒ {} ༒", "❀ {} ❀", "➳ {} ➳", "♜ {} ♜", "▰ {} ▰", "∞ {} ∞"]
    for oi, outer_fmt in enumerate(outer):
        for ii, inner_fmt in enumerate(inner):
            styled = outer_fmt.format(inner_fmt.format(text))
            variants.append((f"ترکیبی فانتزی {oi*10+ii+101}", styled))
    # De-duplicate output while retaining the first descriptive label.
    result=[]; seen=set()
    for name, value in variants:
        if value not in seen:
            seen.add(value); result.append((name, value))
        if len(result) >= 200: break
    # Guarantee exactly 200 unique choices even when a short Persian input makes
    # some decorative wrappers visually identical.
    serial = 1
    while len(result) < 200:
        value = f"『{serial:03d}』 {text} 『{serial:03d}』"
        serial += 1
        if value in seen: continue
        seen.add(value)
        result.append((f"قاب شماره‌دار {serial-1}", value))
    return result

def convert_font(text, style=0):
    variants = font_variants(text)
    return variants[style % len(variants)][1]

def apply_referral(uid, payload):
    """Credit one referral from Telegram's private /start=ref_ID deep link.
    Telegram does not expose a reliable inviter ID on ordinary group join events;
    therefore the invite is credited when the new user starts the bot with the link.
    """
    if not str(payload).startswith("ref_"): return False
    try: referrer = int(str(payload)[4:])
    except (TypeError, ValueError): return False
    uid, referrer = int(uid), int(referrer)
    if referrer == uid: return False
    key = str(uid)
    with LOCK:
        if key in DATA.setdefault("referrals", {}): return False
        ensure_user(uid)
        ensure_user(referrer)
        DATA["referrals"][key] = {"referrer": referrer, "time": now_text(), "rewarded": True}
        reward = max(0, min(1000000, int(bot_settings().get("referral_reward_toman", 5000))))
        if reward:
            transaction(referrer, reward, f"پاداش دعوت کاربر {uid}")
        add_log("referral", "", uid, f"referrer={referrer}; reward_toman={reward}")
        save_data()
    try:
        bot.send_message(referrer, f"🎉 دعوت معتبر ثبت شد!\n💳 مبلغ واریزی: {reward:,} تومان\nموجودی کیف پول: {wallet(referrer):,} تومان")
    except Exception: pass
    return True

def referral_text(uid):
    global BOT_USERNAME
    if not BOT_USERNAME:
        try: BOT_USERNAME = bot.get_me().username or ""
        except Exception: pass
    link = f"https://t.me/{BOT_USERNAME}?start=ref_{uid}" if BOT_USERNAME else "نام کاربری ربات هنوز در دسترس نیست."
    count = sum(1 for x in DATA.get("referrals", {}).values() if isinstance(x, dict) and int(x.get("referrer", 0)) == int(uid))
    reward = max(0, int(bot_settings().get("referral_reward_toman", 5000)))
    return (
        "🎁 <b>باشگاه دعوت دوستان | MASIH GUARD</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🔗 <b>لینک اختصاصی دعوت شما</b>\n"
        f"<code>{esc(link)}</code>\n\n"
        f"👥 دعوت‌های ثبت‌شده: <b>{count}</b>\n"
        f"💰 پاداش هر دعوت معتبر طبق تنظیم فعلی: <b>{reward:,} تومان</b>\n\n"
        "📌 <b>روش استفاده</b>\n"
        "۱. لینک بالا را برای دوستت بفرست.\n"
        "۲. دوستت باید با همان لینک وارد گفت‌وگوی خصوصی ربات شود و Start را بزند.\n"
        "۳. دعوت معتبر طبق قوانین ربات ثبت می‌شود و پاداش احتمالی به کیف پول تومانی اضافه خواهد شد.\n\n"
        "⚠️ هر کاربر فقط یک‌بار محاسبه می‌شود؛ ثبت دعوت یا پاداش، تابع شرایط و تنظیمات ربات است.\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "💳 برای دیدن موجودی، «کیف پول» را بزن؛ برای سوابق، «تراکنش‌ها» را انتخاب کن."
    )


def subscription_packages():
    """Return the validated, currently configured subscription package list."""
    return tuple((int(row[0]), int(row[1])) for row in bot_settings().get("subscription_packages", []))

def subscription_support_keyboard():
    """Official purchase support links; bank details are never invented by the bot."""
    kb = types.InlineKeyboardMarkup(row_width=1)
    kb.add(types.InlineKeyboardButton("👨‍💻 دریافت اطلاعات پرداخت از سازنده", url=OWNER_CONTACT_URL))
    kb.add(types.InlineKeyboardButton("🛒 برگشت به بسته‌های اشتراک", callback_data="user:shop"))
    return kb

def shop_keyboard():
    """Compact subscription menu using real Telegram inline buttons."""
    kb = types.InlineKeyboardMarkup(row_width=1)
    labels = {
        30: "🥉 ۳۰ روزه  ·  ۴۰٬۰۰۰ تومان",
        60: "🥈 ۶۰ روزه  ·  ۸۰٬۰۰۰ تومان",
        90: "🥇 ۹۰ روزه  ·  ۱۲۰٬۰۰۰ تومان",
    }
    for days, price in subscription_packages():
        kb.add(types.InlineKeyboardButton(
            labels.get(days, f"⭐ {days} روز  ·  {price:,} تومان"),
            callback_data=f"shop:request:{days}:{price}"
        ))
    kb.row(types.InlineKeyboardButton("💳 کیف پول", callback_data="user:wallet"),
           types.InlineKeyboardButton("🧾 تراکنش‌ها", callback_data="user:transactions"))
    kb.add(types.InlineKeyboardButton("👨‍💻 پشتیبانی و اطلاعات پرداخت", url=OWNER_CONTACT_URL))
    kb.add(types.InlineKeyboardButton("⬅️ بازگشت به منو", callback_data="user:home"))
    return kb


def shop_text(uid):
    sub = DATA.setdefault("subscriptions", {}).get(str(uid), {})
    expiry = sub.get("expires") or "اشتراک فعال نیست"
    package_text = "\n".join(
        f"  ├ {days} روز  ·  <b>{price:,} تومان</b>"
        for days, price in subscription_packages()
    )
    status_icon = "🟢" if sub.get("expires") else "⚪"
    lines = [
        "💠 <b>مرکز اشتراک</b>",
        "<b>مدیریت گروه | 𝑴𝒂𝒔𝒊𝒉 𝑯𝒂𝒄𝒌𝒆𝒓𝒊𝒏𝒈</b>",
        "━━━━━━━━━━━━━━━━━━",
        f"{status_icon} وضعیت: <b>{'فعال' if sub.get('expires') else 'غیرفعال'}</b>",
        f"💳 موجودی کیف پول: <b>{wallet(uid):,} تومان</b>",
        f"📅 پایان اشتراک: <b>{esc(expiry)}</b>",
        "━━━━━━━━━━━━━━━━━━",
        "💎 <b>بسته‌ات رو انتخاب کن</b>",
        package_text,
        "",
        "🧾 <b>مراحل خرید</b>",
        "۱. یکی از بسته‌های بالا را انتخاب کن.",
        "۲. درخواست خرید برای مالک ثبت می‌شود.",
        "۳. مبلغ دقیق را پرداخت کن و از دکمهٔ «ارسال رسید پرداخت» عکس رسید را بفرست.",
        "۴. اشتراک پس از بررسی و تأیید مالک فعال می‌شود.",
        "",
    ]
    if CARD_NUMBER and CARD_HOLDER:
        lines.extend([
            "💳 <b>اطلاعات پرداخت</b>",
            f"شماره کارت: <code>{esc(CARD_NUMBER)}</code>",
            f"به نام: <b>{esc(CARD_HOLDER)}</b>",
        ])
    else:
        lines.append("💬 برای دریافت اطلاعات پرداخت معتبر، دکمهٔ «پشتیبانی و اطلاعات پرداخت» را بزن.")
    lines.extend([
        "",
        "🔒 رمز کارت، رمز پویا یا اطلاعات ورود بانکی را برای هیچ‌کس نفرست.",
        "<i>MASIH GUARD • Subscription Center</i>",
    ])
    return "\n".join(lines)


def public_wallet(uid):
    ensure_user(uid)
    sub = DATA.setdefault("subscriptions", {}).get(str(uid), {})
    return (f"💳 <b>کیف پول تومانی</b>\n━━━━━━━━━━━━━━\n"
            f"💰 موجودی: <b>{wallet(uid):,} تومان</b>\n"
            f"🎮 امتیاز بازی: {DATA.get('points', {}).get(str(uid),0)}\n"
            f"⭐ اشتراک ویژه تا: {esc(sub.get('expires','نداری'))}")

def transactions_text(uid):
    rows = DATA.setdefault("transactions", {}).get(str(uid), [])[-12:]
    if not rows: return "🧾 هنوز تراکنش تومانی ثبت نشده است."
    return "🧾 <b>آخرین تراکنش‌های تومانی</b>\n" + "\n".join(
        f"{'➕' if int(x.get('amount_toman',0)) >= 0 else '➖'} {abs(int(x.get('amount_toman',0))):,} تومان — {esc(x.get('reason'))}\n<code>{esc(x.get('time'))}</code>"
        for x in reversed(rows))

def request_subscription(uid, days, price):
    days, price, uid = int(days), int(price), int(uid)
    if (days, price) not in subscription_packages():
        return "❌ بستهٔ اشتراک معتبر نیست."
    ensure_user(uid)
    reqs = DATA.setdefault("subscription_requests", {})
    # Avoid duplicate pending requests for the same user/package.
    for rid, req in reqs.items():
        if int(req.get("user_id", 0)) == uid and req.get("status") == "pending":
            if int(req.get("days", 0)) == days:
                return f"⏳ درخواست این بسته قبلاً ثبت شده است. شناسه درخواست: {esc(rid)}\nمنتظر بررسی مالک بمان."
    rid = str(int(time.time() * 1000)) + str(uid)[-4:]
    req = {"user_id": uid, "days": days, "price_toman": price, "status": "pending", "created": now_text()}
    reqs[rid] = req
    save_data()
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.row(types.InlineKeyboardButton("✅ تأیید و فعال‌سازی", callback_data=f"subreq:approve:{rid}"),
           types.InlineKeyboardButton("❌ رد درخواست", callback_data=f"subreq:reject:{rid}"))
    try:
        bot.send_message(OWNER_ID, f"💳 <b>درخواست خرید اشتراک</b>\nشناسه: <code>{esc(rid)}</code>\nکاربر: <code>{uid}</code>\nبسته: {days} روز\nمبلغ: {price:,} تومان\nوضعیت پرداخت را خارج از ربات بررسی کن و فقط پس از دریافت وجه تأیید بزن.", reply_markup=kb)
    except Exception as e:
        # Keep it pending so the owner can still review it from the panel later.
        reqs[rid]["owner_notice_failed"] = True
        reqs[rid]["notice_error"] = str(e)[:160]
        save_data()
        return "⚠️ درخواست ذخیره شد، اما پیام مستقیم به مالک نرسید. از بخش «درخواست‌های اشتراک» پنل مالک هم قابل بررسی است."
    add_log("subscription_requested", "", uid, f"request={rid}; days={days}; price_toman={price}")
    return (f"🧾 <b>درخواست خرید ثبت شد</b>\n━━━━━━━━━━━━━━━━━━━━\n"
            f"📦 بسته: {days} روز\n💳 مبلغ قابل پرداخت: <b>{price:,} تومان</b>\n"
            f"🆔 شناسه درخواست: <code>{esc(rid)}</code>\n\n"
            "👨‍💻 برای دریافت اطلاعات بانکی معتبر، به پیوی سازنده پیام بده؛ شماره کارت را حدس نمی‌زنیم و داخل ربات نمایش نمی‌دهیم.\n"
            "پس از انتقال وجه، رسید یا شماره پیگیری را به سازنده ارسال کن. مالک بعد از بررسی پرداخت درخواست را تأیید می‌کند و سپس اشتراک فعال می‌شود.\n"
            "⚠️ تا قبل از تأیید مالک، اشتراک فعال نیست.")

def decide_subscription_request(rid, approve, owner_uid):
    if not is_owner(owner_uid): return "⛔ فقط مالک ربات مجاز است."
    req = DATA.setdefault("subscription_requests", {}).get(str(rid))
    if not req: return "❌ درخواست پیدا نشد."
    if req.get("status") != "pending": return f"ℹ️ این درخواست قبلاً بررسی شده است: {esc(req.get('status'))}"
    uid, days = int(req["user_id"]), int(req["days"])
    if not approve:
        req["status"] = "rejected"; req["reviewed"] = now_text(); req["reviewed_by"] = int(owner_uid)
        save_data(); add_log("subscription_rejected", "", uid, f"request={rid}")
        try: bot.send_message(uid, f"❌ درخواست اشتراک شما رد شد. شناسه: {esc(rid)}\nاگر فکر می‌کنی اشتباهی شده، با پشتیبانی تماس بگیر.")
        except Exception: pass
        return "❌ درخواست رد شد."
    from datetime import timedelta
    now = datetime.now()
    current = DATA.setdefault("subscriptions", {}).get(str(uid), {}).get("expires", "")
    try: base = datetime.strptime(current, "%Y-%m-%d %H:%M:%S")
    except Exception: base = now
    if base < now: base = now
    expires = (base + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    DATA["subscriptions"][str(uid)] = {"expires": expires, "updated": now_text(), "approved_request": str(rid)}
    req["status"] = "approved"; req["reviewed"] = now_text(); req["reviewed_by"] = int(owner_uid); req["expires"] = expires
    save_data(); add_log("subscription_approved", "", uid, f"request={rid}; days={days}; expires={expires}")
    try: bot.send_message(uid, f"🎉 <b>اشتراک MASIH GUARD فعال شد!</b>\n━━━━━━━━━━━━━━━━━━━━\n✅ پرداخت بررسی و تأیید شد.\n⭐ مدت اشتراک: {days} روز\n📅 پایان اشتراک: <b>{esc(expires)}</b>\n👨‍💻 برای پشتیبانی یا تمدید، از دکمهٔ ارتباط با سازنده استفاده کن.", reply_markup=subscription_support_keyboard())
    except Exception: pass
    return f"✅ درخواست تأیید شد؛ اشتراک کاربر {uid} تا {esc(expires)} فعال شد."



def request_payout(uid, amount_toman):
    uid, amount_toman = int(uid), int(amount_toman)
    if amount_toman <= 0: return "❌ مبلغ برداشت باید بیشتر از صفر باشد."
    if amount_toman > wallet(uid): return f"❌ موجودی کافی نیست. موجودی فعلی: {wallet(uid):,} تومان"
    requests = DATA.setdefault("payout_requests", {})
    for rid, req in requests.items():
        if int(req.get("user_id", 0)) == uid and req.get("status") == "pending":
            return f"⏳ یک درخواست برداشت در انتظار بررسی داری. شناسه: <code>{esc(rid)}</code>"
    rid = str(int(time.time() * 1000)) + str(uid)[-4:]
    requests[rid] = {"user_id": uid, "amount_toman": amount_toman, "status": "pending", "created": now_text()}
    save_data()
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.row(types.InlineKeyboardButton("✅ ثبت پرداخت انجام‌شده", callback_data=f"payout:paid:{rid}"),
           types.InlineKeyboardButton("❌ رد درخواست", callback_data=f"payout:reject:{rid}"))
    try:
        bot.send_message(OWNER_ID, f"💸 <b>درخواست برداشت کیف پول</b>\nشناسه: <code>{esc(rid)}</code>\nکاربر: <code>{uid}</code>\nمبلغ: {amount_toman:,} تومان\nروش پرداخت را با کاربر هماهنگ کن و فقط پس از واریز واقعی، «ثبت پرداخت انجام‌شده» را بزن.", reply_markup=kb)
    except Exception as e:
        requests[rid]["owner_notice_failed"] = True
        requests[rid]["notice_error"] = str(e)[:160]
        save_data()
    add_log("payout_requested", "", uid, f"request={rid}; amount_toman={amount_toman}")
    return f"📨 درخواست برداشت {amount_toman:,} تومان ثبت شد. مالک پس از بررسی و هماهنگی پرداخت آن را بررسی می‌کند.\nشناسه: <code>{esc(rid)}</code>\nتا تأیید نهایی، موجودی از کیف پول کم نمی‌شود."

def decide_payout_request(rid, paid, owner_uid):
    if not is_owner(owner_uid): return "⛔ فقط مالک ربات مجاز است."
    req = DATA.setdefault("payout_requests", {}).get(str(rid))
    if not req: return "❌ درخواست برداشت پیدا نشد."
    if req.get("status") != "pending": return f"ℹ️ این درخواست قبلاً بررسی شده است: {esc(req.get('status'))}"
    uid, amount = int(req["user_id"]), int(req["amount_toman"])
    if not paid:
        req["status"] = "rejected"; req["reviewed"] = now_text(); req["reviewed_by"] = int(owner_uid)
        save_data(); add_log("payout_rejected", "", uid, f"request={rid}")
        try: bot.send_message(uid, f"❌ درخواست برداشت شما رد شد. مبلغ از کیف پول کم نشده است. شناسه: <code>{esc(rid)}</code>")
        except Exception: pass
        return "❌ درخواست برداشت رد شد؛ موجودی تغییری نکرد."
    if wallet(uid) < amount:
        req["status"] = "balance_insufficient"; req["reviewed"] = now_text(); req["reviewed_by"] = int(owner_uid)
        save_data()
        return "❌ موجودی کاربر از زمان ثبت درخواست کمتر شده؛ پرداخت ثبت نشد."
    if not transaction(uid, -amount, f"برداشت تأییدشده {rid}"):
        return "❌ کسر موجودی انجام نشد؛ درخواست در انتظار بررسی باقی ماند."
    req["status"] = "paid"; req["reviewed"] = now_text(); req["reviewed_by"] = int(owner_uid)
    save_data(); add_log("payout_paid", "", uid, f"request={rid}; amount_toman={amount}")
    try: bot.send_message(uid, f"✅ درخواست برداشت ثبت و پرداخت‌شده علامت‌گذاری شد.\n💸 مبلغ: {amount:,} تومان\n💳 موجودی باقی‌مانده: {wallet(uid):,} تومان")
    except Exception: pass
    return f"✅ پرداخت درخواست {esc(rid)} ثبت شد؛ موجودی کیف پول کاربر به‌روزرسانی شد."


# ---------------- Security and moderation ----------------
def get_text(message): return getattr(message, "text", None) or getattr(message, "caption", None) or ""
def has_link(text): return bool(re.search(r"(https?://|www\.|t\.me/|telegram\.me/|@[A-Za-z0-9_]{5,})", text or "", re.I))
def has_tapchi(text):
    """Detect explicit Persian tapchi/ad-bot solicitation phrases."""
    value = normalize_security_text(text or "")
    phrases = ("تبچی", "تبچیگری", "تبلیغچی", "تبلیغچیگری", "تبچی اومد", "تبچی اومدم", "تبلیغچی اومدم")
    return any(normalize_security_text(phrase) in value for phrase in phrases)

def has_ad(text):
    """Conservative Persian/English ad detector; avoid treating every link as an ad."""
    value = normalize_security_text(text or "")
    phrases = (
        "تبلیغ", "تبلیغات", "خرید ممبر", "فروش ممبر", "خریدعضو", "فروشعضو",
        "عضوگیری", "کسب درآمد تضمینی", "درآمد تضمینی", "تبلیغ رایگان",
        "افزایش ممبر", "افزایش فالوور", "فالوور رایگان", "بازدید رایگان",
        "زیرمجموعه گیری", "زیرمجموعهگیری", "پنل فروش", "پنل ممبر",
        "buy members", "buy followers", "cheap followers", "earn money guaranteed",
        "promotion service", "advertise here"
    )
    if any(normalize_security_text(phrase) in value for phrase in phrases):
        return True
    # Multiple links plus a sales/contact call-to-action is a strong ad signal.
    raw = str(text or "").casefold()
    link_count = len(re.findall(r"(?:https?://|www\\.|t\\.me/|telegram\\.me/|@[a-z0-9_]{5,})", raw))
    sales_words = ("دایرکت", "پیام بده", "سفارش", "قیمت", "ثبت سفارش", "خرید", "فروش", "join now", "dm me", "order now")
    return link_count >= 2 and any(word in raw for word in sales_words)
def is_forwarded(m): return any(getattr(m, x, None) for x in ("forward_origin","forward_from","forward_from_chat","forward_date"))
def has_media(m): return any(getattr(m,x,None) for x in ("photo","video","audio","voice","document","animation","sticker","video_note","contact","location"))
def safe_delete(message):
    try: bot.delete_message(message.chat.id, message.message_id); return True
    except Exception as e: print("Delete error:", repr(e)); return False

def normalize_security_text(value):
    """Normalize whitespace, invisible marks and punctuation to catch simple filter evasion."""
    value = str(value or "").casefold()
    value = re.sub(r"[\u200b-\u200f\u202a-\u202e\ufeff]", "", value)
    value = re.sub(r"[\W_]+", "", value, flags=re.UNICODE)
    return value

def is_quiet_hours(settings, moment=None):
    if not settings.get("quiet_hours_on"):
        return False
    moment = moment or datetime.now()
    try:
        start = datetime.strptime(str(settings.get("quiet_start", "23:00")), "%H:%M").time()
        end = datetime.strptime(str(settings.get("quiet_end", "07:00")), "%H:%M").time()
    except ValueError:
        return False
    current = moment.time()
    if start == end:
        return True
    return (start <= current < end) if start < end else (current >= start or current < end)

def track_group_activity(chat_id, user_id, message_id=None):
    key = str(chat_id)
    stats = DATA.setdefault("group_stats", {}).setdefault(key, {"messages": 0, "blocked": 0, "joins": 0, "leaves": 0})
    stats["messages"] = int(stats.get("messages", 0)) + 1
    if user_id:
        members = DATA.setdefault("active_members", {}).setdefault(key, {})
        members[str(user_id)] = time.time()
    if message_id is not None:
        history = DATA.setdefault("message_history", {}).setdefault(key, [])
        history.append({"message_id": int(message_id), "user_id": int(user_id or 0), "time": time.time()})
        DATA["message_history"][key] = history[-300:]

def target_group_admin_status(chat_id, user_id):
    """Return True for a confirmed group creator/admin, False for a regular member, None if unknown."""
    try:
        member = bot.get_chat_member(int(chat_id), int(user_id))
        return getattr(member, "status", "") in ("creator", "administrator")
    except Exception as exc:
        print("Target role check failed; moderation will fail safe:", repr(exc))
        return None


def warn_member(chat_id, user_id, reason="تخلف از قوانین"):
    # Never try to auto-ban the group owner/admin. This also prevents the recurring
    # Telegram error: "Bad Request: can't remove chat owner".
    role = target_group_admin_status(chat_id, user_id)
    if role is True:
        add_log("moderation_skipped_protected", chat_id, user_id, "هدف مدیر/مالک گروه است")
        save_data()
        return False
    key=f"{chat_id}:{user_id}"
    DATA["warnings"][key]=int(DATA["warnings"].get(key,0))+1
    count=DATA["warnings"][key]; limit=max(1,int(get_group_settings(chat_id).get("warn_limit",3) or 3))
    DATA["stats"]["warns"]+=1
    try: bot.send_message(chat_id,f"⚠️ اخطار برای <code>{user_id}</code>\nدلیل: {esc(reason)}\nتعداد: {count}/{limit}")
    except Exception: pass
    add_log("warning",chat_id,user_id,reason)
    if count >= limit:
        # Re-check role before a destructive action; if Telegram cannot confirm the
        # role, skip auto-ban rather than risk an unintended moderation action.
        role = target_group_admin_status(chat_id, user_id)
        if role is not False:
            add_log("auto_ban_skipped", chat_id, user_id, "نقش هدف نامشخص است یا هدف مدیر/مالک گروه است")
            DATA["warnings"][key]=0
        else:
            try:
                bot.ban_chat_member(chat_id,user_id)
                bot.send_message(chat_id,f"⛔ کاربر <code>{user_id}</code> به سقف اخطار رسید و مسدود شد.")
                DATA["warnings"][key]=0
            except Exception as e:
                print("Auto-ban error:",repr(e))
                add_log("auto_ban_failed", chat_id, user_id, str(e)[:160])
    save_data()
    return True


def _force_join_channels(chat_id):
    """Return the validated required-channel list for a group."""
    rows = get_group_settings(chat_id).get("force_join_channels", [])
    result = []
    if not isinstance(rows, list):
        return result
    for row in rows[:10]:
        if not isinstance(row, dict):
            continue
        ident = str(row.get("id", "")).strip()
        url = str(row.get("url", "")).strip()
        title = str(row.get("title", ident)).strip()[:80]
        if ident and url.startswith(("https://t.me/", "http://t.me/")):
            result.append({"id": ident, "url": url, "title": title or ident})
    return result


def force_join_missing(chat_id, user_id, force_refresh=False):
    """Fail closed when Telegram cannot verify membership in a required channel."""
    cache_key = (int(chat_id), int(user_id))
    cached = FORCE_JOIN_CACHE.get(cache_key)
    if not force_refresh and cached and cached[0] > time.monotonic():
        return list(cached[1])
    missing = []
    for channel in _force_join_channels(chat_id):
        try:
            member = bot.get_chat_member(channel["id"], int(user_id))
            status = str(getattr(member, "status", "") or "")
            joined = status in ("creator", "administrator", "member") or (
                status == "restricted" and bool(getattr(member, "is_member", False))
            )
            if not joined:
                missing.append(channel)
        except Exception as exc:
            print("Force-join membership check error:", repr(exc))
            missing.append(channel)
    FORCE_JOIN_CACHE[cache_key] = (time.monotonic() + 8, list(missing))
    return missing


def force_join_markup(chat_id, user_id, missing=None):
    missing = _force_join_channels(chat_id) if missing is None else missing
    kb = types.InlineKeyboardMarkup(row_width=1)
    for channel in missing[:10]:
        kb.add(types.InlineKeyboardButton("📢 عضویت در " + channel["title"][:45], url=channel["url"]))
    kb.add(types.InlineKeyboardButton("🔄 بررسی عضویت", callback_data=f"forcejoin:check:{int(chat_id)}:{int(user_id)}"))
    return kb


def force_add_count(chat_id, user_id):
    group_rows = DATA.setdefault("force_add_credits", {}).get(str(chat_id), {})
    invited = group_rows.get(str(user_id), []) if isinstance(group_rows, dict) else []
    return len(set(str(x) for x in invited if str(x) != str(user_id)))


def track_force_invite_link(chat_id, user_id):
    """Create or reuse a personal invite link so only attributable joins are counted."""
    try:
        for existing_link, record in DATA.setdefault("force_invite_links", {}).items():
            if isinstance(record, dict) and int(record.get("chat_id", 0)) == int(chat_id) and int(record.get("inviter_id", 0)) == int(user_id):
                return existing_link, None
        member = bot.get_chat_member(chat_id, bot.get_me().id)
        if getattr(member, "status", "") not in ("administrator", "creator") or not bool(getattr(member, "can_invite_users", False)):
            return None, "ربات باید مدیر گروه با مجوز «دعوت کاربران» باشد."
        invite = bot.create_chat_invite_link(chat_id, name=f"MG:{int(user_id)}", creates_join_request=False)
        link = str(getattr(invite, "invite_link", "") or "")
        if not link:
            return None, "تلگرام لینک دعوت برنگرداند."
        DATA.setdefault("force_invite_links", {})[link] = {
            "chat_id": int(chat_id), "inviter_id": int(user_id), "created_at": now_text()
        }
        save_data()
        return link, None
    except Exception as exc:
        print("Create force invite link error:", repr(exc))
        return None, "ساخت لینک دعوت ناموفق بود؛ دسترسی مدیر ربات و تنظیمات گروه را بررسی کن."


@bot.chat_member_handler()
def force_add_chat_member_tracker(update):
    """Credit only joins made through a personal link created by /mylink."""
    try:
        chat_id = int(update.chat.id)
        old_member = getattr(update, "old_chat_member", None)
        new_member = getattr(update, "new_chat_member", None)
        old_status = str(getattr(old_member, "status", "") or "")
        new_status = str(getattr(new_member, "status", "") or "")
        invite_obj = getattr(update, "invite_link", None)
        link = str(getattr(invite_obj, "invite_link", "") or "")
        if new_status not in ("member", "administrator", "creator") or old_status in ("member", "administrator", "creator"):
            return
        tracked = DATA.setdefault("force_invite_links", {}).get(link)
        if not isinstance(tracked, dict) or int(tracked.get("chat_id", 0)) != chat_id:
            return
        inviter = int(tracked.get("inviter_id", 0) or 0)
        joined_user_obj = getattr(new_member, "user", None)
        joined_user = int(getattr(joined_user_obj, "id", 0) or 0)
        if not inviter or not joined_user or joined_user == inviter:
            return
        credits = DATA.setdefault("force_add_credits", {}).setdefault(str(chat_id), {})
        invited = credits.setdefault(str(inviter), [])
        if str(joined_user) not in {str(x) for x in invited}:
            invited.append(str(joined_user))
            credits[str(inviter)] = invited[-1000:]
            add_log("force_add_credit", chat_id, inviter, f"invited_user={joined_user}")
            save_data()
    except Exception as exc:
        print("Force-add invite tracking error:", repr(exc))



def entry_gate_notice_allowed(chat_id, user_id):
    key = (int(chat_id), int(user_id))
    now = time.monotonic()
    expiry = ENTRY_GATE_NOTICE_CACHE.get(key, 0)
    if expiry > now:
        return False
    ENTRY_GATE_NOTICE_CACHE[key] = now + 10
    if len(ENTRY_GATE_NOTICE_CACHE) > 5000:
        for old_key, old_expiry in list(ENTRY_GATE_NOTICE_CACHE.items()):
            if old_expiry <= now:
                ENTRY_GATE_NOTICE_CACHE.pop(old_key, None)
    return True


def enforce_group_entry_gates(message):
    """Enforce configured join/add requirements before ordinary group commands run."""
    chat, user = message.chat, message.from_user
    if not user or chat.type not in ("group", "supergroup"):
        return False
    if not is_group_licensed(chat.id):
        return False
    settings = get_group_settings(chat.id)
    if not settings.get("force_join_on") and not settings.get("force_add_on"):
        return False
    role = group_admin_status(chat.id, user.id)
    if role is True or role is None:
        return False
    if settings.get("force_join_on"):
        missing = force_join_missing(chat.id, user.id)
        if missing:
            safe_delete(message)
            if entry_gate_notice_allowed(chat.id, user.id):
                try:
                    name = esc(getattr(user, "first_name", "") or "عضو")
                    bot.send_message(chat.id, f"🔒 {name}، برای ارسال پیام ابتدا عضو کانال‌های لازم شو و «بررسی عضویت» را بزن.", reply_markup=force_join_markup(chat.id, user.id, missing))
                except Exception as exc:
                    print("Force-join prompt error:", repr(exc))
            return True
    if settings.get("force_add_on"):
        required = max(1, min(100, int(settings.get("force_add_count", 3) or 3)))
        actual = force_add_count(chat.id, user.id)
        if actual < required:
            safe_delete(message)
            if entry_gate_notice_allowed(chat.id, user.id):
                try:
                    bot.send_message(chat.id, f"➕ برای ارسال پیام، باید {required} عضو معتبر دعوت کنی. دعوت ثبت‌شده: {actual}. لینک اختصاصی خودت را با /mylink بگیر.")
                except Exception as exc:
                    print("Force-add prompt error:", repr(exc))
            return True
    return False


def handle_tapchi_violation(message, reason="تبلیغ یا تبچی"):
    """Dedicated anti-tapchi escalation: warnings 1–4, one-hour mute at violation 5."""
    chat = message.chat
    user = message.from_user
    if not user or getattr(chat, "type", "") not in ("group", "supergroup"):
        return False
    role = target_group_admin_status(chat.id, user.id)
    # Never punish group admins/owner; if Telegram cannot verify the role, fail safe.
    if role is not False:
        return False

    key = f"{chat.id}:{user.id}"
    records = DATA.setdefault("tapchi_violations", {})
    record = records.get(key, {})
    now = time.time()
    # Keep a rolling 30-day counter so old violations eventually expire.
    if not isinstance(record, dict) or now - float(record.get("last_at", 0) or 0) > 30 * 86400:
        record = {"count": 0, "last_at": 0}
    count = int(record.get("count", 0)) + 1
    record.update({"count": count, "last_at": now, "last_reason": str(reason)[:180]})
    records[key] = record
    DATA.setdefault("stats", {}).setdefault("warns", 0)
    DATA["stats"]["warns"] = int(DATA["stats"]["warns"]) + 1
    add_log("tapchi_violation", chat.id, user.id, f"{count}: {reason}")

    if count < 5:
        try:
            bot.send_message(
                chat.id,
                f"🚫 <b>ضدتبچی فعال شد</b>\\n"
                f"کاربر: <code>{user.id}</code>\\n"
                f"دلیل: {esc(reason)}\\n"
                f"اخطار تبلیغاتی: <b>{count}/5</b>\\n"
                "تخلف پنجم باعث بی‌صدا شدن خودکار می‌شود."
            )
        except Exception as exc:
            print("Tapchi warning notice error:", repr(exc))
        save_data()
        return True

    # At the fifth ad violation, apply a temporary mute rather than a permanent ban.
    try:
        until = int(now + 3600)
        bot.restrict_chat_member(
            chat.id, user.id,
            permissions=types.ChatPermissions(
                can_send_messages=False, can_send_audios=False, can_send_documents=False,
                can_send_photos=False, can_send_videos=False, can_send_video_notes=False,
                can_send_voice_notes=False, can_send_polls=False,
                can_send_other_messages=False, can_add_web_page_previews=False
            ),
            until_date=until
        )
        listing = DATA.setdefault("moderation_lists", {}).setdefault(
            str(chat.id), {"banned": [], "muted": []}
        )
        if str(user.id) not in listing.setdefault("muted", []):
            listing["muted"].append(str(user.id))
        add_log("tapchi_auto_mute", chat.id, user.id, "پنجمین تخلف تبلیغاتی؛ سکوت یک‌ساعته")
        try:
            bot.send_message(
                chat.id,
                f"🔇 <b>ضدتبچی: محدودیت خودکار</b>\\n"
                f"کاربر <code>{user.id}</code> به‌دلیل رسیدن به تخلف <b>{count}/5</b> "
                "برای یک ساعت بی‌صدا شد."
            )
        except Exception as exc:
            print("Tapchi mute notice error:", repr(exc))
    except Exception as exc:
        print("Tapchi auto-mute failed:", repr(exc))
        try:
            bot.send_message(
                chat.id,
                f"⚠️ کاربر <code>{user.id}</code> به تخلف تبلیغاتی پنجم رسید، "
                "اما بی‌صدا کردن ناموفق بود؛ مجوز Restrict Members ربات را بررسی کن."
            )
        except Exception:
            pass
    save_data()
    return True


def process_group_security(message):
    chat,user=message.chat,message.from_user
    if not user or chat.type not in ("group","supergroup"): return False
    s=get_group_settings(chat.id)
    gate_admin_status = group_admin_status(chat.id, user.id)
    if gate_admin_status is True or gate_admin_status is None:
        return False
    if not DATA.get("settings", {}).get("smart_security", True) or not s.get("smart_security", True): return False
    if str(user.id) in {str(x) for x in s.get("whitelist", [])}: return False
    admin_status = group_admin_status(chat.id, user.id)
    if admin_status is True or admin_status is None:
        # Skip enforcement if the member is an admin or Telegram could not confirm
        # their role; avoid accidental moderation during an API outage.
        return False
    text=get_text(message); key=f"{chat.id}:{user.id}"
    prev=DATA["seen"].get(key,{}); now=time.time(); reason=None
    if is_quiet_hours(s): reason="ارسال پیام در ساعت سکوت شبانه"
    elif s.get("media_lock") and has_media(message): reason="ارسال رسانه در حالت قفل رسانه"
    elif s.get("anti_forward") and is_forwarded(message): reason="ارسال پیام فورواردشده"
    elif s.get("lock_photos") and getattr(message,"photo",None): reason="ارسال عکس در حالت قفل عکس"
    elif s.get("lock_videos") and getattr(message,"video",None): reason="ارسال فیلم در حالت قفل فیلم"
    elif s.get("lock_files") and getattr(message,"document",None): reason="ارسال فایل در حالت قفل فایل"
    elif s.get("lock_stickers") and (getattr(message,"sticker",None) or getattr(message,"animation",None)): reason="ارسال استیکر یا گیف در حالت قفل"
    elif s.get("lock_voice") and (getattr(message,"voice",None) or getattr(message,"audio",None)): reason="ارسال پیام صوتی در حالت قفل"
    elif s.get("lock_video_notes") and getattr(message,"video_note",None): reason="ارسال ویدئوی گرد در حالت قفل"
    elif s.get("lock_mentions") and (re.search(r"(?<!\w)@[A-Za-z0-9_]{3,}", text or "") or any(getattr(e, "type", "") in ("mention", "text_mention") for e in (getattr(message, "entities", None) or []))): reason="ارسال تگ یا منشن در حالت قفل"
    elif s.get("lock_hashtags") and (re.search(r"(?<!\w)#[\w\u0600-\u06ff]+", text or "") or any(getattr(e, "type", "") == "hashtag" for e in (getattr(message, "entities", None) or []))): reason="ارسال هشتگ در حالت قفل"
    elif s.get("lock_usernames") and re.search(r"(?<!\w)@[A-Za-z0-9_]{5,}", text or ""): reason="ارسال نام کاربری در حالت قفل"
    elif s.get("anti_tapchi") and has_tapchi(text): reason="ارسال تبلیغ/تبچی"
    elif s.get("anti_ads") and has_ad(text): reason="ارسال تبلیغ"
    elif s.get("anti_link") and has_link(text) and str(user.id) not in [str(x) for x in s.get("whitelist",[])]: reason="ارسال لینک"
    elif s.get("phone_filter") and re.search(r"(?<!\d)(?:\+?\d[\d\s().-]{7,}\d)(?!\d)", text): reason="ارسال شماره تماس در حالت فیلتر شماره"
    elif text and any(w and str(w).casefold() in text.casefold() for w in s.get("bad_words",[])): reason="استفاده از کلمه ممنوع"
    if not reason and text and s.get("anti_repeat") and normalize_security_text(prev.get("normalized", prev.get("text", ""))) == normalize_security_text(text) and normalize_security_text(text) and now-prev.get("time",0)<30: reason="پیام تکراری یا با تغییرات جزئی"
    times=[t for t in prev.get("times",[]) if now-t<8]; times.append(now)
    if not reason and s.get("anti_spam") and len(times)>=7: reason="ارسال پیام‌های پرتعداد"
    DATA["seen"][key]={"text":text,"normalized":normalize_security_text(text),"time":now,"times":[] if reason=="ارسال پیام‌های پرتعداد" else times}
    if reason:
        if safe_delete(message):
            DATA["stats"]["blocked"]+=1
            group_stats=DATA.setdefault("group_stats",{}).setdefault(str(chat.id),{"messages":0,"blocked":0,"joins":0,"leaves":0})
            group_stats["blocked"]=int(group_stats.get("blocked",0))+1
            add_log("blocked",chat.id,user.id,reason)
            if reason.startswith("ارسال تبلیغ/تبچی"):
                handle_tapchi_violation(message, reason)
            else:
                warn_member(chat.id,user.id,reason)
        return True
    save_data(); return False

# Persian aliases and slash commands accepted by the group router.
_GROUP_ALIASES = {
    "help": "help", "راهنما": "help", "دستورات": "help", "کمک": "help", "راهنمای ربات": "help",
    "id": "id", "آیدی": "id", "ایدی": "id", "شناسه": "id",
    "ping": "ping", "پینگ": "ping", "تست": "ping",
    "rules": "rules", "قوانین": "rules", "قانون": "rules",
    "stats": "gstats", "آمار": "gstats", "آمارگروه": "gstats",
    "هوش": "ai", "هوش مصنوعی": "ai",
    "ban": "ban", "بن": "ban", "بن کن": "ban", "بنکن": "ban", "مسدود کن": "ban", "مسدودکن": "ban", "بلاک": "ban", "بلاک کن": "ban", "بلاکن": "ban",
    "unban": "unban", "رفع بن": "unban", "رفع‌بن": "unban", "رفع_بن": "unban", "آزاد کن": "unban", "آزادکن": "unban", "رفع مسدودی": "unban", "رفع‌مسدودی": "unban",
    "mute": "mute", "سیک": "mute", "سکوت": "mute", "سکوت کن": "mute", "سایلنت": "mute", "بی‌صدا": "mute", "بیصدا": "mute",
    "unmute": "unmute", "رفع سکوت": "unmute", "رفع‌سکوت": "unmute", "رفع_سکوت": "unmute", "آزاد سکوت": "unmute", "آزادسکوت": "unmute",
    "kick": "kick", "اخراج": "kick", "اخراج کن": "kick", "اخراج‌کن": "kick", "بنداز بیرون": "kick", "بندازبیرون": "kick",
    "warn": "warn", "اخطار": "warn", "اخطار بده": "warn", "هشدار": "warn",
    "pin": "pin", "سنجاق": "pin", "پین": "pin",
    "unpin": "unpin", "لغوسنجاق": "unpin", "برداشتن‌سنجاق": "unpin",
    "delete": "delete", "حذف": "delete", "پاک‌کن": "delete", "پاککن": "delete",
    "clean": "clean", "پاکسازی": "clean", "پاک سازی": "clean", "پاکسازی پیام": "clean", "پاکسازیپیام": "clean",
    "report": "report", "گزارش": "report", "گزارش‌تخلف": "report",
    "قفل لینک": "set_anti_link_on", "ضدلینک روشن": "set_anti_link_on", "بازکردن لینک": "set_anti_link_off", "ضدلینک خاموش": "set_anti_link_off",
    "قفل تبلیغ": "set_anti_ads_on", "ضدتبلیغ روشن": "set_anti_ads_on", "بازکردن تبلیغ": "set_anti_ads_off", "ضدتبلیغ خاموش": "set_anti_ads_off",
    "قفل تبچی": "set_anti_tapchi_on", "قفل تپچی": "set_anti_tapchi_on", "ضدتبچی روشن": "set_anti_tapchi_on", "بازکردن تبچی": "set_anti_tapchi_off", "ضدتبچی خاموش": "set_anti_tapchi_off",
    "ضد اسپم روشن": "set_anti_spam_on", "ضد اسپم خاموش": "set_anti_spam_off", "ضدتکرار روشن": "set_anti_repeat_on", "ضدتکرار خاموش": "set_anti_repeat_off",
    "قفل فوروارد": "set_anti_forward_on", "بازکردن فوروارد": "set_anti_forward_off",
    "قفل رسانه": "set_media_lock_on", "بازکردن رسانه": "set_media_lock_off",
    "خوشامد روشن": "set_welcome_on_on", "خوشامد خاموش": "set_welcome_on_off",
    "خداحافظی روشن": "set_farewell_on_on", "خداحافظی خاموش": "set_farewell_on_off",
    "تأیید ورود روشن": "set_join_approval_on", "تایید ورود روشن": "set_join_approval_on", "تأیید ورود خاموش": "set_join_approval_off", "تایید ورود خاموش": "set_join_approval_off",
    "قفل عکس": "set_lock_photos_on", "بازکردن عکس": "set_lock_photos_off",
    "قفل فیلم": "set_lock_videos_on", "بازکردن فیلم": "set_lock_videos_off",
    "قفل فایل": "set_lock_files_on", "بازکردن فایل": "set_lock_files_off",
    "قفل استیکر": "set_lock_stickers_on", "بازکردن استیکر": "set_lock_stickers_off",
    "قفل ویس": "set_lock_voice_on", "بازکردن ویس": "set_lock_voice_off",
    "قفل ویدئوی گرد": "set_lock_video_notes_on", "بازکردن ویدئوی گرد": "set_lock_video_notes_off",
    'دستورات کامل': 'help_full',
    'فهرست دستورات': 'help_full',
    'لیست دستورات': 'help_full',
    'همه دستورات': 'help_full',
    'راهنمای کامل': 'help_full',
    'شناسه من': 'id',
    'آیدی من': 'id',
    'آیدی گروه': 'id',
    'شناسه گروه': 'id',
    'شناسه عضو': 'id',
    'وضعیت ربات': 'ping',
    'ربات فعاله': 'ping',
    'تست ربات': 'ping',
    'پینگ ربات': 'ping',
    'بررسی ربات': 'ping',
    'قانون گروه': 'rules',
    'قوانین گروه': 'rules',
    'دیدن قوانین': 'rules',
    'نمایش قوانین': 'rules',
    'قانون ها': 'rules',
    'آمار گروه': 'gstats',
    'گزارش آمار': 'gstats',
    'آمار اعضا': 'gstats',
    'آمار پیام\u200cها': 'gstats',
    'آمار پیامها': 'gstats',
    'هوش بپرس': 'ai',
    'از هوش بپرس': 'ai',
    'سوال هوش': 'ai',
    'سؤال هوش': 'ai',
    'دستیار هوشمند': 'ai',
    'کاربر بن': 'ban',
    'بن کاربر': 'ban',
    'مسدود کاربر': 'ban',
    'مسدودسازی کاربر': 'ban',
    'اخراجی بن': 'ban',
    'رفع مسدودیت': 'unban',
    'لغو بن': 'unban',
    'آزادسازی کاربر': 'unban',
    'رفع بلاک': 'unban',
    'آزاد کردن': 'unban',
    'سکوت کاربر': 'mute',
    'ساکت کن': 'mute',
    'بیصدا کن': 'mute',
    'محدود کن': 'mute',
    'محدودسازی': 'mute',
    'آزاد سکوت': 'unmute',
    'سکوت بردار': 'unmute',
    'رفع محدودیت': 'unmute',
    'بازکردن سکوت': 'unmute',
    'کاربر آزاد': 'unmute',
    'بیرون کن': 'kick',
    'حذف عضو': 'kick',
    'اخراج عضو': 'kick',
    'بنداز بیرون': 'kick',
    'شوتش کن': 'kick',
    'شوت کن': 'kick',
    'بندازش بیرون': 'kick',
    'بفرستش بیرون': 'kick',
    'خارج کن': 'kick',
    'اخطار کاربر': 'warn',
    'هشدار کاربر': 'warn',
    'ثبت اخطار': 'warn',
    'اخطار عضو': 'warn',
    'هشدار بده': 'warn',
    'سنجاق پیام': 'pin',
    'پیام سنجاق': 'pin',
    'پین پیام': 'pin',
    'ثابت کن': 'pin',
    'پین کن': 'pin',
    'لغو پین': 'unpin',
    'بازکردن سنجاق': 'unpin',
    'حذف سنجاق': 'unpin',
    'برداشتن پین': 'unpin',
    'لغو سنجاق': 'unpin',
    'پاک کردن': 'delete',
    'حذف پیام': 'delete',
    'پاک پیام': 'delete',
    'پاکش کن': 'delete',
    'پیام حذف': 'delete',
    'پاکسازی گروه': 'clean',
    'پاکسازی چت': 'clean',
    'تمیزکاری گروه': 'clean',
    'پاک کردن پیامها': 'clean',
    'حذف پیامها': 'clean',
    'گزارش بده': 'report',
    'گزارش تخلف': 'report',
    'ثبت گزارش': 'report',
    'گزارش عضو': 'report',
    'ارسال گزارش': 'report',
    'ضد لینک': 'set_anti_link_on',
    'لینک ممنوع': 'set_anti_link_on',
    'قفل لینک روشن': 'set_anti_link_on',
    'ضدلینک فعال': 'set_anti_link_on',
    'لینک باز': 'set_anti_link_off',
    'ضد تبلیغ': 'set_anti_ads_on',
    'تبلیغ ممنوع': 'set_anti_ads_on',
    'قفل تبلیغ روشن': 'set_anti_ads_on',
    'ضدتبلیغ فعال': 'set_anti_ads_on',
    'تبلیغ آزاد': 'set_anti_ads_off',
    'تغییر نام گروه': 'set_title',
    'اسم گروه به': 'set_title',
    'نام گروه به': 'set_title',
    'تغییر توضیحات گروه': 'set_description',
    'توضیحات گروه به': 'set_description',
}

def _strip_group_bot_prefix(text):
    """Remove a leading bot name/mention so group creators can speak naturally."""
    value = (text or "").strip()
    if not value:
        return value
    # Accept an explicit bot mention at the beginning, e.g. @MasihGuard قفل لینک.
    value = re.sub(r"^@[A-Za-z0-9_]{4,}(?:\s+|[،:؛-]+)?", "", value, count=1)
    # Accept Persian and Latin wake words only at the start; never strip words mid-sentence.
    value = re.sub(
        r"^(?:(?:ربات|هوش(?:\s*مصنوعی)?|دستیار|مسیح\s*گارد|ماسیح\s*گارد|ماسح\s*گارد|masih\s*guard|masihguard))\s*[،:؛-]?\s*",
        "", value, count=1, flags=re.IGNORECASE
    )
    return value.strip()


def _normalize_group_command(text):
    value = (text or "").strip().casefold()
    value = value.replace("ي", "ی").replace("ك", "ک")
    value = re.sub(r"[\u200c\s]+", "", value)
    value = value.lstrip("/")
    if "@" in value:
        value = value.split("@", 1)[0]
    return value

_GROUP_ALIASES_NORMALIZED = {_normalize_group_command(key): value for key, value in _GROUP_ALIASES.items()}


def _reply_target(message):
    replied = getattr(message, "reply_to_message", None)
    return getattr(getattr(replied, "from_user", None), "id", None) if replied else None

def _handle_group_shortcut(message, text):
    """Return True when a recognized group shortcut was handled."""
    if not text:
        return False
    words = text.strip().split()
    command = None
    used_words = 0
    # Longest phrase first supports commands such as «مسدود کن» and «رفع سکوت».
    for n in range(min(3, len(words)), 0, -1):
        candidate = " ".join(words[:n])
        command = _GROUP_ALIASES_NORMALIZED.get(_normalize_group_command(candidate))
        if command:
            used_words = n
            break
    if not command:
        return False
    chat_id = message.chat.id
    user = getattr(message, "from_user", None)
    uid = getattr(user, "id", 0)
    args = " ".join(words[used_words:]).strip()
    if command == "ai":
        # AI is intentionally activated by the word «هوش» or a reply to the bot.
        question = args
        if not question and getattr(message, "reply_to_message", None):
            question = get_text(message.reply_to_message).strip()
        if not question:
            safe_reply_to(message, "جانم، بگو ببینم؟")
            return True
        status = safe_reply_to(message, "🧠 دارم بررسی می‌کنم…")
        answer = ask_ai(question)
        try: bot.edit_message_text(esc(answer[:3900]), status.chat.id, status.message_id)
        except Exception: safe_reply_to(message, esc(answer[:3900]))
        return True
    if command == "help_full":
        phrases = sorted(_GROUP_ALIASES.keys())
        text_out = "📚 <b>فهرست عبارت‌های پشتیبانی‌شده</b>\n" + "، ".join(phrases)
        chunks = [text_out[i:i+3500] for i in range(0, len(text_out), 3500)]
        for index, chunk in enumerate(chunks):
            if index == 0:
                safe_reply_to(message, chunk)
            else:
                bot.send_message(chat_id, chunk)
        return True
    if command == "help":
        safe_reply_to(message, "📚 <b>دستورات عمومی:</b> پینگ، آیدی، قوانین، آمار، هوش، راهنما\n<b>مدیریت (با ریپلای روی پیام عضو):</b> بن، رفع بن، سکوت، رفع سکوت، اخراج، اخطار، سنجاق، لغو سنجاق، حذف، پاکسازی، گزارش\n<b>تنظیمات:</b> ضدلینک، ضدتبلیغ، ضداسپم، ضدتکرار، قفل رسانه و انواع رسانه\n<b>اطلاعات گروه:</b> تغییر اسم و توضیحات با نوشتن متن جدید\nبرای فهرست کامل عبارت‌ها بنویس: «دستورات کامل»\nفرمان‌های مدیریتی فقط با مجوز مدیر گروه اجرا می‌شوند.")
        return True
    if command == "id":
        target = _reply_target(message) or uid
        safe_reply_to(message, f"🆔 شناسهٔ کاربر: <code>{target}</code>\nشناسهٔ گروه: <code>{chat_id}</code>")
        return True
    if command == "ping":
        safe_reply_to(message, "🏓 MASIH GUARD فعاله و پیام رو دریافت کرد.")
        return True
    if command == "rules":
        safe_reply_to(message, "📜 <b>قوانین گروه</b>\n" + esc(get_group_settings(chat_id).get("rules", "قوانینی تنظیم نشده است.")))
        return True
    if command == "gstats":
        gs = DATA.setdefault("group_stats", {}).get(str(chat_id), {})
        active = len(DATA.setdefault("active_members", {}).get(str(chat_id), {}))
        safe_reply_to(message, f"📊 <b>آمار این گروه</b>\nپیام‌ها: {int(gs.get('messages',0))}\nپیام‌های مسدودشده: {int(gs.get('blocked',0))}\nورودها: {int(gs.get('joins',0))}\nخروج‌ها: {int(gs.get('leaves',0))}\nکاربران دیده‌شده: {active}")
        return True
    if command.startswith("set_"):
        setting_action = command[4:]
        enabled = setting_action.endswith("_on")
        setting = setting_action[:-3] if enabled else setting_action[:-4]
        allowed_settings = {"anti_link", "anti_ads", "anti_tapchi", "anti_spam", "anti_repeat", "anti_forward", "media_lock", "farewell_on", "join_approval", "lock_photos", "lock_videos", "lock_files", "lock_stickers", "lock_voice", "lock_video_notes", "lock_mentions", "lock_hashtags", "lock_usernames", "phone_filter"}
        if setting not in allowed_settings:
            safe_reply_to(message, "⚠️ این تنظیم شناخته نشد.")
            return True
        if not user or not is_group_admin(chat_id, uid):
            safe_reply_to(message, "⛔ فقط مدیران گروه می‌توانند تنظیمات امنیتی را تغییر دهند.")
            return True
        # Do not enable moderation filters that the bot cannot enforce due to missing Telegram rights.
        deletion_filters = {"anti_link", "anti_ads", "anti_tapchi", "anti_spam", "anti_repeat", "anti_forward", "media_lock",
                            "lock_photos", "lock_videos", "lock_files", "lock_stickers", "lock_voice",
                            "lock_video_notes", "phone_filter", "lock_mentions", "lock_hashtags", "lock_usernames"}
        required_permission = "can_delete_messages" if setting in deletion_filters else (
            "can_restrict_members" if setting in {"captcha_on", "anti_raid_on"} else
            "can_invite_users" if setting == "join_approval" else "")
        if enabled and required_permission and not bot_has_group_permission(chat_id, required_permission):
            friendly = {"can_delete_messages": "حذف پیام‌ها", "can_restrict_members": "محدودکردن اعضا", "can_invite_users": "دعوت کاربران/مدیریت درخواست ورود"}.get(required_permission, required_permission)
            safe_reply_to(message, f"⚠️ برای فعال‌کردن این قابلیت، ربات باید مدیر گروه با مجوز «{friendly}» باشد. تنظیم تغییر نکرد.")
            return True
        get_group_settings(chat_id)[setting] = enabled
        save_data()
        add_log("group_setting_changed", chat_id, uid, f"{setting}={enabled}")
        safe_reply_to(message, f"✅ {esc(setting)}: {'روشن' if enabled else 'خاموش'}")
        return True
    if command == "report":
        if not getattr(message, "reply_to_message", None):
            safe_reply_to(message, "برای گزارش تخلف، روی پیام موردنظر ریپلای کن و «گزارش» را بفرست.")
            return True
        reported = message.reply_to_message
        add_log("user_report", chat_id, uid, f"reported_message={reported.message_id}; text={get_text(reported)[:180]}")
        try: bot.send_message(OWNER_ID, f"🚨 <b>گزارش تخلف</b>\nگروه: <code>{chat_id}</code>\nگزارش‌دهنده: <code>{uid}</code>\nپیام: <code>{reported.message_id}</code>\n{esc(get_text(reported)[:800])}")
        except Exception as e: print("Report owner notice error:", repr(e))
        safe_reply_to(message, "🚨 گزارش برای مالک ربات ارسال شد.")
        return True
    # Remaining actions change group state and therefore require a group admin.
    if not user or not is_group_admin(chat_id, uid):
        safe_reply_to(message, "⛔ این دستور فقط برای مدیران گروه است.")
        return True
    target = _reply_target(message)
    if command in {"ban", "mute", "unmute", "kick", "warn", "pin", "unpin", "delete"} and not target and command not in {"unban"}:
        if command in {"pin", "unpin", "delete"}:
            if not getattr(message, "reply_to_message", None):
                safe_reply_to(message, "برای این دستور روی پیام موردنظر ریپلای کن.")
                return True
        else:
            safe_reply_to(message, "برای هدف‌گرفتن کاربر، روی یکی از پیام‌های او ریپلای کن.")
            return True
    try:
        if command in {"ban", "mute", "kick", "warn"}:
            target_role = target_group_admin_status(chat_id, int(target))
            if target_role is True:
                safe_reply_to(message, "⛔ برای امنیت، مالک و مدیران گروه از این عملیات مستثنا هستند.")
                return True
            if target_role is None:
                safe_reply_to(message, "⚠️ نقش کاربر از تلگرام تأیید نشد؛ عملیات برای جلوگیری از اقدام اشتباه انجام نشد.")
                return True
        if command == "ban":
            bot.ban_chat_member(chat_id, int(target)); safe_reply_to(message, f"⛔ کاربر <code>{target}</code> مسدود شد.")
        elif command == "unban":
            target_id = int(target or args)
            bot.unban_chat_member(chat_id, target_id, only_if_banned=True); safe_reply_to(message, f"✅ مسدودیت <code>{target_id}</code> برداشته شد.")
        elif command == "mute":
            bot.restrict_chat_member(chat_id, int(target), permissions=types.ChatPermissions(can_send_messages=False))
            safe_reply_to(message, f"🔇 کاربر <code>{target}</code> سکوت شد.")
        elif command == "unmute":
            bot.restrict_chat_member(chat_id, int(target), permissions=types.ChatPermissions(can_send_messages=True, can_send_audios=True, can_send_documents=True, can_send_photos=True, can_send_videos=True, can_send_video_notes=True, can_send_voice_notes=True, can_send_polls=True, can_send_other_messages=True, can_add_web_page_previews=True))
            safe_reply_to(message, f"🔊 سکوت کاربر <code>{target}</code> برداشته شد.")
        elif command == "kick":
            bot.ban_chat_member(chat_id, int(target)); bot.unban_chat_member(chat_id, int(target), only_if_banned=True); safe_reply_to(message, f"👢 کاربر <code>{target}</code> از گروه اخراج شد.")
        elif command == "warn":
            warn_member(chat_id, int(target), args or "اخطار مدیر")
        elif command == "pin":
            bot.pin_chat_message(chat_id, message.reply_to_message.message_id); safe_reply_to(message, "📌 پیام سنجاق شد.")
        elif command == "unpin":
            if message.reply_to_message: bot.unpin_chat_message(chat_id, message.reply_to_message.message_id)
            else: bot.unpin_all_chat_messages(chat_id)
            safe_reply_to(message, "📌 سنجاق برداشته شد.")
        elif command == "delete":
            bot.delete_message(chat_id, message.reply_to_message.message_id); safe_reply_to(message, "🧹 پیام حذف شد.")
        elif command == "clean":
            amount = int(args) if args else 10
            if not 1 <= amount <= 100:
                safe_reply_to(message, "تعداد باید بین ۱ تا ۱۰۰ باشد."); return True
            rows = DATA.setdefault("message_history", {}).get(str(chat_id), [])[-amount:]
            deleted = 0
            for row in reversed(rows):
                try: bot.delete_message(chat_id, int(row["message_id"])); deleted += 1
                except Exception: pass
            safe_reply_to(message, f"🧹 {deleted} پیام حذف شد.")
        add_log("group_command", chat_id, uid, command)
        save_data()
    except (ValueError, TypeError):
        safe_reply_to(message, "⚠️ شناسه یا تعداد واردشده معتبر نیست.")
    except Exception as e:
        print("Group command error:", repr(e))
        safe_reply_to(message, "⚠️ انجام دستور ناموفق بود؛ دسترسی ادمین ربات و مجوزهای گروه را بررسی کن.")
    return True



def handle_group_info_request(message, text=None):
    """Change group title/description after checking requester and bot permissions."""
    raw = re.sub(r"[\u200c\s]+", " ", (text or "").strip()).replace("ي", "ی").replace("ك", "ک")
    if not raw:
        return False
    low = raw.casefold()
    is_description = bool(re.search(r"توضیح(?:ات)?\s*گروه|گروه.{0,12}توضیح", low))
    is_title = bool(re.search(r"(?:اسم|نام|عنوان)\s*گروه|گروه.{0,12}(?:اسم|نام|عنوان)", low))
    if not is_description and not is_title:
        return False
    target = ""
    if is_description:
        patterns = [
            r"(?:توضیح(?:ات)?)\s*گروه\s*(?:(?:را|رو)\s*)?(?:عوض\s*کن|تغییر\s*بده)\s*به\s+(.+)$",
            r"(?:توضیح(?:ات)?)\s*گروه\s*(?:(?:را|رو)\s*)?به\s+(.+)$",
            r"گروه\s*(?:(?:را|رو)\s*)?توضیح(?:ات)?\s*به\s+(.+)$",
        ]
    else:
        patterns = [
            r"(?:اسم|نام|عنوان)\s*گروه\s*(?:(?:را|رو)\s*)?(?:عوض\s*کن|تغییر\s*(?:نام\s*)?بده)\s*به\s+(.+)$",
            r"(?:اسم|نام|عنوان)\s*گروه\s*(?:(?:را|رو)\s*)?به\s+(.+)$",
            r"گروه\s*(?:(?:را|رو)\s*)?به\s+(.+)$",
            r"(?:اسم|نام|عنوان)\s*گروه\s*(?:(?:را|رو)\s*)?(?:بذار|بگذار|بکن|کن)\s+(.+)$",
        ]
    for pattern in patterns:
        match = re.search(pattern, raw, flags=re.IGNORECASE)
        if match:
            target = match.group(1).strip().strip("«»\\\"' ")
            target = re.sub(r"\s+(?:تغییر\s*(?:بده|ده)|عوض\s*کن|تغییر\s*نام\s*(?:بده|ده))$", "", target).strip()
            break
    if not target or target.casefold() in {"عوض کن", "تغییر بده", "تغییر نام بده", "بکن", "بذار"}:
        example = "توضیحات گروه رو به متن جدید تغییر بده" if is_description else "اسم گروه رو به نام جدید تغییر بده"
        safe_reply_to(message, f"✍️ {('متن توضیحات' if is_description else 'اسم جدید')} رو هم بنویس.\nمثال: «{example}»")
        return True
    max_length = 255 if is_description else 128
    if len(target) > max_length:
        safe_reply_to(message, f"⚠️ {'توضیحات' if is_description else 'اسم گروه'} حداکثر {max_length} نویسه می‌تواند باشد.")
        return True
    chat_id = message.chat.id
    user_id = getattr(getattr(message, "from_user", None), "id", 0)
    try:
        requester = bot.get_chat_member(chat_id, user_id)
        requester_status = getattr(requester, "status", "")
        if requester_status not in ("administrator", "creator") or (requester_status != "creator" and not getattr(requester, "can_change_info", False)):
            safe_reply_to(message, "⛔ برای تغییر نام یا توضیحات، باید مدیر گروه با مجوز «تغییر اطلاعات گروه» باشی.")
            return True
        me = bot.get_me()
        bot_member = bot.get_chat_member(chat_id, me.id)
        bot_status = getattr(bot_member, "status", "")
        if bot_status not in ("administrator", "creator") or (bot_status != "creator" and not getattr(bot_member, "can_change_info", False)):
            safe_reply_to(message, "⚠️ ربات باید مدیر گروه باشد و مجوز «تغییر اطلاعات گروه» داشته باشد.")
            return True
        if is_description:
            bot.set_chat_description(chat_id, target)
        else:
            bot.set_chat_title(chat_id, target)
        add_log("group_info_changed", chat_id, user_id, ("description=" if is_description else "title=") + target[:120])
        save_data()
        safe_reply_to(message, f"✅ {'توضیحات' if is_description else 'نام'} گروه تغییر کرد.")
    except Exception as e:
        print("Group info change error:", repr(e))
        safe_reply_to(message, "⚠️ تغییر انجام نشد. مجوز «تغییر اطلاعات گروه» ربات و مدیر درخواست‌دهنده را بررسی کن.")
    return True


def handle_ai_group_management(message, text=None):
    """Execute a small, explicit set of safe group-setting requests from AI replies."""
    normalized = (text or "").casefold().replace("ي", "ی").replace("ك", "ک")
    normalized = re.sub(r"[\u200c\s]+", "", normalized)
    patterns = [
        (("قفللینک", "ضدلینک"), "anti_link"),
        (("قفلتبلیغ", "ضدتبلیغ"), "anti_ads"),
        (("قفلتبچی", "قفل تپچی", "ضدتبچی", "ضدتپچی"), "anti_tapchi"),
        (("ضداسپم", "قفلاسپم"), "anti_spam"),
        (("ضدتکرار", "قفلپیامتکراری"), "anti_repeat"),
        (("قفلرسانه", "قفرسانه"), "media_lock"),
        (("قفلعکس", "قفلتصویر"), "lock_photos"),
        (("قفلفیلم", "قفلویدیو", "قفلکلیپ"), "lock_videos"),
        (("قفلفایل", "قفلمدرک"), "lock_files"),
        (("قفلاستیکر", "قفلگیف"), "lock_stickers"),
        (("قفلویس", "قفلصوت", "قفلپیامصوتی"), "lock_voice"),
        (("قفلپیامگرد", "قفلیدئویگرد"), "lock_video_notes"),
        (("فیلترشماره", "قفلشمارهتماس"), "phone_filter"),
        (("قفلتگ", "قفلمنشن", "قفلمنشنها"), "lock_mentions"),
        (("قفلهاشتگ", "قفلهشتگها"), "lock_hashtags"),
        (("قفلنامکاربری", "قفلآیدی", "قفل یوزرنیم"), "lock_usernames"),
        (("خوشامدگویی", "خوشامد"), "welcome_on"),
        (("خداحافظی",), "farewell_on"),
    ]
    target_setting = None
    for phrases, setting in patterns:
        if any(phrase in normalized for phrase in phrases):
            target_setting = setting
            break
    if not target_setting:
        return False
    if target_setting == "welcome_on":
        safe_reply_to(message, "👋 خوشامدگویی این گروه قابلیت پایهٔ MASIH GUARD است و همیشه فعال می‌ماند؛ برای آن دکمهٔ خاموش‌کردن وجود ندارد.")
        return True
    off_words = ("خاموش", "غیرفعال", "بازکن", "بردار", "غیرفعالشکن", "خاموششکن")
    on_words = ("روشن", "فعال", "ببند", "قفلکن", "فعال‌شکن")
    is_off = any(word in normalized for word in off_words)
    is_on = any(word in normalized for word in on_words)
    if not is_off and not is_on:
        safe_reply_to(message, "می‌خوای این تنظیم روشن بشه یا خاموش؟ لطفاً «روشن کن» یا «خاموش کن» رو مشخص کن.")
        return True
    user_id = getattr(getattr(message, "from_user", None), "id", 0)
    chat_id = message.chat.id
    if not is_group_admin(chat_id, user_id):
        safe_reply_to(message, "⛔ برای تغییر تنظیمات امنیتی باید مدیر همین گروه باشی.")
        return True
    enabled = bool(is_on and not is_off)
    if enabled and target_setting in {"anti_link", "anti_ads", "anti_tapchi", "anti_spam", "anti_repeat", "anti_forward", "media_lock", "lock_photos", "lock_videos", "lock_files", "lock_stickers", "lock_voice", "lock_video_notes", "phone_filter", "lock_mentions", "lock_hashtags", "lock_usernames"}:
        try:
            me = bot.get_me()
            member = bot.get_chat_member(chat_id, me.id)
            member_status = getattr(member, "status", "")
            if member_status not in ("administrator", "creator") or (member_status != "creator" and not getattr(member, "can_delete_messages", False)):
                safe_reply_to(message, "⚠️ برای فعال‌کردن این فیلتر، ربات باید مدیر گروه با مجوز حذف پیام باشد.")
                return True
        except Exception:
            safe_reply_to(message, "⚠️ نتونستم مجوزهای ربات رو بررسی کنم؛ فعلاً تنظیم رو تغییر ندادم.")
            return True
    get_group_settings(chat_id)[target_setting] = enabled
    save_data()
    add_log("ai_group_setting_changed", chat_id, user_id, f"{target_setting}={enabled}")
    label = {
        "anti_link": "قفل لینک", "anti_ads": "ضدتبلیغ", "anti_tapchi": "قفل تبچی", "anti_spam": "ضداسپم",
        "anti_repeat": "ضدتکرار", "media_lock": "قفل رسانه",
        "welcome_on": "خوشامدگویی", "farewell_on": "خداحافظی",
        "lock_photos": "قفل عکس", "lock_videos": "قفل فیلم", "lock_files": "قفل فایل",
        "lock_stickers": "قفل استیکر/گیف", "lock_voice": "قفل ویس", "lock_video_notes": "قفل ویدئوی گرد",
        "phone_filter": "فیلتر شماره تماس", "lock_mentions": "قفل تگ/منشن",
        "lock_hashtags": "قفل هشتگ", "lock_usernames": "قفل نام‌کاربری"
    }.get(target_setting, target_setting)
    safe_reply_to(message, f"✅ {label} {'روشن' if enabled else 'خاموش'} شد.")
    return True


def tag_menu_keyboard():
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.row(types.InlineKeyboardButton("👥 اعضای شناخته‌شده", callback_data="tagmenu:all"),
           types.InlineKeyboardButton("⚡ فعال‌های ۲۴ ساعت", callback_data="tagmenu:active"))
    kb.row(types.InlineKeyboardButton("👑 مدیران گروه", callback_data="tagmenu:admins"),
           types.InlineKeyboardButton("🌙 کم‌فعال‌ها", callback_data="tagmenu:low"))
    kb.row(types.InlineKeyboardButton("🔢 انتخاب تعداد", callback_data="tagmenu:count"))
    return kb


def tag_count_keyboard(mode):
    kb = types.InlineKeyboardMarkup(row_width=3)
    buttons = [
        types.InlineKeyboardButton("۲۰ نفر", callback_data=f"tagrun:{mode}:20"),
        types.InlineKeyboardButton("۵۰ نفر", callback_data=f"tagrun:{mode}:50"),
        types.InlineKeyboardButton("۱۰۰ نفر", callback_data=f"tagrun:{mode}:100"),
        types.InlineKeyboardButton("۲۰۰ نفر", callback_data=f"tagrun:{mode}:200"),
        types.InlineKeyboardButton("همهٔ موجود", callback_data=f"tagrun:{mode}:0"),
    ]
    for b in buttons: kb.add(b)
    kb.add(types.InlineKeyboardButton("⬅️ برگشت", callback_data="tagmenu:back"))
    return kb


def run_tag_selection(chat_id, requester_id, mode, requested_count):
    """Mention only users the bot has observed or can fetch as group admins."""
    group_key = str(chat_id)
    activity = DATA.setdefault("activity_stats", {}).setdefault(group_key, {})
    known_ids = set(DATA.setdefault("active_members", {}).setdefault(group_key, {}).keys()) | set(activity.keys())
    known_ids.discard(str(requester_id))
    now = time.time()
    if mode == "admins":
        try:
            selected_ids = [str(a.user.id) for a in bot.get_chat_administrators(chat_id) if not getattr(a.user, "is_bot", False)]
            selected_ids = [x for x in selected_ids if x != str(requester_id)]
        except Exception:
            return "⚠️ نتونستم فهرست مدیران را از تلگرام بگیرم؛ دوباره تلاش کن."
    elif mode == "active":
        selected_ids = [x for x in known_ids if now - float(activity.get(x, {}).get("last_at", DATA["active_members"].get(group_key, {}).get(x, 0)) or 0) <= 86400]
    elif mode == "low":
        selected_ids = sorted(known_ids, key=lambda x: (int(activity.get(x, {}).get("messages", 0) or 0), float(activity.get(x, {}).get("last_at", 0) or 0)))
    else:
        selected_ids = sorted(known_ids, key=lambda x: float(activity.get(x, {}).get("last_at", DATA["active_members"].get(group_key, {}).get(x, 0)) or 0), reverse=True)
    # Avoid an accidental flood; a single action can mention at most 200 known users.
    cap = 200
    if requested_count > 0:
        selected_ids = selected_ids[:min(requested_count, cap)]
    else:
        selected_ids = selected_ids[:cap]
    if not selected_ids:
        return "ℹ️ هنوز عضوی برای این فهرست ثبت نشده یا در بازهٔ انتخابی فعالیتی دیده نشده است. آمار از زمان فعال‌بودن ثبت ربات جمع می‌شود."
    chunks = [selected_ids[i:i+20] for i in range(0, len(selected_ids), 20)]
    sent = 0
    for ci, chunk in enumerate(chunks, 1):
        mentions = []
        for member_id in chunk:
            try:
                cm = bot.get_chat_member(chat_id, int(member_id)); user = cm.user
                name = " ".join(x for x in [getattr(user, "first_name", ""), getattr(user, "last_name", "")] if x).strip() or "عضو"
            except Exception:
                name = "عضو"
            mentions.append(f'<a href="tg://user?id={int(member_id)}">{esc(name)}</a>')
        try:
            bot.send_message(chat_id, f"🏷️ <b>تگ اعضا {ci}/{len(chunks)}</b>\n" + " ، ".join(mentions), disable_web_page_preview=True)
            sent += len(chunk)
        except Exception as exc:
            print("Tag send error:", repr(exc))
            break
    add_log("group_tag", chat_id, requester_id, f"mode={mode}; requested={requested_count}; sent={sent}")
    return f"✅ تگ انجام شد: {sent} نفر در دسته‌های حداکثر ۲۰ نفره.\nℹ️ تلگرام فهرست کامل اعضا را آزادانه ارائه نمی‌کند؛ «همه» یعنی همهٔ اعضای قابل‌شناسایی ثبت‌شده، تا سقف ایمنی ۲۰۰ نفر."


def group_message_handler(message):
    try:
        text = get_text(message)
        normalized_text = (text or "").strip().casefold().replace("ي", "ی").replace("ك", "ک")
        # Group creator/admin commands may be written naturally with or without addressing the bot.
        command_text = _strip_group_bot_prefix(text)
        first_token = normalized_text.split(maxsplit=1)[0] if normalized_text else ""
        if first_token.split("@", 1)[0] == "/mylink":
            uid = getattr(getattr(message, "from_user", None), "id", 0)
            if not is_group_licensed(message.chat.id):
                safe_reply_to(message, "⚠️ برای استفاده از لینک دعوت اختصاصی، مجوز گروه باید فعال باشد.")
                return
            if not get_group_settings(message.chat.id).get("force_add_on"):
                safe_reply_to(message, "ℹ️ اد اجباری در این گروه خاموش است.")
                return
            link, error = track_force_invite_link(message.chat.id, uid)
            if error:
                safe_reply_to(message, "⚠️ " + esc(error))
            else:
                cfg = get_group_settings(message.chat.id)
                required = max(1, min(100, int(cfg.get("force_add_count", 3) or 3)))
                current = force_add_count(message.chat.id, uid)
                safe_reply_to(message, "🔗 لینک دعوت اختصاصی شما:\n" + esc(link) + f"\n📊 دعوت ثبت‌شده: {current}/{required}\nدعوت‌ها فقط وقتی شمرده می‌شوند که عضو جدید با همین لینک وارد شود.")
            return
        if first_token.split("@", 1)[0] == "/start":
            safe_reply_to(message, group_start_guide(getattr(message.chat, "title", "گروه")))
            return
        if enforce_group_entry_gates(message):
            return
        if re.sub(r"[\s‌]+", "", normalized_text) in {"پنل", "پنلمدیریت", "تنظیماتگروه", "panel", "settings", "پنلگروه"}:
            uid = getattr(getattr(message, "from_user", None), "id", 0)
            send_group_panel(message.chat.id, user_id=uid)
            return
        # Owner activates the current group directly; no group ID needs to be copied.
        normalized_activation = normalized_text.translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789"))
        activation_match = re.fullmatch(r"فعال(?:\s|\u200c)*سازی\s+(\d+)\s*(?:روز(?:ه)?|روزِ)?", normalized_activation)
        if activation_match:
            uid = getattr(getattr(message, "from_user", None), "id", 0)
            if not is_bot_admin(uid):
                safe_reply_to(message, "⛔ فقط مالک اصلی یا ادمین فروشِ ثبت‌شده می‌تواند اشتراک گروه را فعال کند.")
                return
            days = int(activation_match.group(1))
            if not 0 <= days <= 3650:
                safe_reply_to(message, "⚠️ تعداد روز باید بین ۰ تا ۳۶۵۰ باشد؛ عدد ۰ یعنی دائمی.")
                return
            if not is_owner(uid) and days == 0:
                safe_reply_to(message, "🔐 ادمین فروش نمی‌تواند مجوز دائمی بدهد؛ برای امنیت، فقط مالک اصلی می‌تواند فعال‌سازی دائمی انجام دهد.")
                return
            if not is_owner(uid) and days > 365:
                safe_reply_to(message, "🔐 ادمین فروش حداکثر می‌تواند مجوز ۳۶۵ روزه فعال کند؛ مدت بیشتر فقط با مالک اصلی است.")
                return
            try:
                me = bot.get_me()
                member = bot.get_chat_member(message.chat.id, me.id)
                if getattr(member, "status", "") not in ("administrator", "creator"):
                    safe_reply_to(message, "⚠️ برای فعال‌سازی، ابتدا ربات را مدیر همین گروه کن.")
                    return
            except Exception as check_error:
                print("Group activation permission check error:", repr(check_error))
                safe_reply_to(message, "⚠️ نتونستم حضور و مجوز ربات رو بررسی کنم؛ تنظیمات مدیر ربات رو بررسی کن.")
                return
            from datetime import timedelta
            now = datetime.now()
            expires = "" if days == 0 else (now + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
            DATA.setdefault("group_licenses", {})[str(message.chat.id)] = {
                "approved": True, "expires": expires, "activated_by": uid, "updated": now_text()
            }
            DATA.setdefault("group_requests", {}).pop(str(message.chat.id), None)
            add_log("group_license_activated_in_group", message.chat.id, uid, f"days={days}")
            save_data()
            safe_reply_to(message, "🛡️ <b>فعال‌سازی MASIH GUARD موفق بود</b>\n"
                         f"✅ اشتراک این گروه فعال شد.\n⭐ مدت: {'دائمی' if days == 0 else str(days) + ' روز'}\n"
                         f"📅 پایان اعتبار: {esc(expires or 'دائمی')}\n"
                         "🌈 تنظیمات این گروه از این پس جداگانه ذخیره می‌شوند.")
            return
        # Reply to a proxy message and write «ثبت پروکسی» to store that exact link.
        proxy_command = re.sub(r"[\s‌]+", "", normalized_text)
        if proxy_command in {"ثبتپروکسی", "registerproxy"}:
            uid = getattr(getattr(message, "from_user", None), "id", 0)
            if not is_owner(uid):
                safe_reply_to(message, "⛔ ثبت پروکسی فقط برای مالک ربات مجاز است.")
                return
            replied = getattr(message, "reply_to_message", None)
            raw_proxy = ((getattr(replied, "text", None) or getattr(replied, "caption", None) or "").strip() if replied else "")
            candidates = re.findall(r"""(?:https?://|tg://)[^\s<>"']+""", raw_proxy)
            candidates = [x.rstrip(".,،؛!؟)]}") for x in candidates]
            proxy = next((x for x in candidates if proxy_endpoint(x)), raw_proxy if proxy_endpoint(raw_proxy) else "")
            if not proxy:
                safe_reply_to(message, "⚠️ روی پیامی که لینک پروکسی دارد ریپلای کن و بنویس «ثبت پروکسی».")
            elif proxy in DATA["proxies"]:
                safe_reply_to(message, "ℹ️ این پروکسی قبلاً ثبت شده است.")
            elif len(DATA["proxies"]) >= 20:
                safe_reply_to(message, "⚠️ ظرفیت ۲۰ پروکسی پر شده؛ ابتدا یکی را حذف کن.")
            else:
                DATA["proxies"].append(proxy)
                save_data()
                add_log("proxy_added", message.chat.id, uid, "پروکسی با ریپلای ثبت شد")
                ping = proxy_ping_ms(proxy)
                safe_reply_to(message, "✅ پروکسیِ پیام ریپلای‌شده ثبت شد." +
                             (f"\n🟢 پاسخ TCP: {ping} ms" if ping is not None else "\n⚠️ لینک ذخیره شد، اما اتصال TCP فعلاً پاسخ نداد."))
            return
        # Public group commands are handled before the license gate.
        compact_public = re.sub(r"[\s‌]+", "", normalized_text)
        if compact_public in {"راهنما", "help", "commands", "دستورات"}:
            safe_reply_to(message, "📚 <b>راهنمای گروه</b>\n• «پنل» — پنل تنظیمات همین گروه\n• «قوانین» — نمایش قوانین\n• «آمار» — آمار پایه\n• برای اقدام روی عضو، روی پیام او ریپلای کن.\n⚠️ امکانات حفاظتی به مجوز گروه و دسترسی ادمین ربات نیاز دارند.")
            return
        if compact_public in {"قوانین", "قانون", "rules"}:
            safe_reply_to(message, esc(get_group_settings(message.chat.id).get("rules", "قوانینی ثبت نشده است.")))
            return
        if compact_public in {"آمار", "آمارگروه", "stats"}:
            safe_reply_to(message, f"📊 <b>آمار گروه</b>\n💬 پیام‌ها: {DATA['stats'].get('messages', 0)}\n🚫 موارد مسدودشده: {DATA['stats'].get('blocked', 0)}\n⚠️ اخطارها: {DATA['stats'].get('warns', 0)}")
            return
        if compact_public in {"بازی", "یهبازی", "بازیها", "بازی ها", "game", "play"}:
            send_random_game(message)
            return
        if not is_group_licensed(message.chat.id):
            # Keep the bot inert in unlicensed groups and notify once per group.
            req = DATA.setdefault("group_requests", {})
            key = str(message.chat.id)
            last = req.get(key, 0)
            if time.time() - float(last or 0) > 86400:
                req[key] = time.time(); save_data()
                try: bot.send_message(message.chat.id, group_install_message(message.chat.id, getattr(message.chat,"title", "این گروه")), reply_markup=support_contact_markup())
                except Exception: pass
            return
        if command_text and handle_group_info_request(message, command_text):
            return
        compact_group = re.sub(r"[\s‌]+", "", normalized_text)
        # Basic commands stay responsive before the group license gate.
        if compact_group in {"راهنما", "help", "commands", "دستورات"}:
            safe_reply_to(message, "📚 <b>راهنمای گروه</b>\n• «پنل» — پنل تنظیمات همین گروه\n• «قوانین» — نمایش قوانین\n• «آمار» — آمار پایه\n• برای اقدام روی عضو، روی پیام او ریپلای کن.\n⚠️ امکانات حفاظتی به مجوز گروه و دسترسی ادمین ربات نیاز دارند.")
            return
        if compact_group in {"قوانین", "قانون", "rules"}:
            safe_reply_to(message, esc(get_group_settings(message.chat.id).get("rules", "قوانینی ثبت نشده است.")))
            return
        if compact_group in {"آمار", "آمارگروه", "stats"}:
            safe_reply_to(message, f"📊 <b>آمار گروه</b>\n💬 پیام‌ها: {DATA['stats'].get('messages', 0)}\n🚫 موارد مسدودشده: {DATA['stats'].get('blocked', 0)}\n⚠️ اخطارها: {DATA['stats'].get('warns', 0)}")
            return
        if compact_group in {"پروکسی", "لیستپروکسی", "لیستپروکسیها", "پروکسیها", "پروکسیلیست", "پروکسیلیستها", "proxy", "proxies", "proxylist"}:
            safe_reply_to(message, proxy_list_text(limit=20, with_ping=True)); return
        if compact_group in {"فونت", "لیستفونت", "فونتها", "لیستفونتها", "فونتلیست", "فونتلیستها", "فونت۲۰۰", "فونت200", "font", "fonts", "fontlist"}:
            safe_reply_to(message, "🔤 متن یا اسم دلخواهت رو در پیوی ربات بفرست تا ۲۰۰ مدل فونت فانتزی بسازم."); return
        # «تگ» opens a selection menu; it never tags a guessed list immediately.
        tag_match = re.fullmatch(r"(?:تگ|تگکن|منشن)(?:\s*\d{1,3})?", normalized_text.replace("‌", " ").strip())
        if tag_match:
            uid = getattr(getattr(message, "from_user", None), "id", 0)
            if not is_group_admin(message.chat.id, uid):
                safe_reply_to(message, "⛔ منوی تگ گروهی فقط برای مدیران گروه مجاز است."); return
            safe_reply_to(message, "🏷️ <b>تگ هوشمند اعضای گروه</b>\nانتخاب کن چه کسانی تگ شوند. فعالیت‌ها از زمان ثبت‌شدن توسط ربات محاسبه می‌شوند.", reply_markup=tag_menu_keyboard())
            return
        if normalized_text in {"ربات", "دستیار", "هوش", "هوش مصنوعی"}:
            safe_reply_to(message, "جانم! 🌹 برای سؤال، بنویس «ربات سؤال تو» یا «هوش سؤال تو». برای تغییر تنظیمات، دستور را روشن و واضح بنویس؛ مثلاً «قفل لینک روشن کن». ")
            return
        # Allow supported Persian group-management commands without requiring a reply to the bot.
        if command_text and handle_ai_group_management(message, command_text):
            return
        # AI can be activated by replying to the bot or by starting with «هوش»، «ربات» or «دستیار».
        global BOT_USERNAME, BOT_ID
        try:
            if not BOT_ID or not BOT_USERNAME:
                me = bot.get_me()
                BOT_ID = getattr(me, "id", 0) or BOT_ID
                BOT_USERNAME = (getattr(me, "username", "") or "").casefold() or BOT_USERNAME
        except Exception:
            pass
        bot_id = BOT_ID or None
        replied = getattr(message, "reply_to_message", None)
        reply_to_bot = bool(replied and getattr(getattr(replied, "from_user", None), "is_bot", False)
                            and (getattr(getattr(replied, "from_user", None), "id", None) == bot_id
                                 or (BOT_USERNAME and (getattr(getattr(replied, "from_user", None), "username", "") or "").casefold() == BOT_USERNAME)))
        ai_question = ""
        if text and text.strip() and not text.strip().startswith("/"):
            raw_text = text.strip()
            normalized_ai = raw_text.casefold().replace("ي", "ی").replace("ك", "ک")
            if reply_to_bot:
                ai_question = raw_text
            else:
                prefixes = ("از ربات بپرس ", "دستیار ", "ربات ", "هوش مصنوعی ", "هوش ", "هوش‌ ", "هش ", "هوس ", "هوشصنعتی ", "masih guard ", "masihguard ")
                for prefix in prefixes:
                    if normalized_ai.startswith(prefix):
                        ai_question = raw_text[len(prefix):].strip()
                        break
                # Also respond to direct mentions of the bot, without answering every unrelated group message.
                mention_only = False
                if not ai_question and BOT_USERNAME and ("@" + BOT_USERNAME) in normalized_ai:
                    ai_question = re.sub(r"@" + re.escape(BOT_USERNAME), "", raw_text, flags=re.I).strip(" ,،:؛!?؟")
                    mention_only = not bool(ai_question)
                named_bot_only = False
                if not ai_question and any(name in normalized_ai for name in ("masih guard", "masihguard", "مسیح گارد", "ماسیح گارد", "ماسح گارد")):
                    ai_question = re.sub(r"(?i)masih\s*guard|masihguard|مسیح\s*گارد|ماسیح\s*گارد|ماسح\s*گارد", "", raw_text).strip(" ,،:؛!?؟")
                    named_bot_only = not bool(ai_question)
                # Feature questions can be asked naturally without a fixed command prefix.
                feature_terms = ("ضد لینک", "ضدلینک", "ضد اسپم", "ضداسپم", "کپچا", "پنل", "قوانین", "قانون", "آمار", "بازی", "فونت", "پروکسی", "خوشامد", "امنیت گروه", "امکانات ربات", "ربات چیکار", "ربات چکار")
                question_cues = ("چطور", "چجوری", "چگونه", "چرا", "چیه", "چیست", "میشه", "می‌شه", "راهنما", "کمک", "امکانات", "توضیح", "بگو", "چکار", "چیکار", "کار می کنه", "کار می‌کنه")
                action_cues = ("روشن کن", "خاموش کن", "فعال کن", "غیرفعال کن", "قفل کن", "باز کن", "تغییر بده", "بن کن", "سکوت کن", "اخراج کن", "حذف کن", "تنظیم کن")
                if not ai_question and any(term in normalized_ai for term in feature_terms) and any(cue in normalized_ai for cue in question_cues) and not any(cue in normalized_ai for cue in action_cues):
                    ai_question = raw_text
                if named_bot_only or mention_only:
                    safe_reply_to(message, "جانم؟ 🌈 دربارهٔ امکانات، امنیت گروه یا پنل چی می‌خوای بدونی؟")
                    return
                if not ai_question and normalized_ai.strip() in {"ربات", "هوش", "هوش مصنوعی", "دستیار", "masih guard", "masihguard"}:
                    safe_reply_to(message, "جانم؟ 🌈 سؤالت رو هم بنویس تا راهنمایی‌ات کنم.")
                    return
            if ai_question:
                # If the user prefixed a real implemented command with “ربات”, run the command path,
                # not a text-only AI answer. All operations still verify admin and bot permissions.
                if ai_question and _handle_group_shortcut(message, ai_question):
                    return
                if not ai_question:
                    return
                if not ai_question.strip():
                    safe_reply_to(message, "جانم؟ دربارهٔ چه چیزی راهنمایی می‌خوای؟")
                    return
                status = safe_reply_to(message, "🧠 دارم بررسی می‌کنم…")
                answer = ask_ai(ai_question)
                try: bot.edit_message_text(esc(answer[:3900]), status.chat.id, status.message_id)
                except Exception: safe_reply_to(message, esc(answer[:3900]))
                return
        # Track group activity and bounded message history for selected statistics/cleanup features.
        track_group_activity(message.chat.id, getattr(message.from_user,"id",0), message.message_id)
        if command_text and _handle_group_shortcut(message, command_text):
            save_data()
            return
        # Group management shortcuts work only for admins and licensed groups.
        if text and text.split()[0].split("@",1)[0] in {"/pin","/unpin","/clean","/cleanuser","/gstats","/report"}:
            cmd=text.split()[0].split("@",1)[0]
            if not is_group_admin(message.chat.id, message.from_user.id):
                safe_reply_to(message,"⛔ این فرمان فقط برای مدیران گروه است."); return
            if cmd=="/gstats":
                gs=DATA.setdefault("group_stats",{}).get(str(message.chat.id),{})
                active=len(DATA.setdefault("active_members",{}).get(str(message.chat.id),{}))
                safe_reply_to(message, f"📊 <b>آمار این گروه</b>\nپیام‌های ثبت‌شده: {int(gs.get('messages',0))}\nپیام‌های مسدودشده: {int(gs.get('blocked',0))}\nورودها: {int(gs.get('joins',0))}\nخروج‌ها: {int(gs.get('leaves',0))}\nکاربران دیده‌شده: {active}")
                return
            if cmd=="/report":
                if not message.reply_to_message:
                    safe_reply_to(message,"برای گزارش تخلف، به پیام موردنظر پاسخ بده و /report را بفرست."); return
                reported=message.reply_to_message
                detail=f"گزارش توسط {message.from_user.id}; پیام {reported.message_id}; متن={get_text(reported)[:180]}"
                add_log("user_report",message.chat.id,message.from_user.id,detail)
                try: bot.send_message(OWNER_ID,"🚨 <b>گزارش تخلف از گروه</b>\nگروه: <code>"+str(message.chat.id)+"</code>\nگزارش‌دهنده: <code>"+str(message.from_user.id)+"</code>\nپیام: <code>"+str(reported.message_id)+"</code>\n"+esc(get_text(reported)[:800]))
                except Exception as report_error: print("Report owner notice error:",repr(report_error))
                safe_reply_to(message,"🚨 گزارش برای مالک ربات ارسال شد."); return
            if cmd=="/pin":
                if not message.reply_to_message: safe_reply_to(message,"برای سنجاق، به پیام موردنظر پاسخ بده و /pin را بفرست."); return
                bot.pin_chat_message(message.chat.id,message.reply_to_message.message_id)
                add_log("message_pinned",message.chat.id,message.from_user.id,str(message.reply_to_message.message_id))
                safe_reply_to(message,"📌 پیام سنجاق شد."); return
            if cmd=="/unpin":
                if message.reply_to_message: bot.unpin_chat_message(message.chat.id,message.reply_to_message.message_id)
                else: bot.unpin_all_chat_messages(message.chat.id)
                add_log("message_unpinned",message.chat.id,message.from_user.id,"برداشتن سنجاق")
                safe_reply_to(message,"📌 سنجاق پیام برداشته شد."); return
            if cmd=="/clean":
                try: amount=int(text.split(maxsplit=1)[1])
                except Exception: amount=10
                if not 1<=amount<=100: safe_reply_to(message,"تعداد باید بین ۱ تا ۱۰۰ باشد."); return
                ids=[x["message_id"] for x in DATA["message_history"][str(message.chat.id)][-amount:]]
                deleted=0
                for mid in reversed(ids):
                    try: bot.delete_message(message.chat.id,mid); deleted+=1
                    except Exception: pass
                safe_reply_to(message,f"🧹 {deleted} پیام حذف شد."); add_log("messages_cleaned",message.chat.id,message.from_user.id,str(deleted)); return
            if cmd=="/cleanuser":
                parts=text.split()
                if len(parts)<2: safe_reply_to(message,"قالب: /cleanuser شناسه_کاربر [تعداد]"); return
                try: target_user=int(parts[1]); amount=int(parts[2]) if len(parts)>2 else 20
                except ValueError: safe_reply_to(message,"شناسه و تعداد باید عدد باشند."); return
                if not 1<=amount<=100: safe_reply_to(message,"تعداد باید بین ۱ تا ۱۰۰ باشد."); return
                rows=[x for x in DATA["message_history"][str(message.chat.id)] if int(x.get("user_id",0))==target_user][-amount:]
                deleted=0
                for row in reversed(rows):
                    try: bot.delete_message(message.chat.id,int(row["message_id"])); deleted+=1
                    except Exception: pass
                safe_reply_to(message,f"🧹 {deleted} پیام قابل‌حذف از عضو موردنظر پاک شد."); add_log("member_messages_cleaned",message.chat.id,message.from_user.id,f"target={target_user}, deleted={deleted}"); return
        DATA["stats"]["messages"]+=1
        # Track only activity observed from actual messages; Telegram does not expose a full member list.
        activity_uid = getattr(getattr(message, "from_user", None), "id", None)
        if activity_uid and not getattr(message.from_user, "is_bot", False):
            group_key, member_key = str(message.chat.id), str(activity_uid)
            DATA.setdefault("active_members", {}).setdefault(group_key, {})[member_key] = time.time()
            group_activity = DATA.setdefault("activity_stats", {}).setdefault(group_key, {})
            activity_record = group_activity.setdefault(member_key, {"messages": 0, "last_at": 0})
            activity_record["messages"] = int(activity_record.get("messages", 0) or 0) + 1
            activity_record["last_at"] = time.time()
        if process_group_security(message): return
        if text:
            settings=get_group_settings(message.chat.id)
            note_match = re.fullmatch(r"#([\w\u0600-\u06ff-]{1,40})", text.strip())
            if note_match:
                note_name = note_match.group(1).lower()
                note_value = settings.get("notes", {}).get(note_name)
                if note_value is not None:
                    safe_reply_to(message, "📝 <b>" + esc(note_name) + "</b>\n" + esc(note_value))
                    return
            handled=False
            for keyword,reply in settings.get("auto_replies",{}).items():
                if keyword and keyword.casefold() in text.casefold():
                    safe_reply_to(message,str(reply)[:4000]); handled=True; break
            if not handled and text.startswith("!"):
                command=text[1:].split(maxsplit=1)[0].casefold()
                response=settings.get("custom_commands",{}).get(command)
                if response: safe_reply_to(message,str(response)[:4000])
        save_data()
    except Exception as e: print("Group handler error:",repr(e))

def welcome_card(chat_id, member):
    """Build a fresh welcome card using the current group title and configured local timezone."""
    try:
        count = bot.get_chat_member_count(chat_id)
    except Exception:
        count = "نامشخص"
    try:
        # Fetch fresh chat metadata on every welcome so renamed groups show the new title.
        chat = bot.get_chat(chat_id)
        group_title = getattr(chat, "title", None) or "گروه"
    except Exception:
        group_title = "گروه"
    stamp = local_now()
    raw_name = member.first_name or "دوست عزیز"
    name = f'<a href="tg://user?id={int(member.id)}">{esc(raw_name)}</a>'
    uname = ("@" + esc(member.username)) if getattr(member, "username", None) else "ندارد"
    date_text = persian_digits(stamp.strftime("%Y-%m-%d"))
    time_text = persian_digits(stamp.strftime("%H:%M:%S"))
    count_text = persian_digits(count) if isinstance(count, int) else str(count)
    return ("⚡ <b>مدیریت گروه | 𝑴𝒂𝒔𝒊𝒉 𝑯𝒂𝒄𝒌𝒆𝒓𝒊𝒏𝒈</b> ⚡\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"🏷️ <b>گروه:</b> {esc(group_title)}\n"
            "🚀 <b>عضو جدید وارد شد!</b>\n\n"
            f"👤 <b>نام کاربر:</b> {name}\n"
            f"🆔 <b>آیدی:</b> <code>{int(member.id)}</code>\n"
            f"🔖 <b>شناسه:</b> {uname}\n"
            f"📅 <b>تاریخ ورود:</b> {date_text}\n"
            f"🕒 <b>ساعت ورود:</b> {time_text}\n"
            f"👥 <b>تعداد اعضا:</b> {count_text}\n\n"
            "🛡️ <b>سامانهٔ امنیت گروه فعال است</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "<i>قدرت مدیریت گروه با مدیریت گروه | 𝑴𝒂𝒔𝒊𝒉 𝑯𝒂𝒄𝒌𝒆𝒓𝒊𝒏𝒈</i>")


@bot.my_chat_member_handler()
def bot_added_or_removed(update):
    """Unapproved group additions are notified and the bot leaves instead of running for free."""
    try:
        chat = update.chat
        if not chat or chat.type not in ("group", "supergroup"):
            return
        new_status = getattr(getattr(update, "new_chat_member", None), "status", "")
        old_status = getattr(getattr(update, "old_chat_member", None), "status", "")
        if new_status in ("member", "administrator") and old_status in ("left", "kicked") and not is_group_licensed(chat.id):
            DATA.setdefault("group_requests", {})[str(chat.id)] = {"title":getattr(chat,"title", ""),"requested":now_text(),"status":"pending"}; save_data()
            try:
                bot.send_message(OWNER_ID, "📨 <b>درخواست نصب گروه</b>\nنام: " + esc(getattr(chat,"title", "بدون نام")) + f"\nشناسه: <code>{chat.id}</code>\nبرای فعال‌سازی از پنل بخش «مجوز نصب گروه‌ها» استفاده کن.")
            except Exception as owner_error:
                print("Owner group request notice error:", repr(owner_error))
            try:
                bot.send_message(chat.id, group_install_message(chat.id, getattr(chat,"title", "این گروه")), reply_markup=support_contact_markup())
            except Exception as group_notice_error:
                print("Unlicensed group notice error:", repr(group_notice_error))
            # Stay in the group but remain inert until the owner approves its license.
            # This allows the group to receive the one activation confirmation later.
    except Exception as e:
        print("Group license handler error:", repr(e))

@bot.message_handler(content_types=["new_chat_members"], func=lambda m: m.chat.type in ("group","supergroup"))
def welcome_new_members(message):
    if not is_group_licensed(message.chat.id): return
    s=get_group_settings(message.chat.id)
    chat_id = int(message.chat.id)
    join_key = str(chat_id)
    now_ts = time.time()
    join_times = [float(t) for t in DATA.setdefault("join_times", {}).get(join_key, []) if now_ts - float(t) <= 30]
    join_times.extend([now_ts] * len(message.new_chat_members))
    DATA.setdefault("join_times", {})[join_key] = join_times[-100:]
    raid_triggered = bool(s.get("anti_raid_on") and len(join_times) >= 8 and float(s.get("raid_mode_until", 0) or 0) <= now_ts)
    if raid_triggered:
        s["raid_mode_until"] = now_ts + 600
        add_log("anti_raid_triggered", chat_id, 0, f"joins_30s={len(join_times)}; duration=600s")
        try: bot.send_message(chat_id, "🚨 <b>حالت ضد یورش فعال شد</b>\nورودهای پیاپی شناسایی شد؛ اعضای تازه‌وارد باید تأیید کپچا را انجام دهند. این حالت پس از ۱۰ دقیقه خودکار پایان می‌یابد.")
        except Exception: pass
    raid_active = bool(s.get("anti_raid_on") and float(s.get("raid_mode_until", 0) or 0) > now_ts)
    save_data()
    for member in message.new_chat_members:
        if s.get("captcha_on") or raid_active:
            member_id = int(member.id)
            captcha_key = f"{chat_id}:{member_id}"
            a, b = random.randint(2, 9), random.randint(1, 9)
            answer = a + b
            options = list({answer, answer + random.choice([1, 2]), max(0, answer - random.choice([1, 2]))})
            while len(options) < 3: options.append(answer + len(options) + 2)
            random.shuffle(options)
            try:
                me = bot.get_me(); bot_member = bot.get_chat_member(chat_id, me.id)
                if getattr(bot_member, "status", "") == "creator" or bool(getattr(bot_member, "can_restrict_members", False)):
                    bot.restrict_chat_member(chat_id, member_id, permissions=types.ChatPermissions(can_send_messages=False, can_send_audios=False, can_send_documents=False, can_send_photos=False, can_send_videos=False, can_send_video_notes=False, can_send_voice_notes=False, can_send_polls=False, can_send_other_messages=False, can_add_web_page_previews=False))
                    DATA.setdefault("captchas", {})[captcha_key] = {"answer": answer, "expires": time.time() + 300, "created": now_text()}
                    save_data()
                    captcha_kb = types.InlineKeyboardMarkup(row_width=3)
                    captcha_kb.row(*[types.InlineKeyboardButton(str(value), callback_data=f"captcha:{member_id}:{value}") for value in options])
                    bot.send_message(chat_id, f"🔐 <b>تأیید ورود</b>\n{esc(member.first_name or 'عضو جدید')}، برای فعال‌شدن امکان ارسال پیام، جواب این سؤال را انتخاب کن: <b>{a} + {b} = ؟</b>\n⏳ اعتبار دکمه‌ها: ۵ دقیقه", reply_markup=captcha_kb)
                else:
                    bot.send_message(chat_id, "⚠️ کپچا در تنظیمات روشن است، اما ربات مجوز محدودکردن اعضا ندارد؛ از مدیر بخواه مجوز «محدودکردن اعضا» را فعال کند.")
            except Exception as captcha_error:
                DATA.setdefault("captchas", {}).pop(captcha_key, None); save_data()
                print("Captcha setup error:", repr(captcha_error))
        DATA["stats"]["joins"]+=1
        gs=DATA.setdefault("group_stats",{}).setdefault(str(message.chat.id),{"messages":0,"blocked":0,"joins":0,"leaves":0})
        gs["joins"]=int(gs.get("joins",0))+1
        DATA.setdefault("active_members",{}).setdefault(str(message.chat.id),{})[str(member.id)]=time.time()
        add_log("new_member",message.chat.id,member.id,"ورود به گروه")
        # Welcome is a mandatory core feature; it is intentionally not controlled by a panel toggle.
        try:
            # Build once per join; title is fetched live so group renames are reflected.
            card = welcome_card(message.chat.id, member)
            custom=s.get("welcome_text","سلام {name}، به گروه خوش آمدی!")
            custom_text = ""
            if custom and custom != DEFAULT_GROUP["welcome_text"]:
                custom_text = esc(custom).replace(
                    "{name}",
                    f'<a href="tg://user?id={int(member.id)}">{esc(member.first_name or "دوست عزیز")}</a>'
                )
            kb=types.InlineKeyboardMarkup()
            kb.add(types.InlineKeyboardButton("📜 مشاهده قوانین گروه", callback_data=f"group_rules:{message.chat.id}"))
            final_text = card + ("\n\n" + custom_text if custom_text else "")
            image_url = str(s.get("welcome_image", "") or "").strip()
            sent = None
            if image_url:
                try:
                    sent = bot.send_photo(
                        message.chat.id, image_url,
                        caption=card[:1024], reply_markup=kb
                    )
                except Exception as image_error:
                    # The configured URL may be a webpage rather than a direct image.
                    # Always deliver the text welcome instead of dropping the whole welcome.
                    print("Welcome image send failed; falling back to text:", repr(image_error))
                    sent = bot.send_message(
                        message.chat.id, final_text[:3900], reply_markup=kb,
                        disable_web_page_preview=True
                    )
                else:
                    if custom_text:
                        try:
                            bot.send_message(message.chat.id, custom_text[:3500], disable_web_page_preview=True)
                        except Exception as custom_welcome_error:
                            print("Custom welcome text send failed:", repr(custom_welcome_error))
            else:
                sent = bot.send_message(
                    message.chat.id, final_text[:3900], reply_markup=kb,
                    disable_web_page_preview=True
                )
            delete_after=int(s.get("welcome_delete_seconds",0) or 0)
            if delete_after>0:
                def _delete_welcome(cid=message.chat.id, mid=sent.message_id):
                    try: bot.delete_message(cid,mid)
                    except Exception as delete_error: print("Welcome auto-delete error:",repr(delete_error))
                timer=threading.Timer(delete_after,_delete_welcome); timer.daemon=True; timer.start()
        except Exception as e: print("Welcome error:",repr(e))
    save_data()

@bot.message_handler(content_types=["left_chat_member"], func=lambda m: m.chat.type in ("group","supergroup"))
def farewell_member(message):
    if not is_group_licensed(message.chat.id): return
    s=get_group_settings(message.chat.id); member=message.left_chat_member
    if member and s.get("farewell_on"):
        try:
            custom = s.get("farewell_text", DEFAULT_GROUP["farewell_text"])
            body = esc(custom).replace("{name}", f'<a href="tg://user?id={int(member.id)}">{esc(member.first_name or "دوست ما")}</a>')
            bot.send_message(message.chat.id, "🌙 <b>مدیریت گروه | 𝑴𝒂𝒔𝒊𝒉 𝑯𝒂𝒄𝒌𝒆𝒓𝒊𝒏𝒈</b>\n━━━━━━━━━━━━━━\n👋 " + body)
        except Exception as e: print("Farewell error:",repr(e))
    if member:
        gs=DATA.setdefault("group_stats",{}).setdefault(str(message.chat.id),{"messages":0,"blocked":0,"joins":0,"leaves":0})
        gs["leaves"]=int(gs.get("leaves",0))+1
        DATA.setdefault("active_members",{}).setdefault(str(message.chat.id),{}).pop(str(member.id),None)
        add_log("member_left",message.chat.id,member.id,"خروج از گروه")
        save_data()

@bot.chat_join_request_handler()
def handle_join_request(request):
    try:
        if not is_group_licensed(request.chat.id): return
        if get_group_settings(request.chat.id).get("join_approval"):
            bot.approve_chat_join_request(request.chat.id,request.from_user.id)
            DATA["stats"]["joins"]+=1; add_log("join_request_approved",request.chat.id,request.from_user.id,"تأیید خودکار ورود"); save_data()
    except Exception as e: print("Join request approval error:",repr(e))

def local_bot_faq(question):
    """Useful Persian answers when the optional external AI API is not configured."""
    q = re.sub(r"[\s‌]+", " ", str(question or "").casefold().replace("ي", "ی").replace("ك", "ک")).strip()
    if any(x in q for x in ("قفل لینک", "ضد لینک", "ضدلینک", "لینک ممنوع")):
        return "🔗 برای تنظیم ضدلینک، در گروه بنویس «پنل» و بخش امنیت را باز کن؛ تغییر تنظیمات فقط برای مدیر گروه فعال است. ربات برای حذف لینک‌ها باید مجوز حذف پیام داشته باشد."
    if any(x in q for x in ("ضد اسپم", "ضداسپم", "اسپم", "پیام تکراری")):
        return "🛡️ برای کنترل اسپم و پیام تکراری، پنل گروه را با نوشتن «پنل» باز کن. مدیر گروه می‌تواند گزینه‌های امنیتی را تغییر دهد؛ برای اجرای حذف پیام، ربات به مجوز حذف پیام نیاز دارد."
    if any(x in q for x in ("کپچا", "تأیید ورود", "تایید ورود", "عضو جدید")):
        return "🔐 کپچا و تأیید ورود را از پنل گروه مدیریت کن. ربات باید مدیر گروه و دارای مجوز محدودکردن اعضا باشد؛ حتماً پس از فعال‌سازی، ورود عضو جدید را در گروه آزمایش کن."
    if any(x in q for x in ("پنل", "تنظیمات گروه", "مدیریت گروه")):
        return "🛡️ برای دیدن پنل کامل همین گروه بنویس «پنل». همه می‌توانند راهنما و آمار را ببینند؛ دکمه‌های تغییر تنظیمات فقط برای مدیران گروه فعال هستند."
    if any(x in q for x in ("بازی", "گیم", "بازی ها", "بازی‌ها")):
        return "🎮 برای بازی‌ها بنویس «بازی» یا از دکمهٔ بازی‌ها در پنل گروه استفاده کن. اگر صفحهٔ بازی باز نشد، آدرس HTTPS آن باید در WEB_GAME_URL هاست تنظیم شده باشد."
    if any(x in q for x in ("فونت", "فانتزی")):
        return "🔤 برای ساخت فونت فانتزی، در گفت‌وگوی خصوصی ربات کلمهٔ «فونت» را بفرست و بعد متن دلخواهت را ارسال کن."
    if any(x in q for x in ("پروکسی", "proxy")):
        return "🌐 برای دیدن فهرست پروکسی‌ها، در گفت‌وگوی خصوصی ربات «پروکسی» را بفرست. افزودن یا حذف پروکسی به سطح دسترسی مالک نیاز دارد."
    if any(x in q for x in ("قانون", "قوانین")):
        return "📜 برای دیدن قوانین گروه، بنویس «قوانین» یا در پنل روی «مشاهده قوانین» بزن."
    if any(x in q for x in ("آمار", "چند نفر", "تعداد اعضا")):
        return "📊 برای آمار پایه بنویس «آمار»؛ آمار دقیق‌تر در پنل گروه در دسترس است. اطلاعات اعضا به داده‌هایی محدود است که تلگرام و ربات در اختیار می‌گذارند."
    if any(x in q for x in ("سلام", "درود", "خوبی", "چطوری")):
        return "سلام! 🌈 من MASIH GUARD هستم. دربارهٔ پنل گروه، امنیت، قوانین، بازی‌ها، فونت‌ها یا امکاناتم بپرس. برای اجرای تنظیمات مدیریتی باید مدیر گروه باشی."
    return "🧠 پیام مرتبطت رو دریافت کردم. می‌تونم دربارهٔ پنل گروه، امنیت، ضدلینک، ضداسپم، کپچا، قوانین، آمار، بازی‌ها، فونت و پروکسی راهنمایی بدم. برای گفت‌وگوی آزادتر، مالک باید AI_API_KEY معتبر را در هاست تنظیم کند."

def ask_ai(question):
    if not AI_API_KEY: return local_bot_faq(question)
    system_prompt = (
        "تو دستیار هوش مصنوعی کاملاً فارسیِ MASIH GUARD هستی. همیشه فقط به زبان فارسی پاسخ بده؛ "
        "همهٔ توضیح‌ها، راهنماها، عنوان‌ها و پیام‌های خطا باید فارسی و روان باشند. "
        "حتی اگر کاربر انگلیسی نوشت، پاسخ را فارسی بده مگر اینکه صریحاً ترجمهٔ متن بخواهد؛ "
        "در آن حالت فقط متن ترجمه‌شده می‌تواند زبان دیگری داشته باشد. "
        "اگر دربارهٔ قابلیت یا تنظیمی مطمئن نیستی، ادعای انجام‌شدن نکن و شفاف بگو. "
        "برای اقدامات مدیریتی فقط راهنمایی کن و ادعا نکن کاری را در تلگرام انجام داده‌ای "
        "مگر اینکه ابزار واقعاً آن را تأیید کرده باشد. پاسخ‌ها دوستانه، دقیق و ایمن باشند."
    )
    payload={"model":AI_MODEL,"messages":[{"role":"system","content":system_prompt},{"role":"user","content":str(question)[:5000]}],"temperature":0.5,"max_tokens":1200}
    req=urllib.request.Request(AI_BASE_URL+"/chat/completions",data=json.dumps(payload,ensure_ascii=False).encode("utf-8"),
       headers={"Authorization":"Bearer "+AI_API_KEY,"Content-Type":"application/json","Accept":"application/json"},method="POST")
    try:
        with urllib.request.urlopen(req,timeout=40) as response: result=json.loads(response.read().decode("utf-8"))
        answer=result["choices"][0]["message"]["content"]
        return answer.strip() if isinstance(answer,str) and answer.strip() else "⚠️ پاسخ خالی از سرویس دریافت شد."
    except urllib.error.HTTPError as e:
        print("AI HTTP error:",e.code)
        if e.code==401: return "❌ کلید هوش مصنوعی معتبر نیست."
        if e.code==429: return "⏳ محدودیت درخواست یا اعتبار سرویس را بررسی کن."
        return f"❌ سرویس هوش مصنوعی خطای HTTP {e.code} داد."
    except Exception as e: print("AI request error:",repr(e)); return "❌ ارتباط با هوش مصنوعی برقرار نشد."

def stats_text():
    s=DATA["stats"]
    return (f"📊 <b>آمار {BRAND}</b>\n━━━━━━━━━━━━━━━━━━\n"
            f"👤 کاربران یکتای استارت‌زده: {int(s.get('users_started', 0)):,}\n"
            f"🚀 مجموع دفعات /start: {int(s.get('start_commands', 0)):,}\n"
            f"💬 پیام‌ها: {s['messages']}\n🚫 حذف‌شده‌ها: {s['blocked']}\n"
            f"⚠️ اخطارها: {s['warns']}\n👥 ورود اعضا: {s['joins']}\n"
            f"🎫 تیکت‌ها: {s['tickets']}\n💼 مشتریان: {len(DATA['customers'])}")

def create_ticket(uid, username, text):
    tid=str(int(time.time()*1000))
    DATA["tickets"][tid]={"user_id":int(uid),"username":username or "","text":text[:3500],"status":"open","created":now_text()}
    DATA["stats"]["tickets"]+=1; save_data()
    try: bot.send_message(OWNER_ID,f"🎫 <b>تیکت جدید</b>\nشناسه: <code>{tid}</code>\nکاربر: <code>{uid}</code>\n\n{esc(text[:3500])}")
    except Exception as e: print("Ticket forwarding error:",repr(e))
    return tid

def proxy_endpoint(proxy_url):
    """Extract the server and port from Telegram proxy links without exposing secrets."""
    try:
        parsed = urlparse(str(proxy_url).strip())
        query = parse_qs(parsed.query)
        host = (query.get("server") or [""])[0].strip()
        port = int((query.get("port") or ["0"])[0])
        if not host or not (1 <= port <= 65535):
            return None
        return host, port
    except (TypeError, ValueError):
        return None

def proxy_ping_ms(proxy_url, timeout=1.5):
    """Measure TCP reachability/latency to a Telegram proxy endpoint (not a full Telegram handshake)."""
    endpoint = proxy_endpoint(proxy_url)
    if not endpoint:
        return None
    start = time.perf_counter()
    try:
        with socket.create_connection(endpoint, timeout=timeout):
            return round((time.perf_counter() - start) * 1000)
    except OSError:
        return None

def proxy_list_text(limit=20, with_ping=False):
    items = DATA.get("proxies", [])[:limit]
    if not items:
        return "🌐 هنوز پروکسی‌ای توسط مالک ذخیره نشده است."
    rows = []
    for i, item in enumerate(items, 1):
        if with_ping:
            ping = proxy_ping_ms(item)
            status = f"🟢 {ping} ms" if ping is not None else "🔴 در دسترس نیست/قالب نامعتبر"
            rows.append(f"{i}. {status}\n<code>{esc(item)}</code>")
        else:
            rows.append(f"{i}. <code>{esc(item)}</code>")
    return "🌐 <b>فهرست پروکسی‌ها</b>\n━━━━━━━━━━━━━━\n" + "\n\n".join(rows)

def send_backup(chat_id):
    if not is_owner(chat_id): bot.send_message(chat_id,"⛔ نسخه پشتیبان فقط برای مالک است."); return
    f=io.BytesIO(json.dumps(DATA,ensure_ascii=False,indent=2).encode("utf-8")); f.name="masih_guard_backup.json"
    bot.send_document(chat_id,f,caption="💾 نسخه پشتیبان MASIH GUARD")

def moderate_member(action,chat_id,user_id):
    group_key=str(chat_id); member_key=str(user_id)
    listing=DATA.setdefault("moderation_lists",{}).setdefault(group_key,{"banned":[],"muted":[]})
    if action in {"ban", "kick", "mute", "warn"}:
        role = target_group_admin_status(chat_id, user_id)
        if role is True:
            return "⛔ برای امنیت، مالک و مدیران گروه از این عملیات مستثنا هستند."
        if role is None:
            return "⚠️ نقش کاربر از تلگرام تأیید نشد؛ برای جلوگیری از اقدام اشتباه، عملیات انجام نشد."
    if action=="warn": warn_member(chat_id,user_id,"اخطار مدیر"); return "⚠️ اخطار ثبت شد."
    if action=="ban":
        bot.ban_chat_member(chat_id,user_id)
        if member_key not in listing["banned"]: listing["banned"].append(member_key)
        add_log("manual_ban",chat_id,user_id,"مسدودسازی مدیر"); save_data(); return "⛔ عضو مسدود شد."
    if action=="unban":
        bot.unban_chat_member(chat_id,user_id,only_if_banned=True)
        listing["banned"]=[x for x in listing["banned"] if x!=member_key]; save_data(); return "✅ مسدودی برداشته شد."
    if action=="kick":
        bot.ban_chat_member(chat_id,user_id); bot.unban_chat_member(chat_id,user_id,only_if_banned=True)
        add_log("manual_kick",chat_id,user_id,"اخراج مدیر"); save_data(); return "👢 عضو اخراج شد."
    if action in ("mute","unmute"):
        allowed=action=="unmute"
        perms=types.ChatPermissions(can_send_messages=allowed,can_send_audios=allowed,can_send_documents=allowed,
            can_send_photos=allowed,can_send_videos=allowed,can_send_video_notes=allowed,can_send_voice_notes=allowed,
            can_send_polls=allowed,can_send_other_messages=allowed,can_add_web_page_previews=allowed)
        bot.restrict_chat_member(chat_id,user_id,permissions=perms)
        if allowed: listing["muted"]=[x for x in listing["muted"] if x!=member_key]
        elif member_key not in listing["muted"]: listing["muted"].append(member_key)
        save_data()
        return "🔊 محدودیت برداشته شد." if allowed else "🔇 عضو محدود شد."
    raise ValueError("عملیات ناشناخته است.")

LOG_ACTION_LABELS = {
    "referral": "ثبت زیرمجموعه", "subscription_bought": "خرید اشتراک",
    "group_license_activated": "فعال‌سازی مجوز گروه", "group_license_extended": "تمدید مجوز گروه",
    "group_license_revoked": "لغو مجوز گروه", "warning": "ثبت اخطار", "blocked": "مسدودسازی پیام",
    "new_member": "ورود عضو", "member_left": "خروج عضو", "proxy_added": "افزودن پروکسی",
    "proxy_deleted": "حذف پروکسی", "announcement": "ارسال اطلاعیه", "manual_ban": "مسدودسازی عضو",
    "manual_kick": "اخراج عضو", "messages_cleaned": "پاک‌سازی پیام‌ها", "member_messages_cleaned": "پاک‌سازی پیام‌های عضو",
    "message_pinned": "سنجاق پیام", "message_unpinned": "برداشتن سنجاق", "user_report": "گزارش تخلف",
    "join_request_approved": "تأیید درخواست عضویت", "quiet_hours_set": "تنظیم ساعت سکوت",
    "bot_setting_updated": "به‌روزرسانی تنظیمات ربات", "setting_toggled": "تغییر تنظیم گروه",
}
def log_action_label(value):
    value = str(value or "")
    return LOG_ACTION_LABELS.get(value, value.replace("_", " "))

def _parse_log_time(value):
    try: return datetime.strptime(str(value), "%Y-%m-%d %H:%M:%S").timestamp()
    except (ValueError, TypeError): return 0

def handle_show(uid, action):
    if action=="stats": bot.send_message(uid,stats_text())
    elif action=="weekly_report":
        cutoff=time.time()-7*86400
        recent=[x for x in DATA.get("logs",[]) if _parse_log_time(x.get("time", "")) >= cutoff]
        joins=sum(1 for x in recent if x.get("action")=="new_member")
        leaves=sum(1 for x in recent if x.get("action")=="member_left")
        warns=sum(1 for x in recent if x.get("action")=="warning")
        blocked=sum(1 for x in recent if x.get("action")=="blocked")
        bot.send_message(uid,f"📅 <b>گزارش هفتگی</b>\n━━━━━━━━━━━━━━\nرویدادهای ثبت‌شده: {len(recent)}\nورود اعضا: {joins}\nخروج اعضا: {leaves}\nاخطارها: {warns}\nپیام‌های مسدودشده: {blocked}")
    elif action=="security_status":
        bot.send_message(uid, "🛡 <b>وضعیت امنیت</b>\nامنیت هوشمند سراسری: " + ("روشن" if DATA.get("settings",{}).get("smart_security",True) else "خاموش") + f"\nگروه‌های دارای مجوز: {sum(1 for gid in DATA.get('group_licenses',{}) if is_group_licensed(gid))}\nگزارش‌های ذخیره‌شده: {len(DATA.get('logs',[]))}")
    elif action=="subscription_sales":
        rows=[x for x in DATA.get("logs",[]) if x.get("action") in {"subscription_bought","group_license_activated","group_license_extended","group_license_revoked"}][-30:]
        text="\n".join(f"{esc(x.get('time'))} — {esc(log_action_label(x.get('action')))} — {esc(x.get('chat_id'))} — {esc(x.get('detail'))}" for x in reversed(rows))
        bot.send_message(uid,"💳 <b>فروش و تمدید اشتراک / مجوز</b>\n"+(text or "هنوز تراکنش یا تمدیدی ثبت نشده است."))
    elif action=="status": bot.send_message(uid,f"🚀 <b>{BRAND} {VERSION}</b>\nربات در حال اجراست.\nهوش مصنوعی: {'تنظیم شده' if AI_API_KEY else 'تنظیم نشده'}")
    elif action=="rules":
        p=WAITING.get(uid,{}); bot.send_message(uid,esc(get_group_settings(p.get("chat_id",uid))["rules"]))
    elif action=="notes":
        p=WAITING.get(uid,{})
        notes=get_group_settings(p.get("chat_id",uid)).get("notes",{})
        body="\n\n".join(f"<b>#{esc(k)}</b>\n{esc(v)}" for k,v in notes.items())
        bot.send_message(uid,"📝 <b>یادداشت‌های گروه</b>\n"+(body or "یادداشتی ثبت نشده است."))
    elif action=="proxies":
        bot.send_message(uid,proxy_list_text(limit=20, with_ping=True))
    elif action=="group_licenses":
        rows=[]
        for gid,rec in list(DATA.setdefault("group_licenses",{}).items())[-50:]:
            active,_=group_license_status(gid)
            rows.append(f"{'🟢' if active else '🔴'} <code>{esc(gid)}</code> — {esc(rec.get('expires') or 'دائمی')}")
        bot.send_message(uid,"🛡️ <b>مجوزهای گروه</b>\n"+("\n".join(rows) if rows else "هنوز گروهی فعال نشده است."))
    elif action=="group_requests":
        req=DATA.setdefault("group_requests",{})
        rows=[f"• <code>{esc(gid)}</code>" for gid in req]
        bot.send_message(uid,"📨 <b>گروه‌هایی که درخواست نصب داشته‌اند</b>\n"+("\n".join(rows[-50:]) if rows else "درخواستی ثبت نشده است."))
    elif action in {"ban_list","mute_list","whitelist"}:
        target=WAITING.get(uid,{}).get("chat_id")
        kind="banned" if action=="ban_list" else "muted"
        values=DATA.setdefault("moderation_lists",{}).get(str(target),{}).get(kind,[])
        bot.send_message(uid,("📋 <b>فهرست اعضا</b>\n"+"\n".join(f"• <code>{esc(x)}</code>" for x in values)) if values else "فهرست ثبت‌شده توسط ربات خالی است.")
    elif action=="customers":
        rows=[f"• {esc(v.get('name'))} — <code>{esc(k)}</code>" for k,v in list(DATA["customers"].items())[:50]]
        bot.send_message(uid,"💼 <b>مشتریان</b>\n"+"\n".join(rows) if rows else "مشتری ثبت نشده است.")
    elif action=="logs":
        rows=[f"{esc(x.get('time'))} — {esc(log_action_label(x.get('action')))} — {esc(x.get('detail'))}" for x in DATA["logs"][-20:]]
        bot.send_message(uid,"🧾 <b>آخرین گزارش‌ها</b>\n"+"\n".join(rows) if rows else "گزارشی ثبت نشده است.")
    elif action=="backup": send_backup(uid)
    elif action=="daily":
        day=today(); recent=[x for x in DATA.get("logs",[]) if str(x.get("time","" )).startswith(day)]
        joins=sum(1 for x in recent if x.get("action")=="new_member")
        leaves=sum(1 for x in recent if x.get("action")=="member_left")
        warns=sum(1 for x in recent if x.get("action")=="warning")
        blocked=sum(1 for x in recent if x.get("action")=="blocked")
        bot.send_message(uid,f"📅 <b>گزارش روزانه — {day}</b>\n━━━━━━━━━━━━━━\nورودها: {joins}\nخروج‌ها: {leaves}\nاخطارها: {warns}\nپیام‌های مسدودشده: {blocked}\nکل پیام‌های ثبت‌شده: {DATA['stats'].get('messages',0)}")
    elif action=="points": bot.send_message(uid,f"🏆 امتیاز شما: {DATA['points'].get(str(uid),0)}")
    elif action=="tickets":
        rows=[(k,v) for k,v in DATA["tickets"].items() if v.get("user_id")==uid or is_owner(uid)]
        bot.send_message(uid,"\n\n".join(f"🎫 <code>{esc(k)}</code> — {'باز' if v.get('status') == 'open' else 'بسته'}\n{esc(v.get('text','')[:200])}" for k,v in rows[-15:]) if rows else "تیکتی ثبت نشده است.")
    elif action in {"diamond_stats", "wallet_stats"}:
        total = sum(max(0, int(u.get("wallet_toman", 0))) for u in DATA.get("users", {}).values() if isinstance(u, dict))
        bot.send_message(uid, f"💳 <b>آمار کیف پول تومانی</b>\nکاربران: {len(DATA.get('users', {}))}\nموجودی کل: {total:,} تومان\nدعوت‌ها: {len(DATA.get('referrals', {}))}\nاشتراک‌ها: {len(DATA.get('subscriptions', {}))}")
    elif action=="referral_stats":
        reward = int(bot_settings().get("referral_reward_toman", 5000))
        bot.send_message(uid,f"👥 کل دعوت‌های ثبت‌شده: {len(DATA['referrals'])}\n💳 پاداش هر دعوت معتبر: {reward:,} تومان")
    elif action=="payout_requests":
        rows = [(rid, req) for rid, req in DATA.get("payout_requests", {}).items() if req.get("status") == "pending"]
        if not rows:
            bot.send_message(uid, "📨 درخواست برداشتِ در انتظار بررسی وجود ندارد.")
        else:
            for rid, req in rows[-20:]:
                kb = types.InlineKeyboardMarkup(row_width=2)
                kb.row(types.InlineKeyboardButton("✅ ثبت پرداخت‌شده", callback_data=f"payout:paid:{rid}"), types.InlineKeyboardButton("❌ رد", callback_data=f"payout:reject:{rid}"))
                bot.send_message(uid, f"💸 درخواست برداشت <code>{esc(rid)}</code>\nکاربر: <code>{req.get('user_id')}</code>\nمبلغ: {int(req.get('amount_toman',0)):,} تومان", reply_markup=kb)
    elif action=="subscription_requests":
        rows = [(rid, req) for rid, req in DATA.get("subscription_requests", {}).items() if req.get("status") == "pending"]
        if not rows:
            bot.send_message(uid, "📨 درخواست اشتراکِ در انتظار بررسی وجود ندارد.")
        else:
            for rid, req in rows[-20:]:
                kb = types.InlineKeyboardMarkup(row_width=2)
                kb.row(types.InlineKeyboardButton("✅ تأیید", callback_data=f"subreq:approve:{rid}"), types.InlineKeyboardButton("❌ رد", callback_data=f"subreq:reject:{rid}"))
                bot.send_message(uid, f"💳 درخواست <code>{esc(rid)}</code>\nکاربر: <code>{req.get('user_id')}</code>\nمدت: {req.get('days')} روز\nمبلغ: {int(req.get('price_toman',0)):,} تومان", reply_markup=kb)
    elif action=="shop": bot.send_message(uid,shop_text(uid),reply_markup=shop_keyboard())
    elif action=="bot_settings":
        cfg = bot_settings()
        packages = "، ".join(f"{days} روز/{price:,} تومان" for days, price in subscription_packages())
        custom_intro = "سفارشی" if str(cfg.get("public_features", "")).strip() else "پیش‌فرض"
        bot.send_message(uid,
            "🎛️ <b>تنظیمات عمومی ذخیره‌شده</b>\n━━━━━━━━━━━━━━\n"
            f"📝 متن معرفی /start: {custom_intro}\n"
            f"👥 پاداش دعوت: {int(cfg.get('referral_reward_toman', 5000)):,} تومان\n"
            f"🛒 بسته‌ها: {esc(packages)}\n"
            f"📢 کانال: {esc(cfg.get('channel_url', CHANNEL_URL))}\n"
            f"🌐 وب‌سایت: {esc(cfg.get('website_url', WEBSITE_URL))}")

# ---------------- Commands and callbacks ----------------
@bot.message_handler(commands=["start"])
def start_command(message):
    uid=message.from_user.id if message.from_user else 0
    if message.chat.type=="private":
        user_record = ensure_user(uid, message.from_user.username, message.from_user.first_name)
        with LOCK:
            DATA["stats"]["start_commands"] = int(DATA["stats"].get("start_commands", 0)) + 1
            if not user_record.get("start_seen", False):
                user_record["start_seen"] = True
                user_record["first_start"] = now_text()
                DATA["stats"]["users_started"] = int(DATA["stats"].get("users_started", 0)) + 1
            save_data()
        args=(message.text or "").split(maxsplit=1)
        if len(args)>1: apply_referral(uid,args[1].strip())
        markup = owner_start_keyboard() if is_owner(uid) else public_keyboard()
        bot.send_message(message.chat.id,start_welcome_text(message.from_user),
                         reply_markup=markup,disable_web_page_preview=True)
        return
    safe_reply_to(message, group_start_guide(getattr(message.chat,"title","گروه")))

@bot.message_handler(commands=["health", "statuscheck", "diagnose"])
def health_command(message):
    """A small live diagnostic without exposing secrets or internal configuration to groups."""
    user = getattr(message, "from_user", None)
    uid = int(getattr(user, "id", 0) or 0)
    chat_type = getattr(getattr(message, "chat", None), "type", "private")
    uptime = max(0, int(time.time() - STARTED_AT))
    days, rem = divmod(uptime, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, seconds = divmod(rem, 60)
    uptime_text = f"{days}روز {hours}ساعت {minutes}دقیقه {seconds}ثانیه"
    if chat_type != "private" or not is_owner(uid):
        safe_reply_to(message, f"🟢 <b>{BRAND} {VERSION}</b> در حال اجراست.\n⏱ زمان فعالیت این اجرا: {esc(uptime_text)}")
        return
    telegram_ok = False
    bot_label = "نامشخص"
    try:
        me = bot.get_me(timeout=5)
        telegram_ok = True
        bot_label = "@" + me.username if getattr(me, "username", None) else str(getattr(me, "first_name", "ربات"))
    except Exception as error:
        print("Health Telegram API check failed:", repr(error))
    data_bytes = 0
    data_valid = False
    data_writable = False
    try:
        data_bytes = os.path.getsize(DATA_FILE) if os.path.isfile(DATA_FILE) else 0
        if os.path.isfile(DATA_FILE):
            with open(DATA_FILE, "r", encoding="utf-8") as data_stream:
                parsed_data = json.load(data_stream)
            data_valid = isinstance(parsed_data, dict)
        else:
            data_valid = True  # The first save will create the file.
        parent_dir = os.path.dirname(os.path.abspath(DATA_FILE)) or "."
        data_writable = os.path.isdir(parent_dir) and os.access(parent_dir, os.W_OK)
    except (OSError, ValueError, TypeError) as storage_error:
        print("Health storage check failed:", repr(storage_error))
    licensed = sum(1 for gid in DATA.get("group_licenses", {}) if is_group_licensed(gid))
    body = (
        f"🧪 <b>گزارش سلامت {BRAND} {VERSION}</b>\n━━━━━━━━━━━━━━━━━━\n"
        f"📡 ارتباط API تلگرام: {'🟢 برقرار' if telegram_ok else '🔴 ناموفق؛ شبکه یا توکن را بررسی کن'}\n"
        f"🤖 حساب ربات: <code>{esc(bot_label)}</code>\n"
        f"⏱ زمان فعالیت: {esc(uptime_text)}\n"
        f"💾 فایل داده: {'🟢 JSON معتبر' if data_valid else '🔴 نامعتبر/خوانده‌نشده'} ({data_bytes:,} بایت)\n"
        f"✍️ دسترسی نوشتن پوشهٔ داده: {'🟢 مجاز' if data_writable else '🔴 بررسی شود'}\n"
        f"🛡️ گروه‌های دارای مجوز فعال: {licensed}\n"
        f"🧠 هوش مصنوعی: {'تنظیم شده' if AI_API_KEY else 'کلید تنظیم نشده؛ پاسخ محلی فعال است'}\n"
        f"🎮 صفحهٔ بازی: {'آدرس HTTPS پیدا شد' if get_game_url() else 'WEB_GAME_URL را در هاست تنظیم کن'}\n"
        "🔐 توکن و کلیدهای محرمانه در این گزارش نمایش داده نمی‌شوند."
    )
    bot.send_message(message.chat.id, body)


@bot.message_handler(commands=["version"])
def version_command(message):
    safe_reply_to(message, f"🛡️ <b>{BRAND} {VERSION}</b>\nنسخهٔ تک‌فایلی پایتون؛ امکانات فعال به تنظیمات هاست و مجوزهای تلگرام وابسته‌اند.")


@bot.message_handler(commands=["ping"])
def ping_command(message):
    safe_reply_to(message, "🏓 MASIH GUARD فعاله و پیام رو دریافت کرد.")

@bot.message_handler(commands=["id"])
def id_command(message):
    safe_reply_to(message,f"🆔 شناسه کاربر: <code>{message.from_user.id}</code>\nشناسه چت: <code>{message.chat.id}</code>")

@bot.message_handler(commands=["ai","ask"])
def ai_command(message):
    parts=(message.text or "").split(maxsplit=1)
    if len(parts)<2:
        safe_reply_to(message,"🤖 سؤال را بعد از دستور بنویس:\n/ai سلام، خودت را معرفی کن"); return
    status=safe_reply_to(message,"🤖 در حال بررسی سؤال...")
    answer=ask_ai(parts[1].strip())
    try: bot.edit_message_text(esc(answer[:3900]),status.chat.id,status.message_id)
    except Exception: bot.send_message(message.chat.id,esc(answer[:3900]))

@bot.message_handler(commands=["help", "commands"])
def help_command(message):
    if getattr(message.chat, "type", "private") in ("group", "supergroup"):
        safe_reply_to(message,
            "📚 <b>راهنمای مدیریت گروه | 𝑴𝒂𝒔𝒊𝒉 𝑯𝒂𝒄𝒌𝒆𝒓𝒊𝒏𝒈</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "🔎 <b>اطلاعات:</b> /groupinfo /members /admins /time /date /myrank /invitecount /activity /settings /rules /chatid /userid /whois /botinfo /uptime\n"
            "📊 <b>آمار:</b> /stats /stats24 /topactive /exportstats\n"
            "👮 <b>مدیریت عضو</b> (روی پیام عضو ریپلای کن): /warn /mute /unmute /kick /ban /unban\n"
            "🧹 <b>پیام‌ها:</b> /delete /pin /unpin /cleanlast\n"
            "🛡️ <b>امنیت و فیلتر:</b> «قفل لینک»، «قفل تبلیغ»، «ضد اسپم روشن»، «ضدتکرار روشن»، «قفل فوروارد»؛ همچنین /filteradd /filterdel /filterlist\n"
            "👋 <b>خوشامد و تنظیمات:</b> /setrules /setwelcome /setfarewell /welcomeon /welcomeoff /farewellon /farewelloff /setquiet /quieton /quietoff\n"
            "🗒️ <b>ابزارهای مدیر:</b> /noteadd /notedel /note /autoreplyadd /autoreplydel /echo متن /scanfile (بررسی پایهٔ فایل، نه تضمین ضدویروس)\n"
            "📢 <b>عضویت اجباری:</b> کانال‌ها از پنل گروه تنظیم می‌شوند؛ در صورت فعال بودن، عضویت بررسی می‌شود. /mylink لینک دعوت اختصاصی را می‌دهد.\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "🔒 برای اقدامات مدیریتی روی پیام کاربر ریپلای کن؛ مدیر بودن درخواست‌دهنده و دسترسی ربات بررسی می‌شود. بعضی امکانات وابسته به مجوز نصب یا تنظیم سرویس هستند.")
    else:
        bot.send_message(message.chat.id,
            "📚 <b>راهنمای کامل | مدیریت گروه | 𝑴𝒂𝒔𝒊𝒉 𝑯𝒂𝒄𝒌𝒆𝒓𝒊𝒏𝒈</b>\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "🚀 <b>فرمان‌های اصلی</b>\n"
            "/start — معرفی و منوی اصلی | /help — همین راهنما | /panel — پنل مالک/گروه | /profile — پروفایل و کیف پول\n"
            "/stats — آمار | /id — شناسه | /ping — پاسخ‌گویی | /health یا /diagnose — سلامت | /version — نسخه | /cancel — لغو\n"
            "/ai متن سؤال — دستیار هوشمند | /game — بازی‌ها | /top — جدول امتیازها\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "🛡️ <b>امنیت گروه:</b> ضدلینک، ضدتبلیغ، ضداسپم و تکرار، کنترل فوروارد و رسانه، فیلتر شماره/کلمات، کپچا و ضدیورش؛ تنظیمات در پنل گروه و از طریق فرمان‌های پشتیبانی‌شده.\n"
            "👥 <b>اعضا:</b> اخطار، سکوت/رفع سکوت، اخراج، بن/رفع بن، اطلاعات و مقام کاربر، شمارش دعوت، سنجاق/لغو سنجاق و حذف پیام.\n"
            "👋 <b>ورود و قوانین:</b> خوشامد و خداحافظی، متن قابل‌تنظیم، قوانین، جوین اجباری کانال و اد اجباری با لینک دعوت اختصاصی.\n"
            "⚙️ <b>مدیریت:</b> فیلتر کلمات، یادداشت، پاسخ خودکار، ساعت سکوت، پاک‌سازی پیام‌های اخیر، آمار فعالیت و گزارش خروجی.\n"
            "🎨 <b>ابزارها:</b> فونت متنی، بازی، تیکت پشتیبانی، تاریخ/ساعت، اکو متن و بررسی پایهٔ اطلاعات فایل.\n"
            "💳 <b>خدمات کاربری:</b> کیف پول تومانی، تراکنش‌ها، اشتراک، دعوت دوستان و درخواست برداشت؛ شرایط و وضعیت مالی از پنل و سوابق قابل بررسی است.\n"
            "━━━━━━━━━━━━━━━━━━━━\n"
            "👥 <b>در گروه:</b> «پنل»، «راهنما»، «قوانین»، «آمار»؛ فرمان‌های مدیریتی باید در گروه اجرا شوند و برای عملیات روی عضو، روی پیام او ریپلای کن.\n"
            "🔐 امکانات به مجوز نصب، تنظیمات و دسترسی‌های واقعی تلگرام وابسته‌اند؛ سرویس‌های خارجی فقط پس از پیکربندی کار می‌کنند.",
            reply_markup=public_keyboard(), disable_web_page_preview=True)


@bot.message_handler(commands=["profile", "me"])
def profile_command(message):
    user = getattr(message, "from_user", None)
    if not user:
        return
    uid = int(user.id)
    profile = ensure_user(uid, getattr(user, "username", ""), getattr(user, "first_name", ""))
    referrals = sum(1 for row in DATA.setdefault("referrals", {}).values() if isinstance(row, dict) and int(row.get("referrer", 0) or 0) == uid)
    points = int(DATA.setdefault("points", {}).get(str(uid), 0) or 0)
    bot.send_message(message.chat.id,
        "👤 <b>پروفایل شما</b>\n━━━━━━━━━━━━━━\n"
        f"نام: {esc(getattr(user, 'first_name', '') or 'کاربر')}\n"
        f"شناسه: <code>{uid}</code>\n"
        f"⭐ امتیاز بازی: <b>{points}</b>\n"
        f"👥 دعوت‌های ثبت‌شده: <b>{referrals}</b>\n"
        f"💳 موجودی کیف پول: <b>{wallet(uid):,} تومان</b>\n"
        f"📅 عضویت در ربات: {esc(profile.get('joined', 'ثبت نشده'))}")

@bot.message_handler(commands=["top", "leaderboard"])
def leaderboard_command(message):
    points = DATA.setdefault("points", {})
    rows = sorted(((int(uid), int(score or 0)) for uid, score in points.items()), key=lambda row: row[1], reverse=True)[:10]
    if not rows or not any(score for _, score in rows):
        bot.send_message(message.chat.id, "🏆 هنوز امتیازی ثبت نشده؛ با نوشتن «بازی» یا /game شروع کن.")
        return
    lines = []
    medals = ["🥇", "🥈", "🥉"]
    for index, (uid, score) in enumerate(rows, 1):
        user = DATA.setdefault("users", {}).get(str(uid), {})
        name = (user.get("first_name") or user.get("username") or f"کاربر {uid}") if isinstance(user, dict) else f"کاربر {uid}"
        icon = medals[index-1] if index <= 3 else f"{index}."
        lines.append(f"{icon} {esc(name)} — <b>{score}</b> امتیاز")
    bot.send_message(message.chat.id, "🏆 <b>جدول امتیازهای MASIH GUARD</b>\n━━━━━━━━━━━━━━\n" + "\n".join(lines))

@bot.message_handler(commands=["panel"])
def panel_command(message):
    uid = int(getattr(getattr(message, "from_user", None), "id", 0) or 0)
    chat_type = getattr(getattr(message, "chat", None), "type", "private")
    if chat_type in ("group", "supergroup"):
        send_group_panel(message.chat.id, user_id=uid)
        return
    if not is_owner(uid):
        bot.send_message(uid, "⛔ پنل مدیریت مالک فقط برای مالک اصلی ربات در دسترس است.")
        return
    send_panel(uid, user_id=uid)

@bot.message_handler(commands=["stats"])
def stats_command(message):
    if getattr(message.chat, "type", "private") in ("group", "supergroup"):
        gs = DATA.setdefault("group_stats", {}).get(str(message.chat.id), {})
        active = len(DATA.setdefault("active_members", {}).get(str(message.chat.id), {}))
        safe_reply_to(message, f"📊 <b>آمار گروه</b>\nپیام‌ها: {int(gs.get('messages', 0))}\nپیام‌های مسدودشده: {int(gs.get('blocked', 0))}\nورودها: {int(gs.get('joins', 0))}\nخروج‌ها: {int(gs.get('leaves', 0))}\nکاربران دیده‌شده: {active}")
    else:
        bot.send_message(message.chat.id, stats_text())

@bot.message_handler(commands=["cancel"])
def cancel_command(message):
    uid = int(getattr(getattr(message, "from_user", None), "id", 0) or 0)
    pending = WAITING.pop(uid, None)
    GAMES.pop(uid, None)
    if pending:
        safe_reply_to(message, "✅ عملیات در انتظار لغو شد.")
    else:
        safe_reply_to(message, "ℹ️ عملیات فعالی برای لغو وجود نداشت.")

# ---------------- MASIH GUARD: 50 selectable arcade games ----------------
_ARCADE_TITLES = ['مسابقه ماشین نئونی', 'مسابقه موتور کارتونی', 'مسابقه جمع\u200cآوری ستاره\u200cها', 'پیچ\u200cهای نئونی', 'مسابقه جت فضایی', 'مسیر قطار رنگی', 'پرش سکویی کارتونی', 'مسابقه قایق', 'مسیر امتیاز نئونی', 'مسیر پر از تله', 'پرش روی سکوهای کارتونی', 'برج بی\u200cنهایت', 'هزارتوی رنگی', 'غار اسرارآمیز', 'گنج\u200cیابی', 'پرش روی سکوهای متحرک', 'آبشار جادویی', 'ماجراجویی در جنگل', 'پل\u200cهای شناور جادویی', 'فرار از معبد باستانی', 'کاوش فضایی', 'حفاظت از پایگاه ربات\u200cها', 'جمع\u200cآوری ستاره\u200cها در موج\u200cها', 'ربات\u200cهای دوستانه', 'شکار کریستال', 'کاوش سیاره', 'ساخت برج نور', 'چالش غول کاغذی', 'مسیر پازل نورها', 'مأموریت مخفی', 'حل معمای لیزر', 'جورچین رنگ\u200cها', 'هزارتوی زمان\u200cدار', 'پیدا کردن اشیای مخفی', 'رمزگشایی', 'حافظه تصویری', 'چالش واکنش سریع', 'رکورد پرش کارتونی', 'ساخت مسیر', 'فرار از اتاق', 'فوتبال پنالتی', 'بسکتبال امتیازی', 'بولینگ', 'پینگ\u200cپنگ', 'بیلیارد', 'پیدا کردن ستاره\u200cهای رنگی', 'پرتاب به سبد', 'عبور از دروازه\u200cهای نوری', 'تعادل توپ', 'آرکید ترکیبی رکوردشکنی']
ARCADE_GAMES = [{"id": i + 1, "title": title} for i, title in enumerate(_ARCADE_TITLES)]

def _make_arcade_preview(game):
    """Generate a moving preview that matches the selected game's visual family."""
    from PIL import Image, ImageDraw
    import math
    title = str(game.get("title", "بازی")); mode = int(game.get("id", 1)); family = (mode - 1) // 10
    palettes = [(20,220,255),(255,180,60),(255,70,110),(170,110,255),(80,245,150)]
    accent = palettes[family]; frames=[]
    for frame_no in range(8):
        bg=[(5,12,30),(24,18,9),(10,8,28),(9,20,25),(12,12,25)][family]
        im=Image.new("RGB",(480,270),bg); d=ImageDraw.Draw(im)
        if family==0:  # racing track and car
            d.polygon([(0,155),(480,155),(480,270),(0,270)],fill=(35,42,55)); d.polygon([(150,155),(330,155),(430,270),(50,270)],fill=(15,19,28))
            for k in range(5):
                y=(165+k*27+frame_no*8)%275; d.rectangle((235,y,245,y+13),fill=(255,255,230))
            x=210+int(20*math.sin(frame_no*.7)); d.rounded_rectangle((x,190,x+62,229),radius=8,fill=accent,outline="white",width=2); d.rectangle((x+12,179,x+50,199),fill=(130,230,255))
            for wx in (x+8,x+44): d.ellipse((wx,221,wx+14,239),fill=(5,5,8),outline=(230,240,255))
        elif family==1:  # parkour platforms and jumper
            d.rectangle((0,220,480,270),fill=(31,58,45))
            for k in range(6):
                x=k*86-15; y=190-((k*29+mode*7)%95); d.polygon([(x,y),(x+68,y-10),(x+80,y+8),(x+8,y+18)],fill=(55,76,92),outline=accent)
            hx=90+frame_no*22; d.ellipse((hx,115,hx+22,137),fill=(255,218,177)); d.line((hx+11,138,hx+4,175),fill=accent,width=8); d.line((hx+5,174,hx-8,193),fill="white",width=5); d.polygon([(390,90),(405,105),(390,120),(375,105)],fill=(255,220,80))
        elif family==2:  # space action
            for k in range(42):
                x=(k*67+frame_no*9)%480; y=(k*31)%210; d.ellipse((x,y,x+2,y+2),fill=(220,240,255))
            d.polygon([(240,70),(268,140),(240,127),(212,140)],fill=accent,outline="white"); d.polygon([(240,170),(480,225),(480,270),(0,270),(0,225)],fill=(24,32,52))
            for k in range(4):
                x=(k*113+frame_no*13)%470; d.rectangle((x,180+(k%2)*18,x+24,205+(k%2)*18),fill=(90,30,55),outline=(255,90,120),width=2)
        elif family==3:  # puzzle board
            d.rectangle((35,30,445,240),fill=(18,34,50),outline=accent,width=3)
            for yy in range(3):
                for xx in range(5):
                    x=65+xx*72; y=55+yy*58; c=palettes[(xx+yy+mode)%5]; d.rounded_rectangle((x,y,x+42,y+34),radius=5,fill=c if (xx+yy+frame_no)%4 else (235,245,255))
        else:  # sports field and moving ball
            d.rectangle((0,35,480,270),fill=(20,85,55))
            for x in range(0,480,48): d.line((x,35,x,270),fill=(32,110,68),width=1)
            d.rectangle((350,95,455,210),outline=(240,250,255),width=5); d.rectangle((375,125,430,180),outline=(255,255,255),width=4)
            bx=115+frame_no*17; d.ellipse((bx,170,bx+28,198),fill=(255,255,255),outline=accent,width=3)
        d.rounded_rectangle((12,10,350,38),radius=8,fill=(4,8,18),outline=accent,width=2); d.text((22,18),title[:30],fill=(245,250,255)); d.text((408,18),str(mode)+"/50",fill=accent)
        frames.append(im)
    out=io.BytesIO(); frames[0].save(out,format="GIF",save_all=True,append_images=frames[1:],duration=110,loop=0,optimize=True); out.seek(0); out.name="masih-guard-game-%02d.gif"%mode
    return out

def send_random_game(message):
    game_url = get_game_url()
    if not game_url.startswith("https://"):
        safe_reply_to(message, "⚠️ آدرس امن بازی تنظیم نشده است. متغیر WEB_GAME_URL را روی https://masih-guard.fadehost.app/game قرار بده.")
        return
    kb = types.InlineKeyboardMarkup(row_width=2)
    for game in ARCADE_GAMES:
        kb.add(types.InlineKeyboardButton("🎮 %02d. %s" % (game["id"], game["title"]), callback_data="arcade:play:%d" % game["id"]))
    safe_reply_to(message, "🎮 <b>آرکید مسیح هکرینگ | ۵۰ بازی</b>\nیکی از ۵۰ بازی را انتخاب کن؛ پیش‌نمایش مخصوص همان بازی فرستاده می‌شود.", reply_markup=kb)

def send_selected_game(call, game_id):
    game = next((g for g in ARCADE_GAMES if int(g["id"]) == int(game_id)), None)
    if not game:
        bot.answer_callback_query(call.id, "این بازی پیدا نشد.", show_alert=True); return
    game_url = get_game_url()
    if not game_url.startswith("https://"):
        bot.answer_callback_query(call.id, "آدرس امن بازی تنظیم نشده است.", show_alert=True); return
    game_link = game_url + ("&" if "?" in game_url else "?") + "mode=" + str(game["id"]) + "&name=" + quote(game["title"])
    kb = types.InlineKeyboardMarkup(); kb.add(types.InlineKeyboardButton("🚀 اجرای " + game["title"], url=game_link))
    caption = "🎮 <b>MASIH GUARD ARCADE</b>\n🕹️ " + esc(game["title"]) + "\n🎯 بازی " + str(game["id"]) + " از ۵۰\nبرای شروع، دکمهٔ اجرا را بزن."
    try:
        bot.send_animation(call.message.chat.id, animation=_make_arcade_preview(game), caption=caption, reply_markup=kb, reply_to_message_id=call.message.message_id, parse_mode="HTML")
    except Exception as exc:
        print("Arcade preview fallback:", repr(exc)); bot.send_message(call.message.chat.id, caption + "\nپیش‌نمایش متحرک در دسترس نبود.", reply_markup=kb, parse_mode="HTML")
    bot.answer_callback_query(call.id, "بازی انتخاب شد: " + game["title"])

@bot.message_handler(commands=["game", "games"])
def game_command(message):
    send_random_game(message)

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    try:
        data=call.data or ""; uid=call.from_user.id; chat_id=call.message.chat.id if call.message else uid
        if data.startswith("arcade:play:"):
            send_selected_game(call, int(data.rsplit(":", 1)[1]))
            return
        if data.startswith("tagmenu:") or data.startswith("tagrun:"):
            if not call.message or call.message.chat.type not in ("group", "supergroup"):
                bot.answer_callback_query(call.id, "این منو فقط داخل گروه کار می‌کند.", show_alert=True); return
            if not is_group_admin(chat_id, uid):
                bot.answer_callback_query(call.id, "فقط مدیر گروه می‌تواند از تگ گروهی استفاده کند.", show_alert=True); return
            if data == "tagmenu:back":
                bot.answer_callback_query(call.id)
                bot.edit_message_text("🏷️ <b>تگ هوشمند اعضای گروه</b>\nچه کسانی را می‌خواهی تگ کنی؟", chat_id, call.message.message_id, reply_markup=tag_menu_keyboard())
                return
            if data.startswith("tagmenu:"):
                mode = data.split(":", 1)[1]
                bot.answer_callback_query(call.id)
                if mode == "count":
                    bot.edit_message_text("🔢 <b>تعداد تگ اعضای شناخته‌شده</b>\nتعداد دلخواه را انتخاب کن. برای انتخاب نوع دیگر اعضا، به منوی قبلی برگرد.", chat_id, call.message.message_id, reply_markup=tag_count_keyboard("all"))
                    return
                labels = {"all":"اعضای شناخته‌شده", "active":"فعال‌های ۲۴ ساعت اخیر", "admins":"مدیران گروه", "low":"کم‌فعال‌ها"}
                if mode not in labels:
                    bot.answer_callback_query(call.id, "گزینه نامعتبر است.", show_alert=True); return
                bot.edit_message_text(f"🏷️ <b>تگ {labels[mode]}</b>\nچند نفر تگ شوند؟", chat_id, call.message.message_id, reply_markup=tag_count_keyboard(mode))
                return
            if data.startswith("tagrun:"):
                parts = data.split(":")
                if len(parts) != 3 or parts[1] not in {"all", "active", "admins", "low"}:
                    bot.answer_callback_query(call.id, "انتخاب نامعتبر است.", show_alert=True); return
                try: count = int(parts[2])
                except ValueError: bot.answer_callback_query(call.id, "تعداد نامعتبر است.", show_alert=True); return
                if count not in {0, 20, 50, 100, 200}:
                    bot.answer_callback_query(call.id, "تعداد پشتیبانی نمی‌شود.", show_alert=True); return
                bot.answer_callback_query(call.id, "در حال آماده‌کردن فهرست…")
                result = run_tag_selection(chat_id, uid, parts[1], count)
                try: bot.edit_message_text("🏷️ <b>نتیجهٔ تگ</b>\n" + esc(result), chat_id, call.message.message_id, reply_markup=None)
                except Exception: bot.send_message(chat_id, esc(result))
                return
        if data.startswith("forcejoin:check:"):
            parts = data.split(":")
            if len(parts) != 4:
                bot.answer_callback_query(call.id, "دکمه نامعتبر است.", show_alert=True); return
            try:
                target_chat, target_user = int(parts[2]), int(parts[3])
            except ValueError:
                bot.answer_callback_query(call.id, "دکمه نامعتبر است.", show_alert=True); return
            if int(uid) != target_user:
                bot.answer_callback_query(call.id, "این دکمه برای عضو دیگری است.", show_alert=True); return
            missing = force_join_missing(target_chat, target_user, force_refresh=True)
            if missing:
                bot.answer_callback_query(call.id, "هنوز عضویت همه کانال‌ها تأیید نشده؛ اگر عضو شدی چند ثانیه بعد دوباره بزن.", show_alert=True)
                try:
                    bot.edit_message_reply_markup(target_chat, call.message.message_id, reply_markup=force_join_markup(target_chat, target_user, missing))
                except Exception:
                    pass
            else:
                bot.answer_callback_query(call.id, "عضویت تأیید شد؛ حالا می‌توانی پیام بدهی.")
                try:
                    bot.edit_message_text("✅ عضویت شما تأیید شد. حالا می‌توانی در گروه پیام بدهی.", target_chat, call.message.message_id, reply_markup=None)
                except Exception:
                    pass
            return
        if data.startswith("captcha:"):
            if not call.message or call.message.chat.type not in ("group", "supergroup"):
                bot.answer_callback_query(call.id, "این تأیید فقط داخل گروه انجام می‌شود.", show_alert=True); return
            parts = data.split(":", 2)
            if len(parts) != 3:
                bot.answer_callback_query(call.id, "درخواست کپچا نامعتبر است.", show_alert=True); return
            try: target_uid, chosen = int(parts[1]), int(parts[2])
            except ValueError:
                bot.answer_callback_query(call.id, "درخواست کپچا نامعتبر است.", show_alert=True); return
            if int(call.from_user.id) != target_uid:
                bot.answer_callback_query(call.id, "این دکمه برای عضو دیگری است.", show_alert=True); return
            captcha_key = f"{call.message.chat.id}:{target_uid}"
            record = DATA.setdefault("captchas", {}).get(captcha_key)
            if not record:
                bot.answer_callback_query(call.id, "کپچای فعالی برای این عضو ثبت نشده است؛ از مدیر بخواه وضعیت ورودت را بررسی کند.", show_alert=True); return
            if float(record.get("expires", 0)) < time.time():
                a, b = random.randint(2, 9), random.randint(1, 9)
                answer = a + b
                options = list({answer, answer + random.choice([1, 2]), max(0, answer - random.choice([1, 2]))})
                while len(options) < 3: options.append(answer + len(options) + 2)
                random.shuffle(options)
                DATA.setdefault("captchas", {})[captcha_key] = {"answer": answer, "expires": time.time() + 300, "created": now_text()}
                save_data()
                kb = types.InlineKeyboardMarkup(row_width=3)
                kb.row(*[types.InlineKeyboardButton(str(value), callback_data=f"captcha:{target_uid}:{value}") for value in options])
                bot.answer_callback_query(call.id, "زمان قبلی تمام شد؛ سؤال جدید آماده شد.", show_alert=True)
                try: bot.edit_message_text(f"🔐 <b>تأیید ورود</b>\nبرای ادامه، جواب را انتخاب کن: <b>{a} + {b} = ؟</b>\n⏳ اعتبار: ۵ دقیقه", call.message.chat.id, call.message.message_id, reply_markup=kb)
                except Exception: pass
                return
            if chosen != int(record.get("answer", -999)):
                bot.answer_callback_query(call.id, "جواب درست نیست؛ دوباره تلاش کن.", show_alert=True); return
            try:
                chat = bot.get_chat(call.message.chat.id)
                defaults = getattr(chat, "permissions", None)
                fields = ("can_send_messages", "can_send_audios", "can_send_documents", "can_send_photos", "can_send_videos", "can_send_video_notes", "can_send_voice_notes", "can_send_polls", "can_send_other_messages", "can_add_web_page_previews")
                permissions = {field: (getattr(defaults, field, None) is not False) for field in fields}
                bot.restrict_chat_member(call.message.chat.id, target_uid, permissions=types.ChatPermissions(**permissions))
                DATA.setdefault("captchas", {}).pop(captcha_key, None); save_data()
                bot.answer_callback_query(call.id, "تأیید شد؛ خوش آمدی!")
                try: bot.edit_message_text("✅ <b>تأیید انجام شد</b> — عضو می‌تواند طبق مجوزهای پیش‌فرض گروه پیام بدهد.", call.message.chat.id, call.message.message_id, reply_markup=None)
                except Exception: pass
            except Exception as captcha_error:
                print("Captcha unrestrict error:", repr(captcha_error))
                bot.answer_callback_query(call.id, "تأیید انجام شد اما رفع محدودیت ناموفق بود؛ مدیر باید مجوز ربات را بررسی کند.", show_alert=True)
            return
        if data.startswith("gpanel:"):
            if not call.message or call.message.chat.type not in ("group", "supergroup"):
                bot.answer_callback_query(call.id, "این پنل فقط داخل گروه کار می‌کند.", show_alert=True)
                return
            if data.startswith("gpanel:page:"):
                section = data.split(":", 2)[2]
                bot.answer_callback_query(call.id)
                send_group_panel(chat_id, call.message.message_id, user_id=uid, section=section)
                return
            if data.startswith("gpanel:ask:"):
                if not is_group_admin(chat_id, uid):
                    bot.answer_callback_query(call.id, "⛔ فقط مدیر گروه مجاز است.", show_alert=True)
                    return
                action = data.split(":", 2)[2]
                allowed_actions = {"warn_limit", "quiet_hours", "welcome_text", "farewell_text",
                                   "rules", "welcome_image", "welcome_delete_seconds",
                                   "auto_reply", "delete_reply", "bad_word", "add_custom_command",
                                   "delete_custom_command", "add_note", "delete_note"}
                if action not in allowed_actions:
                    bot.answer_callback_query(call.id, "این تنظیم از پنل پشتیبانی نمی‌شود.", show_alert=True)
                    return
                WAITING[uid] = {"action": action, "chat_id": int(chat_id)}
                prompts = {
                    "warn_limit": "سقف اخطار را از ۱ تا ۲۰ بفرست.",
                    "quiet_hours": "بازهٔ سکوت را مثل 23:00-07:00 بفرست؛ برای خاموش‌کردن بنویس خاموش.",
                    "welcome_text": "متن خوشامد را بفرست؛ می‌توانی {name} بگذاری.",
                    "farewell_text": "متن خداحافظی را بفرست؛ می‌توانی {name} بگذاری.",
                    "rules": "قوانین جدید گروه را بفرست.",
                    "welcome_image": "لینک مستقیم تصویر HTTPS را بفرست؛ برای حذف بنویس حذف.",
                    "welcome_delete_seconds": "زمان حذف خوشامد را به ثانیه بفرست (۰ تا ۳۶۰۰).",
                    "auto_reply": "قالب: کلمه کلیدی | متن پاسخ",
                    "delete_reply": "کلمه کلیدی پاسخ خودکار را بفرست.",
                    "bad_word": "کلمه یا عبارت ممنوع را بفرست.",
                    "add_custom_command": "قالب: نام فرمان بدون ! | متن پاسخ",
                    "delete_custom_command": "نام فرمان سفارشی را بفرست.",
                    "add_note": "قالب: نام کوتاه | متن یادداشت",
                    "delete_note": "نام یادداشت را بفرست."
                }
                bot.answer_callback_query(call.id, "ادامه تنظیم در پیام خصوصی")
                try:
                    bot.send_message(uid, f"⚙️ تنظیم گروه <code>{chat_id}</code>\n{prompts[action]}")
                except Exception:
                    bot.send_message(chat_id, "برای تنظیم، ابتدا ربات را در خصوصی باز کن و /start بزن.", reply_to_message_id=call.message.message_id)
                return
            if data == "gpanel:mylink":
                bot.answer_callback_query(call.id)
                bot.send_message(chat_id, "برای دریافت لینک دعوت اختصاصی، دستور /mylink را در همین گروه بفرست.")
                return
            if data == "gpanel:settings":
                bot.answer_callback_query(call.id)
                cfg = get_group_settings(chat_id)
                labels = {"anti_link":"ضد لینک","anti_ads":"ضد تبلیغ","anti_spam":"ضد اسپم",
                           "anti_repeat":"ضد تکرار","anti_forward":"ضد فوروارد","media_lock":"قفل رسانه",
                           "lock_mentions":"قفل منشن","lock_hashtags":"قفل هشتگ","lock_usernames":"قفل نام‌کاربری",
                           "phone_filter":"فیلتر شماره","welcome_on":"خوشامد","farewell_on":"خداحافظی",
                           "captcha_on":"کپچا","anti_raid_on":"ضد یورش","smart_security":"امنیت هوشمند",
                           "force_join_on":"جوین اجباری","force_add_on":"اد اجباری"}
                body = "\n".join(f"• {label}: {'روشن' if cfg.get(key) else 'خاموش'}" for key,label in labels.items())
                bot.send_message(chat_id, "⚙️ <b>وضعیت تنظیمات گروه</b>\n" + body)
                return
            if data == "gpanel:commands":
                bot.answer_callback_query(call.id)
                bot.send_message(chat_id, "📚 <b>فرمان‌های مهم</b>\n"
                    "/panel — پنل گروه\n/mylink — لینک دعوت اختصاصی (اگر اد اجباری فعال باشد)\n"
                    "/rules — قوانین (در صورت پشتیبانی نسخه)\n/id — شناسه\n/help — راهنما\n"
                    "فرمان‌های مدیریتی فقط با مجوز مناسب اجرا می‌شوند.")
                return
            if data == "gpanel:health":
                bot.answer_callback_query(call.id)
                bot.send_message(chat_id, "🧪 <b>سلامت پایه</b>\n"
                    f"نسخه: {BRAND} {VERSION}\n"
                    f"مجوز گروه: {'فعال' if is_group_licensed(chat_id) else 'غیرفعال'}\n"
                    "این بررسی، اتصال API و مجوزهای ربات را تضمین نمی‌کند؛ برای آن لاگ هاست را هم بررسی کن.")
                return
            if data == "gpanel:locked":
                bot.answer_callback_query(call.id, "🔒 این دکمه برای مشاهده‌گرها قفل است؛ مدیر گروه می‌تواند از آن استفاده کند.", show_alert=True)
                return
            if data == "gpanel:rules":
                bot.answer_callback_query(call.id)
                bot.send_message(chat_id, "📜 <b>قوانین گروه</b>\n" + esc(get_group_settings(chat_id).get("rules", "قوانینی ثبت نشده است.")))
                return
            if data == "gpanel:stats":
                bot.answer_callback_query(call.id)
                gs = DATA.setdefault("group_stats", {}).get(str(chat_id), {})
                active = len(DATA.setdefault("active_members", {}).get(str(chat_id), {}))
                bot.send_message(chat_id, f"📊 <b>آمار گروه</b>\nپیام‌ها: {int(gs.get('messages', 0))}\nموارد مسدودشده: {int(gs.get('blocked', 0))}\nورودها: {int(gs.get('joins', 0))}\nخروج‌ها: {int(gs.get('leaves', 0))}\nکاربران دیده‌شده: {active}")
                return
            if data == "gpanel:help":
                bot.answer_callback_query(call.id)
                bot.send_message(chat_id, "📚 <b>راهنمای پنل MASIH GUARD</b>\nاعضا می‌توانند قوانین، آمار و راهنما را ببینند. دکمه‌های قفل‌شده فقط برای مدیران گروه فعال می‌شوند. برای تغییر تنظیمات، ربات باید مدیر گروه و دارای مجوزهای لازم باشد.\nبرای پرسش از دستیار بنویس: <code>ربات [سؤالت]</code> یا روی پیام ربات پاسخ بده.")
                return
            if data == "gpanel:games":
                bot.answer_callback_query(call.id)
                game_url = get_game_url()
                if game_url.startswith("https://"):
                    game_kb = types.InlineKeyboardMarkup()
                    game_kb.add(types.InlineKeyboardButton("🎮 باز کردن بازی‌ها", url=game_url))
                    bot.send_message(chat_id, "🎮 <b>MASIH GUARD ARCADE</b>", reply_markup=game_kb)
                else:
                    bot.send_message(chat_id, "⚠️ آدرس بازی هنوز در هاست تنظیم نشده است.")
                return
            if data == "gpanel:refresh":
                bot.answer_callback_query(call.id)
                current_section = GROUP_PANEL_PAGES.get((int(chat_id), int(call.message.message_id)), "home")
                send_group_panel(chat_id, call.message.message_id, user_id=uid, section=current_section)
                return
            if not is_group_admin(chat_id, uid):
                bot.answer_callback_query(call.id, "⛔ فقط مدیر گروه یا مالک اجازه تغییر تنظیمات دارد.", show_alert=True)
                return
            if data in {"gpanel:configure_force_join", "gpanel:configure_force_add"}:
                action = "force_join" if data.endswith("force_join") else "force_add"
                WAITING[uid] = {"action": action, "chat_id": int(chat_id)}
                prompt = ("هر کانال را در یک خط بفرست: @channel | https://t.me/channel | نام نمایشی. حداکثر ۱۰ کانال؛ برای خاموش‌کردن بنویس خاموش."
                          if action == "force_join" else
                          "تعداد دعوت معتبر لازم را از ۱ تا ۱۰۰ بفرست. اعضا باید در گروه /mylink بزنند؛ برای خاموش‌کردن بنویس خاموش.")
                bot.answer_callback_query(call.id, "ادامه تنظیم در پیام خصوصی")
                try:
                    bot.send_message(uid, "⚙️ تنظیمات گروه " + str(chat_id) + "\n" + prompt)
                except Exception:
                    bot.send_message(chat_id, "برای ادامهٔ تنظیمات، ابتدا ربات را در خصوصی باز کن و /start بزن.", reply_to_message_id=call.message.message_id)
                return
            if data.startswith("gpanel:toggle:"):
                key = data.split(":", 2)[2]
                allowed = {"anti_link", "anti_ads", "anti_tapchi", "anti_spam", "anti_repeat", "anti_forward", "farewell_on", "media_lock", "phone_filter", "captcha_on", "anti_raid_on", "join_approval", "lock_mentions", "lock_hashtags", "lock_usernames", "lock_photos", "lock_videos", "lock_files", "lock_stickers", "lock_voice", "lock_video_notes", "smart_security"}
                if key not in allowed:
                    bot.answer_callback_query(call.id, "تنظیم نامعتبر است.", show_alert=True)
                    return
                settings = get_group_settings(chat_id)
                next_enabled = not bool(settings.get(key, False))
                required_permission = "can_delete_messages" if key in {"anti_link", "anti_ads", "anti_tapchi", "anti_spam", "anti_repeat", "anti_forward", "media_lock", "phone_filter", "lock_mentions", "lock_hashtags", "lock_usernames", "lock_photos", "lock_videos", "lock_files", "lock_stickers", "lock_voice", "lock_video_notes"} else (
                    "can_restrict_members" if key in {"captcha_on", "anti_raid_on"} else
                    "can_invite_users" if key == "join_approval" else "")
                if next_enabled and required_permission and not bot_has_group_permission(chat_id, required_permission):
                    friendly = {"can_delete_messages": "حذف پیام‌ها", "can_restrict_members": "محدودکردن اعضا", "can_invite_users": "دعوت کاربران/مدیریت درخواست ورود"}.get(required_permission, required_permission)
                    bot.answer_callback_query(call.id, f"برای فعال‌کردن این قابلیت، ربات باید مجوز «{friendly}» داشته باشد.", show_alert=True)
                    return
                settings[key] = next_enabled
                save_data()
                bot.answer_callback_query(call.id, "روشن شد." if settings[key] else "خاموش شد.")
                current_section = GROUP_PANEL_PAGES.get((int(chat_id), int(call.message.message_id)), "home")
                send_group_panel(chat_id, call.message.message_id, user_id=uid, section=current_section)
                return
        management_action = data.startswith(("panel:", "toggle:", "ask:", "show:"))
        if management_action:
            if not call.message or call.message.chat.type != "private" or call.message.chat.id != uid:
                bot.answer_callback_query(call.id, "پنل فقط در گفت‌وگوی خصوصی ربات نمایش داده می‌شود.", show_alert=True); return
            if not is_owner(uid):
                bot.answer_callback_query(call.id, "⛔ این پنل مخصوص مالک رباته!", show_alert=True); return
        if data.startswith("payout:"):
            if not is_owner(uid):
                bot.answer_callback_query(call.id, "⛔ این پنل مخصوص مالک رباته!", show_alert=True); return
            parts = data.split(":", 2)
            if len(parts) != 3 or parts[1] not in {"paid", "reject"}:
                bot.answer_callback_query(call.id, "درخواست برداشت نامعتبر است.", show_alert=True); return
            result = decide_payout_request(parts[2], parts[1] == "paid", uid)
            bot.answer_callback_query(call.id, result[:180], show_alert=True)
            try: bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=None)
            except Exception: pass
            bot.send_message(uid, result)
            return
        if data.startswith("subreq:"):
            if not is_owner(uid):
                bot.answer_callback_query(call.id, "⛔ این پنل مخصوص مالک رباته!", show_alert=True); return
            parts = data.split(":", 2)
            if len(parts) != 3 or parts[1] not in {"approve", "reject"}:
                bot.answer_callback_query(call.id, "درخواست نامعتبر است.", show_alert=True); return
            result = decide_subscription_request(parts[2], parts[1] == "approve", uid)
            bot.answer_callback_query(call.id, result[:180], show_alert=True)
            try: bot.edit_message_reply_markup(chat_id, call.message.message_id, reply_markup=None)
            except Exception: pass
            bot.send_message(uid, result)
            return
        if data.startswith("user:") or data.startswith("shop:"):
            if not call.message or call.message.chat.type!="private":
                bot.answer_callback_query(call.id,"این گزینه را در گفت‌وگوی خصوصی ربات استفاده کن.",show_alert=True); return
            ensure_user(uid,call.from_user.username,call.from_user.first_name)
            if data.startswith("user:receipt:"):
                rid = data.split(":", 2)[2]
                req = DATA.get("subscription_requests", {}).get(rid)
                if not req or int(req.get("user_id", 0)) != int(uid) or req.get("status") != "pending":
                    bot.answer_callback_query(call.id, "درخواست معتبر یا در انتظار پرداخت پیدا نشد.", show_alert=True)
                    return
                WAITING[uid] = {"action": "payment_receipt", "request_id": rid}
                bot.answer_callback_query(call.id)
                bot.send_message(uid, f"📤 لطفاً عکس رسید پرداخت را همین‌جا ارسال کن.\nشناسه درخواست: <code>{esc(rid)}</code>\nشناسه عددی تلگرام تو: <code>{uid}</code>\nتا بررسی مالک، اشتراک فعال نمی‌شود.")
                return
            if data=="user:home":
                bot.answer_callback_query(call.id); bot.send_message(uid,public_features_text(),reply_markup=public_keyboard()); return
            if data=="user:wallet": bot.answer_callback_query(call.id); bot.send_message(uid,public_wallet(uid)); return
            if data=="user:shop": bot.answer_callback_query(call.id); bot.send_message(uid,shop_text(uid),reply_markup=shop_keyboard()); return
            if data=="user:referrals": bot.answer_callback_query(call.id); bot.send_message(uid,referral_text(uid)); return
            if data=="user:transactions": bot.answer_callback_query(call.id); bot.send_message(uid,transactions_text(uid)); return
            if data=="user:payout":
                WAITING[uid]={"action":"payout_amount"}
                bot.answer_callback_query(call.id); bot.send_message(uid, f"💸 مبلغ برداشت را به تومان وارد کن. موجودی فعلی: {wallet(uid):,} تومان\nروش پرداخت را بعداً با مالک هماهنگ می‌کنی؛ اطلاعات بانکی را اینجا نفرست."); return
            if data=="user:font":
                WAITING[uid]={"action":"public_font_text"}; bot.answer_callback_query(call.id); bot.send_message(uid,"🔤 ۲۰۰ سبک فونت کاملاً رایگان است. متن را بفرست؛ خروجی در ۲۰ پیام ۱۰تایی نمایش داده می‌شود."); return
            if data=="user:proxies":
                bot.answer_callback_query(call.id)
                bot.send_message(uid,proxy_list_text(limit=10, with_ping=False)); return
            if data=="user:ticket":
                WAITING[uid]={"action":"ticket"}; bot.answer_callback_query(call.id); bot.send_message(uid,"متن تیکت پشتیبانی را بفرست."); return
            if data=="user:ai":
                WAITING[uid]={"action":"ai"}; bot.answer_callback_query(call.id); bot.send_message(uid,"سؤال خود را برای هوش مصنوعی بفرست."); return
            if data.startswith("shop:request:"):
                _,_,days,price=data.split(":")
                result=request_subscription(uid,int(days),int(price))
                pending_rows = [(rid, req) for rid, req in DATA.get("subscription_requests", {}).items()
                                if int(req.get("user_id", 0)) == int(uid) and req.get("status") == "pending"]
                receipt_markup = types.InlineKeyboardMarkup(row_width=1)
                if pending_rows:
                    rid, _req = pending_rows[-1]
                    receipt_markup.add(types.InlineKeyboardButton("📤 ارسال رسید پرداخت", callback_data=f"user:receipt:{rid}"))
                receipt_markup.add(types.InlineKeyboardButton("👨‍💻 ارتباط با سازنده", url=OWNER_CONTACT_URL))
                bot.answer_callback_query(call.id)
                bot.send_message(uid,result,reply_markup=receipt_markup)
                return

        if data.startswith("group_rules:"):
            try: target=int(data.split(":",1)[1])
            except ValueError: target=0
            if target and is_group_licensed(target):
                bot.answer_callback_query(call.id)
                bot.send_message(uid,"📜 <b>قوانین گروه</b>\n"+esc(get_group_settings(target).get("rules","قوانینی ثبت نشده است.")))
            else: bot.answer_callback_query(call.id,"این گروه مجوز فعال ندارد.",show_alert=True)
            return
        if data=="panel:open":
            PANEL_HISTORY[uid]=[]
            send_panel(uid,"home",user_id=uid)
            bot.answer_callback_query(call.id)
            return
        if data=="panel:back":
            if not is_owner(uid):
                bot.answer_callback_query(call.id,"⛔ این پنل مخصوص مالک رباته!",show_alert=True); return
            history=PANEL_HISTORY.setdefault(uid,[]); section=history.pop() if history else "home"
            send_panel(chat_id,section,call.message.message_id if call.message else None,user_id=uid)
            bot.answer_callback_query(call.id); return
        if data=="panel:home":
            if not is_owner(uid):
                bot.answer_callback_query(call.id,"⛔ این پنل مخصوص مالک رباته!",show_alert=True); return
            PANEL_HISTORY[uid]=[]; send_panel(chat_id,"home",call.message.message_id if call.message else None,user_id=uid)
            bot.answer_callback_query(call.id); return
        if data.startswith("panel:"):
            if not is_owner(uid):
                bot.answer_callback_query(call.id,"⛔ این پنل مخصوص مالک رباته!",show_alert=True); return
            section=data.split(":",1)[1]
            if section not in SECTIONS: bot.answer_callback_query(call.id,"بخش شناخته نشد."); return
            previous=PANEL_CURRENT.get(uid,"home")
            if previous!=section: PANEL_HISTORY.setdefault(uid,[]).append(previous)
            send_panel(chat_id,section,call.message.message_id if call.message else None,user_id=uid)
            bot.answer_callback_query(call.id); return
        if data.startswith("toggle:"):
            setting=data.split(":",1)[1]
            if not is_owner(uid):
                bot.answer_callback_query(call.id,"⛔ این پنل مخصوص مالک رباته!",show_alert=True); return
            if setting=="smart_security":
                DATA["settings"]["smart_security"]=not DATA["settings"].get("smart_security",True); save_data()
                bot.answer_callback_query(call.id,"امنیت هوشمند سراسری: "+("روشن" if DATA["settings"]["smart_security"] else "خاموش")); send_panel(chat_id,"smart",call.message.message_id if call.message else None,user_id=uid); return
            WAITING[uid]={"action":"toggle_group_setting","setting":"smart_security" if setting=="group_smart_security" else setting}
            bot.answer_callback_query(call.id)
            bot.send_message(uid,"🆔 شناسه گروه را بفرست (معمولاً با ‎-100‎ شروع می‌شود).")
            return
        if data.startswith("ask:"):
            if not is_owner(uid):
                bot.answer_callback_query(call.id,"⛔ این پنل مخصوص مالک رباته!",show_alert=True); return
            action=data.split(":",1)[1]
            global_actions={"public_features","channel_url","website_url","referral_reward_toman","subscription_packages","wallet_adjust","add_whitelist","remove_whitelist","member_info","clear_warnings","activate_group","extend_group","revoke_group","announcement","group_stats","group_settings","search_logs","register_bot_admin","remove_bot_admin"}
            if action in global_actions:
                WAITING[uid]={"action":action}
                prompts={
                    "public_features":"متن معرفی کاربران در /start را بفرست. برای رفتن به خط بعدی از خط جدید استفاده کن؛ این متن به‌صورت ساده نمایش داده می‌شود.",
                    "channel_url":"لینک کامل کانال با https:// را بفرست.",
                    "website_url":"لینک کامل وب‌سایت با https:// را بفرست.",
                    "referral_reward_toman":"مبلغ پاداش هر دعوت معتبر را به تومان وارد کن (پیش‌فرض ۵۰۰۰).",
                    "subscription_packages":"بسته‌ها را به شکل روز:قیمت وارد کن؛ مثال: 30:40000,60:80000,90:120000 . این فهرست جایگزین بسته‌های قبلی می‌شود.",
                    "wallet_adjust":"قالب: شناسه کاربر | مبلغ (+برای افزایش و -برای کاهش) | دلیل تغییر",
                    "add_whitelist":"شناسه گروه | شناسه کاربر را بفرست.",
                    "remove_whitelist":"شناسه گروه | شناسه کاربر را بفرست.",
                    "member_info":"شناسه گروه | شناسه کاربر را بفرست.",
                    "clear_warnings":"شناسه گروه | شناسه کاربر را بفرست.",
                    "activate_group":"ربات را مدیر گروه کن؛ سپس داخل همان گروه بنویس: فعال سازی ۳۰ روز (عدد ۰ یعنی دائمی).",
                    "extend_group":"شناسه گروه | تعداد روز را بفرست.",
                    "revoke_group":"شناسه گروه را بفرست.",
                    "announcement":"شناسه گروه | متن اطلاعیه را بفرست.",
                    "group_stats":"شناسه گروه را بفرست (مثلاً -1001234567890).",
                    "group_settings":"شناسه گروه را بفرست (مثلاً -1001234567890).",
                    "search_logs":"عبارت یا شناسه‌ای برای جست‌وجو در گزارش‌ها بفرست.",
                    "register_bot_admin":"فقط نام کاربری تلگرام را با @ بفرست؛ نمونه: @username\nنکته امنیتی: آن شخص باید قبلاً ربات را باز کرده و /start زده باشد.",
                    "remove_bot_admin":"نام کاربری ادمینی را که می‌خواهی دسترسی‌اش حذف شود با @ بفرست؛ نمونه: @username"
                }
                bot.answer_callback_query(call.id); bot.send_message(uid,prompts[action]); return
            group_actions={"welcome_text","farewell_text","rules","auto_reply","delete_reply","bad_word","warn_limit","whitelist","add_custom_command","delete_custom_command","add_note","delete_note","quiet_hours","welcome_image","welcome_delete_seconds","force_join","force_add"}
            if action in group_actions:
                WAITING[uid]={"action":"select_group_for_action","next_action":action}
                bot.answer_callback_query(call.id); bot.send_message(uid,"🆔 شناسه گروه را بفرست (معمولاً با -100 شروع می‌شود). سپس مقدار تنظیم را می‌پرسم."); return
            WAITING[uid]={"action":action,"chat_id":chat_id}
            prompts={"welcome_text":"متن خوشامد را بفرست؛ {name} نام کاربر را جایگزین می‌کند.","farewell_text":"متن خداحافظی را بفرست؛ {name} نام کاربر را جایگزین می‌کند.","add_note":"قالب یادداشت: نام کوتاه | متن یادداشت. در گروه با #نام یادداشت نمایش داده می‌شود.","delete_note":"نام یادداشتی را که می‌خواهی حذف شود بفرست.","rules":"قوانین جدید را بفرست.","auto_reply":"قالب: کلمه کلیدی | متن پاسخ","delete_reply":"کلمه کلیدی پاسخ خودکار را بفرست.","bad_word":"کلمه ممنوع را بفرست.","warn":"شناسه کاربر یا گروه | شناسه کاربر را بفرست.","mute":"شناسه کاربر یا گروه | شناسه کاربر را بفرست.","unmute":"شناسه کاربر یا گروه | شناسه کاربر را بفرست.","ban":"شناسه کاربر یا گروه | شناسه کاربر را بفرست.","unban":"شناسه کاربر یا گروه | شناسه کاربر را بفرست.","kick":"شناسه کاربر یا گروه | شناسه کاربر را بفرست.","font":"متن را بفرست.","add_proxy":"لینک t.me/proxy یا tg://proxy را بفرست.","delete_proxy":"شماره پروکسی را بفرست.","add_customer":"قالب: شناسه | نام | توضیحات","find_customer":"شناسه مشتری را بفرست.","ticket":"متن تیکت را بفرست.","ai":"سؤال خود را بفرست.","warn_limit":"سقف اخطار بین ۱ تا ۲۰ را بفرست.", "add_whitelist":"شناسه گروه | شناسه کاربر را بفرست.", "remove_whitelist":"شناسه گروه | شناسه کاربر را بفرست.", "member_info":"شناسه گروه | شناسه کاربر را بفرست.", "clear_warnings":"شناسه گروه | شناسه کاربر را بفرست.", "activate_group":"ربات را مدیر گروه کن؛ سپس داخل همان گروه بنویس: فعال سازی ۳۰ روز (عدد ۰ یعنی دائمی).", "extend_group":"شناسه گروه | تعداد روز را بفرست.", "revoke_group":"شناسه گروه را بفرست.", "add_custom_command":"قالب: نام فرمان بدون ! | متن پاسخ","delete_custom_command":"نام فرمان را بفرست.", "announcement":"شناسه گروه | متن اطلاعیه را بفرست.", "group_stats":"شناسه گروه را بفرست (مثلاً -1001234567890).", "group_settings":"شناسه گروه را بفرست (مثلاً -1001234567890).", "search_logs":"عبارت یا شناسه‌ای برای جست‌وجو در گزارش‌ها بفرست.", "quiet_hours":"بازهٔ سکوت را به شکل 23:00-07:00 بفرست؛ برای خاموش‌کردن بنویس خاموش.", "welcome_image":"لینک مستقیم تصویر (https://...) را بفرست؛ برای حذف تصویر بنویس حذف.", "welcome_delete_seconds":"زمان حذف خوشامد به ثانیه (۰ تا ۳۶۰۰) را بفرست."}
            bot.answer_callback_query(call.id); bot.send_message(uid,prompts.get(action,"اطلاعات موردنیاز را بفرست.")); return
        if data.startswith("show:"):
            if not is_owner(uid):
                bot.answer_callback_query(call.id,"⛔ این پنل مخصوص مالک رباته!",show_alert=True); return
            action=data.split(":",1)[1]
            if action in {"ban_list","mute_list","whitelist"}:
                WAITING[uid]={"action":"show_list_group","list_type":action}
                bot.answer_callback_query(call.id); bot.send_message(uid,"شناسه گروه را بفرست (مثلاً -1001234567890).")
                return
            if action == "rules":
                WAITING[uid]={"action":"show_rules_group"}
                bot.answer_callback_query(call.id); bot.send_message(uid,"شناسه گروه را بفرست تا قوانین همان گروه نمایش داده شود.")
                return
            if action == "notes":
                WAITING[uid]={"action":"show_notes_group"}
                bot.answer_callback_query(call.id); bot.send_message(uid,"شناسه گروه را بفرست تا یادداشت‌های همان گروه نمایش داده شوند.")
                return
            if action == "bot_admins":
                admins = DATA.setdefault("bot_admins", {})
                if not admins:
                    body = "📋 هنوز ادمین جانبی ثبت نشده است."
                else:
                    lines = []
                    for admin_id, row in admins.items():
                        username = row.get("username", "") if isinstance(row, dict) else str(row)
                        lines.append(f"• @{esc(username.lstrip('@'))} — شناسه: <code>{esc(admin_id)}</code>")
                    body = "👮 <b>ادمین‌های ثبت‌شده</b>\n━━━━━━━━━━━━━━\n" + "\n".join(lines)
                bot.answer_callback_query(call.id); bot.send_message(uid, body); return
            WAITING[uid]={"action":"show_"+action,"chat_id":chat_id}
            bot.answer_callback_query(call.id); handle_show(uid,action); WAITING.pop(uid,None); return
        if data=="game:guess":
            GAMES[uid]=random.randint(1,5); WAITING[uid]={"action":"game:guess","chat_id":uid}
            bot.answer_callback_query(call.id); bot.send_message(uid,"🎮 عددی بین ۱ تا ۵ حدس بزن و بفرست."); return
        bot.answer_callback_query(call.id,"گزینه ناشناخته است.")
    except Exception as e:
        print("Callback error:",repr(e))
        try: bot.answer_callback_query(call.id,"خطا رخ داد؛ دوباره تلاش کن.",show_alert=True)
        except Exception: pass

@bot.message_handler(content_types=["photo"], func=lambda m: m.chat.type == "private")
def private_receipt_photo_handler(message):
    uid = int(message.from_user.id)
    pending = WAITING.get(uid, {})
    if pending.get("action") != "payment_receipt":
        return
    rid = str(pending.get("request_id", ""))
    req = DATA.get("subscription_requests", {}).get(rid)
    if not req or int(req.get("user_id", 0)) != uid or req.get("status") != "pending":
        WAITING.pop(uid, None)
        safe_reply_to(message, "⚠️ درخواست پرداخت معتبر نیست یا قبلاً بررسی شده است.")
        return
    photo = getattr(message, "photo", None) or []
    if not photo:
        safe_reply_to(message, "لطفاً عکس رسید را به‌صورت تصویر ارسال کن.")
        return
    file_id = getattr(photo[-1], "file_id", "")
    if not file_id:
        safe_reply_to(message, "⚠️ دریافت شناسهٔ تصویر ناموفق بود؛ دوباره ارسال کن.")
        return
    req["receipt_file_id"] = file_id
    req["receipt_user_id"] = uid
    req["receipt_received_at"] = now_text()
    req["receipt_message_id"] = int(message.message_id)
    save_data()
    caption = (f"🧾 <b>رسید پرداخت اشتراک</b>\nدرخواست: <code>{esc(rid)}</code>\n"
               f"شناسه عددی کاربر: <code>{uid}</code>\nمدت: {int(req.get('days', 0))} روز\n"
               f"مبلغ: {int(req.get('price_toman', 0)):,} تومان\n"
               "⚠️ رسید را دستی بررسی کن؛ دریافت تصویر به معنی تأیید پرداخت نیست.")
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.row(types.InlineKeyboardButton("✅ تأیید و فعال‌سازی", callback_data=f"subreq:approve:{rid}"),
           types.InlineKeyboardButton("❌ رد درخواست", callback_data=f"subreq:reject:{rid}"))
    try:
        bot.send_photo(OWNER_ID, file_id, caption=caption, reply_markup=kb)
        WAITING.pop(uid, None)
        safe_reply_to(message, "✅ رسید برای مالک ارسال شد. پس از بررسی، نتیجه اعلام می‌شود؛ اشتراک هنوز فعال نشده است.")
    except Exception as e:
        print("Receipt forwarding error:", repr(e))
        safe_reply_to(message, "⚠️ رسید ذخیره شد، اما ارسال آن به مالک ناموفق بود. کمی بعد دوباره تلاش کن.")


@bot.message_handler(content_types=["text"], func=lambda m: m.chat.type=="private")
def private_text_handler(message):
    uid=message.from_user.id; text=(message.text or "").strip()
    ensure_user(uid,message.from_user.username,message.from_user.first_name)
    if text.startswith("/"): return
    normalized_private = text.replace("ي", "ی").replace("ك", "ک").strip().casefold()
    # Direct utilities are intentionally command-triggered, not unsolicited chat.
    compact = re.sub(r"[\s‌]+", "", normalized_private)
    if compact in {"پروکسی", "لیستپروکسی", "لیستپروکسیها", "پروکسیها", "پروکسیلیست", "پروکسیلیستها", "proxy", "proxies", "proxylist"}:
        bot.send_message(uid, proxy_list_text(limit=20, with_ping=True)); return
    if compact in {"فونت", "لیستفونت", "فونتها", "لیستفونتها", "فونتلیست", "فونتلیستها", "فونت۲۰۰", "فونت200", "font", "fonts", "fontlist"}:
        WAITING[uid] = {"action":"public_font_text"}
        bot.send_message(uid, "🔤 متن یا اسم دلخواهت رو بفرست تا ۲۰۰ مدل فونت فانتزی و جیگول میگول بسازم.")
        return
    if compact in {"بازی", "یهبازی", "بازیها", "بازی ها", "game", "play"}:
        send_random_game(message); return
    if normalized_private in {"هوش", "هوش مصنوعی", "دستیار", "دستیار هوشمند"}:
        bot.send_message(uid, "🧠 دستیار آماده است. درخواستت رو بعد از «هوش» بنویس؛ مثلاً «هوش این متن رو خلاصه کن» یا «هوش راهنمای قفل لینک رو بگو».")
        return
    # Recognize panel commands in private chat too; previously they were silently ignored.
    if normalized_private in {"پنل", "پنل مدیریت", "پنل مالک", "مدیریت"}:
        if is_owner(uid):
            bot.send_message(uid, "🔐 پنل خصوصی مالک باز شد.")
            send_panel(uid, user_id=uid)
        else:
            bot.send_message(uid, "⛔ پنل مدیریت فقط برای مالک ربات است.")
        return
    if normalized_private in {"سلام", "سلام ربات", "درود", "راهنما", "امکانات", "شروع", "help", "hi", "hello"}:
        bot.send_message(uid, start_welcome_text(message.from_user),
                         reply_markup=owner_start_keyboard() if is_owner(uid) else public_keyboard())
        return
    question = ""
    for prefix in ("از ربات بپرس ", "دستیار ", "ربات ", "هوش مصنوعی ", "هوش ", "هوش‌ ", "هش ", "هوس ", "هوشصنعتی "):
        if normalized_private.startswith(prefix):
            question = text[len(prefix):].strip()
            break
    replied = getattr(message, "reply_to_message", None)
    if not question and replied and getattr(getattr(replied, "from_user", None), "is_bot", False) and text and not text.startswith("/"):
        question = text
    if question:
        status = safe_reply_to(message, "🧠 دارم بررسی می‌کنم…")
        answer = ask_ai(question)
        try: bot.edit_message_text(esc(answer[:3900]), status.chat.id, status.message_id)
        except Exception: safe_reply_to(message, esc(answer[:3900]))
        return
    public_shortcuts = {
        "کیف پول": "user:wallet", "موجودی": "user:wallet", "wallet": "user:wallet",
        "خرید اشتراک": "user:shop", "اشتراک": "user:shop", "shop": "user:shop",
        "زیرمجموعه": "user:referrals", "دعوت‌ها": "user:referrals", "دعوت ها": "user:referrals",
        "تراکنش": "user:transactions", "تراکنش‌ها": "user:transactions", "تراکنش ها": "user:transactions",
        "امکانات": "user:home", "راهنما": "user:home", "help": "user:home",
    }
    shortcut = public_shortcuts.get(text.casefold())
    if shortcut == "user:wallet": bot.send_message(uid, public_wallet(uid)); return
    if shortcut == "user:shop": bot.send_message(uid, shop_text(uid), reply_markup=shop_keyboard()); return
    if shortcut == "user:referrals": bot.send_message(uid, referral_text(uid)); return
    if shortcut == "user:transactions": bot.send_message(uid, transactions_text(uid)); return
    if shortcut == "user:home": bot.send_message(uid, public_features_text(), reply_markup=public_keyboard()); return
    pending=WAITING.get(uid)
    if not pending: return
    action=pending.get("action",""); chat_id=pending.get("chat_id",uid)
    owner_only={"add_proxy","delete_proxy","add_customer","find_customer","delete_reply","bad_word","warn_limit","toggle_group_setting","select_group_for_action",
                "public_features","channel_url","website_url","referral_reward_toman","subscription_packages","wallet_adjust","add_whitelist","remove_whitelist","member_info","clear_warnings","activate_group","extend_group","revoke_group","add_custom_command","delete_custom_command","announcement","group_stats","group_settings","search_logs",
                "welcome_text","farewell_text","rules","auto_reply","add_note","delete_note","quiet_hours","welcome_image","welcome_delete_seconds","warn","mute","unmute","ban","unban","kick","show_list_group","show_rules_group","show_notes_group","register_bot_admin","remove_bot_admin"}
    # These actions are owner-only when launched from the owner's private panel,
    # but group administrators may configure the group they administer through
    # the group panel. The target chat ID is stored in WAITING and re-verified.
    group_admin_waiting_actions = {
        "delete_reply", "bad_word", "warn_limit", "add_custom_command", "delete_custom_command",
        "welcome_text", "farewell_text", "rules", "auto_reply", "add_note", "delete_note",
        "quiet_hours", "welcome_image", "welcome_delete_s
