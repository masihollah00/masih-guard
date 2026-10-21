# -*- coding: utf-8 -*-
"""MASIH GUARD S1000+ — single-file Telegram group management bot."""
import os, re, json, time, random, threading, io, urllib.request, urllib.error, html
from datetime import datetime
import telebot
from telebot import types

# ---------------- Configuration ----------------
BOT_TOKEN = (os.getenv('BOT_TOKEN') or os.getenv('TELEGRAM_BOT_TOKEN') or '').strip()
OWNER_ID = int(os.getenv('OWNER_ID', '8620924698'))
DATA_FILE = os.getenv('DATA_FILE', 'masih_guard_data.json')
AI_API_KEY = os.getenv('AI_API_KEY', '').strip()
AI_BASE_URL = os.getenv('AI_BASE_URL', 'https://openrouter.ai/api/v1').rstrip('/')
AI_MODEL = os.getenv('AI_MODEL', 'openai/gpt-4o-mini').strip()
WEBSITE_URL = os.getenv('WEBSITE_URL', 'https://neon-portfolio-7vhj.onrender.com').strip()
CHANNEL_URL = os.getenv('CHANNEL_URL', 'https://t.me/').strip()
BRAND, VERSION = 'MASIH GUARD', 'S1000+'
if not BOT_TOKEN:
    raise RuntimeError('BOT_TOKEN تنظیم نشده است؛ آن را در Environment هاست قرار بده.')

bot = telebot.TeleBot(BOT_TOKEN, parse_mode='HTML', threaded=True, num_threads=4)
LOCK = threading.RLock()
WAITING = {}
GAMES = {}
PANEL_CURRENT = {}
PANEL_HISTORY = {}

DEFAULT_GROUP = {
    'anti_link': True, 'anti_ads': True, 'anti_spam': True,
    'anti_repeat': True, 'anti_forward': False, 'media_lock': False,
    'welcome_on': True, 'farewell_on': False, 'join_approval': False,
    'bad_words': [], 'whitelist': [], 'warn_limit': 3,
    'rules': 'احترام به اعضا الزامی است.',
    'welcome_text': 'سلام {name}، به گروه خوش آمدی!',
    'farewell_text': 'خداحافظ {name}', 'auto_replies': {}
}
DEFAULT_DATA = {
    'groups': {}, 'admins': {}, 'warnings': {}, 'logs': [], 'proxies': [],
    'customers': {}, 'tickets': {}, 'points': {}, 'seen': {},
    'stats': {'messages': 0, 'blocked': 0, 'warns': 0, 'joins': 0, 'tickets': 0},
    'settings': {'smart_security': True}, 'last_daily': ''
}

def clone(obj): return json.loads(json.dumps(obj, ensure_ascii=False))
def esc(value): return html.escape(str(value or ''), quote=False)
def now_text(): return datetime.now().strftime('%Y-%m-%d %H:%M:%S')

def load_data():
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f: data = json.load(f)
        if not isinstance(data, dict): raise ValueError('Invalid data')
    except (OSError, ValueError, TypeError):
        data = clone(DEFAULT_DATA)
    for k, v in DEFAULT_DATA.items():
        if k not in data: data[k] = clone(v)
    for k, v in DEFAULT_DATA['stats'].items(): data['stats'].setdefault(k, v)
    for k, v in DEFAULT_DATA['settings'].items(): data['settings'].setdefault(k, v)
    for k in ('groups','admins','warnings','logs','proxies','customers','tickets','points','seen'):
        if not isinstance(data.get(k), type(DEFAULT_DATA[k])): data[k] = clone(DEFAULT_DATA[k])
    return data
DATA = load_data()

def save_data():
    with LOCK:
        tmp = DATA_FILE + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(DATA, f, ensure_ascii=False, indent=2)
            f.flush(); os.fsync(f.fileno())
        os.replace(tmp, DATA_FILE)

def add_log(action, chat_id='', user_id='', detail=''):
    with LOCK:
        DATA['logs'].append({'time': now_text(), 'action': str(action), 'chat_id': str(chat_id), 'user_id': str(user_id), 'detail': str(detail)[:250]})
        DATA['logs'] = DATA['logs'][-800:]
        save_data()

def is_owner(uid): return int(uid or 0) == OWNER_ID
def get_group_settings(chat_id):
    key = str(chat_id)
    if key not in DATA['groups']: DATA['groups'][key] = clone(DEFAULT_GROUP)
    settings = DATA['groups'][key]
    for k, v in DEFAULT_GROUP.items(): settings.setdefault(k, clone(v))
    return settings

def is_group_admin(chat_id, user_id):
    if is_owner(user_id): return True
    try: return bot.get_chat_member(chat_id, user_id).status in ('administrator', 'creator')
    except Exception: return False

def is_admin(chat_id, user_id): return is_group_admin(chat_id, user_id)

SECTIONS = {
    'security':'🛡 امنیت گروه', 'members':'👥 مدیریت اعضا', 'settings':'⚙️ تنظیمات گروه',
    'welcome':'👋 خوشامد و دکمه‌ها', 'rules':'📜 قوانین و پاسخ خودکار', 'font':'🔤 سازنده فونت',
    'proxy':'🌐 پنل پروکسی', 'stats':'📊 آمار و گزارش', 'customers':'💼 مشتریان و اشتراک',
    'tickets':'🎫 تیکت پشتیبانی', 'ai':'🧠 هوش مصنوعی', 'games':'🎮 بازی و امتیاز',
    'backup':'💾 پشتیبان‌گیری', 'daily':'📅 گزارش روزانه', 'smart':'🧩 امنیت هوشمند', 'status':'🚀 وضعیت ربات'
}

