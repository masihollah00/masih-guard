# -*- coding: utf-8 -*-
"""MASIH GUARD S1000+ — single-file Telegram group management bot."""
import os, re, json, time, random, threading, io, urllib.request, urllib.error, html
from datetime import datetime, date
import telebot
from telebot import types

# ---------------- Configuration ----------------
BOT_TOKEN = (os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
OWNER_ID = int(os.getenv("OWNER_ID", "8620924698"))
DATA_FILE = os.getenv("DATA_FILE", "masih_guard_data.json")
AI_API_KEY = os.getenv("AI_API_KEY", "").strip()
AI_BASE_URL = os.getenv("AI_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
AI_MODEL = os.getenv("AI_MODEL", "openai/gpt-4o-mini").strip()
WEBSITE_URL = os.getenv("WEBSITE_URL", "https://neon-portfolio-7vhj.onrender.com").strip()
CHANNEL_URL = os.getenv("CHANNEL_URL", "https://t.me/IRHACK_APP33").strip()
BRAND, VERSION = "MASIH GUARD", "S1000+"
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN تنظیم نشده است؛ آن را در Environment هاست قرار بده.")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML", threaded=True, num_threads=4)
LOCK = threading.RLock()
WAITING, GAMES, PANEL_CURRENT, PANEL_HISTORY = {}, {}, {}, {}
BOT_USERNAME = ""

DEFAULT_GROUP = {
    "anti_link": True, "anti_ads": True, "anti_spam": True, "anti_repeat": True,
    "anti_forward": False, "media_lock": False, "welcome_on": True,
    "farewell_on": False, "join_approval": False, "bad_words": [], "whitelist": [],
    "warn_limit": 3, "rules": "احترام به اعضا الزامی است.",
    "welcome_text": "سلام {name}، به گروه خوش آمدی!", "farewell_text": "خداحافظ {name}",
    "auto_replies": {}
}
DEFAULT_DATA = {
    "groups": {}, "warnings": {}, "logs": [], "proxies": [], "customers": {},
    "tickets": {}, "points": {}, "seen": {}, "stats": {"messages": 0, "blocked": 0,
    "warns": 0, "joins": 0, "tickets": 0},
    "settings": {"smart_security": True},
    "bot_settings": {
        "public_features": "", "channel_url": "https://t.me/IRHACK_APP33",
        "website_url": "https://neon-portfolio-7vhj.onrender.com",
        "daily_reward": 10, "luck_max": 5, "referral_reward": 5,
        "shop_packages": [[40, 15], [80, 30], [120, 45], [160, 60]]
    },
    "users": {}, "referrals": {}, "subscriptions": {}, "transactions": {},
    "last_daily": {}
}

def clone(obj): return json.loads(json.dumps(obj, ensure_ascii=False))
def esc(value): return html.escape(str(value or ""), quote=False)
def now_text(): return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
def today(): return date.today().isoformat()

def load_data():
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict): raise ValueError("Invalid data")
    except (OSError, ValueError, TypeError):
        data = clone(DEFAULT_DATA)
    for k, v in DEFAULT_DATA.items():
        if k not in data: data[k] = clone(v)
    for k, v in DEFAULT_DATA["stats"].items(): data["stats"].setdefault(k, v)
    for k, v in DEFAULT_DATA["settings"].items(): data["settings"].setdefault(k, v)
    for k, v in DEFAULT_DATA.items():
        if isinstance(v, dict) and not isinstance(data.get(k), dict): data[k] = clone(v)
        if isinstance(v, list) and not isinstance(data.get(k), list): data[k] = clone(v)
    return data

DATA = load_data()

def save_data():
    with LOCK:
        tmp = DATA_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(DATA, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, DATA_FILE)

def add_log(action, chat_id="", user_id="", detail=""):
    with LOCK:
        DATA["logs"].append({"time": now_text(), "action": str(action), "chat_id": str(chat_id),
                             "user_id": str(user_id), "detail": str(detail)[:250]})
        DATA["logs"] = DATA["logs"][-800:]
        save_data()

def is_owner(uid): return int(uid or 0) == OWNER_ID

def ensure_user(uid, username="", first_name=""):
    key = str(int(uid))
    with LOCK:
        user = DATA["users"].setdefault(key, {"diamonds": 0, "username": "", "first_name": "",
                                               "joined": now_text(), "last_daily": "", "last_luck": ""})
        if username: user["username"] = username
        if first_name: user["first_name"] = first_name
        user.setdefault("diamonds", 0); user.setdefault("last_daily", ""); user.setdefault("last_luck", "")
        DATA["transactions"].setdefault(key, [])
    return user

def wallet(uid):
    u = ensure_user(uid)
    return max(0, int(u.get("diamonds", 0)))

def transaction(uid, amount, reason):
    key = str(int(uid))
    with LOCK:
        u = ensure_user(uid)
        new_balance = int(u.get("diamonds", 0)) + int(amount)
        if new_balance < 0: return False
        u["diamonds"] = new_balance
        history = DATA["transactions"].setdefault(key, [])
        history.append({"time": now_text(), "amount": int(amount), "reason": str(reason)[:100], "balance": new_balance})
        DATA["transactions"][key] = history[-100:]
        save_data()
    return True

def get_group_settings(chat_id):
    key = str(chat_id)
    if key not in DATA["groups"]: DATA["groups"][key] = clone(DEFAULT_GROUP)
    settings = DATA["groups"][key]
    for k, v in DEFAULT_GROUP.items(): settings.setdefault(k, clone(v))
    return settings

def bot_settings():
    """Return persisted global settings, filling defaults for older data files."""
    defaults = DEFAULT_DATA["bot_settings"]
    settings = DATA.setdefault("bot_settings", clone(defaults))
    for key, value in defaults.items():
        settings.setdefault(key, clone(value))
    if not isinstance(settings.get("shop_packages"), list) or not settings["shop_packages"]:
        settings["shop_packages"] = clone(defaults["shop_packages"])
    return settings

def public_features_text():
    custom = str(bot_settings().get("public_features", "") or "").strip()
    return esc(custom) if custom else PUBLIC_FEATURES

def configured_url(key, fallback):
    value = str(bot_settings().get(key, "") or fallback).strip()
    return value if value.startswith(("https://", "http://")) else fallback

def is_group_admin(chat_id, user_id):
    if is_owner(user_id): return True
    try: return bot.get_chat_member(chat_id, user_id).status in ("administrator", "creator")
    except Exception: return False

# ---------------- Menus ----------------
SECTIONS = {
    "security":"🛡 امنیت گروه", "members":"👥 مدیریت اعضا", "settings":"⚙️ تنظیمات گروه",
    "welcome":"👋 خوشامد و خداحافظی", "rules":"📜 قوانین و پاسخ خودکار",
    "referrals":"👥 زیرمجموعه‌گیری و الماس", "proxy":"🌐 پنل پروکسی",
    "stats":"📊 آمار و گزارش", "customers":"💼 مشتریان و اشتراک",
    "tickets":"🎫 تیکت پشتیبانی", "ai":"🧠 هوش مصنوعی", "games":"🎮 بازی و امتیاز",
    "backup":"💾 پشتیبان‌گیری", "daily":"📅 گزارش روزانه",
    "smart":"🧩 امنیت هوشمند", "status":"🚀 وضعیت ربات",
    "bot_settings":"🎛️ تنظیمات عمومی ربات"
}

