# -*- coding: utf-8 -*-
"""MASIH GUARD v10.0 — Persian Telegram group manager.
Python 3.11+. Keep secrets in host environment variables.
"""
import os, re, json, time, logging, threading, unicodedata
from collections import defaultdict, deque
from datetime import datetime, timezone
import requests
import telebot
from telebot import types
from flask import Flask, jsonify

BOT_NAME = "MASIH GUARD"
BOT_TITLE = "مسیح گارد"
VERSION = "10.0"
BOT_TOKEN = (os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
AI_API_KEY = os.getenv("AI_API_KEY", "").strip()
AI_BASE_URL = (os.getenv("AI_BASE_URL") or "https://openrouter.ai/api/v1").strip().rstrip("/")
AI_MODEL = (os.getenv("AI_MODEL") or "openrouter/free").strip()
DATA_FILE = os.getenv("DATA_FILE", "masih_guard_data.json")
CHANNEL_URL = "https://t.me/IRHACK_APP33"
CREATOR_URL = "https://t.me/Ma3ih01"
try: OWNER_ID = int(os.getenv("OWNER_ID", "8620924698"))
except (TypeError, ValueError): OWNER_ID = 0
try: PORT = int(os.getenv("PORT", "8080"))
except (TypeError, ValueError): PORT = 8080

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper(), format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger(BOT_NAME)
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing. Set BOT_TOKEN in hosting environment variables.")
if not AI_BASE_URL.startswith("https://"): AI_BASE_URL = "https://openrouter.ai/api/v1"
if not AI_MODEL or AI_MODEL.startswith(("http://", "https://")) or AI_MODEL.endswith("/api/v1"): AI_MODEL = "openrouter/free"
bot = telebot.TeleBot(BOT_TOKEN, parse_mode=None, threaded=True, num_threads=6)
app = Flask(__name__)
lock = threading.RLock()
spam_history = defaultdict(deque)
duplicate_history = defaultdict(lambda: deque(maxlen=8))
font_waiting = {}
bot_username = ""

DEFAULT_SETTINGS = {
    "anti_link": True, "anti_spam": True, "anti_duplicate": True,
    "badword_filter": True, "welcome_enabled": True,
    "max_messages": 6, "spam_window": 8, "max_warnings": 3,
    "mute_seconds": 60, "welcome_text": "👋 خوش اومدی {name} عزیز! به گروه خوش اومدی 💜",
    "captcha_enabled": False, "lock_media": False
}
def default_data(): return {"badwords": {}, "warnings": {}, "settings": {}, "logs": [], "stats": {}, "subscriptions": {}}
def load_data():
    try:
        if os.path.isfile(DATA_FILE):
            with open(DATA_FILE, "r", encoding="utf-8") as f: saved = json.load(f)
            if isinstance(saved, dict):
                base = default_data()
                for k, v in base.items():
                    if isinstance(saved.get(k), type(v)): base[k] = saved[k]
                return base
    except Exception: log.exception("بارگذاری اطلاعات ناموفق بود")
    return default_data()
data = load_data()
def save_data():
    with lock:
        try:
            folder = os.path.dirname(os.path.abspath(DATA_FILE)); os.makedirs(folder, exist_ok=True)
            tmp = DATA_FILE + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, DATA_FILE)
        except Exception: log.exception("ذخیره اطلاعات ناموفق بود")
def settings(cid):
    with lock:
        s = data["settings"].setdefault(str(cid), {})
        for k, v in DEFAULT_SETTINGS.items(): s.setdefault(k, v)
        return s
def log_action(cid, message):
    with lock:
        data["logs"].append({"chat": str(cid), "time": datetime.now(timezone.utc).isoformat(), "text": str(message)[:240]})
        data["logs"] = data["logs"][-500:]
    save_data()
def reply(m, text, **kwargs):
    try: return bot.reply_to(m, str(text)[:4000], **kwargs)
    except Exception: log.exception("ارسال پاسخ ناموفق بود"); return None
def send_text(cid, text, reply_to=None):
    text = str(text or "پاسخی دریافت نشد.")
    for pos in range(0, len(text), 3900):
        try:
            kw = {"chat_id": cid, "text": text[pos:pos+3900]}
            if reply_to is not None: kw["reply_to_message_id"] = reply_to
            bot.send_message(**kw)
        except Exception: log.exception("ارسال پیام ناموفق بود"); break
def group_chat(m): return m.chat.type in ("group", "supergroup")
def owner(uid): return bool(uid and OWNER_ID and uid == OWNER_ID)
def is_admin(cid, uid):
    if owner(uid): return True
    try: return bot.get_chat_member(cid, uid).status in ("administrator", "creator")
    except Exception: return False
def is_link(text):
    if not text: return False
    pats = [r"(?i)\b(?:https?://|ftp://|www\.)[^\s<>]+", r"(?i)(?<![\w@])(?:t\.me|telegram\.me|telegram\.dog)/[^\s<>]*", r"(?i)(?<![\w@])(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+(?:com|net|org|io|co|me|info|biz|xyz|app|dev|site|online|ir|de|uk|ru|tr)(?::\d+)?(?:[/?:#][^\s<>]*)?"]
    return any(re.search(p, str(text)) for p in pats)