def main_keyboard():
    # Telegram doesn't permit custom button background colors; use a consistent seven-color neon palette in labels.
    palette = ['🔴', '🟠', '🟡', '🟢', '🔵', '🟣', '🌈']
    kb = types.InlineKeyboardMarkup(row_width=2)
    items = list(SECTIONS.items())
    for i in range(0, len(items), 2):
        row = []
        for j, (key, title) in enumerate(items[i:i+2]):
            color = palette[(i + j) % len(palette)]
            row.append(types.InlineKeyboardButton(f'{color} {title}', callback_data='panel:'+key))
        kb.row(*row)
    # The website link appears only once in the main panel.
    kb.row(types.InlineKeyboardButton('🌐 وب‌سایت رسمی', url=WEBSITE_URL))
    kb.row(types.InlineKeyboardButton('📢 کانال رسمی', url=CHANNEL_URL))
    return kb

def section_keyboard(section):
    kb = types.InlineKeyboardMarkup(row_width=1)
    choices = {
      'security':[('🔗 ضد لینک','toggle:anti_link'),('📢 ضد تبلیغ','toggle:anti_ads'),('🚫 ضد اسپم','toggle:anti_spam'),('🔁 ضد پیام تکراری','toggle:anti_repeat'),('↪️ ضد فوروارد','toggle:anti_forward'),('🖼 قفل رسانه','toggle:media_lock')],
      'welcome':[('👋 خوشامدگویی','toggle:welcome_on'),('👋 پیام خداحافظی','toggle:farewell_on'),('🛂 تأیید خودکار ورود','toggle:join_approval'),('✏️ تنظیم متن خوشامد','ask:welcome_text'),('✏️ تنظیم متن خداحافظی','ask:farewell_text')],
      'rules':[('📜 مشاهده قوانین','show:rules'),('✏️ تنظیم قوانین','ask:rules'),('💬 افزودن پاسخ خودکار','ask:auto_reply'),('🗑 حذف پاسخ خودکار','ask:delete_reply'),('🚫 افزودن کلمه ممنوع','ask:bad_word')],
      'members':[('⚠️ اخطار به عضو','ask:warn'),('🔇 سکوت عضو','ask:mute'),('🔊 برداشتن سکوت','ask:unmute'),('⛔ مسدود کردن عضو','ask:ban'),('✅ آزاد کردن عضو','ask:unban'),('👢 اخراج عضو','ask:kick')],
      'settings':[('⚙️ تنظیم سقف اخطار','ask:warn_limit'),('📜 تنظیم قوانین','ask:rules')],
      'font':[('🔤 تبدیل متن به فونت','ask:font')],
      'proxy':[('➕ افزودن پروکسی','ask:add_proxy'),('📋 نمایش پروکسی‌ها','show:proxies'),('🗑 حذف پروکسی','ask:delete_proxy')],
      'stats':[('📊 آمار ربات','show:stats'),('🧾 گزارش فعالیت','show:logs')],
      'customers':[('➕ افزودن مشتری','ask:add_customer'),('📋 فهرست مشتریان','show:customers'),('🔎 جست‌وجوی مشتری','ask:find_customer')],
      'tickets':[('🎫 ثبت تیکت','ask:ticket'),('📋 تیکت‌های من','show:tickets')],
      'ai':[('🧠 پرسش از هوش مصنوعی','ask:ai')],
      'games':[('🎮 بازی حدس عدد','game:guess'),('🏆 امتیاز من','show:points')],
      'backup':[('💾 دریافت نسخه پشتیبان','show:backup')], 'daily':[('📅 گزارش روزانه','show:daily')],
      'smart':[('🧩 روشن/خاموش امنیت هوشمند','toggle:smart_security')], 'status':[('🚀 وضعیت ربات','show:status')]
    }
    for label, data in choices.get(section, []): kb.add(types.InlineKeyboardButton(label, callback_data=data))
    kb.add(types.InlineKeyboardButton('⬅️ بازگشت به منوی قبلی', callback_data='panel:back'))
    return kb

def send_panel(chat_id, section='home', message_id=None, user_id=None):
    if user_id is not None:
        PANEL_CURRENT[user_id] = section
    if section == 'home':
        text = f'🌈 <b>{BRAND} {VERSION}</b>\n━━━━━━━━━━━━━━━━━━\n👑 پنل مدیریت هفت‌رنگ\n\nیکی از بخش‌ها را انتخاب کن.'
        kb = main_keyboard()
    else:
        text = f'🌈 <b>{BRAND} {VERSION}</b>\n━━━━━━━━━━━━━━━━━━\n<b>{esc(SECTIONS.get(section, "پنل مدیریت"))}</b>\n\nتنظیمات را از گزینه‌های زیر تغییر بده.'
        kb = section_keyboard(section)
    if message_id is not None:
        try:
            bot.edit_message_text(text, chat_id, message_id, reply_markup=kb)
            return
        except Exception as e:
            # Telegram rejects an edit if the content is unchanged; in that case the existing panel is already correct.
            if 'message is not modified' in str(e).lower():
                return
            print('Panel edit error:', repr(e))
    bot.send_message(chat_id, text, reply_markup=kb)