PUBLIC_FEATURES = (
    "🌈 <b>MASIH GUARD S1000+</b>\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "🛡 <b>امنیت گروه</b>\n"
    "├ ضد لینک و تبلیغات\n├ ضد اسپم و پیام تکراری\n├ کنترل فوروارد و رسانه\n"
    "├ کلمات ممنوع و اخطار خودکار\n\n"
    "👥 <b>مدیریت اعضا</b>\n"
    "├ اخطار، سکوت، رفع سکوت\n├ مسدودسازی، آزادسازی و اخراج\n"
    "├ خوشامد و خداحافظی سایبری\n├ تأیید درخواست عضویت\n\n"
    "⚙️ <b>ابزارهای کاربردی</b>\n"
    "├ قوانین و پاسخ خودکار\n├ تبدیل متن به فونت‌های فانتزی\n"
    "├ دریافت پروکسی‌های ذخیره‌شده\n├ هوش مصنوعی و تیکت پشتیبانی\n"
    "├ بازی، امتیاز و گزارش فعالیت\n\n"
    "💎 <b>سیستم الماس و اشتراک</b>\n"
    "├ پاداش روزانه و شانس الماس اضافه\n├ دعوت دوستان و دریافت الماس\n"
    "├ کیف پول و تاریخچه تراکنش\n├ فروشگاه بسته‌های ویژه\n\n"
    "━━━━━━━━━━━━━━━━━━━━\n"
    "👇 از دکمه‌های زیر برای شروع استفاده کن."
)

def public_keyboard():
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.row(types.InlineKeyboardButton("💎 کیف پول", callback_data="user:wallet"),
           types.InlineKeyboardButton("🎁 پاداش روزانه", callback_data="user:daily"))
    kb.row(types.InlineKeyboardButton("🍀 شانس الماس", callback_data="user:luck"),
           types.InlineKeyboardButton("🛒 خرید اشتراک", callback_data="user:shop"))
    kb.row(types.InlineKeyboardButton("👥 زیرمجموعه‌گیری", callback_data="user:referrals"),
           types.InlineKeyboardButton("🧾 تراکنش‌ها", callback_data="user:transactions"))
    kb.row(types.InlineKeyboardButton("🔤 تبدیل فونت", callback_data="user:font"),
           types.InlineKeyboardButton("🌐 پروکسی‌ها", callback_data="user:proxies"))
    kb.row(types.InlineKeyboardButton("🎫 پشتیبانی", callback_data="user:ticket"),
           types.InlineKeyboardButton("🧠 هوش مصنوعی", callback_data="user:ai"))
    kb.row(types.InlineKeyboardButton("📢 کانال رسمی", url=configured_url("channel_url", CHANNEL_URL)),
           types.InlineKeyboardButton("🌐 وب‌سایت", url=configured_url("website_url", WEBSITE_URL)))
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
    kb.row(types.InlineKeyboardButton("📢 کانال رسمی", url=configured_url("channel_url", CHANNEL_URL)))
    return kb

def section_keyboard(section):
    kb = types.InlineKeyboardMarkup(row_width=1)
    choices = {
      "security":[("🔗 ضد لینک","toggle:anti_link"),("📢 ضد تبلیغ","toggle:anti_ads"),("🚫 ضد اسپم","toggle:anti_spam"),("🔁 ضد پیام تکراری","toggle:anti_repeat"),("↪️ ضد فوروارد","toggle:anti_forward"),("🖼 قفل رسانه","toggle:media_lock")],
      "welcome":[("👋 خوشامدگویی","toggle:welcome_on"),("👋 پیام خداحافظی","toggle:farewell_on"),("🛂 تأیید خودکار ورود","toggle:join_approval"),("✏️ تنظیم متن خوشامد","ask:welcome_text"),("✏️ تنظیم متن خداحافظی","ask:farewell_text")],
      "rules":[("📜 مشاهده قوانین","show:rules"),("✏️ تنظیم قوانین","ask:rules"),("💬 افزودن پاسخ خودکار","ask:auto_reply"),("🗑 حذف پاسخ خودکار","ask:delete_reply"),("🚫 افزودن کلمه ممنوع","ask:bad_word")],
      "members":[(x, "ask:"+a) for x,a in [("⚠️ اخطار عضو","warn"),("🔇 سکوت عضو","mute"),("🔊 رفع سکوت","unmute"),("⛔ مسدودسازی","ban"),("✅ رفع مسدودی","unban"),("👢 اخراج عضو","kick")]],
      "settings":[("⚙️ تنظیم سقف اخطار","ask:warn_limit"),("📜 تنظیم قوانین","ask:rules")],
      "referrals":[("💎 تنظیمات و آمار الماس","show:diamond_stats"),("👥 نظام زیرمجموعه","show:referral_stats"),("🛒 فروشگاه اشتراک","show:shop")],
      "proxy":[("➕ افزودن پروکسی","ask:add_proxy"),("📋 نمایش پروکسی‌ها","show:proxies"),("🗑 حذف پروکسی","ask:delete_proxy")],
      "stats":[("📊 آمار ربات","show:stats"),("🧾 گزارش فعالیت","show:logs")],
      "customers":[("➕ افزودن مشتری","ask:add_customer"),("📋 فهرست مشتریان","show:customers"),("🔎 جست‌وجوی مشتری","ask:find_customer")],
      "tickets":[("🎫 ثبت تیکت","ask:ticket"),("📋 تیکت‌ها","show:tickets")],
      "ai":[("🧠 پرسش از هوش مصنوعی","ask:ai")],
      "games":[("🎮 بازی حدس عدد","game:guess"),("🏆 امتیاز من","show:points")],
      "backup":[("💾 دریافت نسخه پشتیبان","show:backup")],
      "daily":[("📅 گزارش روزانه","show:daily")],
      "smart":[("🧩 روشن/خاموش امنیت هوشمند","toggle:smart_security")],
      "status":[("🚀 وضعیت ربات","show:status")],
      "bot_settings":[
        ("📝 متن معرفی /start","ask:public_features"),
        ("📢 تغییر لینک کانال","ask:channel_url"),
        ("🌐 تغییر لینک وب‌سایت","ask:website_url"),
        ("🎁 تنظیم پاداش روزانه","ask:daily_reward"),
        ("🍀 تنظیم سقف شانس الماس","ask:luck_max"),
        ("👥 تنظیم پاداش دعوت","ask:referral_reward"),
        ("🛒 تنظیم بسته‌های اشتراک","ask:shop_packages"),
        ("📋 مشاهده تنظیمات فعلی","show:bot_settings")
      ]
    }
    for label, data in choices.get(section, []):
        kb.add(types.InlineKeyboardButton(label, callback_data=data))
    kb.add(types.InlineKeyboardButton("⬅️ بازگشت", callback_data="panel:back"))
    return kb