def has_link(m, text):
    if is_link(text): return True
    return any(getattr(e, "type", "") in ("url", "text_link") for attr in ("entities", "caption_entities") for e in (getattr(m, attr, None) or []))
def target_user(m):
    r = getattr(m, "reply_to_message", None)
    if r and getattr(r, "from_user", None): return r.from_user
    parts = (m.text or "").split()
    if len(parts) > 1 and parts[1].lstrip("-").isdigit():
        try: return bot.get_chat_member(m.chat.id, int(parts[1])).user
        except Exception: return None
    return None
def manageable(m):
    if not group_chat(m): reply(m, "این دستور را داخل گروه اجرا کن."); return None
    if not is_admin(m.chat.id, m.from_user.id): reply(m, "⛔ فقط مدیران گروه اجازه دارند."); return None
    u = target_user(m)
    if not u: reply(m, "⚠️ روی پیام کاربر ریپلای کن یا آیدی عددی او را بنویس."); return None
    if u.id in (m.from_user.id, OWNER_ID): reply(m, "⛔ این کاربر قابل هدف‌گیری نیست."); return None
    try:
        if bot.get_chat_member(m.chat.id, u.id).status in ("administrator", "creator"):
            reply(m, "⛔ این دستور روی مدیران گروه اجرا نمی‌شود."); return None
    except Exception: pass
    return u
def badwords(cid):
    with lock:
        v = data["badwords"].get(str(cid), [])
        return list(v) if isinstance(v, list) else []
def add_warning(cid, uid):
    key=f"{cid}:{uid}"
    with lock: data["warnings"][key] = int(data["warnings"].get(key, 0)) + 1; n=data["warnings"][key]
    save_data(); return n
def get_warnings(cid, uid):
    with lock: return int(data["warnings"].get(f"{cid}:{uid}", 0))

@app.get("/")
def root(): return jsonify({"name": BOT_NAME, "version": VERSION, "status": "running"})
@app.get("/health")
def health(): return jsonify({"status": "ok", "bot": BOT_NAME, "version": VERSION})

def ai_answer(question, context=""):
    if not AI_API_KEY: return "⚠️ هوش مصنوعی تنظیم نشده؛ مقدار AI_API_KEY را در متغیرهای محیطی هاست قرار بده."
    payload={"model":AI_MODEL,"messages":[{"role":"system","content":"تو دستیار فارسی‌زبان MASIH GUARD هستی. روشن، مودب، دقیق و ایمن جواب بده؛ اگر مطمئن نیستی صادقانه بگو."},{"role":"user","content":f"گفتگو: {context or 'خصوصی'}\nپرسش: {str(question)[:3500]}"}],"temperature":0.7,"max_tokens":900}
    try:
        r=requests.post(AI_BASE_URL+"/chat/completions",headers={"Authorization":"Bearer "+AI_API_KEY,"Content-Type":"application/json","HTTP-Referer":"https://github.com/masihollah00/masih-guard","X-OpenRouter-Title":BOT_NAME},json=payload,timeout=(10,45))
        if not r.ok:
            log.error("AI API HTTP %s: %s",r.status_code,r.text[:250])
            return {401:"⚠️ کلید هوش مصنوعی نامعتبر است.",403:"⚠️ دسترسی سرویس رد شد.",429:"⚠️ محدودیت درخواست؛ کمی بعد دوباره امتحان کن.",402:"⚠️ سرویس اعتبار کافی ندارد یا پرداخت لازم است.",400:"⚠️ تنظیمات مدل را بررسی کن.",404:"⚠️ مدل پیدا نشد؛ مقدار AI_MODEL را بررسی کن."}.get(r.status_code,f"⚠️ خطای سرویس هوش مصنوعی: HTTP {r.status_code}")
        choices=r.json().get("choices") or []; content=(choices[0].get("message") or {}).get("content") if choices else None
        if isinstance(content,list): content="\n".join(str(x.get("text","")) for x in content if isinstance(x,dict))
        return content.strip() if isinstance(content,str) and content.strip() else "⚠️ پاسخ هوش مصنوعی خالی بود."
    except requests.Timeout: return "⚠️ پاسخ هوش مصنوعی طول کشید؛ دوباره امتحان کن."
    except requests.RequestException: log.exception("AI request failed"); return "⚠️ اتصال به سرویس هوش مصنوعی برقرار نشد."
    except Exception: log.exception("Unexpected AI error"); return "⚠️ خطای غیرمنتظره در هوش مصنوعی."
def ai_reply(m, question):
    status=reply(m,"🤖 دارم فکر می‌کنم...")
    answer=ai_answer(question,getattr(m.chat,"title","") or "")
    if status:
        try: bot.edit_message_text(str(answer)[:4000],m.chat.id,status.message_id); return
        except Exception: pass
    send_text(m.chat.id,answer,m.message_id)