@bot.message_handler(commands=['start','panel','help'])
def start_command(message):
    uid = message.from_user.id if message.from_user else 0
    if message.chat.type == 'private' and not is_owner(uid):
        bot.reply_to(message, 'سلام! 🌟 برای راهنما از /help استفاده کن. پنل مدیریت فقط در اختیار مالک ربات است.')
        return
    if message.chat.type != 'private' and not is_owner(uid):
        bot.reply_to(message, 'پنل مدیریت فقط در اختیار مالک ربات است.')
        return
    send_panel(message.chat.id, user_id=uid)

@bot.message_handler(commands=['id'])
def id_command(message): bot.reply_to(message, f'🆔 شناسه کاربر: <code>{message.from_user.id}</code>\nشناسه چت: <code>{message.chat.id}</code>')

# Moderation and security helpers
def get_text(message): return (getattr(message,'text',None) or getattr(message,'caption',None) or '')
def has_link(text): return bool(re.search(r'(https?://|www\.|t\.me/|telegram\.me/|@[A-Za-z0-9_]{5,})', text or '', re.I))
def has_ad(text): return any(x in (text or '').casefold() for x in ['تبلیغ','تبلیغات','خرید ممبر','فروش ممبر','عضوگیری','کسب درآمد تضمینی'])
def is_forwarded(m): return any(getattr(m, x, None) for x in ('forward_origin','forward_from','forward_from_chat','forward_date'))
def has_media(m): return any(getattr(m, x, None) for x in ('photo','video','audio','voice','document','animation','sticker','video_note','contact','location'))
def safe_delete(message):
    try: bot.delete_message(message.chat.id, message.message_id); return True
    except Exception as e: print('Delete error:', repr(e)); return False

def warn_member(chat_id, user_id, reason='تخلف از قوانین'):
    key=f'{chat_id}:{user_id}'; DATA['warnings'][key]=int(DATA['warnings'].get(key,0))+1; count=DATA['warnings'][key]
    limit=max(1, int(get_group_settings(chat_id).get('warn_limit',3) or 3))
    DATA['stats']['warns']+=1; add_log('warning',chat_id,user_id,reason)
    try: bot.send_message(chat_id, f'⚠️ اخطار برای <code>{user_id}</code>\nدلیل: {esc(reason)}\nتعداد: {count}/{limit}')
    except Exception as e: print('Warning message error:', repr(e))
    if count >= limit:
        try:
            bot.ban_chat_member(chat_id,user_id); bot.send_message(chat_id,f'⛔ کاربر <code>{user_id}</code> به سقف اخطار رسید و مسدود شد.')
            DATA['warnings'][key]=0; add_log('auto_ban',chat_id,user_id,reason)
        except Exception as e: print('Auto-ban error:',repr(e))
    save_data()

def process_group_security(message):
    chat, user = message.chat, message.from_user
    if not user or chat.type not in ('group','supergroup') or is_group_admin(chat.id,user.id): return False
    settings=get_group_settings(chat.id); text=get_text(message); key=f'{chat.id}:{user.id}'; previous=DATA['seen'].get(key,{}) ; now=time.time(); reason=None
    if settings.get('media_lock') and has_media(message): reason='ارسال رسانه در حالت قفل رسانه'
    elif settings.get('anti_forward') and is_forwarded(message): reason='ارسال پیام فورواردشده'
    elif settings.get('anti_link') and has_link(text) and str(user.id) not in [str(x) for x in settings.get('whitelist',[])]: reason='ارسال لینک'
    elif settings.get('anti_ads') and has_ad(text): reason='ارسال تبلیغ'
    elif text and any(w and str(w).casefold() in text.casefold() for w in settings.get('bad_words',[])): reason='استفاده از کلمه ممنوع'
    if not reason and text and settings.get('anti_repeat') and previous.get('text') == text and now-previous.get('time',0)<30: reason='پیام تکراری'
    times=[t for t in previous.get('times',[]) if now-t<8]; times.append(now)
    if not reason and settings.get('anti_spam') and len(times)>=7: reason='ارسال پیام‌های پرتعداد'
    DATA['seen'][key]={'text':text,'time':now,'times':[] if reason=='ارسال پیام‌های پرتعداد' else times}
    if reason:
        if safe_delete(message): DATA['stats']['blocked']+=1; add_log('blocked',chat.id,user.id,reason); warn_member(chat.id,user.id,reason)
        return True
    save_data(); return False

@bot.message_handler(content_types=['text','photo','video','audio','voice','document','sticker','animation','video_note','contact','location'], func=lambda m: m.chat.type in ('group','supergroup'))
def group_message_handler(message):
    try:
        DATA['stats']['messages']+=1
        if process_group_security(message): return
        text=get_text(message)
        if text:
            settings=get_group_settings(message.chat.id)
            for keyword, reply in settings.get('auto_replies',{}).items():
                if keyword and keyword.casefold() in text.casefold(): bot.reply_to(message, str(reply)[:4000]); break
        save_data()
    except Exception as e: print('Group handler error:',repr(e))

