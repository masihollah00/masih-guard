# -*- coding: utf-8 -*-
"""MASIH GUARD v30.1 | by Masih Hackring
Group moderation, seven-colour inline panel, 100 text styles, public proxy links and optional AI.
Required env: TELEGRAM_BOT_TOKEN (or BOT_TOKEN)
Optional env: OWNER_ID, AI_API_KEY, AI_MODEL, AI_BASE_URL, CHANNEL_URL, CREATOR_URL, PORT, DATA_FILE
"""
import os, re, json, time, html, logging, threading
from collections import defaultdict, deque

import requests
import telebot
from telebot import types
from flask import Flask, jsonify

BOT_TOKEN = (os.getenv('TELEGRAM_BOT_TOKEN') or os.getenv('BOT_TOKEN') or '').strip()
BOT_NAME = 'MASIH GUARD'
VERSION = '30.1'
AUTHOR = 'Masih Hackring'
OWNER_ID = int(os.getenv('OWNER_ID', '8620924698'))
PORT = int(os.getenv('PORT', '8080'))
DATA_FILE = os.getenv('DATA_FILE', 'masih_guard_data.json')
AI_API_KEY = os.getenv('AI_API_KEY', '').strip()
AI_BASE_URL = os.getenv('AI_BASE_URL', 'https://openrouter.ai/api/v1/chat/completions').strip()
AI_MODEL = os.getenv('AI_MODEL', 'openrouter/free').strip()
CHANNEL_URL = os.getenv('CHANNEL_URL', 'https://t.me/IRHACK_APP33').strip()
CREATOR_URL = os.getenv('CREATOR_URL', 'https://t.me/Ma3ih01').strip()

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
log = logging.getLogger('masih_guard')
if not BOT_TOKEN:
    raise RuntimeError('BOT_TOKEN is not set. Add TELEGRAM_BOT_TOKEN or BOT_TOKEN in host environment variables.')

bot = telebot.TeleBot(BOT_TOKEN, parse_mode='HTML', threaded=True, num_threads=8)
app = Flask(__name__)
LOCK = threading.RLock()
DEFAULT_SETTINGS = {
    'anti_link': True, 'anti_spam': True, 'anti_duplicate': True,
    'badword_filter': False, 'welcome_enabled': True, 'captcha_enabled': False,
    'lock_media': False, 'max_messages': 6, 'spam_window': 8,
    'max_warnings': 3, 'mute_seconds': 60,
    'rules': '🌈 قوانین گروه:\n1) احترام به همه\n2) تبلیغات و لینک ممنوع مگر با اجازه مدیر\n3) اسپم و توهین ممنوع\n━━━ 🛡️ MASIH GUARD ━━━',
    'welcome_text': 'سلام {name} به گروه: {group} خوش اومدی! 🍻💜\n🌈 جمع گرم و دوست‌داشتنی گروه منتظرته.\n━━━ 🛡️ MASIH GUARD 〰️ ━━━\n〰️ توسط: Masih Hackring',
    'bad_words': ['کص', 'کسکش', 'جنده'],
}
DATA = {'groups': {}, 'warnings': {}, 'muted': {}, 'banned': {}, 'stats': {'messages': 0, 'blocked': 0, 'welcomes': 0}}


def load_data():
    global DATA
    try:
        if os.path.isfile(DATA_FILE):
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                for k, v in loaded.items():
                    if isinstance(v, dict) and isinstance(DATA.get(k), dict): DATA[k].update(v)
                    else: DATA[k] = v
    except Exception as e: log.warning('Could not load data: %s', e)


def save_data():
    try:
        with LOCK:
            tmp = DATA_FILE + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as f: json.dump(DATA, f, ensure_ascii=False, indent=2)
            os.replace(tmp, DATA_FILE)
    except Exception as e: log.warning('Could not save data: %s', e)


def settings(chat_id):
    key = str(chat_id)
    with LOCK:
        DATA.setdefault('groups', {})
        if key not in DATA['groups']: DATA['groups'][key] = dict(DEFAULT_SETTINGS)
        else:
            for k, v in DEFAULT_SETTINGS.items(): DATA['groups'][key].setdefault(k, v)
        return DATA['groups'][key]


def display_name(user):
    name = ' '.join(x for x in [getattr(user, 'first_name', ''), getattr(user, 'last_name', '')] if x).strip()
    return html.escape(name or getattr(user, 'username', None) or str(getattr(user, 'id', 'کاربر')))