# 100 font styles: mathematical Unicode alphabets where available.
def _map_range(start, upper=True):
    chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZ" if upper else "abcdefghijklmnopqrstuvwxyz"
    out=[]
    for ch in chars:
        cp=ord(ch)
        if upper and ch in "CHRSZ" and start in (0x1D400,0x1D434,0x1D468,0x1D504,0x1D538,0x1D56C,0x1D5A0,0x1D5D4,0x1D608,0x1D63C,0x1D670):
            special={0x1D400:{"C":"ℂ","H":"ℍ","N":"ℕ","P":"ℙ","Q":"ℚ","R":"ℝ","Z":"ℤ"},0x1D434:{"B":"ℬ","E":"ℰ","F":"ℱ","H":"ℋ","I":"ℐ","L":"ℒ","M":"ℳ","R":"ℛ"},0x1D468:{"C":"ℭ","H":"ℌ","I":"ℑ","R":"ℜ","Z":"ℨ"},0x1D538:{"C":"ℂ","H":"ℍ","N":"ℕ","P":"ℙ","Q":"ℚ","R":"ℝ","Z":"ℤ"}}
            if ch in special.get(start,{}): out.append(special[start][ch]); continue
        out.append(chr(start+cp-ord("A" if upper else "a")))
    return "".join(out)
# Each entry is a named conversion; style names are translated for users.
STYLE_STARTS=[0x1D400,0x1D434,0x1D468,0x1D504,0x1D538,0x1D56C,0x1D5A0,0x1D5D4,0x1D608,0x1D63C,0x1D670]
STYLE_NAMES=["پررنگ","ایتالیک","پررنگ ایتالیک","گوتیک","دوبل","گوتیک پررنگ","بدون سریف","بدون سریف پررنگ","بدون سریف ایتالیک","بدون سریف پررنگ ایتالیک","تک‌فاصله"]
def make_style_map(index):
    start=STYLE_STARTS[index%len(STYLE_STARTS)]
    upper=_map_range(start,True)
    # Mathematical lowercase ranges have matching offsets for most alphabets.
    lower_start=start+0x20
    if start==0x1D400: lower_start=0x1D41A
    elif start==0x1D434: lower_start=0x1D44E
    elif start==0x1D468: lower_start=0x1D482
    elif start==0x1D504: lower_start=0x1D51E
    elif start==0x1D538: lower_start=0x1D552
    elif start==0x1D56C: lower_start=0x1D586
    elif start==0x1D5A0: lower_start=0x1D5BA
    elif start==0x1D5D4: lower_start=0x1D5EE
    elif start==0x1D608: lower_start=0x1D622
    elif start==0x1D63C: lower_start=0x1D656
    elif start==0x1D670: lower_start=0x1D68A
    lower="".join(chr(lower_start+i) for i in range(26))
    return str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz",upper+lower)

def convert_font(text, index):
    try: return str(text).translate(make_style_map(index))
    except Exception: return str(text)
def font_menu(page=0):
    kb=types.InlineKeyboardMarkup(row_width=2)
    start=page*10
    for i in range(start,min(start+10,100)):
        label=f"{i+1:02d} · {STYLE_NAMES[i%len(STYLE_NAMES)]}"
        kb.add(types.InlineKeyboardButton(label,callback_data=f"fontstyle:{i}"))
    nav=[]
    if page>0: nav.append(types.InlineKeyboardButton("⬅️ قبلی",callback_data=f"fontpage:{page-1}"))
    if page<9: nav.append(types.InlineKeyboardButton("بعدی ➡️",callback_data=f"fontpage:{page+1}"))
    if nav: kb.row(*nav)
    kb.add(types.InlineKeyboardButton("🔙 منوی اصلی",callback_data="menu:home"))
    return kb

def home_markup():
    k=types.InlineKeyboardMarkup(row_width=2)
    k.add(types.InlineKeyboardButton("🛡 مدیریت گروه",callback_data="menu:manage"),types.InlineKeyboardButton("✨ قابلیت‌ها",callback_data="menu:features"))
    k.add(types.InlineKeyboardButton("🖋 فونت‌ساز ۱۰۰تایی",callback_data="menu:fonts"),types.InlineKeyboardButton("🌐 پروکسی",callback_data="menu:proxy"))
    k.add(types.InlineKeyboardButton("🤖 هوش مصنوعی",callback_data="menu:ai"),types.InlineKeyboardButton("📊 آمار",callback_data="menu:stats"))
    k.add(types.InlineKeyboardButton("👑 درباره سازنده",callback_data="menu:team"),types.InlineKeyboardButton("💎 ربات اشتراکی",callback_data="menu:shared"))
    k.add(types.InlineKeyboardButton("📢 کانال",url=CHANNEL_URL),types.InlineKeyboardButton("👨‍💻 سازنده",url=CREATOR_URL))
    return k
def back_markup():
    k=types.InlineKeyboardMarkup(); k.add(types.InlineKeyboardButton("🔙 بازگشت به منوی اصلی",callback_data="menu:home")); return k