@bot.message_handler(content_types=['new_chat_members'], func=lambda m: m.chat.type in ('group','supergroup'))
def welcome_new_members(message):
    settings=get_group_settings(message.chat.id)
    for member in message.new_chat_members:
        DATA['stats']['joins']+=1; add_log('new_member',message.chat.id,member.id,'ورود به گروه')
        if settings.get('welcome_on'):
            name=esc(member.first_name or 'دوست عزیز'); welcome=esc(settings.get('welcome_text','سلام {name}!')).replace('{name}',name)
            try: bot.send_message(message.chat.id,welcome)
            except Exception as e: print('Welcome error:',repr(e))
    if settings.get('join_approval'): add_log('join_approval_not_implemented',message.chat.id,'','تأیید خودکار ورود نیازمند پیاده‌سازی جداگانه است')
    save_data()

@bot.chat_join_request_handler()
def handle_join_request(request):
    try:
        settings = get_group_settings(request.chat.id)
        if settings.get('join_approval'):
            bot.approve_chat_join_request(request.chat.id, request.from_user.id)
            DATA['stats']['joins'] += 1
            add_log('join_request_approved', request.chat.id, request.from_user.id, 'تأیید خودکار ورود')
            save_data()
    except Exception as e:
        print('Join request approval error:', repr(e))


@bot.message_handler(content_types=['left_chat_member'], func=lambda m: m.chat.type in ('group','supergroup'))
def farewell_member(message):
    settings=get_group_settings(message.chat.id); member=message.left_chat_member
    if member and settings.get('farewell_on'):
        name=esc(member.first_name or 'دوست ما'); text=esc(settings.get('farewell_text','خداحافظ {name}')).replace('{name}',name)
        try: bot.send_message(message.chat.id,text)
        except Exception as e: print('Farewell error:',repr(e))
    if member: add_log('member_left',message.chat.id,member.id,'خروج از گروه')

# Fonts
FONT_MAPS=[
 str.maketrans('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz','𝔸𝔹ℂ𝔻𝔼𝔽𝔾ℍ𝕀𝕁𝕂𝕃𝕄ℕ𝕆ℙℚℝ𝕊𝕋𝕌𝕍𝕎𝕏𝕐ℤ𝕒𝕓𝕔𝕕𝕖𝕗𝕘𝕙𝕚𝕛𝕜𝕝𝕞𝕟𝕠𝕡𝕢𝕣𝕤𝕥𝕦𝕧𝕨𝕩𝕪𝕫'),
 str.maketrans('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz','𝘈𝘉𝘊𝘋𝘌𝘍𝘎𝘏𝘐𝘑𝘒𝘓𝘔𝘕𝘖𝘗𝘘𝘙𝘚𝘛𝘜𝘝𝘞𝘟𝘠𝘡𝘢𝘣𝘤𝘥𝘦𝘧𝘨𝘩𝘪𝘫𝘬𝘭𝘮𝘯𝘰𝘱𝘲𝘳𝘴𝘵𝘶𝘷𝘸𝘹𝘺𝘻'),
 str.maketrans('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz','ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ')]
def convert_font(text,style=0): return text.translate(FONT_MAPS[style%len(FONT_MAPS)])

# AI: one shared OpenAI-compatible endpoint, supports OpenRouter via AI_BASE_URL

def ask_ai(question):
    if not AI_API_KEY: return '⚠️ کلید هوش مصنوعی تنظیم نشده است. متغیر AI_API_KEY را در هاست وارد کن.'
    payload={'model':AI_MODEL,'messages':[{'role':'system','content':'تو دستیار فارسی MASIH GUARD هستی. روشن، دقیق و دوستانه پاسخ بده و متن فارسی و یونیکد را حفظ کن.'},{'role':'user','content':str(question)[:5000]}],'temperature':0.7,'max_tokens':1200}
    req=urllib.request.Request(AI_BASE_URL+'/chat/completions',data=json.dumps(payload,ensure_ascii=False).encode('utf-8'),headers={'Authorization':'Bearer '+AI_API_KEY,'Content-Type':'application/json','Accept':'application/json'},method='POST')
    try:
        with urllib.request.urlopen(req,timeout=40) as response: result=json.loads(response.read().decode('utf-8'))
        answer=result['choices'][0]['message']['content']
        return answer.strip() if isinstance(answer,str) and answer.strip() else '⚠️ پاسخ خالی از سرویس دریافت شد.'
    except urllib.error.HTTPError as e:
        detail=''
        try: detail=e.read().decode('utf-8',errors='replace')[:300]
        except Exception: pass
        print('AI HTTP error:',e.code,detail)
        if e.code==401: return '❌ کلید هوش مصنوعی معتبر نیست.'
        if e.code==429: return '⏳ محدودیت درخواست یا اعتبار سرویس را بررسی کن.'
        return f'❌ سرویس هوش مصنوعی خطای HTTP {e.code} داد.'
    except Exception as e: print('AI request error:',repr(e)); return '❌ ارتباط با هوش مصنوعی برقرار نشد؛ آدرس، کلید و اتصال هاست را بررسی کن.'

def stats_text():
    s=DATA['stats']; return (f'📊 <b>آمار {BRAND}</b>\n━━━━━━━━━━━━━━━━━━\n💬 پیام‌ها: {s["messages"]}\n🚫 حذف‌شده‌ها: {s["blocked"]}\n⚠️ اخطارها: {s["warns"]}\n👥 ورود اعضا: {s["joins"]}\n🎫 تیکت‌ها: {s["tickets"]}\n🌐 پروکسی‌ها: {len(DATA["proxies"])}\n💼 مشتریان: {len(DATA["customers"])}')