def send_panel(chat_id, section="home", message_id=None, user_id=None):
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
FONT_MAPS = [
 str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz","𝔸𝔹ℂ𝔻𝔼𝔽𝔾ℍ𝕀𝕁𝕂𝕃𝕄ℕ𝕆ℙℚℝ𝕊𝕋𝕌𝕍𝕎𝕏𝕐ℤ𝕒𝕓𝕔𝕕𝕖𝕗𝕘𝕙𝕚𝕛𝕜𝕝𝕞𝕟𝕠𝕡𝕢𝕣𝕤𝕥𝕦𝕧𝕨𝕩𝕪𝕫"),
 str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz","𝘈𝘉𝘊𝘋𝘌𝘍𝘎𝘏𝘐𝘑𝘒𝘓𝘔𝘕𝘖𝘗𝘘𝘙𝘚𝘛𝘜𝘝𝘞𝘟𝘠𝘡𝘢𝘣𝘤𝘥𝘦𝘧𝘨𝘩𝘪𝘫𝘬𝘭𝘮𝘯𝘰𝘱𝘲𝘳𝘴𝘵𝘶𝘷𝘸𝘹𝘺𝘻"),
 str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz","ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ")]
def convert_font(text, style=0): return text.translate(FONT_MAPS[style % len(FONT_MAPS)])

def apply_referral(uid, payload):
    if not payload.startswith("ref_"): return
    try: referrer = int(payload[4:])
    except ValueError: return
    if referrer == uid: return
    key = str(uid)
    if key in DATA["referrals"]: return
    ensure_user(uid)
    ensure_user(referrer)
    DATA["referrals"][key] = {"referrer": referrer, "time": now_text()}
    reward = max(0, min(100000, int(bot_settings().get("referral_reward", 5))))
    if reward:
        transaction(referrer, reward, f"زیرمجموعه معتبر: {uid}")
    add_log("referral", "", uid, f"referrer={referrer}")
    try: bot.send_message(referrer, f"🎉 یک زیرمجموعه جدید ثبت شد!\n💎 {reward} الماس دریافت کردی.\nموجودی: {wallet(referrer)}")
    except Exception: pass
    save_data()

def referral_text(uid):
    global BOT_USERNAME
    if not BOT_USERNAME:
        try: BOT_USERNAME = bot.get_me().username or ""
        except Exception: pass
    link = f"https://t.me/{BOT_USERNAME}?start=ref_{uid}" if BOT_USERNAME else "نام کاربری ربات هنوز در دسترس نیست."
    count = sum(1 for x in DATA["referrals"].values() if int(x.get("referrer", 0)) == int(uid))
    reward = max(0, int(bot_settings().get("referral_reward", 5)))
    return f"👥 <b>زیرمجموعه‌گیری</b>\n━━━━━━━━━━━━━━\n🔗 لینک دعوت شما:\n<code>{esc(link)}</code>\n\n👥 زیرمجموعه‌های ثبت‌شده: {count}\n💎 پاداش هر زیرمجموعه جدید: {reward} الماس\n⚠️ دعوت خودت یا ثبت دوباره پاداش نمی‌گیرد."

def shop_keyboard():
    kb = types.InlineKeyboardMarkup(row_width=1)
    for item in bot_settings().get("shop_packages", [[40,15],[80,30],[120,45],[160,60]]):
        try: diamonds, days = int(item[0]), int(item[1])
        except (TypeError, ValueError, IndexError): continue
        if diamonds > 0 and days > 0:
            kb.add(types.InlineKeyboardButton(f"💎 {diamonds} الماس — {days} روز امکانات ویژه", callback_data=f"shop:buy:{diamonds}:{days}"))
    kb.add(types.InlineKeyboardButton("⬅️ منوی کاربر", callback_data="user:home"))
    return kb

def shop_text(uid):
    sub = DATA["subscriptions"].get(str(uid), {})
    expiry = sub.get("expires", "نداری")
    packages = bot_settings().get("shop_packages", [[40,15],[80,30],[120,45],[160,60]])
    package_text = "\n".join(f"💎 {int(x[0])} الماس = {int(x[1])} روز" for x in packages if isinstance(x, (list, tuple)) and len(x) == 2)
    return ("🛒 <b>فروشگاه اشتراک MASIH GUARD</b>\n━━━━━━━━━━━━━━\n"
            f"{package_text}\n\n"
            f"💰 موجودی شما: {wallet(uid)} الماس\n⭐ پایان اشتراک فعلی: {esc(expiry)}\n"
            "بسته ویژه پس از خرید به حساب شما افزوده می‌شود.")

def public_wallet(uid):
    u = ensure_user(uid)
    sub = DATA["subscriptions"].get(str(uid), {})
    return (f"💎 <b>کیف پول شما</b>\n━━━━━━━━━━━━━━\n"
            f"💰 موجودی: <b>{wallet(uid)}</b> الماس\n"
            f"🎮 امتیاز بازی: {DATA['points'].get(str(uid),0)}\n"
            f"⭐ اشتراک ویژه تا: {esc(sub.get('expires','نداری'))}")

def transactions_text(uid):
    rows = DATA["transactions"].get(str(uid), [])[-12:]
    if not rows: return "🧾 هنوز تراکنشی ثبت نشده است."
    return "🧾 <b>آخرین تراکنش‌ها</b>\n" + "\n".join(
        f"{'➕' if x['amount'] >= 0 else '➖'} {x['amount']} الماس — {esc(x['reason'])}\n<code>{esc(x['time'])}</code>"
        for x in reversed(rows))

def daily_reward(uid):
    u = ensure_user(uid)
    if u.get("last_daily") == today(): return "⏳ پاداش روزانه‌ات را امروز گرفته‌ای؛ فردا دوباره بیا."
    amount = max(0, min(100000, int(bot_settings().get("daily_reward", 10))))
    u["last_daily"] = today()
    transaction(uid, amount, "پاداش روزانه")
    save_data()
    return f"🎁 {amount} الماس پاداش روزانه گرفتی!\n💎 موجودی: {wallet(uid)}"

def luck_reward(uid):
    u = ensure_user(uid)
    if u.get("last_luck") == today(): return "🍀 شانس روزانه‌ات را امروز امتحان کرده‌ای؛ فردا دوباره بیا."
    u["last_luck"] = today()
    maximum = max(0, min(1000, int(bot_settings().get("luck_max", 5))))
    amount = random.randint(0, maximum)
    if amount: transaction(uid, amount, "شانس روزانه")
    else: save_data()
    return f"🍀 نتیجه شانس امروز: {amount} الماس!\n💎 موجودی: {wallet(uid)}"

def buy_subscription(uid, diamonds, days):
    packages = {}
    for item in bot_settings().get("shop_packages", [[40,15],[80,30],[120,45],[160,60]]):
        try: packages[int(item[0])] = int(item[1])
        except (TypeError, ValueError, IndexError): continue
    if packages.get(diamonds) != days: return "❌ بسته معتبر نیست."
    if wallet(uid) < diamonds: return "💎 الماس کافی نداری؛ از پاداش روزانه یا زیرمجموعه‌گیری استفاده کن."
    # Charge then extend from the later of now or current expiry.
    from datetime import timedelta
    now = datetime.now()
    current = DATA["subscriptions"].get(str(uid), {}).get("expires", "")
    try: base = datetime.strptime(current, "%Y-%m-%d %H:%M:%S")
    except Exception: base = now
    if base < now: base = now
    if not transaction(uid, -diamonds, f"خرید اشتراک {days} روزه"): return "❌ خرید انجام نشد."
    expires = (base + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    DATA["subscriptions"][str(uid)] = {"expires": expires, "updated": now_text()}
    save_data()
    add_log("subscription_bought", "", uid, f"{days} days")
    return f"✅ خرید موفق بود!\n⭐ اشتراک ویژه تا {esc(expires)} فعال است.\n💎 مانده: {wallet(uid)}"

# ---------------- Security and moderation ----------------
def get_text(message): return getattr(message, "text", None) or getattr(message, "caption", None) or ""
def has_link(text): return bool(re.search(r"(https?://|www\.|t\.me/|telegram\.me/|@[A-Za-z0-9_]{5,})", text or "", re.I))
def has_ad(text): return any(x in (text or "").casefold() for x in ["تبلیغ", "تبلیغات", "خرید ممبر", "فروش ممبر", "عضوگیری", "کسب درآمد تضمینی"])
def is_forwarded(m): return any(getattr(m, x, None) for x in ("forward_origin","forward_from","forward_from_chat","forward_date"))
def has_media(m): return any(getattr(m,x,None) for x in ("photo","video","audio","voice","document","animation","sticker","video_note","contact","location"))
def safe_delete(message):
    try: bot.delete_message(message.chat.id, message.message_id); return True
    except Exception as e: print("Delete error:", repr(e)); return False

def warn_member(chat_id, user_id, reason="تخلف از قوانین"):
    key=f"{chat_id}:{user_id}"
    DATA["warnings"][key]=int(DATA["warnings"].get(key,0))+1
    count=DATA["warnings"][key]; limit=max(1,int(get_group_settings(chat_id).get("warn_limit",3) or 3))
    DATA["stats"]["warns"]+=1
    try: bot.send_message(chat_id,f"⚠️ اخطار برای <code>{user_id}</code>\nدلیل: {esc(reason)}\nتعداد: {count}/{limit}")
    except Exception: pass
    add_log("warning",chat_id,user_id,reason)
    if count >= limit:
        try:
            bot.ban_chat_member(chat_id,user_id)
            bot.send_message(chat_id,f"⛔ کاربر <code>{user_id}</code> به سقف اخطار رسید و مسدود شد.")
            DATA["warnings"][key]=0
        except Exception as e: print("Auto-ban error:",repr(e))
    save_data()

def process_group_security(message):
    chat,user=message.chat,message.from_user
    if not DATA.get("settings", {}).get("smart_security", True): return False
    if not user or chat.type not in ("group","supergroup") or is_group_admin(chat.id,user.id): return False
    s=get_group_settings(chat.id); text=get_text(message); key=f"{chat.id}:{user.id}"
    prev=DATA["seen"].get(key,{}); now=time.time(); reason=None
    if s.get("media_lock") and has_media(message): reason="ارسال رسانه در حالت قفل رسانه"
    elif s.get("anti_forward") and is_forwarded(message): reason="ارسال پیام فورواردشده"
    elif s.get("anti_link") and has_link(text) and str(user.id) not in [str(x) for x in s.get("whitelist",[])]: reason="ارسال لینک"
    elif s.get("anti_ads") and has_ad(text): reason="ارسال تبلیغ"
    elif text and any(w and str(w).casefold() in text.casefold() for w in s.get("bad_words",[])): reason="استفاده از کلمه ممنوع"
    if not reason and text and s.get("anti_repeat") and prev.get("text")==text and now-prev.get("time",0)<30: reason="پیام تکراری"
    times=[t for t in prev.get("times",[]) if now-t<8]; times.append(now)
    if not reason and s.get("anti_spam") and len(times)>=7: reason="ارسال پیام‌های پرتعداد"
    DATA["seen"][key]={"text":text,"time":now,"times":[] if reason=="ارسال پیام‌های پرتعداد" else times}
    if reason:
        if safe_delete(message):
            DATA["stats"]["blocked"]+=1; add_log("blocked",chat.id,user.id,reason); warn_member(chat.id,user.id,reason)
        return True
    save_data(); return False

@bot.message_handler(content_types=["text","photo","video","audio","voice","document","sticker","animation","video_note","contact","location"], func=lambda m: m.chat.type in ("group","supergroup"))
def group_message_handler(message):
    try:
        DATA["stats"]["messages"]+=1
        if process_group_security(message): return
        text=get_text(message)
        if text:
            for keyword,reply in get_group_settings(message.chat.id).get("auto_replies",{}).items():
                if keyword and keyword.casefold() in text.casefold():
                    bot.reply_to(message,str(reply)[:4000]); break
        save_data()
    except Exception as e: print("Group handler error:",repr(e))

def welcome_card(chat_id, member):
    try:
        count = bot.get_chat_member_count(chat_id)
    except Exception: count = "نامشخص"
    stamp = datetime.now()
    name = esc(member.first_name or "دوست عزیز")
    uname = ("@" + esc(member.username)) if getattr(member,"username",None) else "ندارد"
    return ("⚡ <b>MASIH GUARD</b> ⚡\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "🚀 <b>عضو جدید وارد شد!</b>\n\n"
            f"👤 <b>نام کاربر:</b> {name}\n"
            f"🆔 <b>آیدی:</b> <code>{member.id}</code>\n"
            f"🔖 <b>شناسه:</b> {uname}\n"
            f"📅 <b>تاریخ ورود:</b> {stamp.strftime('%Y-%m-%d')}\n"
            f"🕒 <b>ساعت ورود:</b> {stamp.strftime('%H:%M:%S')}\n"
            f"👥 <b>تعداد اعضا:</b> {count}\n\n"
            "🛡️ <b>امنیت گروه فعال است</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "<i>Powered by MASIH GUARD S1000+</i>")

@bot.message_handler(content_types=["new_chat_members"], func=lambda m: m.chat.type in ("group","supergroup"))
def welcome_new_members(message):
    s=get_group_settings(message.chat.id)
    for member in message.new_chat_members:
        DATA["stats"]["joins"]+=1; add_log("new_member",message.chat.id,member.id,"ورود به گروه")
        if s.get("welcome_on"):
            try:
                # Use the approved cyber-style card while preserving a custom welcome message if configured.
                custom=s.get("welcome_text","سلام {name}، به گروه خوش آمدی!")
                if custom and custom != DEFAULT_GROUP["welcome_text"]:
                    text=esc(custom).replace("{name}",esc(member.first_name or "دوست عزیز"))
                    bot.send_message(message.chat.id, welcome_card(message.chat.id,member)+"\n\n"+text)
                else: bot.send_message(message.chat.id,welcome_card(message.chat.id,member))
            except Exception as e: print("Welcome error:",repr(e))
    save_data()

@bot.message_handler(content_types=["left_chat_member"], func=lambda m: m.chat.type in ("group","supergroup"))
def farewell_member(message):
    s=get_group_settings(message.chat.id); member=message.left_chat_member
    if member and s.get("farewell_on"):
        try:
            custom = s.get("farewell_text", DEFAULT_GROUP["farewell_text"])
            body = esc(custom).replace("{name}", esc(member.first_name or "دوست ما"))
            bot.send_message(message.chat.id, "🌙 <b>MASIH GUARD S1000+</b>\n━━━━━━━━━━━━━━\n👋 " + body)
        except Exception as e: print("Farewell error:",repr(e))
    if member: add_log("member_left",message.chat.id,member.id,"خروج از گروه")

@bot.chat_join_request_handler()
def handle_join_request(request):
    try:
        if get_group_settings(request.chat.id).get("join_approval"):
            bot.approve_chat_join_request(request.chat.id,request.from_user.id)
            DATA["stats"]["joins"]+=1; add_log("join_request_approved",request.chat.id,request.from_user.id,"تأیید خودکار ورود"); save_data()
    except Exception as e: print("Join request approval error:",repr(e))

def ask_ai(question):
    if not AI_API_KEY: return "⚠️ کلید هوش مصنوعی تنظیم نشده است. متغیر AI_API_KEY را در هاست وارد کن."
    payload={"model":AI_MODEL,"messages":[{"role":"system","content":"تو دستیار فارسی MASIH GUARD هستی. روشن، دقیق و دوستانه پاسخ بده."},{"role":"user","content":str(question)[:5000]}],"temperature":0.7,"max_tokens":1200}
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
    return (f"📊 <b>آمار {BRAND}</b>\n━━━━━━━━━━━━━━━━━━\n💬 پیام‌ها: {s['messages']}\n"
            f"🚫 حذف‌شده‌ها: {s['blocked']}\n⚠️ اخطارها: {s['warns']}\n👥 ورود اعضا: {s['joins']}\n"
            f"🎫 تیکت‌ها: {s['tickets']}\n🌐 پروکسی‌ها: {len(DATA['proxies'])}\n💼 مشتریان: {len(DATA['customers'])}")

def create_ticket(uid, username, text):
    tid=str(int(time.time()*1000))
    DATA["tickets"][tid]={"user_id":int(uid),"username":username or "","text":text[:3500],"status":"open","created":now_text()}
    DATA["stats"]["tickets"]+=1; save_data()
    try: bot.send_message(OWNER_ID,f"🎫 <b>تیکت جدید</b>\nشناسه: <code>{tid}</code>\nکاربر: <code>{uid}</code>\n\n{esc(text[:3500])}")
    except Exception as e: print("Ticket forwarding error:",repr(e))
    return tid

def send_backup(chat_id):
    if not is_owner(chat_id): bot.send_message(chat_id,"⛔ نسخه پشتیبان فقط برای مالک است."); return
    f=io.BytesIO(json.dumps(DATA,ensure_ascii=False,indent=2).encode("utf-8")); f.name="masih_guard_backup.json"
    bot.send_document(chat_id,f,caption="💾 نسخه پشتیبان MASIH GUARD")

def moderate_member(action,chat_id,user_id):
    if action=="warn": warn_member(chat_id,user_id,"اخطار مدیر"); return "⚠️ اخطار ثبت شد."
    if action=="ban": bot.ban_chat_member(chat_id,user_id); add_log("manual_ban",chat_id,user_id,"مسدودسازی مدیر"); return "⛔ عضو مسدود شد."
    if action=="unban": bot.unban_chat_member(chat_id,user_id,only_if_banned=True); return "✅ مسدودی برداشته شد."
    if action=="kick": bot.ban_chat_member(chat_id,user_id); bot.unban_chat_member(chat_id,user_id,only_if_banned=True); return "👢 عضو اخراج شد."
    if action in ("mute","unmute"):
        allowed=action=="unmute"
        perms=types.ChatPermissions(can_send_messages=allowed,can_send_audios=allowed,can_send_documents=allowed,
            can_send_photos=allowed,can_send_videos=allowed,can_send_video_notes=allowed,can_send_voice_notes=allowed,
            can_send_polls=allowed,can_send_other_messages=allowed,can_add_web_page_previews=allowed)
        bot.restrict_chat_member(chat_id,user_id,permissions=perms)
        return "🔊 محدودیت برداشته شد." if allowed else "🔇 عضو محدود شد."
    raise ValueError("عملیات ناشناخته است.")

def handle_show(uid, action):
    if action=="stats": bot.send_message(uid,stats_text())
    elif action=="status": bot.send_message(uid,f"🚀 <b>{BRAND} {VERSION}</b>\nربات در حال اجراست.\nهوش مصنوعی: {'تنظیم شده' if AI_API_KEY else 'تنظیم نشده'}")
    elif action=="rules":
        p=WAITING.get(uid,{}); bot.send_message(uid,esc(get_group_settings(p.get("chat_id",uid))["rules"]))
    elif action=="proxies":
        bot.send_message(uid,"\n".join(f"{i+1}. {esc(x)}" for i,x in enumerate(DATA["proxies"][:10])) if DATA["proxies"] else "فهرست پروکسی‌ها خالی است.")
    elif action=="customers":
        rows=[f"• {esc(v.get('name'))} — <code>{esc(k)}</code>" for k,v in list(DATA["customers"].items())[:50]]
        bot.send_message(uid,"💼 <b>مشتریان</b>\n"+"\n".join(rows) if rows else "مشتری ثبت نشده است.")
    elif action=="logs":
        rows=[f"{esc(x.get('time'))} — {esc(x.get('action'))} — {esc(x.get('detail'))}" for x in DATA["logs"][-20:]]
        bot.send_message(uid,"🧾 <b>آخرین گزارش‌ها</b>\n"+"\n".join(rows) if rows else "گزارشی ثبت نشده است.")
    elif action=="backup": send_backup(uid)
    elif action=="daily": bot.send_message(uid,stats_text()+"\n\nگزارش از شمارنده‌های ذخیره‌شده ساخته شده است.")
    elif action=="points": bot.send_message(uid,f"🏆 امتیاز شما: {DATA['points'].get(str(uid),0)}")
    elif action=="tickets":
        rows=[(k,v) for k,v in DATA["tickets"].items() if v.get("user_id")==uid or is_owner(uid)]
        bot.send_message(uid,"\n\n".join(f"🎫 <code>{esc(k)}</code> — {esc(v.get('status'))}\n{esc(v.get('text','')[:200])}" for k,v in rows[-15:]) if rows else "تیکتی ثبت نشده است.")
    elif action=="diamond_stats":
        bot.send_message(uid,f"💎 کاربران کیف پول‌دار: {len(DATA['users'])}\n👥 زیرمجموعه‌های ثبت‌شده: {len(DATA['referrals'])}\n⭐ اشتراک‌ها: {len(DATA['subscriptions'])}")
    elif action=="referral_stats":
        bot.send_message(uid,f"👥 کل زیرمجموعه‌های ثبت‌شده: {len(DATA['referrals'])}\n💎 پاداش هر دعوت معتبر: ۵ الماس")
    elif action=="shop": bot.send_message(uid,shop_text(uid),reply_markup=shop_keyboard())
    elif action=="bot_settings":
        cfg = bot_settings()
        packages = "، ".join(f"{int(x[0])} الماس/{int(x[1])} روز" for x in cfg.get("shop_packages", []) if isinstance(x, (list, tuple)) and len(x) == 2)
        custom_intro = "سفارشی" if str(cfg.get("public_features", "")).strip() else "پیش‌فرض"
        bot.send_message(uid,
            "🎛️ <b>تنظیمات عمومی ذخیره‌شده</b>\n━━━━━━━━━━━━━━\n"
            f"📝 متن معرفی /start: {custom_intro}\n"
            f"🎁 پاداش روزانه: {cfg.get('daily_reward', 10)} الماس\n"
            f"🍀 سقف شانس: {cfg.get('luck_max', 5)} الماس\n"
            f"👥 پاداش دعوت: {cfg.get('referral_reward', 5)} الماس\n"
            f"🛒 بسته‌ها: {esc(packages)}\n"
            f"📢 کانال: {esc(cfg.get('channel_url', CHANNEL_URL))}\n"
            f"🌐 وب‌سایت: {esc(cfg.get('website_url', WEBSITE_URL))}")

# ---------------- Commands and callbacks ----------------
@bot.message_handler(commands=["start","panel","help"])
def start_command(message):
    uid=message.from_user.id if message.from_user else 0
    if message.chat.type=="private":
        ensure_user(uid,message.from_user.username,message.from_user.first_name)
        args=(message.text or "").split(maxsplit=1)
        if len(args)>1: apply_referral(uid,args[1].strip())
        if is_owner(uid):
            send_panel(message.chat.id,user_id=uid)
            bot.send_message(message.chat.id,public_features_text(),reply_markup=public_keyboard())
        else:
            bot.send_message(message.chat.id,public_features_text(),reply_markup=public_keyboard())
        return
    if not is_owner(uid):
        bot.reply_to(message,"پنل مدیریت فقط در اختیار مالک ربات است؛ برای فهرست امکانات به گفت‌وگوی خصوصی ربات برو.")
        return
    send_panel(message.chat.id,user_id=uid)

@bot.message_handler(commands=["id"])
def id_command(message):
    bot.reply_to(message,f"🆔 شناسه کاربر: <code>{message.from_user.id}</code>\nشناسه چت: <code>{message.chat.id}</code>")

@bot.message_handler(commands=["ai","ask"])
def ai_command(message):
    parts=(message.text or "").split(maxsplit=1)
    if len(parts)<2:
        bot.reply_to(message,"🤖 سؤال را بعد از دستور بنویس:\n/ai سلام، خودت را معرفی کن"); return
    status=bot.reply_to(message,"🤖 در حال بررسی سؤال...")
    answer=ask_ai(parts[1].strip())
    try: bot.edit_message_text(esc(answer[:3900]),status.chat.id,status.message_id)
    except Exception: bot.send_message(message.chat.id,esc(answer[:3900]))

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    try:
        data=call.data or ""; uid=call.from_user.id; chat_id=call.message.chat.id if call.message else uid
        if data.startswith("user:") or data.startswith("shop:"):
            if not call.message or call.message.chat.type!="private":
                bot.answer_callback_query(call.id,"این گزینه را در گفت‌وگوی خصوصی ربات استفاده کن.",show_alert=True); return
            ensure_user(uid,call.from_user.username,call.from_user.first_name)
            if data=="user:home":
                bot.answer_callback_query(call.id); bot.send_message(uid,public_features_text(),reply_markup=public_keyboard()); return
            if data=="user:wallet": bot.answer_callback_query(call.id); bot.send_message(uid,public_wallet(uid)); return
            if data=="user:daily": bot.answer_callback_query(call.id); bot.send_message(uid,daily_reward(uid)); return
            if data=="user:luck": bot.answer_callback_query(call.id); bot.send_message(uid,luck_reward(uid)); return
            if data=="user:shop": bot.answer_callback_query(call.id); bot.send_message(uid,shop_text(uid),reply_markup=shop_keyboard()); return
            if data=="user:referrals": bot.answer_callback_query(call.id); bot.send_message(uid,referral_text(uid)); return
            if data=="user:transactions": bot.answer_callback_query(call.id); bot.send_message(uid,transactions_text(uid)); return
            if data=="user:font":
                WAITING[uid]={"action":"public_font"}; bot.answer_callback_query(call.id); bot.send_message(uid,"متنی را بفرست تا در سه سبک فونت تبدیل کنم."); return
            if data=="user:proxies":
                bot.answer_callback_query(call.id)
                bot.send_message(uid,"\n".join(f"{i+1}. <code>{esc(x)}</code>" for i,x in enumerate(DATA["proxies"][:10])) if DATA["proxies"] else "🌐 هنوز پروکسی‌ای توسط مالک ذخیره نشده است."); return
            if data=="user:ticket":
                WAITING[uid]={"action":"ticket"}; bot.answer_callback_query(call.id); bot.send_message(uid,"متن تیکت پشتیبانی را بفرست."); return
            if data=="user:ai":
                WAITING[uid]={"action":"ai"}; bot.answer_callback_query(call.id); bot.send_message(uid,"سؤال خود را برای هوش مصنوعی بفرست."); return
            if data.startswith("shop:buy:"):
                _,_,d,days=data.split(":"); result=buy_subscription(uid,int(d),int(days))
                bot.answer_callback_query(call.id); bot.send_message(uid,result); return

        if data=="panel:back":
            history=PANEL_HISTORY.setdefault(uid,[]); section=history.pop() if history else "home"
            send_panel(chat_id,section,call.message.message_id if call.message else None,user_id=uid)
            bot.answer_callback_query(call.id); return
        if data=="panel:home":
            PANEL_HISTORY[uid]=[]; send_panel(chat_id,"home",call.message.message_id if call.message else None,user_id=uid)
            bot.answer_callback_query(call.id); return
        if data.startswith("panel:"):
            if not is_owner(uid):
                bot.answer_callback_query(call.id,"فقط مالک ربات مجاز است.",show_alert=True); return
            section=data.split(":",1)[1]
            if section not in SECTIONS: bot.answer_callback_query(call.id,"بخش شناخته نشد."); return
            previous=PANEL_CURRENT.get(uid,"home")
            if previous!=section: PANEL_HISTORY.setdefault(uid,[]).append(previous)
            send_panel(chat_id,section,call.message.message_id if call.message else None,user_id=uid)
            bot.answer_callback_query(call.id); return
        if data.startswith("toggle:"):
            setting=data.split(":",1)[1]
            if not is_owner(uid):
                bot.answer_callback_query(call.id,"فقط مالک مجاز است.",show_alert=True); return
            if setting=="smart_security":
                DATA["settings"]["smart_security"]=not DATA["settings"].get("smart_security",True); save_data()
                bot.answer_callback_query(call.id,"تغییر ذخیره شد."); send_panel(chat_id,"smart",call.message.message_id if call.message else None); return
            WAITING[uid]={"action":"toggle_group_setting","setting":setting}
            bot.answer_callback_query(call.id)
            bot.send_message(uid,"🆔 شناسه گروه را بفرست (معمولاً با ‎-100‎ شروع می‌شود).")
            return
        if data.startswith("ask:"):
            if not is_owner(uid):
                bot.answer_callback_query(call.id,"فقط مالک مجاز است.",show_alert=True); return
            action=data.split(":",1)[1]
            global_actions={"public_features","channel_url","website_url","daily_reward","luck_max","referral_reward","shop_packages"}
            if action in global_actions:
                WAITING[uid]={"action":action}
                prompts={
                    "public_features":"متن معرفی کاربران در /start را بفرست. برای رفتن به خط بعدی از خط جدید استفاده کن؛ این متن به‌صورت ساده نمایش داده می‌شود.",
                    "channel_url":"لینک کامل کانال با https:// را بفرست.",
                    "website_url":"لینک کامل وب‌سایت با https:// را بفرست.",
                    "daily_reward":"تعداد الماس پاداش روزانه را به‌صورت عدد ۰ تا ۱۰۰۰۰۰ بفرست.",
                    "luck_max":"حداکثر الماس شانس روزانه را به‌صورت عدد ۰ تا ۱۰۰۰ بفرست.",
                    "referral_reward":"پاداش هر زیرمجموعه معتبر را به‌صورت عدد ۰ تا ۱۰۰۰۰۰ بفرست.",
                    "shop_packages":"بسته‌ها را این‌طور بفرست: 40=15,80=30,120=45,160=60 (الماس=روز). حداقل یک بسته لازم است."
                }
                bot.answer_callback_query(call.id); bot.send_message(uid,prompts[action]); return
            group_actions={"welcome_text","farewell_text","rules","auto_reply","delete_reply","bad_word","warn_limit"}
            if action in group_actions:
                WAITING[uid]={"action":"select_group_for_action","next_action":action}
                bot.answer_callback_query(call.id); bot.send_message(uid,"🆔 شناسه گروه را بفرست (معمولاً با -100 شروع می‌شود). سپس مقدار تنظیم را می‌پرسم."); return
            WAITING[uid]={"action":action,"chat_id":chat_id}
            prompts={"welcome_text":"متن خوشامد را بفرست؛ {name} نام کاربر را جایگزین می‌کند.","farewell_text":"متن خداحافظی را بفرست؛ {name} نام کاربر را جایگزین می‌کند.","rules":"قوانین جدید را بفرست.","auto_reply":"قالب: کلمه کلیدی | متن پاسخ","delete_reply":"کلمه کلیدی پاسخ خودکار را بفرست.","bad_word":"کلمه ممنوع را بفرست.","warn":"شناسه کاربر یا گروه | شناسه کاربر را بفرست.","mute":"شناسه کاربر یا گروه | شناسه کاربر را بفرست.","unmute":"شناسه کاربر یا گروه | شناسه کاربر را بفرست.","ban":"شناسه کاربر یا گروه | شناسه کاربر را بفرست.","unban":"شناسه کاربر یا گروه | شناسه کاربر را بفرست.","kick":"شناسه کاربر یا گروه | شناسه کاربر را بفرست.","font":"متن را بفرست.","add_proxy":"لینک t.me/proxy یا tg://proxy را بفرست.","delete_proxy":"شماره پروکسی را بفرست.","add_customer":"قالب: شناسه | نام | توضیحات","find_customer":"شناسه مشتری را بفرست.","ticket":"متن تیکت را بفرست.","ai":"سؤال خود را بفرست.","warn_limit":"سقف اخطار بین ۱ تا ۲۰ را بفرست."}
            bot.answer_callback_query(call.id); bot.send_message(uid,prompts.get(action,"اطلاعات موردنیاز را بفرست.")); return
        if data.startswith("show:"):
            if not is_owner(uid):
                bot.answer_callback_query(call.id,"فقط مالک مجاز است.",show_alert=True); return
            action=data.split(":",1)[1]
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

@bot.message_handler(content_types=["text"], func=lambda m: m.chat.type=="private")
def private_text_handler(message):
    uid=message.from_user.id; text=(message.text or "").strip()
    ensure_user(uid,message.from_user.username,message.from_user.first_name)
    if text.startswith("/"): return
    # Direct public tools work without opening a panel first.
    if text.casefold()=="پروکسی":
        bot.send_message(uid,"\n".join(f"{i+1}. <code>{esc(x)}</code>" for i,x in enumerate(DATA["proxies"][:10])) if DATA["proxies"] else "🌐 هنوز پروکسی‌ای توسط مالک ذخیره نشده است.")
        return
    if text.casefold()=="فونت":
        WAITING[uid]={"action":"public_font"}; bot.send_message(uid,"متنی را بفرست تا در سه سبک فونت تبدیل کنم."); return
    if text.casefold().startswith("فونت "):
        raw=text[5:].strip()
        bot.send_message(uid,"🔤 <b>سه سبک فونت</b>\n\n"+esc(convert_font(raw,0))+"\n\n"+esc(convert_font(raw,1))+"\n\n"+esc(convert_font(raw,2))); return
    pending=WAITING.get(uid)
    if not pending: return
    action=pending.get("action",""); chat_id=pending.get("chat_id",uid)
    owner_only={"add_proxy","delete_proxy","add_customer","find_customer","delete_reply","bad_word","warn_limit","toggle_group_setting","select_group_for_action",
                "public_features","channel_url","website_url","daily_reward","luck_max","referral_reward","shop_packages"}
    if action in owner_only and not is_owner(uid):
        WAITING.pop(uid,None); bot.send_message(uid,"⛔ این عملیات فقط برای مالک است."); return
    try:
        if action in {"public_features","channel_url","website_url","daily_reward","luck_max","referral_reward","shop_packages"}:
            cfg = bot_settings()
            if action == "public_features":
                if text.casefold() in {"پیش‌فرض", "default", "بازنشانی"}:
                    cfg["public_features"] = ""
                    message_text = "✅ متن معرفی به حالت پیش‌فرض برگشت."
                else:
                    if len(text) > 3500: raise ValueError("متن معرفی حداکثر ۳۵۰۰ نویسه باشد.")
                    cfg["public_features"] = text
                    message_text = "✅ متن معرفی /start ذخیره شد."
            elif action in ("channel_url", "website_url"):
                if not text.startswith(("https://", "http://")) or len(text) > 500:
                    raise ValueError("لینک کامل با https:// یا http:// وارد کن.")
                cfg[action] = text
                message_text = "✅ لینک ذخیره شد."
            elif action in ("daily_reward", "luck_max", "referral_reward"):
                value = int(text)
                maximum = 1000 if action == "luck_max" else 100000
                if not 0 <= value <= maximum: raise ValueError(f"عدد باید بین ۰ تا {maximum} باشد.")
                cfg[action] = value
                message_text = "✅ مقدار جدید ذخیره شد."
            else:
                packages = []
                for part in text.split(","):
                    if "=" not in part: raise ValueError("قالب درست: 40=15,80=30")
                    diamonds, days = (int(v.strip()) for v in part.split("=", 1))
                    if not (1 <= diamonds <= 1000000 and 1 <= days <= 3650):
                        raise ValueError("الماس باید ۱ تا ۱۰۰۰۰۰۰ و روز ۱ تا ۳۶۵۰ باشد.")
                    if any(old[0] == diamonds for old in packages): raise ValueError("مقدار الماس تکراری است.")
                    packages.append([diamonds, days])
                if not packages or len(packages) > 10: raise ValueError("از ۱ تا ۱۰ بسته وارد کن.")
                cfg["shop_packages"] = packages
                message_text = "✅ بسته‌های اشتراک ذخیره شدند."
            save_data(); add_log("bot_setting_updated", "", uid, action)
            WAITING.pop(uid, None)
            bot.send_message(uid, message_text)
            return
        if action=="select_group_for_action":
            target=int(text)
            if target>=0: raise ValueError("شناسه گروه باید منفی باشد.")
            next_action=pending.get("next_action","")
            WAITING[uid]={"action":next_action,"chat_id":target}
            prompts={"welcome_text":"متن خوشامد را بفرست؛ می‌توانی {name} بگذاری.","farewell_text":"متن خداحافظی را بفرست.","rules":"قوانین جدید را بفرست.","auto_reply":"قالب: کلمه کلیدی | متن پاسخ","delete_reply":"کلمه کلیدی را بفرست.","bad_word":"کلمه ممنوع را بفرست.","warn_limit":"سقف اخطار ۱ تا ۲۰ را بفرست."}
            bot.send_message(uid,"✅ گروه انتخاب شد.\n"+prompts.get(next_action,"مقدار تنظیم را بفرست.")); return
        if action=="toggle_group_setting":
            target=int(text)
            if target>=0: raise ValueError("شناسه گروه باید منفی باشد.")
            setting=pending.get("setting",""); s=get_group_settings(target)
            if not isinstance(s.get(setting),bool): raise ValueError("این تنظیم قابل تغییر نیست.")
            s[setting]=not s[setting]; save_data(); add_log("setting_toggled",target,uid,f"{setting}={s[setting]}")
            bot.send_message(uid,f"✅ تنظیم {setting} برای گروه <code>{target}</code>: {'روشن' if s[setting] else 'خاموش'}")
        elif action in ("public_font","font"):
            bot.send_message(uid,"🔤 <b>سه سبک فونت</b>\n\n"+esc(convert_font(text,0))+"\n\n"+esc(convert_font(text,1))+"\n\n"+esc(convert_font(text,2)))
        elif action in ("welcome_text","farewell_text","rules"):
            s=get_group_settings(chat_id); s[action]=text[:3000]; save_data(); bot.send_message(uid,"✅ ذخیره شد.")
        elif action=="auto_reply":
            if "|" not in text: bot.send_message(uid,"قالب: کلمه کلیدی | متن پاسخ"); return
            keyword,reply=[p.strip() for p in text.split("|",1)]
            if not keyword or not reply: raise ValueError("کلمه کلیدی و پاسخ خالی نباشند.")
            get_group_settings(chat_id)["auto_replies"][keyword]=reply[:2000]; save_data(); bot.send_message(uid,"✅ پاسخ خودکار ذخیره شد.")
        elif action=="delete_reply":
            existed=get_group_settings(chat_id)["auto_replies"].pop(text,None); save_data()
            bot.send_message(uid,"🗑 پاسخ حذف شد." if existed is not None else "کلمه کلیدی پیدا نشد.")
        elif action=="bad_word":
            s=get_group_settings(chat_id)
            if text not in s["bad_words"]: s["bad_words"].append(text[:100])
            save_data(); bot.send_message(uid,"✅ کلمه ممنوع ثبت شد.")
        elif action=="warn_limit":
            n=int(text)
            if not 1<=n<=20: raise ValueError("عدد باید بین ۱ تا ۲۰ باشد.")
            get_group_settings(chat_id)["warn_limit"]=n; save_data(); bot.send_message(uid,"✅ سقف اخطار ذخیره شد.")
        elif action in ("warn","mute","unmute","ban","unban","kick"):
            parts=[x.strip() for x in text.split("|")]
            target_chat,target_user=(int(chat_id),int(parts[0])) if len(parts)==1 else (int(parts[0]),int(parts[1]))
            if not is_owner(uid) and not is_group_admin(target_chat,uid): raise PermissionError("باید مدیر همان گروه باشی.")
            bot.send_message(uid,moderate_member(action,target_chat,target_user))
        elif action=="add_proxy":
            if not (text.startswith("https://t.me/proxy?") or text.startswith("http://t.me/proxy?") or text.startswith("tg://proxy?")): raise ValueError("لینک معتبر t.me/proxy یا tg://proxy وارد کن.")
            if text in DATA["proxies"]: bot.send_message(uid,"این پروکسی قبلاً ثبت شده است.")
            else: DATA["proxies"].append(text); save_data(); add_log("proxy_added","",uid,text); bot.send_message(uid,"✅ پروکسی ذخیره شد.")
        elif action=="delete_proxy":
            i=int(text)-1
            if not 0<=i<len(DATA["proxies"]): raise ValueError("شماره پروکسی معتبر نیست.")
            removed=DATA["proxies"].pop(i); save_data(); add_log("proxy_deleted","",uid,removed); bot.send_message(uid,"🗑 پروکسی حذف شد.")
        elif action=="add_customer":
            parts=[p.strip() for p in text.split("|",2)]
            if len(parts)<2: raise ValueError("قالب: شناسه | نام | توضیحات")
            DATA["customers"][parts[0]]={"name":parts[1],"details":parts[2] if len(parts)>2 else "","created":now_text()}
            save_data(); bot.send_message(uid,"✅ مشتری ثبت شد.")
        elif action=="find_customer":
            c=DATA["customers"].get(text)
            bot.send_message(uid,(f"💼 <b>{esc(c['name'])}</b>\nشناسه: <code>{esc(text)}</code>\nتوضیحات: {esc(c.get('details',''))}") if c else "مشتری پیدا نشد.")
        elif action=="ticket":
            tid=create_ticket(uid,message.from_user.username,text); bot.send_message(uid,f"🎫 تیکت ثبت شد. شناسه: <code>{tid}</code>")
        elif action=="ai":
            status=bot.send_message(uid,"🧠 در حال دریافت پاسخ...")
            answer=ask_ai(text)
            try: bot.edit_message_text(esc(answer[:3900]),uid,status.message_id)
            except Exception: bot.send_message(uid,esc(answer[:3900]))
        elif action=="game:guess":
            guess=int(text)
            if not 1<=guess<=5: raise ValueError("عدد باید بین ۱ تا ۵ باشد.")
            answer=GAMES.get(uid)
            if answer is None: raise ValueError("بازی فعالی نیست.")
            if guess==answer:
                DATA["points"][str(uid)]=DATA["points"].get(str(uid),0)+1; save_data()
                bot.send_message(uid,f"🎉 درست بود! عدد {answer} بود؛ یک امتیاز گرفتی.")
            else: bot.send_message(uid,f"این بار نه؛ عدد درست {answer} بود.")
            GAMES.pop(uid,None)
        elif action.startswith("show_"): handle_show(uid,action[5:])
        else: bot.send_message(uid,"این عملیات هنوز پیاده‌سازی نشده است.")
        WAITING.pop(uid,None)
    except (ValueError,TypeError,PermissionError) as e:
        bot.send_message(uid,"⚠️ ورودی یا دسترسی معتبر نیست.\n"+esc(str(e)))
    except Exception as e:
        print("Private action error:",repr(e)); bot.send_message(uid,"⚠️ عملیات ناموفق بود؛ دسترسی ربات و اطلاعات واردشده را بررسی کن.")

if __name__ == "__main__":
    print(f"{BRAND} {VERSION}: starting polling")
    try:
        bot.infinity_polling(skip_pending=True, timeout=30, long_polling_timeout=25)
    except Exception as e:
        print("Polling stopped:",repr(e))
        raise