def mention(user): return f'<a href="tg://user?id={user.id}">{display_name(user)}</a>'

def is_owner(user_id): return int(user_id) == OWNER_ID

def is_admin(chat_id, user_id):
    if is_owner(user_id): return True
    try: return bot.get_chat_member(chat_id, user_id).status in ('administrator', 'creator')
    except Exception: return False


def admin_required(message):
    if not message.from_user or not is_admin(message.chat.id, message.from_user.id):
        bot.reply_to(message, '⛔ این دستور فقط برای مدیران گروه است.')
        return False
    return True


def target_from_message(message):
    if message.reply_to_message and message.reply_to_message.from_user: return message.reply_to_message.from_user
    p = (message.text or '').split()
    if len(p) > 1 and p[1].isdigit():
        try: return bot.get_chat_member(message.chat.id, int(p[1])).user
        except Exception: return None
    return None


def main_panel():
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton('🔴 مدیریت', callback_data='panel:manage'),
        types.InlineKeyboardButton('🟠 امنیت', callback_data='panel:security'),
        types.InlineKeyboardButton('🟡 قوانین', callback_data='panel:rules'),
        types.InlineKeyboardButton('🟢 راهنما', callback_data='panel:help'),
        types.InlineKeyboardButton('🔵 وضعیت', callback_data='panel:status'),
        types.InlineKeyboardButton('🟣 سازنده', callback_data='panel:creator'),
        types.InlineKeyboardButton('🌈 پنل هفت‌رنگ', callback_data='panel:rainbow'),
        types.InlineKeyboardButton('📢 کانال', url=CHANNEL_URL),
    )
    return kb


def panel_text():
    # Intentionally no font or proxy commands/buttons in the panel.
    return (f'🌈 <b>{BOT_NAME} | نسخه {VERSION}</b>\n'
            '━━━━━━━━━━━━━━━━━━\n🛡️ ربات مدیریت و امنیت گروه\n'
            '🔴 مدیریت  🟠 امنیت  🟡 قوانین\n🟢 راهنما  🔵 وضعیت  🟣 سازنده\n'
            '━━━━━━━━━━━━━━━━━━\n✦ سازنده: <b>Masih Hackring</b>\n'
            'برای امکانات مدیریتی از دکمه‌های رنگی استفاده کن.')


def send_long(chat_id, text, reply_to=None):
    chunks, current = [], ''
    for line in text.splitlines(True):
        if len(current) + len(line) > 3800:
            if current: chunks.append(current)
            current = ''
        current += line
    if current: chunks.append(current)
    if not chunks: chunks = [text]
    for i, chunk in enumerate(chunks):
        bot.send_message(chat_id, chunk, reply_to_message_id=reply_to if i == 0 else None, disable_web_page_preview=True)

# -------------------- 100 styles --------------------
_UPPER = {
 'bold':0x1D400,'italic':0x1D434,'bold_italic':0x1D468,'script':0x1D49C,
 'bold_script':0x1D4D0,'fraktur':0x1D504,'double':0x1D538,'bold_fraktur':0x1D56C,
 'sans':0x1D5A0,'sans_bold':0x1D5D4,'sans_italic':0x1D608,'sans_bold_italic':0x1D63C,'mono':0x1D670}
_LOWER = {
 'bold':0x1D41A,'italic':0x1D44E,'bold_italic':0x1D482,'script':0x1D4B6,
 'bold_script':0x1D4EA,'fraktur':0x1D51E,'double':0x1D552,'bold_fraktur':0x1D586,
 'sans':0x1D5BA,'sans_bold':0x1D5EE,'sans_italic':0x1D622,'sans_bold_italic':0x1D656,'mono':0x1D68A}