def panel_markup(cid):
    s=settings(cid); k=types.InlineKeyboardMarkup(row_width=2)
    items=[("anti_link","🔗 ضدلینک"),("anti_spam","🚫 ضداسپم"),("anti_duplicate","🔁 ضدتکرار"),("badword_filter","🤬 فیلتر کلمات"),("welcome_enabled","👋 خوشامدگویی"),("lock_media","🖼 قفل رسانه")]
    for key,label in items: k.add(types.InlineKeyboardButton(f"{label} {'🟢' if s[key] else '🔴'}",callback_data="toggle:"+key))
    k.add(types.InlineKeyboardButton("📊 آمار گروه",callback_data="menu:stats"),types.InlineKeyboardButton("🔙 منوی اصلی",callback_data="menu:home"))
    return k

@bot.message_handler(commands=["start","help"])
def start(m):
    text=(f"⚡ {BOT_TITLE} | {BOT_NAME} نسخه {VERSION}\n\n🛡 مدیریت گروه، فونت‌ساز ۱۰۰ سبکی، هوش مصنوعی و ابزارهای کاربردی\n\nبرای بازکردن پنل بنویس: پنل\nبرای فونت‌ها بنویس: فونت masih\nبرای فهرست پروکسی بنویس: پروکسی\n\nدستورات: /panel /ping /id /rules /ai /font /proxy /proxies /stats")
    bot.send_message(m.chat.id,text,reply_markup=home_markup())
@bot.callback_query_handler(func=lambda c: bool(c.data and c.data.startswith("menu:")))
def menu_callback(c):
    try:
        key=c.data.split(":",1)[1]
        pages={
          "home":(f"⚡ {BOT_TITLE} | {BOT_NAME} نسخه {VERSION}\nهمه ابزارها از این منو در دسترس‌اند.",home_markup()),
          "features":("✨ قابلیت‌ها\n• ضدلینک، ضداسپم و ضدتکرار\n• فیلتر کلمات و خوشامدگویی\n• اخطار، سکوت، مسدودسازی، اخراج و پاک‌سازی\n• فونت‌ساز با ۱۰۰ سبک\n• دستیار هوش مصنوعی فارسی\n• آمار و تنظیمات گروه",back_markup()),
          "manage":("🛡 مدیریت گروه\nربات را مدیر گروه کن و «پنل» را بنویس.\nدستورها: /warn /warnings /unwarn /mute /unmute /ban /unban /kick /purge",back_markup()),
          "fonts":("🖋 فونت‌ساز ۱۰۰ سبکی\nبرای شروع بنویس: فونت masih\nیا دستور /font شماره سبک متن را استفاده کن؛ مثلاً /font 1 Hello Masih\nبسیاری از سبک‌ها حروف انگلیسی را تغییر می‌دهند و حروف فارسی معمولاً بدون تغییر می‌مانند.",font_menu(0)),
          "proxy":("🌐 دریافت پروکسی\nبنویس «پروکسی» یا /proxies تا فهرست عمومی بررسی شود. فعال‌بودن و امنیت لینک‌ها تضمین‌شده نیست.",back_markup()),
          "ai":("🤖 هوش مصنوعی\nدر گفت‌وگوی خصوصی پیام بفرست یا /ai سؤال را بنویس. باید AI_API_KEY در تنظیمات هاست وارد شده باشد.",back_markup()),
          "team":("👑 درباره سازنده\nساخت ربات تلگرام، وب‌سایت و ابزارهای کاربردی.\nسازنده: @Ma3ih01",back_markup()),
          "shared":("💎 ربات اشتراکی\nقابلیت‌های مدیریت و ابزارهای کاربردی در یک ربات. این نسخه پرداخت خودکار یا اشتراک پولی فعال ندارد مگر اینکه جداگانه راه‌اندازی و تأیید شود.",back_markup()),
          "stats":("📊 آمار گروه\nبرای مشاهده آمار گروه، دستور /stats را به‌عنوان مدیر داخل گروه اجرا کن.",back_markup())}
        if key=="fonts":
            bot.edit_message_text(pages[key][0],c.message.chat.id,c.message.message_id,reply_markup=pages[key][1])
        else:
            text,markup=pages.get(key,pages["home"]); bot.edit_message_text(text,c.message.chat.id,c.message.message_id,reply_markup=markup)
        bot.answer_callback_query(c.id)
    except Exception:
        log.exception("Menu callback failed")
        try: bot.answer_callback_query(c.id,"بازکردن منو ناموفق بود.")
        except Exception: pass
@bot.callback_query_handler(func=lambda c: bool(c.data and c.data.startswith("toggle:")))
def toggle_callback(c):
    try:
        if not c.message:return
        cid=c.message.chat.id
        if not is_admin(cid,c.from_user.id): bot.answer_callback_query(c.id,"فقط مدیر گروه اجازه دارد.",show_alert=True); return
        key=c.data.split(":",1)[1]
        if key not in ("anti_link","anti_spam","anti_duplicate","badword_filter","welcome_enabled","lock_media"): bot.answer_callback_query(c.id,"تنظیم نامعتبر"); return
        s=settings(cid); s[key]=not bool(s[key]); save_data(); bot.answer_callback_query(c.id,"تنظیم ذخیره شد.")
        bot.edit_message_reply_markup(cid,c.message.message_id,reply_markup=panel_markup(cid))
    except Exception: log.exception("Toggle callback failed")