def send_backup(chat_id):
    if not is_owner(chat_id): bot.send_message(chat_id,'⛔ نسخه پشتیبان فقط برای مالک ربات است.'); return
    file_obj=io.BytesIO(json.dumps(DATA,ensure_ascii=False,indent=2).encode('utf-8')); file_obj.name='masih_guard_backup.json'
    bot.send_document(chat_id,file_obj,caption='💾 نسخه پشتیبان MASIH GUARD')

def moderate_member(action,chat_id,user_id):
    if action=='warn': warn_member(chat_id,user_id,'اخطار مدیر'); return '⚠️ اخطار ثبت شد.'
    if action=='ban': bot.ban_chat_member(chat_id,user_id); add_log('manual_ban',chat_id,user_id,'مسدودسازی مدیر'); return '⛔ عضو مسدود شد.'
    if action=='unban': bot.unban_chat_member(chat_id,user_id,only_if_banned=True); add_log('unban',chat_id,user_id,'رفع مسدودی'); return '✅ مسدودی برداشته شد.'
    if action=='kick': bot.ban_chat_member(chat_id,user_id); bot.unban_chat_member(chat_id,user_id,only_if_banned=True); add_log('kick',chat_id,user_id,'اخراج مدیر'); return '👢 عضو اخراج شد.'
    if action in ('mute','unmute'):
        allowed=action=='unmute'; perms=types.ChatPermissions(can_send_messages=allowed,can_send_audios=allowed,can_send_documents=allowed,can_send_photos=allowed,can_send_videos=allowed,can_send_video_notes=allowed,can_send_voice_notes=allowed,can_send_polls=allowed,can_send_other_messages=allowed,can_add_web_page_previews=allowed)
        bot.restrict_chat_member(chat_id,user_id,permissions=perms); add_log(action,chat_id,user_id,'تغییر محدودیت مدیر'); return '🔊 محدودیت برداشته شد.' if allowed else '🔇 عضو محدود شد.'
    raise ValueError('عملیات ناشناخته است.')

def create_ticket(user_id, username, text):
    tid=str(int(time.time()*1000)); DATA['tickets'][tid]={'user_id':int(user_id),'username':username or '', 'text':text[:3500], 'status':'open','created':now_text()}; DATA['stats']['tickets']+=1; save_data(); add_log('ticket_created','',user_id,'Ticket '+tid)
    try: bot.send_message(OWNER_ID,f'🎫 <b>تیکت جدید MASIH GUARD</b>\nشناسه: <code>{tid}</code>\nکاربر: <code>{user_id}</code>\nنام کاربری: @{esc(username or "ندارد")}\n\n{esc(text[:3500])}')
    except Exception as e: print('Ticket forwarding error:',repr(e))
    return tid