def stylize_latin(text, style):
    out=[]
    for ch in text:
        if 'A' <= ch <= 'Z':
            cp=_UPPER[style]+ord(ch)-ord('A')
            # Unicode mathematical alphabets have a few reserved holes.
            holes={0x1D49C: {0,1,4,5,7,8,11,12,13,14,17,18,19,20,21}, 0x1D4D0:{4,5,6,7,8,11,12,13,14,17,18,19,20,21}, 0x1D504:{2,7,17}, 0x1D56C:{2,7,17}}
            out.append(ch if cp in holes.get(_UPPER[style], set()) else chr(cp))
        elif 'a' <= ch <= 'z':
            cp=_LOWER[style]+ord(ch)-ord('a')
            holes={0x1D49C:{4,6,7,11,12,13,14,17,18,19,20,21,22,23,24,25},0x1D4B6:{4,6,7,11,12,13,14,17,18,19,20,21,22,23,24,25}}
            out.append(ch if cp in holes.get(_LOWER[style],set()) else chr(cp))
        elif ch.isdigit() and style in ('double','sans','sans_bold','mono'):
            base={'double':0x1D7D8,'sans':0x1D7E2,'sans_bold':0x1D7EC,'mono':0x1D7F6}[style]
            out.append(chr(base+int(ch)))
        else: out.append(ch)
    return ''.join(out)

_WRAPPERS = [
('Neon','✨ {x} ✨'),('Stars','★彡 {x} 彡★'),('Crown','♛ {x} ♛'),('Diamond','◇◆ {x} ◆◇'),('Fire','🔥 {x} 🔥'),('Purple','💜 {x} 💜'),('Blue','💙 {x} 💙'),('Green','💚 {x} 💚'),('Red','❤️ {x} ❤️'),('Gold','👑 {x} 👑'),('Cyber','⟦ {x} ⟧'),('Box','『 {x} 』'),('Wave','〰️ {x} 〰️'),('Spark','⋆｡°✩ {x} ✩°｡⋆'),('Arrow','➤ {x} ◀'),('Moon','☾ {x} ☽'),('Flower','❀ {x} ❀'),('Heart','ღ {x} ღ'),('Music','♫ {x} ♫'),('Royal','༺ {x} ༻'),('Frame','【 {x} 】'),('Square','▣ {x} ▣'),('Circle','◉ {x} ◉'),('Cross','✞ {x} ✞'),('Butterfly','ʚ♡ɞ {x} ʚ♡ɞ'),('Cloud','☁ {x} ☁'),('Lightning','ϟ {x} ϟ'),('Pixel','▓▒░ {x} ░▒▓'),('Glitch','≋ {x} ≋'),('Minimal','• {x} •'),('Slash','╱ {x} ╲'),('Bracket','⟪ {x} ⟫'),('Flame','♨ {x} ♨'),('Gem','💎 {x} 💎'),('Angel','୨୧ {x} ୨୧'),('Devil','𖤐 {x} 𖤐'),('Leaf','❦ {x} ❦'),('Ribbon','୨୧・{x}・୨୧'),('Neon 2','⫷ {x} ⫸'),('Cyber 2','⌁ {x} ⌁'),('Royal 2','♔ {x} ♔'),('Stars 2','✦✧ {x} ✧✦'),('Cute','૮₍ ˶ᵔ ᵕ ᵔ˶ ₎ა {x}'),('Retro','《 {x} 》'),('Tech','‹ {x} /›'),('Matrix','▌│█║▌║▌ {x} ▌║▌║█│▌'),('Line','━━ {x} ━━'),('Dots','··· {x} ···'),('Wave 2','≈≈ {x} ≈≈'),('Crown 2','♕ {x} ♕'),('Heart 2','♡ {x} ♡'),('Flower 2','✿ {x} ✿'),('Sparkle 2','✧ {x} ✧'),('Magic','☄ {x} ☄'),('Badge','『★』{x}『★』'),('Shield','🛡️ {x} 🛡️'),('Rainbow','🌈 {x} 🌈'),('Purple 2','🟣〔{x}〕🟣'),('Blue 2','🔵〔{x}〕🔵'),('Green 2','🟢〔{x}〕🟢'),('Yellow','🟡〔{x}〕🟡'),('Orange','🟠〔{x}〕🟠'),('Red 2','🔴〔{x}〕🔴'),('Square 2','▰ {x} ▰'),('Triangle','△ {x} △'),('Diamond 2','◈ {x} ◈'),('Vintage','༒ {x} ༒'),('Fancy','꧁ {x} ꧂'),('Fancy 2','꧁༺ {x} ༻꧂'),('Mystic','𓆩 {x} 𓆪'),('Space','⭒ {x} ⭒'),('Comet','☄︎ {x} ☄︎'),('Wave 3','〜 {x} 〜'),('Bracket 2','〖 {x} 〗'),('Frame 2','╭─ {x} ─╮'),('Frame 3','╰─ {x} ─╯'),('Star 3','✪ {x} ✪'),('Music 2','♪ {x} ♪'),('Love','💞 {x} 💞'),('Butterfly 2','🦋 {x} 🦋'),('Fox','ᵔᴥᵔ {x}'),('Cat','ฅ^•ﻌ•^ฅ {x}'),('Bear','ʕ•ᴥ•ʔ {x}'),('Sun','☀ {x} ☀'),('Moon 2','☽⋆ {x} ⋆☾'),('Cloud 2','☁︎ {x} ☁︎'),('Wave 4','≋≋ {x} ≋≋'),('Hash','# {x} #'),('Percent','% {x} %'),('At','@ {x} @'),('Plus','✚ {x} ✚'),('Infinity','∞ {x} ∞'),('Omega','Ω {x} Ω'),('Lambda','Λ {x} Λ'),('Terminal','root@masih:~$ {x}'),('Code','[ {x} ]'),('System',':: {x} ::'),('Final','༺🌈 {x} 🌈༻')]