@bot.callback_query_handler(func=lambda c: bool(c.data and c.data.startswith("fontpage:")))
def font_page_cb(c):
    try:
        page=max(0,min(9,int(c.data.split(":")[1])))
        bot.edit_message_reply_markup(c.message.chat.id,c.message.message_id,reply_markup=font_menu(page)); bot.answer_callback_query(c.id,f"صفحه {page+1} از ۱۰")
    except Exception: bot.answer_callback_query(c.id,"رفتن به صفحه ناموفق بود.")
@bot.callback_query_handler(func=lambda c: bool(c.data and c.data.startswith("fontstyle:")))
def font_style_cb(c):
    try:
        index=max(0,min(99,int(c.data.split(":")[1])))
        font_waiting[c.from_user.id]=index
        bot.answer_callback_query(c.id,"سبک انتخاب شد؛ حالا متن را بفرست.")
        bot.send_message(c.from_user.id,f"🖋 سبک شماره {index+1} انتخاب شد. متن انگلیسی‌ات را همین‌جا بفرست تا تبدیل کنم.")
    except Exception: log.exception("Font style callback failed")
@bot.message_handler(func=lambda m: bool(m.text) and m.text.strip().lower() in ("پنل","پنل مدیریت","/panel@"+(bot_username or "never")))
def panel_text(m):
    if not group_chat(m):
        if owner(m.from_user.id): bot.send_message(m.chat.id,"👑 پنل مالک MASIH GUARD",reply_markup=home_markup())
        else: reply(m,"⚙️ پنل مدیریت گروه را داخل گروه و با دسترسی مدیر باز کن.")
        return
    if not is_admin(m.chat.id,m.from_user.id): reply(m,"⛔ پنل فقط برای مدیران گروه است."); return
    bot.send_message(m.chat.id,"✨ پنل مدیریت MASIH GUARD v10.0\n🟢 روشن | 🔴 خاموش",reply_markup=panel_markup(m.chat.id))
@bot.message_handler(commands=["panel"])
def panel(m):
    if not group_chat(m):
        if owner(m.from_user.id): bot.send_message(m.chat.id,"👑 پنل مالک MASIH GUARD",reply_markup=home_markup())
        else: reply(m,"⚙️ پنل مدیریت را داخل گروه باز کن.")
        return
    if not is_admin(m.chat.id,m.from_user.id): reply(m,"⛔ پنل فقط برای مدیران گروه است."); return
    bot.send_message(m.chat.id,"✨ پنل مدیریت MASIH GUARD v10.0\n🟢 روشن | 🔴 خاموش",reply_markup=panel_markup(m.chat.id))
@bot.message_handler(commands=["ping"])
def ping(m): reply(m,f"✅ {BOT_NAME} آنلاین است | نسخه {VERSION}")
@bot.message_handler(commands=["id"])
def ids(m): reply(m,f"👤 شناسه شما: {m.from_user.id}\n💬 شناسه گفتگو: {m.chat.id}")
@bot.message_handler(commands=["rules"])
def rules(m): reply(m,"📘 قوانین پیشنهادی: احترام، پرهیز از اسپم و لینک ناخواسته، رعایت قوانین تلگرام و گروه.")
@bot.message_handler(commands=["ai"])
def ai_cmd(m):
    q=(m.text or "").partition(" ")[2].strip()
    if not q and m.reply_to_message:q=(m.reply_to_message.text or m.reply_to_message.caption or "").strip()
    if not q:reply(m,"نمونه: /ai درباره فضا توضیح بده");return
    ai_reply(m,q)
@bot.message_handler(commands=["font"])
def font_cmd(m):
    parts=(m.text or "").split(maxsplit=2)
    if len(parts)<3: reply(m,"استفاده: /font شماره_سبک متن\nمثال: /font 1 Hello Masih\nیا بنویس «فونت masih» و از منو انتخاب کن.");return
    try: idx=int(parts[1])-1
    except ValueError: idx=0
    if idx<0 or idx>99:reply(m,"شماره سبک باید بین ۱ تا ۱۰۰ باشد.");return
    reply(m,convert_font(parts[2],idx))
@bot.message_handler(commands=["proxy"])
def proxy_help(m): reply(m,"🌐 برای دریافت فهرست عمومی، بنویس «پروکسی» یا از /proxies استفاده کن. امنیت و فعال‌بودن لینک‌ها تضمین‌شده نیست.")
@bot.message_handler(commands=["proxies"])
def proxies(m):
    status=reply(m,"🌐 در حال دریافت فهرست پروکسی…")
    sources=["https://raw.githubusercontent.com/ALIILAPRO/MTProtoProxy/main/proxy.txt","https://raw.githubusercontent.com/ALIILAPRO/MTProtoProxy/master/proxy.txt"]
    found=[]
    for url in sources:
        try:
            r=requests.get(url,timeout=10); r.raise_for_status()
            found.extend(re.findall(r"https?://t\.me/proxy\?[^\s<>\"']+",r.text))
            if found:break
        except Exception: log.warning("دریافت منبع پروکسی ناموفق بود: %s",url)
    unique=list(dict.fromkeys(found))[:10]
    out=("🌐 لینک‌های عمومی پیدا شده (فعال‌بودن بررسی نشده):\n\n"+"\n".join(f"{i+1}. {u}" for i,u in enumerate(unique))+"\n\n⚠️ از منابع ناشناس برای حساب‌های حساس استفاده نکن.") if unique else "⚠️ دریافت فهرست پروکسی ممکن نشد؛ اتصال هاست یا منبع عمومی را بررسی کن."
    try:
        if status:bot.edit_message_text(out[:4000],m.chat.id,status.message_id)
        else:send_text(m.chat.id,out)
    except Exception:send_text(m.chat.id,out)