def handle_show(user_id, action):
    if action=='stats': bot.send_message(user_id,stats_text())
    elif action=='status': bot.send_message(user_id,f'🚀 <b>{BRAND} {VERSION}</b>\nربات در حال اجراست.\nهوش مصنوعی: {"تنظیم شده" if AI_API_KEY else "تنظیم نشده"}')
    elif action=='rules':
        pending=WAITING.get(user_id,{}); chat_id=pending.get('chat_id',user_id); bot.send_message(user_id,esc(get_group_settings(chat_id)['rules']))
    elif action=='proxies': bot.send_message(user_id,'\n'.join(f'{i+1}. {esc(x)}' for i,x in enumerate(DATA['proxies'])) if DATA['proxies'] else 'فهرست پروکسی‌ها خالی است.')
    elif action=='customers':
        rows=[f'• {esc(v.get("name"))} — <code>{esc(k)}</code>' for k,v in list(DATA['customers'].items())[:50]]; bot.send_message(user_id,'💼 <b>مشتریان</b>\n'+'\n'.join(rows) if rows else 'مشتری ثبت نشده است.')
    elif action=='logs':
        rows=[f'{esc(x.get("time"))} — {esc(x.get("action"))} — {esc(x.get("detail"))}' for x in DATA['logs'][-20:]]; bot.send_message(user_id,'🧾 <b>آخرین گزارش‌ها</b>\n'+'\n'.join(rows) if rows else 'گزارشی ثبت نشده است.')
    elif action=='backup': send_backup(user_id)
    elif action=='daily': bot.send_message(user_id,stats_text()+'\n\nاین گزارش از شمارنده‌های ذخیره‌شده ساخته شده است.')
    elif action=='points': bot.send_message(user_id,f'🏆 امتیاز شما: {DATA["points"].get(str(user_id),0)}')
    elif action=='tickets':
        rows=[(k,v) for k,v in DATA['tickets'].items() if v.get('user_id')==user_id or is_owner(user_id)]
        bot.send_message(user_id,'\n\n'.join(f'🎫 <code>{esc(k)}</code> — {esc(v.get("status"))}\n{esc(v.get("text","")[:200])}' for k,v in rows[-15:]) if rows else 'تیکتی ثبت نشده است.')

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    try:
        data=call.data or ''; uid=call.from_user.id; chat_id=call.message.chat.id if call.message else uid
        if data == 'panel:back':
            history = PANEL_HISTORY.setdefault(uid, [])
            section = history.pop() if history else 'home'
            send_panel(chat_id, section, call.message.message_id if call.message else None, user_id=uid)
            bot.answer_callback_query(call.id)
            return
        if data == 'panel:home':
            PANEL_HISTORY[uid] = []
            send_panel(chat_id, 'home', call.message.message_id if call.message else None, user_id=uid)
            bot.answer_callback_query(call.id)
            return
        if data.startswith('panel:'):
            section=data.split(':',1)[1]
            if section not in SECTIONS:
                bot.answer_callback_query(call.id,'بخش شناخته نشد.')
                return
            previous = PANEL_CURRENT.get(uid, 'home')
            if previous != section:
                PANEL_HISTORY.setdefault(uid, []).append(previous)
            send_panel(chat_id,section,call.message.message_id if call.message else None,user_id=uid)
            bot.answer_callback_query(call.id)
            return
        if data.startswith('toggle:'):
            setting=data.split(':',1)[1]
            if setting=='smart_security':
                if not is_owner(uid): bot.answer_callback_query(call.id,'فقط مالک مجاز است.',show_alert=True); return
                DATA['settings']['smart_security']=not DATA['settings'].get('smart_security',True); save_data(); bot.answer_callback_query(call.id,'تغییر ذخیره شد.'); send_panel(chat_id,'smart',call.message.message_id if call.message else None); return
            if call.message and call.message.chat.type == 'private':
                if not is_owner(uid):
                    bot.answer_callback_query(call.id,'فقط مالک می‌تواند از پنل خصوصی تنظیم کند.',show_alert=True)
                    return
                WAITING[uid] = {'action':'toggle_group_setting','setting':setting}
                bot.answer_callback_query(call.id)
                bot.send_message(uid, '🆔 شناسهٔ گروه را بفرست (معمولاً با ‎-100‎ شروع می‌شود). برای ذخیره، ربات باید داخل گروه باشد.')
                return
            if not is_group_admin(chat_id,uid):
                bot.answer_callback_query(call.id,'باید مدیر همان گروه باشی.',show_alert=True)
                return
            settings=get_group_settings(chat_id)
            if not isinstance(settings.get(setting),bool): bot.answer_callback_query(call.id,'تنظیم قابل تغییر نیست.',show_alert=True); return
            settings[setting]=not settings[setting]; save_data(); bot.answer_callback_query(call.id,'فعال شد.' if settings[setting] else 'غیرفعال شد.'); send_panel(chat_id,'welcome' if setting in ('welcome_on','farewell_on','join_approval') else 'security',call.message.message_id if call.message else None); return
        if data.startswith('ask:'):
            action=data.split(':',1)[1]
            owner_only={'add_proxy','delete_proxy','add_customer','find_customer','delete_reply','bad_word','warn_limit'}
            if action in owner_only and not is_owner(uid): bot.answer_callback_query(call.id,'فقط مالک مجاز است.',show_alert=True); return
            group_actions = {'welcome_text','farewell_text','rules','auto_reply','delete_reply','bad_word','warn_limit'}
            if call.message and call.message.chat.type == 'private' and action in group_actions:
                WAITING[uid] = {'action':'select_group_for_action','next_action':action}
                bot.answer_callback_query(call.id)
                bot.send_message(uid, '🆔 اول شناسهٔ گروه را بفرست (معمولاً با ‎-100‎ شروع می‌شود). بعد از آن مقدار تنظیم را می‌فرستی.')
                return
            WAITING[uid]={'action':action,'chat_id':chat_id}
            prompts={'welcome_text':'متن خوشامد را بفرست؛ می‌توانی از {name} استفاده کنی.','farewell_text':'متن خداحافظی را بفرست؛ می‌توانی از {name} استفاده کنی.','rules':'متن قوانین جدید را بفرست.','auto_reply':'قالب: کلمه کلیدی | متن پاسخ','delete_reply':'کلمه کلیدی پاسخ خودکار را بفرست.','bad_word':'کلمه ممنوع را بفرست.','warn':'شناسه عضو یا شناسه گروه | شناسه عضو را بفرست.','mute':'شناسه عضو یا شناسه گروه | شناسه عضو را بفرست.','unmute':'شناسه عضو یا شناسه گروه | شناسه عضو را بفرست.','ban':'شناسه عضو یا شناسه گروه | شناسه عضو را بفرست.','unban':'شناسه عضو یا شناسه گروه | شناسه عضو را بفرست.','kick':'شناسه عضو یا شناسه گروه | شناسه عضو را بفرست.','font':'متنی را برای تبدیل فونت بفرست.','add_proxy':'لینک t.me/proxy یا tg://proxy را بفرست.','delete_proxy':'شماره پروکسی را بفرست.','add_customer':'قالب: شناسه | نام | توضیحات','find_customer':'شناسه مشتری را بفرست.','ticket':'متن تیکت را بفرست.','ai':'سؤال خود را بفرست.','warn_limit':'سقف اخطار بین ۱ تا ۲۰ را بفرست.'}
            bot.answer_callback_query(call.id); bot.send_message(uid,prompts.get(action,'اطلاعات موردنیاز را بفرست.')); return
        if data.startswith('show:'):
            action=data.split(':',1)[1]
            owner_actions={'proxies','customers','logs','backup','daily'}
            if action in owner_actions and not is_owner(uid): bot.answer_callback_query(call.id,'فقط مالک مجاز است.',show_alert=True); return
            WAITING[uid]={'action':'show_'+action,'chat_id':chat_id}; bot.answer_callback_query(call.id); handle_show(uid,action); WAITING.pop(uid,None); return
        if data=='game:guess': GAMES[uid]=random.randint(1,5); WAITING[uid]={'action':'game:guess','chat_id':chat_id}; bot.answer_callback_query(call.id); bot.send_message(uid,'🎮 عددی بین ۱ تا ۵ حدس بزن و بفرست.'); return
        bot.answer_callback_query(call.id,'گزینه ناشناخته است.')
    except Exception as e:
        print('Callback error:',repr(e))
        try: bot.answer_callback_query(call.id,'خطا رخ داد؛ دوباره تلاش کن.',show_alert=True)
        except Exception: pass