def font_variants(text):
    result=[]
    for style in _UPPER: result.append((style.replace('_',' ').title(),stylize_latin(text,style)))
    result.extend((name,fmt.format(x=text)) for name,fmt in _WRAPPERS)
    return result[:100]


def handle_font_command(message, raw_text=None):
    raw=(raw_text if raw_text is not None else (message.text or '')).strip()
    m=re.match(r'^(?:فونت|font)(?:\s+(.+))?$',raw,re.I|re.S)
    if not m or not m.group(1):
        bot.reply_to(message,'✍️ اسم یا متن رو بعد از «فونت» بنویس.\nمثال: <code>فونت Masih Hackring</code>')
        return
    supplied=m.group(1).strip()
    if len(supplied)>120:
        bot.reply_to(message,'⚠️ متن حداکثر ۱۲۰ کاراکتر باشه تا ۱۰۰ مدل خوانا بمونه.')
        return
    lines=[f'🌈 <b>۱۰۰ مدل نوشتار برای:</b> {html.escape(supplied)}','━━━━━━━━━━━━━━━━━━']
    for i,(style,value) in enumerate(font_variants(supplied),1): lines.append(f'{i:02d}. {html.escape(value)}')
    lines.append('\n✦ سازنده: <b>Masih Hackring</b>')
    send_long(message.chat.id,'\n'.join(lines),message.message_id)

# -------------------- Public proxy links --------------------
def get_proxy_links():
    sources=[
      'https://raw.githubusercontent.com/ALIILAPRO/Telegram-Proxy/main/proxy.txt',
      'https://raw.githubusercontent.com/hookzof/socks5_list/master/tg/mtproto.txt',
    ]
    patterns=[r'https?://t\.me/(?:proxy|socks)\?[A-Za-z0-9_=%&.+-]+',r'tg://proxy\?[A-Za-z0-9_=%&.+-]+']
    found=[]
    for url in sources:
        try:
            response=requests.get(url,timeout=9,headers={'User-Agent':'MASIH-GUARD/30.1'})
            if response.ok:
                for pat in patterns:
                    for link in re.findall(pat,response.text):
                        link=link.rstrip('.,);]}')
                        if link not in found: found.append(link)
        except Exception as e: log.info('Proxy source unavailable: %s',e)
    return found[:10]


def handle_proxy(message):
    bot.send_chat_action(message.chat.id,'typing')
    links=get_proxy_links()
    if not links:
        bot.reply_to(message,'⚠️ فعلاً منبع عمومی پروکسی پاسخ نداد. چند دقیقه بعد دوباره «پروکسی» رو بفرست.')
        return
    # Plain links are intentionally left unescaped so Telegram can recognize them as links.
    lines=['🌐 <b>پروکسی‌های عمومی تلگرام</b>','━━━━━━━━━━━━━━━━━━']
    lines.extend(f'{i}. {link}' for i,link in enumerate(links,1))
    lines.extend(['','⚠️ فعال‌بودن، سرعت و پینگ این لینک‌ها تضمین‌شده نیست. پروکسی ناشناس رو برای کارهای حساس با احتیاط استفاده کن.','✦ <b>Masih Hackring</b>'])
    send_long(message.chat.id,'\n'.join(lines),message.message_id)