@bot.message_handler(commands=["stats"])
def stats(m):
    if not group_chat(m) or not is_admin(m.chat.id,m.from_user.id):reply(m,"⛔ این دستور فقط برای مدیر گروه است.");return
    with lock:
        logs=[x for x in data["logs"] if x.get("chat")==str(m.chat.id)]
        warned=sum(1 for k,v in data["warnings"].items() if k.startswith(str(m.chat.id)+":") and int(v or 0)>0)
        count=int(data["stats"].get(str(m.chat.id),0))
    s=settings(m.chat.id); active=[label for key,label in [("anti_link","ضدلینک"),("anti_spam","ضداسپم"),("anti_duplicate","ضدتکرار"),("badword_filter","فیلتر کلمات"),("welcome_enabled","خوشامدگویی")] if s[key]]
    reply(m,f"📊 آمار MASIH GUARD\nپیام‌های دیده‌شده از شروع ذخیره آمار: {count}\nگزارش‌های ثبت‌شده: {len(logs)}\nکاربران دارای اخطار: {warned}\nقابلیت‌های روشن: {', '.join(active) if active else 'هیچ‌کدام'}")
@bot.message_handler(commands=["warn"])
def warn(m):
    u=manageable(m)
    if not u:return
    n=add_warning(m.chat.id,u.id); limit=int(settings(m.chat.id)["max_warnings"])
    reply(m,f"⚠️ اخطار ثبت شد: {n}/{limit}");log_action(m.chat.id,f"اخطار برای {u.id}: {n}")
    if n>=limit:
        try:bot.ban_chat_member(m.chat.id,u.id);reply(m,"⛔ سقف اخطار رسید؛ کاربر مسدود شد.");log_action(m.chat.id,f"مسدودسازی خودکار {u.id}")
        except Exception:log.exception("Auto-ban failed");reply(m,"⚠️ مسدودسازی خودکار ناموفق بود؛ مجوزهای ربات را بررسی کن.")
@bot.message_handler(commands=["warnings"])
def warnings_cmd(m):
    u=target_user(m);uid=u.id if u else m.from_user.id;reply(m,f"⚠️ تعداد اخطارها: {get_warnings(m.chat.id,uid)}")
@bot.message_handler(commands=["unwarn"])
def unwarn(m):
    u=manageable(m)
    if not u:return
    with lock:data["warnings"][f"{m.chat.id}:{u.id}"]=0
    save_data();reply(m,"✅ اخطارهای کاربر پاک شد.")
@bot.message_handler(commands=["mute"])
def mute(m):
    u=manageable(m)
    if not u:return
    try:
        secs=max(30,min(86400,int(settings(m.chat.id)["mute_seconds"])))
        bot.restrict_chat_member(m.chat.id,u.id,until_date=int(time.time())+secs,permissions=types.ChatPermissions(can_send_messages=False))
        reply(m,f"🔇 کاربر برای {secs} ثانیه سکوت شد.");log_action(m.chat.id,f"سکوت {u.id} برای {secs} ثانیه")
    except Exception:log.exception("Mute failed");reply(m,"⚠️ سکوت ناموفق بود؛ مجوز محدودکردن اعضا را بررسی کن.")
@bot.message_handler(commands=["unmute"])
def unmute(m):
    u=manageable(m)
    if not u:return
    try:
        bot.restrict_chat_member(m.chat.id,u.id,permissions=types.ChatPermissions(can_send_messages=True,can_send_audios=True,can_send_documents=True,can_send_photos=True,can_send_videos=True,can_send_video_notes=True,can_send_voice_notes=True,can_send_polls=True,can_send_other_messages=True,can_add_web_page_previews=True))
        reply(m,"🔊 سکوت کاربر برداشته شد.")
    except Exception:log.exception("Unmute failed");reply(m,"⚠️ رفع سکوت ناموفق بود؛ مجوزها را بررسی کن.")
@bot.message_handler(commands=["ban"])
def ban(m):
    u=manageable(m)
    if not u:return
    try:bot.ban_chat_member(m.chat.id,u.id);reply(m,"⛔ کاربر مسدود شد.");log_action(m.chat.id,f"مسدودسازی {u.id}")
    except Exception:log.exception("Ban failed");reply(m,"⚠️ مسدودسازی ناموفق بود؛ مجوزهای ربات را بررسی کن.")