@bot.message_handler(content_types=['text'], func=lambda m: m.chat.type=='private')
def private_text_handler(message):
    uid=message.from_user.id; text=(message.text or '').strip()
    if text.startswith('/'): return
    pending=WAITING.get(uid)
    if not pending: return
    action=pending.get('action',''); chat_id=pending.get('chat_id',uid)
    owner_only={'add_proxy','delete_proxy','add_customer','find_customer','delete_reply','bad_word','warn_limit','show_backup','show_logs','show_customers','show_daily'}
    if action in owner_only and not is_owner(uid): WAITING.pop(uid,None); bot.send_message(uid,'⛔ این عملیات فقط برای مالک است.'); return
    try:
        if action == 'select_group_for_action':
            target_chat = int(text)
            if target_chat >= 0:
                raise ValueError('شناسهٔ گروه باید منفی باشد؛ شناسهٔ گروه را بررسی کن.')
            next_action = pending.get('next_action', '')
            if not is_owner(uid):
                raise PermissionError('این عملیات فقط برای مالک ربات است.')
            WAITING[uid] = {'action':next_action, 'chat_id':target_chat}
            next_prompts = {
                'welcome_text':'متن خوشامد را بفرست؛ می‌توانی از {name} استفاده کنی.',
                'farewell_text':'متن خداحافظی را بفرست؛ می‌توانی از {name} استفاده کنی.',
                'rules':'متن قوانین جدید را بفرست.',
                'auto_reply':'قالب را بفرست: کلمه کلیدی | متن پاسخ',
                'delete_reply':'کلمه کلیدی پاسخ خودکار را بفرست.',
                'bad_word':'کلمهٔ ممنوع را بفرست.',
                'warn_limit':'سقف اخطار را بین ۱ تا ۲۰ بفرست.'
            }
            bot.send_message(uid, '✅ گروه انتخاب شد.\n' + next_prompts.get(next_action, 'مقدار تنظیم را بفرست.'))
            return
        if action == 'toggle_group_setting':
            target_chat = int(text)
            if target_chat >= 0:
                raise ValueError('شناسهٔ گروه باید منفی باشد؛ شناسهٔ گروه را دوباره بررسی کن.')
            if not is_owner(uid):
                raise PermissionError('این عملیات فقط برای مالک ربات است.')
            settings = get_group_settings(target_chat)
            setting = pending.get('setting', '')
            if not isinstance(settings.get(setting), bool):
                raise ValueError('این تنظیم قابل تغییر نیست.')
            settings[setting] = not settings[setting]
            save_data()
            add_log('setting_toggled', target_chat, uid, setting + '=' + str(settings[setting]))
            bot.send_message(uid, f'✅ تنظیم «{esc(SECTIONS.get("security", "امنیت"))}» برای گروه <code>{target_chat}</code> ذخیره شد: {"روشن" if settings[setting] else "خاموش"}')
        elif action=='font': bot.send_message(uid,'🔤 <b>نتیجه تبدیل</b>\n\n'+esc(text)+'\n\n'+esc(convert_font(text,0))+'\n\n'+esc(convert_font(text,1))+'\n\n'+esc(convert_font(text,2)))
        elif action in ('welcome_text','farewell_text','rules'):
            if chat_id>0 and not is_owner(uid): bot.send_message(uid,'برای تنظیم گروه، باید مدیر گروه باشی و شناسه گروه را مشخص کنی.'); return
            s=get_group_settings(chat_id); s[{'welcome_text':'welcome_text','farewell_text':'farewell_text','rules':'rules'}[action]]=text[:3000]; save_data(); bot.send_message(uid,'✅ ذخیره شد.')
        elif action=='auto_reply':
            if '|' not in text: bot.send_message(uid,'قالب: کلمه کلیدی | متن پاسخ'); return
            keyword,reply=[p.strip() for p in text.split('|',1)]
            if not keyword or not reply: raise ValueError('کلمه کلیدی و پاسخ خالی نباشند.')
            get_group_settings(chat_id)['auto_replies'][keyword]=reply[:2000]; save_data(); bot.send_message(uid,'✅ پاسخ خودکار ذخیره شد.')
        elif action=='delete_reply':
            existed=get_group_settings(chat_id)['auto_replies'].pop(text,None); save_data(); bot.send_message(uid,'🗑 پاسخ حذف شد.' if existed is not None else 'کلمه کلیدی پیدا نشد.')
        elif action=='bad_word':
            s=get_group_settings(chat_id)
            if text not in s['bad_words']: s['bad_words'].append(text[:100])
            save_data(); bot.send_message(uid,'✅ کلمه ممنوع ثبت شد.')
        elif action=='warn_limit':
            n=int(text)
            if not 1<=n<=20: raise ValueError('عدد باید بین ۱ تا ۲۰ باشد.')
            get_group_settings(chat_id)['warn_limit']=n; save_data(); bot.send_message(uid,'✅ سقف اخطار ذخیره شد.')
        elif action in ('warn','mute','unmute','ban','unban','kick'):
            parts=[x.strip() for x in text.split('|')]
            target_chat,target_user=(int(chat_id),int(parts[0])) if len(parts)==1 else (int(parts[0]),int(parts[1]))
            if not is_owner(uid) and not is_group_admin(target_chat,uid): raise PermissionError('باید مدیر همان گروه باشی.')
            bot.send_message(uid,moderate_member(action,target_chat,target_user))
        elif action=='add_proxy':
            if not (text.startswith('https://t.me/proxy?') or text.startswith('http://t.me/proxy?') or text.startswith('tg://proxy?')): raise ValueError('لینک معتبر t.me/proxy یا tg://proxy وارد کن.')
            if text in DATA['proxies']: bot.send_message(uid,'این پروکسی قبلاً ثبت شده است.')
            else: DATA['proxies'].append(text); save_data(); add_log('proxy_added','',uid,text); bot.send_message(uid,'✅ پروکسی ذخیره شد.')
        elif action=='delete_proxy':
            i=int(text)-1
            if not 0<=i<len(DATA['proxies']): raise ValueError('شماره پروکسی معتبر نیست.')
            removed=DATA['proxies'].pop(i); save_data(); add_log('proxy_deleted','',uid,removed); bot.send_message(uid,'🗑 پروکسی حذف شد.')
        elif action=='add_customer':
            parts=[p.strip() for p in text.split('|',2)]
            if len(parts)<2: raise ValueError('قالب: شناسه | نام | توضیحات')
            DATA['customers'][parts[0]]={'name':parts[1],'details':parts[2] if len(parts)>2 else '', 'created':now_text()}; save_data(); add_log('customer_added','',parts[0],parts[1]); bot.send_message(uid,'✅ مشتری ثبت شد.')
        elif action=='find_customer':
            c=DATA['customers'].get(text); bot.send_message(uid,(f'💼 <b>{esc(c["name"])}</b>\nشناسه: <code>{esc(text)}</code>\nتوضیحات: {esc(c["details"])}\nثبت: {esc(c["created"])}') if c else 'مشتری پیدا نشد.')
        elif action=='ticket':
            tid=create_ticket(uid,message.from_user.username,text); bot.send_message(uid,f'🎫 تیکت ثبت شد. شناسه: <code>{tid}</code>')
        elif action=='ai':
            status=bot.send_message(uid,'🧠 در حال دریافت پاسخ...'); answer=ask_ai(text)
            try: bot.edit_message_text(esc(answer[:4000]),uid,status.message_id)
            except Exception: bot.send_message(uid,esc(answer[:4000]))
        elif action=='game:guess':
            guess=int(text)
            if not 1<=guess<=5: raise ValueError('عدد باید بین ۱ تا ۵ باشد.')
            answer=GAMES.get(uid)
            if answer is None: raise ValueError('بازی فعالی نیست؛ دوباره از پنل شروع کن.')
            if guess==answer: DATA['points'][str(uid)]=DATA['points'].get(str(uid),0)+1; save_data(); bot.send_message(uid,f'🎉 درست بود! عدد {answer} بود؛ یک امتیاز گرفتی.')
            else: bot.send_message(uid,f'این بار نه؛ عدد درست {answer} بود.')
            GAMES.pop(uid,None)
        elif action.startswith('show_'): handle_show(uid,action[5:])
        else: bot.send_message(uid,'این عملیات هنوز پیاده‌سازی نشده است.')
        WAITING.pop(uid,None)
    except (ValueError,TypeError,PermissionError) as e: bot.send_message(uid,'⚠️ ورودی یا دسترسی معتبر نیست.\n'+esc(str(e)))
    except Exception as e: print('Private action error:',repr(e)); bot.send_message(uid,'⚠️ عملیات ناموفق بود؛ دسترسی ربات و اطلاعات واردشده را بررسی کن.')

@bot.message_handler(commands=['ai','ask'])
def ai_command(message):
    parts=(message.text or '').split(maxsplit=1)
    if len(parts)<2: bot.reply_to(message,'🤖 سؤال را بعد از دستور بنویس:\n/ai سلام، خودت را معرفی کن'); return
    status=bot.reply_to(message,'🤖 در حال بررسی سؤال...'); answer=ask_ai(parts[1].strip())
    chunks=[answer[i:i+3900] for i in range(0,len(answer),3900)] or ['پاسخی دریافت نشد.']
    try:
        bot.edit_message_text(esc(chunks[0]),status.chat.id,status.message_id)
        for chunk in chunks[1:]: bot.send_message(message.chat.id,esc(chunk))
    except Exception as e:
        print('AI send error:',repr(e))
        try: bot.send_message(message.chat.id,esc(answer[:3900]))
        except Exception: pass

if __name__ == '__main__':
    print(f'{BRAND} {VERSION}: starting polling')
    try:
        bot.infinity_polling(skip_pending=True, timeout=30, long_polling_timeout=25)
    except Exception as e:
        print('Polling stopped:',repr(e))
        raise