# -------------------- Moderation helpers --------------------
def mute_user(chat_id,user_id,seconds):
    until=int(time.time())+max(30,min(int(seconds),2592000))
    permissions=types.ChatPermissions(can_send_messages=False,can_send_audios=False,can_send_documents=False,can_send_photos=False,can_send_videos=False,can_send_video_notes=False,can_send_voice_notes=False,can_send_polls=False,can_send_other_messages=False,can_add_web_page_previews=False)
    bot.restrict_chat_member(chat_id,user_id,permissions,until_date=until)
    DATA.setdefault('muted',{})[f'{chat_id}:{user_id}']=until; save_data()

def unmute_user(chat_id,user_id):
    permissions=types.ChatPermissions(can_send_messages=True,can_send_audios=True,can_send_documents=True,can_send_photos=True,can_send_videos=True,can_send_video_notes=True,can_send_voice_notes=True,can_send_polls=True,can_send_other_messages=True,can_add_web_page_previews=True)
    bot.restrict_chat_member(chat_id,user_id,permissions)
    DATA.setdefault('muted',{}).pop(f'{chat_id}:{user_id}',None); save_data()

def ban_user(chat_id,user_id):
    bot.ban_chat_member(chat_id,user_id); DATA.setdefault('banned',{})[f'{chat_id}:{user_id}']=int(time.time()); save_data()

def moderation_notice(message,user,status,reason=None):
    text=f'〰️ کاربر {display_name(user)} {status}\n🎖 وضعیت کاربر : {"سکوت در گروه" if "تبچی" in status else "مسدود شد" if "مسدود" in status else status}'
    if reason: text+=f'\n📝 دلیل: {html.escape(reason)}'
    text+='\n━━━ 💢 MASIH GUARD 〰️ ━━━\n〰️ توسط : Masih Hackring'
    bot.send_message(message.chat.id,text,reply_to_message_id=message.message_id)

def add_warning(chat_id,user_id):
    key=f'{chat_id}:{user_id}'; DATA.setdefault('warnings',{})[key]=int(DATA['warnings'].get(key,0))+1; save_data(); return DATA['warnings'][key]

def try_delete(message):
    try: bot.delete_message(message.chat.id,message.message_id); return True
    except Exception: return False

@bot.message_handler(commands=['start','panel'])
def start(message): bot.send_message(message.chat.id,panel_text(),reply_markup=main_panel(),disable_web_page_preview=True)

@bot.message_handler(commands=['about'])
def about(message): bot.reply_to(message,f'🌈 <b>{BOT_NAME} v{VERSION}</b>\n🛡️ ابزار مدیریت گروه، ضداسپم و خوشامدگویی\n✦ سازنده: <b>{AUTHOR}</b>\n📨 ارتباط: {html.escape(CREATOR_URL)}')

@bot.message_handler(commands=['help'])
def help_command(message):
    txt = (f'🌈 <b>راهنمای MASIH GUARD v{VERSION}</b>\n━━━━━━━━━━━━━━━━━━\n'
           '• <code>/panel</code> پنل اصلی\n• <code>/rules</code> دیدن قوانین\n• <code>/setrules متن</code> تنظیم قوانین (مدیر)\n'
           '• <code>/antilink on|off</code> ضدلینک\n• <code>/antispam on|off</code> ضداسپم\n• <code>/antiduplicate on|off</code> ضدتکرار\n'
           '• <code>/badwords on|off</code> فیلتر کلمات\n• <code>/welcome on|off</code> خوشامدگویی\n• <code>/lockmedia on|off</code> قفل رسانه\n'
           '• <code>/warn</code> اخطار (ریپلای)\n• <code>/mute 60</code> سکوت (ریپلای)\n• <code>/unmute</code> رفع سکوت (ریپلای)\n'
           '• <code>/ban</code> مسدودکردن (ریپلای)\n• <code>/unban شناسه</code> رفع مسدودی\n• <code>/kick</code> اخراج (ریپلای)\n• <code>/purge</code> حذف پیام ریپلای‌شده\n'
           '• برای ساخت ۱۰۰ مدل نوشتار، در چت بنویس <code>فونت اسم یا متن</code>\n• برای دریافت لینک‌های عمومی تلگرام، در چت بنویس <code>پروکسی</code>\n'
           '━━━━━━━━━━━━━━━━━━\n⚠️ برای اعمال مدیریت، ربات باید مدیر گروه و دارای دسترسی مربوطه باشد.')
    bot.reply_to(message, txt)

@bot.message_handler(commands=['rules'])
def rules_command(message): bot.reply_to(message,settings(message.chat.id)['rules'])