@bot.message_handler(commands=["unban"])
def unban(m):
    if not group_chat(m) or not is_admin(m.chat.id,m.from_user.id):reply(m,"⛔ فقط مدیر گروه.");return
    p=(m.text or "").split()
    if len(p)<2 or not p[1].lstrip("-").isdigit():reply(m,"استفاده: /unban شناسه_عددی");return
    try:bot.unban_chat_member(m.chat.id,int(p[1]));reply(m,"✅ مسدودیت برداشته شد.")
    except Exception:log.exception("Unban failed");reply(m,"⚠️ رفع مسدودیت ناموفق بود.")
@bot.message_handler(commands=["kick"])
def kick(m):
    u=manageable(m)
    if not u:return
    try:bot.ban_chat_member(m.chat.id,u.id);bot.unban_chat_member(m.chat.id,u.id);reply(m,"👢 کاربر از گروه اخراج شد.");log_action(m.chat.id,f"اخراج {u.id}")
    except Exception:log.exception("Kick failed");reply(m,"⚠️ اخراج ناموفق بود.")
@bot.message_handler(commands=["purge"])
def purge(m):
    if not group_chat(m) or not is_admin(m.chat.id,m.from_user.id):reply(m,"⛔ فقط مدیر گروه.");return
    if not m.reply_to_message:reply(m,"روی اولین پیام موردنظر ریپلای کن و /purge بزن.");return
    first=m.reply_to_message.message_id;last=m.message_id-1
    if last-first>100:first=last-100
    deleted=0
    for mid in range(first,last+1):
        try:bot.delete_message(m.chat.id,mid);deleted+=1
        except Exception:pass
    reply(m,f"🧹 پاک‌سازی تمام شد؛ پیام‌های پاک‌شده: {deleted}")
def set_setting(m,key,value):
    if not group_chat(m) or not is_admin(m.chat.id,m.from_user.id):reply(m,"⛔ مدیر گروه باید این دستور را داخل گروه اجرا کند.");return
    settings(m.chat.id)[key]=value;save_data();reply(m,"✅ تنظیم ذخیره شد.")
for _cmd,_key,_value in [("antilink_on","anti_link",True),("antilink_off","anti_link",False),("antispam_on","anti_spam",True),("antispam_off","anti_spam",False),("welcome_on","welcome_enabled",True),("welcome_off","welcome_enabled",False)]:
    def _make_handler(key,value):
        def _handler(m):set_setting(m,key,value)
        return _handler
    bot.message_handler(commands=[_cmd])(_make_handler(_key,_value))
@bot.message_handler(commands=["addbadword"])
def add_badword(m):
    if not group_chat(m) or not is_admin(m.chat.id,m.from_user.id):reply(m,"⛔ فقط مدیر گروه.");return
    word=(m.text or "").partition(" ")[2].strip()[:100]
    if not word:reply(m,"استفاده: /addbadword کلمه");return
    with lock:
        arr=data["badwords"].setdefault(str(m.chat.id),[])
        if word.casefold() not in [str(x).casefold() for x in arr]:arr.append(word)
    save_data();reply(m,"✅ کلمه به فیلتر اضافه شد.")
@bot.message_handler(commands=["delbadword"])
def del_badword(m):
    if not group_chat(m) or not is_admin(m.chat.id,m.from_user.id):reply(m,"⛔ فقط مدیر گروه.");return
    word=(m.text or "").partition(" ")[2].strip()
    if not word:reply(m,"استفاده: /delbadword کلمه");return
    with lock:data["badwords"][str(m.chat.id)]=[x for x in data["badwords"].get(str(m.chat.id),[]) if str(x).casefold()!=word.casefold()]
    save_data();reply(m,"✅ کلمه از فیلتر حذف شد.")
@bot.message_handler(commands=["badwords"])
def list_badwords(m):
    if not group_chat(m) or not is_admin(m.chat.id,m.from_user.id):reply(m,"⛔ فقط مدیر گروه.");return
    arr=badwords(m.chat.id);reply(m,"📃 کلمات فیلتر:\n"+("\n".join(arr) if arr else "هنوز کلمه‌ای ثبت نشده."))
@bot.message_handler(content_types=["new_chat_members"])
def welcome_members(m):
    s=settings(m.chat.id)
    if not s["welcome_enabled"]:return
    template=str(s.get("welcome_text") or DEFAULT_SETTINGS["welcome_text"])
    for u in m.new_chat_members:
        if not u.is_bot:
            try:bot.send_message(m.chat.id,template.replace("{name}",u.first_name or "دوست عزیز"))
            except Exception:log.exception("Welcome failed")
def group_ai(m,text_value):
    if not bot_username or not text_value:return False
    mentioned=bool(re.search(r"@"+re.escape(bot_username)+r"\b",text_value,re.I));r=m.reply_to_message
    replied=bool(r and r.from_user and r.from_user.is_bot and (r.from_user.username or "").lower()==bot_username.lower())
    if not (mentioned or replied):return False
    cleaned=re.sub(r"@"+re.escape(bot_username)+r"\b","",text_value,flags=re.I).strip()
    if not cleaned and r:cleaned=(r.text or r.caption or "").strip()
    if cleaned:ai_reply(m,cleaned)
    else:reply(m,"سؤالت رو هم بنویس تا جواب بدم.")
    return True