@bot.message_handler(commands=['setrules'])
def setrules_command(message):
    if not admin_required(message): return
    text=(message.text or '').partition(' ')[2].strip()
    if not text: bot.reply_to(message,'نمونه: <code>/setrules احترام به همه و ممنوعیت تبلیغات</code>'); return
    settings(message.chat.id)['rules']=text; save_data(); bot.reply_to(message,'✅ قوانین گروه ذخیره شد.')

@bot.message_handler(commands=['antilink','antispam','antiduplicate','badwords','welcome','lockmedia'])
def toggle_command(message):
    if not admin_required(message): return
    cmd=message.text.split()[0].split('@')[0].lstrip('/'); parts=(message.text or '').split()
    if len(parts)<2 or parts[1].lower() not in ('on','off'):
        bot.reply_to(message,f'استفاده: <code>/{cmd} on</code> یا <code>/{cmd} off</code>'); return
    key={'antilink':'anti_link','antispam':'anti_spam','antiduplicate':'anti_duplicate','badwords':'badword_filter','welcome':'welcome_enabled','lockmedia':'lock_media'}[cmd]
    settings(message.chat.id)[key]=parts[1].lower()=='on'; save_data()
    bot.reply_to(message,f'✅ {cmd}: {"روشن" if settings(message.chat.id)[key] else "خاموش"} شد.')

@bot.message_handler(commands=['warn','mute','unmute','ban','unban','kick'])
def moderation_command(message):
    if not admin_required(message): return
    cmd=message.text.split()[0].split('@')[0].lstrip('/'); target=target_from_message(message)
    if cmd=='unban' and not target:
        parts=(message.text or '').split()
        if len(parts)>1 and parts[1].isdigit():
            try:
                bot.unban_chat_member(message.chat.id,int(parts[1]),only_if_banned=True); DATA.setdefault('banned',{}).pop(f'{message.chat.id}:{parts[1]}',None); save_data(); bot.reply_to(message,'✅ مسدودی کاربر برداشته شد.')
            except Exception as e: bot.reply_to(message,f'❌ انجام نشد: <code>{html.escape(str(e)[:250])}</code>')
        else: bot.reply_to(message,'روی پیام کاربر ریپلای کن یا شناسه بده: <code>/unban 123456</code>')
        return
    if not target: bot.reply_to(message,'⚠️ روی پیام کاربر ریپلای کن و دستور رو بفرست.'); return
    if target.id in (OWNER_ID,message.from_user.id): bot.reply_to(message,'⛔ این کاربر رو نمی‌تونم با این دستور مدیریت کنم.'); return
    try:
        if cmd=='warn':
            count=add_warning(message.chat.id,target.id); limit=int(settings(message.chat.id)['max_warnings'])
            bot.reply_to(message,f'⚠️ به {mention(target)} اخطار داده شد. ({count}/{limit})')
            if count>=limit:
                mute_user(message.chat.id,target.id,int(settings(message.chat.id)['mute_seconds'])); DATA['warnings'][f'{message.chat.id}:{target.id}']=0; save_data()
                bot.send_message(message.chat.id,f'🔇 {mention(target)} به دلیل دریافت چند اخطار، موقتاً ساکت شد.')
        elif cmd=='mute':
            p=(message.text or '').split(); secs=int(p[1]) if len(p)>1 and p[1].isdigit() else int(settings(message.chat.id)['mute_seconds'])
            mute_user(message.chat.id,target.id,secs); moderation_notice(message,target,'در لیست تبچی بود !')
        elif cmd=='unmute': unmute_user(message.chat.id,target.id); bot.reply_to(message,f'🔊 سکوت {mention(target)} برداشته شد.')
        elif cmd=='ban':
            ban_user(message.chat.id,target.id); moderation_notice(message,target,'در لیست مسدودها شد !','ادمین باهاش حال نکرد')
        elif cmd=='kick':
            bot.ban_chat_member(message.chat.id,target.id); bot.unban_chat_member(message.chat.id,target.id,only_if_banned=True); bot.reply_to(message,f'👢 {mention(target)} از گروه اخراج شد.')
    except Exception as e: bot.reply_to(message,f'❌ انجام نشد؛ دسترسی مدیر ربات رو بررسی کن.\n<code>{html.escape(str(e)[:300])}</code>')

@bot.message_handler(commands=['purge'])
def purge_command(message):
    if not admin_required(message): return
    if not message.reply_to_message: bot.reply_to(message,'برای پاک‌کردن پیام، روی همون پیام ریپلای کن و /purge بفرست.'); return
    try: bot.delete_message(message.chat.id,message.reply_to_message.message_id); bot.delete_message(message.chat.id,message.message_id)
    except Exception as e: bot.reply_to(message,f'❌ حذف پیام انجام نشد؛ دسترسی حذف پیام رو بررسی کن.\n<code>{html.escape(str(e)[:200])}</code>')

@bot.callback_query_handler(func=lambda call: bool(call.data) and call.data.startswith('panel:'))
def panel_callbacks(call):
    key=call.data.split(':',1)[1]; chat_id=call.message.chat.id if call.message else call.from_user.id
    if key=='manage': text='🔴 <b>مدیریت گروه</b>\nروی پیام کاربر ریپلای کن: /warn، /mute 60، /unmute، /ban یا /kick\nبرای رفع مسدودی: /unban شناسه'
    elif key=='security': text='🟠 <b>امنیت</b>\n/antilink on|off\n/antispam on|off\n/antiduplicate on|off\n/badwords on|off\n/welcome on|off\n/lockmedia on|off'
    elif key=='rules': text=settings(chat_id)['rules']
    elif key=='help': text='🟢 <b>راهنما</b>\nبرای راهنمای کامل دستور /help رو بفرست.\nاز دکمه‌های رنگی پنل برای مدیریت استفاده کن.'
    elif key=='status':
        st=DATA.get('stats',{}); text=f'🔵 <b>وضعیت ربات</b>\nنسخه: {VERSION}\nپیام‌های بررسی‌شده: {st.get("messages",0)}\nموارد مسدودشده: {st.get("blocked",0)}\nخوشامدها: {st.get("welcomes",0)}'
    elif key=='creator': text=f'🟣 سازنده: <b>{AUTHOR}</b>\nارتباط: {html.escape(CREATOR_URL)}'
    else: text=f'🌈 <b>MASIH GUARD | پنل هفت‌رنگ</b>\n🔴 مدیریت 🟠 امنیت 🟡 قوانین\n🟢 راهنما 🔵 وضعیت 🟣 سازنده\n✦ by {AUTHOR}'
    try:
        bot.answer_callback_query(call.id)
        bot.send_message(chat_id,text,reply_markup=main_panel() if key=='rainbow' else None,disable_web_page_preview=True)
    except Exception as e: log.warning('Callback failed: %s',e)

# Private text: users type the feature they want; font/proxy are NOT panel buttons.
@bot.message_handler(func=lambda m: m.chat.type=='private' and bool(m.text) and not m.text.startswith('/'),content_types=['text'])
def private_text(message):
    text=message.text.strip()
    if re.match(r'^(?:فونت|font)(?:\s|$)',text,re.I): handle_font_command(message,text); return
    if re.fullmatch(r'پروکسی|proxy',text,re.I): handle_proxy(message); return
    if AI_API_KEY:
        try:
            r=requests.post(AI_BASE_URL,headers={'Authorization':f'Bearer {AI_API_KEY}','Content-Type':'application/json','HTTP-Referer':'https://t.me/','X-Title':BOT_NAME},json={'model':AI_MODEL,'messages':[{'role':'system','content':'تو دستیار فارسی‌زبان مودب MASIH GUARD هستی. پاسخ کوتاه، مفید و امن بده.'},{'role':'user','content':text}]},timeout=25)
            if r.ok:
                answer=r.json()['choices'][0]['message']['content'].strip(); send_long(message.chat.id,html.escape(answer),message.message_id); return
            log.warning('AI API returned HTTP %s',r.status_code)
        except Exception as e: log.warning('AI request failed: %s',e)
    bot.reply_to(message,'سلام! 🌈 برای امکانات مدیریتی /help رو بزن. برای فونت بنویس «فونت اسم دلخواه» و برای پروکسی فقط بنویس «پروکسی».')