@bot.message_handler(func=lambda m: bool(m.text) and m.chat.type=="private" and not m.text.startswith("/"),content_types=["text"])
def private_ai(m):
    if m.from_user and not m.from_user.is_bot:
        if m.from_user.id in font_waiting:
            idx=font_waiting.pop(m.from_user.id); reply(m,convert_font(m.text,idx)); return
        ai_reply(m,m.text.strip())

GROUP_CONTENT=["text","photo","video","document","audio","voice","animation","sticker","video_note","contact","location","venue","poll"]
@bot.message_handler(func=lambda m: True,content_types=GROUP_CONTENT)
def moderate(m):
    if not m.from_user or m.from_user.is_bot or not group_chat(m):return
    text_value=(m.text or m.caption or "").strip()
    # Persian text aliases; checked here so generic moderation cannot swallow them.
    normalized=text_value.casefold().strip()
    if normalized in ("پروکسی","proxy"):
        proxies(m);return
    if normalized in ("فونت masih","فونت مسیح","فونت" ):
        bot.send_message(m.chat.id,"🖋 یکی از ۱۰۰ سبک فونت را انتخاب کن؛ بعد از انتخاب، متن را در گفت‌وگوی خصوصی ربات بفرست.",reply_markup=font_menu(0));return
    if normalized in ("پنل","پنل مدیریت"):
        if is_admin(m.chat.id,m.from_user.id):bot.send_message(m.chat.id,"✨ پنل مدیریت MASIH GUARD v10.0",reply_markup=panel_markup(m.chat.id))
        else:reply(m,"⛔ پنل فقط برای مدیران گروه است.")
        return
    s=settings(m.chat.id); admin=is_admin(m.chat.id,m.from_user.id)
    with lock:data["stats"][str(m.chat.id)]=int(data["stats"].get(str(m.chat.id),0))+1
    if not admin:
        if s["anti_link"] and has_link(m,text_value):
            try:bot.delete_message(m.chat.id,m.message_id);log_action(m.chat.id,f"حذف لینک از {m.from_user.id}");bot.send_message(m.chat.id,"🔗 ارسال لینک در گروه مجاز نیست.")
            except Exception:log.exception("Anti-link failed; check delete permission")
            return
        words=badwords(m.chat.id)
        if s["badword_filter"] and text_value and any(w and w.casefold() in text_value.casefold() for w in words):
            try:bot.delete_message(m.chat.id,m.message_id);log_action(m.chat.id,f"حذف کلمه فیلترشده از {m.from_user.id}")
            except Exception:log.exception("Badword delete failed")
            return
        if s["lock_media"] and m.content_type in ("photo","video","document","audio","voice","animation","video_note","sticker"):
            try:bot.delete_message(m.chat.id,m.message_id)
            except Exception:log.exception("Media lock failed")
            return
        if s["anti_duplicate"] and text_value:
            hist=duplicate_history[(m.chat.id,m.from_user.id)];norm=re.sub(r"\s+"," ",text_value).casefold()
            if norm and norm in hist:
                try:bot.delete_message(m.chat.id,m.message_id);log_action(m.chat.id,f"حذف پیام تکراری از {m.from_user.id}")
                except Exception:log.exception("Duplicate delete failed")
                return
            hist.append(norm)
        if s["anti_spam"]:
            now=time.time();hist=spam_history[(m.chat.id,m.from_user.id)];hist.append(now);window=max(1,min(60,int(s.get("spam_window",8))))
            while hist and now-hist[0]>window:hist.popleft()
            maximum=max(2,min(30,int(s.get("max_messages",6))))
            if len(hist)>maximum:
                try:
                    bot.delete_message(m.chat.id,m.message_id);secs=max(30,min(86400,int(s.get("mute_seconds",60))))
                    bot.restrict_chat_member(m.chat.id,m.from_user.id,until_date=int(time.time())+secs,permissions=types.ChatPermissions(can_send_messages=False))
                    bot.send_message(m.chat.id,f"🚫 به دلیل ارسال پیام‌های زیاد، کاربر برای {secs} ثانیه سکوت شد.");log_action(m.chat.id,f"ضداسپم: سکوت {m.from_user.id}")
                except Exception:log.exception("Anti-spam failed; check admin permissions")
                finally:hist.clear()
                return
    group_ai(m,text_value)

def flask_thread():app.run(host="0.0.0.0",port=PORT,use_reloader=False)
def polling_loop():
    global bot_username
    delay=3
    while True:
        try:
            log.info("Starting %s v%s",BOT_NAME,VERSION);me=bot.get_me();bot_username=me.username or ""
            log.info("Telegram connected as @%s",bot_username or "unknown");bot.remove_webhook()
            bot.infinity_polling(timeout=30,long_polling_timeout=25,skip_pending=False);delay=3
        except KeyboardInterrupt:log.info("Bot stopped");break
        except Exception:log.exception("Polling stopped; reconnect in %s seconds",delay);time.sleep(delay);delay=min(delay*2,60)
if __name__=="__main__":
    threading.Thread(target=flask_thread,daemon=True).start()
    polling_loop()