# Group welcome and moderation filters
message_times=defaultdict(deque); last_messages={}
@bot.message_handler(content_types=['new_chat_members'])
def welcome_members(message):
    cfg=settings(message.chat.id)
    if not cfg.get('welcome_enabled',True): return
    try: bot_id=bot.get_me().id
    except Exception: bot_id=None
    for user in message.new_chat_members or []:
        if user.id==bot_id: continue
        template=cfg.get('welcome_text',DEFAULT_SETTINGS['welcome_text'])
        try: out=template.format(name=display_name(user),group=html.escape(message.chat.title or 'گروه'))
        except Exception: out=f'سلام {display_name(user)} به گروه: {html.escape(message.chat.title or "گروه")} خوش اومدی! 🍻💜\n━━━ 🛡️ MASIH GUARD ━━━\n〰️ توسط: Masih Hackring'
        bot.send_message(message.chat.id,out,disable_web_page_preview=True)
        DATA.setdefault('stats',{}); DATA['stats']['welcomes']=DATA['stats'].get('welcomes',0)+1
    save_data()

@bot.message_handler(content_types=['text','photo','video','document','animation','audio','voice','video_note','sticker'])
def group_moderation(message):
    if message.chat.type not in ('group','supergroup') or not message.from_user or message.from_user.is_bot: return
    text=message.text or message.caption or ''; cfg=settings(message.chat.id)
    # Non-command feature triggers work for ordinary members too.
    if text and re.match(r'^(?:فونت|font)(?:\s|$)',text.strip(),re.I): handle_font_command(message,text.strip()); return
    if text and re.fullmatch(r'پروکسی|proxy',text.strip(),re.I): handle_proxy(message); return
    if is_admin(message.chat.id,message.from_user.id): return
    DATA.setdefault('stats',{}); DATA['stats']['messages']=DATA['stats'].get('messages',0)+1
    now=time.time(); uid=f'{message.chat.id}:{message.from_user.id}'; q=message_times[uid]; q.append(now)
    window=int(cfg.get('spam_window',8))
    while q and now-q[0]>window: q.popleft()
    normalized=re.sub(r'\s+',' ',text).strip().lower(); repeated=bool(normalized and last_messages.get(uid)==normalized); last_messages[uid]=normalized
    spam=cfg.get('anti_spam',True) and len(q)>int(cfg.get('max_messages',6))
    duplicate=cfg.get('anti_duplicate',True) and repeated and len(normalized)>3
    link=cfg.get('anti_link',True) and bool(re.search(r'(?:https?://|www\.|t\.me/|telegram\.me/)',text,re.I))
    badword=cfg.get('badword_filter',False) and any(w in text.lower() for w in cfg.get('bad_words',[]))
    media_locked=cfg.get('lock_media',False) and message.content_type in ('photo','video','document','animation','audio','voice','video_note','sticker')
    if spam or duplicate:
        try:
            try_delete(message); mute_user(message.chat.id,message.from_user.id,int(cfg.get('mute_seconds',60)))
            DATA['stats']['blocked']=DATA['stats'].get('blocked',0)+1; save_data()
            bot.send_message(message.chat.id,f'〰️ کاربر {display_name(message.from_user)} در لیست تبچی بود !\n🎖 وضعیت کاربر : سکوت در گروه\n━━━ 💢 MASIH GUARD 〰️ ━━━\n〰️ توسط : Masih Hackring')
        except Exception as e: log.warning('Anti-spam action failed: %s',e)
        return
    if link or badword or media_locked:
        try:
            if try_delete(message):
                DATA['stats']['blocked']=DATA['stats'].get('blocked',0)+1; save_data()
                reason='ارسال لینک' if link else 'کلمات ممنوعه' if badword else 'ارسال رسانه در حالت قفل'
                bot.send_message(message.chat.id,f'⚠️ {mention(message.from_user)} پیام حذف شد.\n📝 دلیل: {reason}\n━━━ 💢 MASIH GUARD 〰️ ━━━')
        except Exception as e: log.warning('Filter action failed: %s',e)

@app.get('/')
def home(): return f'{BOT_NAME} v{VERSION} is running | by {AUTHOR}',200
@app.get('/health')
def health(): return jsonify({'ok':True,'bot':BOT_NAME,'version':VERSION}),200

def run_web(): app.run(host='0.0.0.0',port=PORT,debug=False,use_reloader=False)
def run_bot():
    while True:
        try:
            log.info('Starting %s v%s',BOT_NAME,VERSION)
            try: bot.remove_webhook()
            except Exception: pass
            bot.infinity_polling(skip_pending=True,timeout=30,long_polling_timeout=25,allowed_updates=['message','callback_query'])
        except Exception as e: log.exception('Polling stopped: %s',e); time.sleep(5)

load_data()
threading.Thread(target=run_web,daemon=True).start()
run_bot()
