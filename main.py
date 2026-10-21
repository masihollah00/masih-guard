# -*- coding: utf-8 -*-
"""MASIH GUARD S1000 - simple Persian Telegram group manager.
Required env: TELEGRAM_BOT_TOKEN (or BOT_TOKEN)
Optional env: OWNER_ID (default 8620924698), PORT (default 8080)
"""
import os, json, time, logging, threading, re
from pathlib import Path
from flask import Flask
import telebot
from telebot import types

BOT_TOKEN = (os.getenv('TELEGRAM_BOT_TOKEN') or os.getenv('BOT_TOKEN') or '').strip()
OWNER_ID = int(os.getenv('OWNER_ID', '8620924698'))
PORT = int(os.getenv('PORT', '8080'))
DATA_FILE = Path(os.getenv('DATA_FILE', 'masih_guard_data.json'))
BOT_NAME = 'MASIH GUARD'
VERSION = 'S1000'
logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
log = logging.getLogger('masih_guard')

if not BOT_TOKEN:
    raise RuntimeError('BOT TOKEN is missing. Set TELEGRAM_BOT_TOKEN or BOT_TOKEN in host environment variables.')

bot = telebot.TeleBot(BOT_TOKEN, parse_mode='HTML', threaded=True, num_threads=4)
app = Flask(__name__)

DEFAULTS = {
    'welcome_enabled': True,
    'welcome_text': 'سلام {name} عزیز! 🌟\nبه گروه <b>{group}</b> خوش اومدی.\nلطفاً قوانین گروه رو رعایت کن 💙',
    'welcome_buttons': [],
    'farewell_enabled': False,
    'farewell_text': '👋 {name} از گروه خارج شد.',
    'rules': '📌 قوانین گروه:\n۱. احترام به همه\n۲. ارسال نکردن لینک تبلیغاتی\n۳. رعایت موضوع گروه',
    'anti_link': False,
    'anti_spam': True,
    'bad_words': [],
    'warns': {},
    'known_groups': {},
    'pending': {}
}

_data_lock = threading.RLock()
def load_data():
    try:
        if DATA_FILE.exists():
            raw = json.loads(DATA_FILE.read_text(encoding='utf-8'))
            if isinstance(raw, dict):
                return raw
    except Exception:
        log.exception('Could not read data file; starting with defaults')
    return {'global': dict(DEFAULTS), 'groups': {}}

data = load_data()
data.setdefault('global', dict(DEFAULTS))
data.setdefault('groups', {})
for k, v in DEFAULTS.items():
    data['global'].setdefault(k, v)

def save_data():
    with _data_lock:
        tmp = DATA_FILE.with_suffix('.tmp')
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
        tmp.replace(DATA_FILE)

def cfg(chat_id=None):
    if chat_id is None:
        return data['global']
    key = str(chat_id)
    data['groups'].setdefault(key, {})
    g = data['groups'][key]
    for k, v in DEFAULTS.items():
        g.setdefault(k, data['global'].get(k, v))
    return g

def is_owner(user_id):
    return int(user_id or 0) == OWNER_ID

def is_group_admin(chat_id, user_id):
    if is_owner(user_id):
        return True
    try:
        m = bot.get_chat_member(chat_id, user_id)
        return m.status in ('administrator', 'creator')
    except Exception:
        return False

def esc(s):
    from html import escape
    return escape(str(s), quote=False)

def format_text(template, name, group):
    # Only allow the documented placeholders; text is escaped before substitution.
    safe_name, safe_group = esc(name), esc(group)
    result = str(template).replace('{name}', safe_name).replace('{group}', safe_group)
    return result[:3500]

def welcome_markup(settings):
    rows, row = [], []
    for item in settings.get('welcome_buttons', [])[:12]:
        text = str(item.get('text', ''))[:40]
        url = str(item.get('url', ''))
        if text and re.match(r'^https?://', url):
            row.append(types.InlineKeyboardButton(text, url=url))
            if len(row) == 2:
                rows.append(row); row = []
    if row: rows.append(row)
    return types.InlineKeyboardMarkup(rows) if rows else None

def main_markup(private=False):
    kb = types.InlineKeyboardMarkup(row_width=2)
    if private:
        kb.add(types.InlineKeyboardButton('👋 تنظیم خوشامد', callback_data='own:welcome'),
               types.InlineKeyboardButton('🔘 دکمه‌های خوشامد', callback_data='own:buttons'))
        kb.add(types.InlineKeyboardButton('📝 متن خوشامد', callback_data='own:text'),
               types.InlineKeyboardButton('📌 قوانین پیش‌فرض', callback_data='own:rules'))
        kb.add(types.InlineKeyboardButton('📊 وضعیت', callback_data='own:status'),
               types.InlineKeyboardButton('❔ راهنما', callback_data='own:help'))
    else:
        kb.add(types.InlineKeyboardButton('📌 قوانین', callback_data='group:rules'),
               types.InlineKeyboardButton('📊 وضعیت گروه', callback_data='group:status'))
        kb.add(types.InlineKeyboardButton('🛡 راهنمای مدیران', callback_data='group:help'))
    return kb

def back_markup(dest='home'):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton('⬅️ بازگشت', callback_data='back:' + dest))
    return kb

def safe_edit(call, text, markup=None):
    try:
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup, disable_web_page_preview=True)
    except Exception as e:
        if 'message is not modified' not in str(e).lower():
            log.info('edit failed: %s', e)
            try: bot.answer_callback_query(call.id, 'این پیام قابل ویرایش نبود؛ دوباره /panel را بزن.', show_alert=True)
            except Exception: pass

def remember_group(message):
    if message.chat.type in ('group', 'supergroup'):
        data['global']['known_groups'][str(message.chat.id)] = message.chat.title or str(message.chat.id)
        save_data()

def panel_text():
    return ('<b>👑 پنل مالک | MASIH GUARD ' + VERSION + '</b>\n\n'
            'از دکمه‌ها برای تنظیم خوشامدگویی و دکمه‌های زیر پیام استفاده کن.\n'
            'این پنل فقط برای مالک ربات قابل استفاده است.')

@bot.message_handler(commands=['start', 'panel', 'پنل'])
def start(message):
    remember_group(message)
    if message.chat.type == 'private':
        if is_owner(message.from_user.id):
            bot.send_message(message.chat.id, panel_text(), reply_markup=main_markup(private=True))
        else:
            bot.send_message(message.chat.id, 'سلام! 🌟 من <b>MASIH GUARD</b> هستم.\nبرای راهنما از /help استفاده کن. تنظیمات فقط در اختیار مالک ربات است.')
    else:
        bot.send_message(message.chat.id, 'سلام! 👋\nبرای دیدن قوانین: /rules\nپنل تنظیمات فقط در گفت‌وگوی خصوصی مالک ربات در دسترس است.')

@bot.message_handler(commands=['help', 'راهنما'])
def help_cmd(message):
    txt = ('<b>📚 راهنمای MASIH GUARD</b>\n'
           '/start — شروع ربات\n/panel — پنل مالک (خصوصی)\n/rules — قوانین گروه\n'
           '/id — نمایش شناسه\n\n'
           'دستورات مدیران گروه:\n/antilink on یا /antilink off\n/warn با ریپلای به پیام کاربر\n/mute با ریپلای و مدت دقیقه\n/ban با ریپلای به پیام کاربر\n/purge با ریپلای به پیام برای حذف چند پیام اخیر')
    bot.reply_to(message, txt)

@bot.message_handler(commands=['id'])
def id_cmd(message):
    bot.reply_to(message, f'🆔 شناسه شما: <code>{message.from_user.id}</code>\nشناسه گفتگو: <code>{message.chat.id}</code>')

@bot.message_handler(commands=['rules', 'قوانین'])
def rules_cmd(message):
    remember_group(message)
    bot.reply_to(message, cfg(message.chat.id).get('rules', DEFAULTS['rules']))

@bot.callback_query_handler(func=lambda c: True)
def callbacks(call):
    try:
        user_id = call.from_user.id
        key = call.data or ''
        if key.startswith('own:') or key.startswith('back:') and key.endswith('owner'):
            if not is_owner(user_id):
                bot.answer_callback_query(call.id, '⛔ این بخش فقط برای مالک ربات است.', show_alert=True); return
        if key == 'back:home':
            safe_edit(call, panel_text(), main_markup(private=True)); bot.answer_callback_query(call.id); return
        if key == 'own:welcome':
            c = cfg()
            status = 'روشن ✅' if c['welcome_enabled'] else 'خاموش ❌'
            kb = types.InlineKeyboardMarkup(row_width=2)
            kb.add(types.InlineKeyboardButton('✅ روشن کردن', callback_data='own:welcome:on'), types.InlineKeyboardButton('❌ خاموش کردن', callback_data='own:welcome:off'))
            kb.add(types.InlineKeyboardButton('📝 ویرایش متن', callback_data='own:text'), types.InlineKeyboardButton('🔘 دکمه‌ها', callback_data='own:buttons'))
            kb.add(types.InlineKeyboardButton('⬅️ بازگشت', callback_data='back:home'))
            safe_edit(call, f'<b>👋 تنظیم خوشامدگویی</b>\nوضعیت: {status}\n\nبرای تغییر وضعیت یا متن، یکی از دکمه‌ها را بزن.', kb); bot.answer_callback_query(call.id); return
        if key in ('own:welcome:on', 'own:welcome:off'):
            cfg()['welcome_enabled'] = key.endswith(':on'); save_data()
            bot.answer_callback_query(call.id, 'ذخیره شد ✅')
            # Refresh the current panel in place
            c = cfg(); kb = types.InlineKeyboardMarkup(row_width=2)
            kb.add(types.InlineKeyboardButton('✅ روشن کردن', callback_data='own:welcome:on'), types.InlineKeyboardButton('❌ خاموش کردن', callback_data='own:welcome:off'))
            kb.add(types.InlineKeyboardButton('📝 ویرایش متن', callback_data='own:text'), types.InlineKeyboardButton('🔘 دکمه‌ها', callback_data='own:buttons'))
            kb.add(types.InlineKeyboardButton('⬅️ بازگشت', callback_data='back:home'))
            safe_edit(call, f"<b>👋 تنظیم خوشامدگویی</b>\nوضعیت: {'روشن ✅' if c['welcome_enabled'] else 'خاموش ❌'}\n\nتغییرات ذخیره شد.", kb); return
        if key == 'own:text':
            data['global']['pending'][str(user_id)] = 'welcome_text'; save_data()
            kb = back_markup('home')
            safe_edit(call, '<b>📝 ویرایش متن خوشامد</b>\nحالا متن جدید را در همین گفت‌وگو به صورت یک پیام بفرست.\n\nجایگزین‌ها: <code>{name}</code> نام عضو، <code>{group}</code> نام گروه.\nبرای لغو، دکمه بازگشت را بزن.', kb); bot.answer_callback_query(call.id); return
        if key == 'own:buttons':
            c = cfg(); kb = types.InlineKeyboardMarkup(row_width=1)
            kb.add(types.InlineKeyboardButton('➕ افزودن دکمه', callback_data='own:button:add'))
            for i, b in enumerate(c['welcome_buttons'][:12]):
                kb.add(types.InlineKeyboardButton(f"🗑 حذف: {b.get('text','دکمه')}", callback_data=f'own:button:del:{i}'))
            kb.add(types.InlineKeyboardButton('⬅️ بازگشت', callback_data='back:home'))
            summary = '\n'.join([f"• {esc(b.get('text',''))} → {esc(b.get('url',''))}" for b in c['welcome_buttons']]) or 'هنوز دکمه‌ای اضافه نشده.'
            safe_edit(call, '<b>🔘 دکمه‌های خوشامد</b>\nبرای هر دکمه یک عنوان و یک لینک https وارد کن.\n\n' + summary, kb); bot.answer_callback_query(call.id); return
        if key == 'own:button:add':
            data['global']['pending'][str(user_id)] = 'button_text'; save_data()
            safe_edit(call, '➕ <b>افزودن دکمه</b>\nاول عنوان دکمه را بفرست؛ مثال: کانال ما\nبعد از آن لینک را می‌پرسم.', back_markup('home')); bot.answer_callback_query(call.id); return
        if key.startswith('own:button:del:'):
            try:
                idx = int(key.rsplit(':', 1)[1]); buttons = cfg()['welcome_buttons']
                if 0 <= idx < len(buttons): buttons.pop(idx); save_data()
            except Exception: pass
            bot.answer_callback_query(call.id, 'اگر دکمه وجود داشت حذف شد.')
            c = cfg(); kb = types.InlineKeyboardMarkup(row_width=1); kb.add(types.InlineKeyboardButton('➕ افزودن دکمه', callback_data='own:button:add'))
            for i, b in enumerate(c['welcome_buttons'][:12]): kb.add(types.InlineKeyboardButton(f"🗑 حذف: {b.get('text','دکمه')}", callback_data=f'own:button:del:{i}'))
            kb.add(types.InlineKeyboardButton('⬅️ بازگشت', callback_data='back:home'))
            safe_edit(call, '<b>🔘 دکمه‌های خوشامد</b>\nتغییرات ذخیره شد.', kb); return
        if key == 'own:rules':
            data['global']['pending'][str(user_id)] = 'rules'; save_data()
            safe_edit(call, '<b>📌 تنظیم قوانین پیش‌فرض</b>\nمتن جدید قوانین را بفرست. این متن برای گروه‌هایی استفاده می‌شود که قوانین اختصاصی ندارند.', back_markup('home')); bot.answer_callback_query(call.id); return
        if key == 'own:status':
            groups = cfg().get('known_groups', {})
            safe_edit(call, f'<b>📊 وضعیت ربات</b>\nنسخه: {VERSION}\nگروه‌های شناخته‌شده: {len(groups)}\nخوشامد: {"روشن" if cfg()["welcome_enabled"] else "خاموش"}\nدکمه‌های خوشامد: {len(cfg()["welcome_buttons"])}', back_markup('home')); bot.answer_callback_query(call.id); return
        if key == 'own:help':
            safe_edit(call, '<b>❔ راهنمای مالک</b>\nاز پنل خوشامد را روشن/خاموش کن، متن را تغییر بده و دکمه‌های لینک‌دار اضافه یا حذف کن.\nبرای جایگزینی نام عضو از <code>{name}</code> و نام گروه از <code>{group}</code> استفاده کن.', back_markup('home')); bot.answer_callback_query(call.id); return
        if key.startswith('group:'):
            chat_id = call.message.chat.id
            if key == 'group:rules':
                safe_edit(call, cfg(chat_id).get('rules', DEFAULTS['rules']), back_markup('group')); bot.answer_callback_query(call.id); return
            if key == 'group:status':
                safe_edit(call, f'<b>📊 وضعیت گروه</b>\nضدلینک: {"روشن" if cfg(chat_id)["anti_link"] else "خاموش"}\nضدتکرار: {"روشن" if cfg(chat_id)["anti_spam"] else "خاموش"}', back_markup('group')); bot.answer_callback_query(call.id); return
            if key == 'group:help':
                safe_edit(call, 'تنظیمات مدیریتی فقط برای مالک ربات فعال است. مدیران تلگرام می‌توانند از دستورات مدیریتی موجود استفاده کنند.', back_markup('group')); bot.answer_callback_query(call.id); return
        if key == 'back:group':
            safe_edit(call, '👋 پنل گروه', main_markup(False)); bot.answer_callback_query(call.id); return
        bot.answer_callback_query(call.id)
    except Exception:
        log.exception('callback failed')
        try: bot.answer_callback_query(call.id, 'خطا رخ داد؛ دوباره تلاش کن.', show_alert=True)
        except Exception: pass

@bot.message_handler(func=lambda m: m.chat.type == 'private' and bool(m.from_user) and is_owner(m.from_user.id) and bool(data['global'].get('pending', {}).get(str(m.from_user.id))), content_types=['text'])
def owner_input(message):
    uid = str(message.from_user.id)
    pending = data['global']['pending'].get(uid)
    text = (message.text or '').strip()
    if text.startswith('/'):
        return
    if pending == 'welcome_text':
        if not text: bot.reply_to(message, 'متن خالی پذیرفته نیست.'); return
        cfg()['welcome_text'] = text[:3500]
        data['global']['pending'].pop(uid, None); save_data()
        bot.reply_to(message, '✅ متن خوشامد ذخیره شد.', reply_markup=main_markup(private=True))
    elif pending == 'button_text':
        if len(cfg()['welcome_buttons']) >= 12:
            data['global']['pending'].pop(uid, None); save_data(); bot.reply_to(message, 'حداکثر ۱۲ دکمه مجاز است.'); return
        data['global']['pending'][uid] = 'button_url'; data['global']['pending'][uid + ':button_text'] = text[:40]; save_data()
        bot.reply_to(message, 'حالا لینک دکمه را بفرست؛ باید با https:// یا http:// شروع شود.')
    elif pending == 'button_url':
        if not re.match(r'^https?://\S+$', text):
            bot.reply_to(message, '❌ لینک معتبر نیست. یک لینک کامل با https:// بفرست.'); return
        label = data['global']['pending'].pop(uid + ':button_text', 'لینک')
        cfg()['welcome_buttons'].append({'text': label, 'url': text[:500]})
        data['global']['pending'].pop(uid, None); save_data()
        bot.reply_to(message, f'✅ دکمه «{esc(label)}» اضافه شد.', reply_markup=main_markup(private=True))
    elif pending == 'rules':
        cfg()['rules'] = text[:3500]; data['global']['pending'].pop(uid, None); save_data()
        bot.reply_to(message, '✅ قوانین پیش‌فرض ذخیره شد.', reply_markup=main_markup(private=True))

@bot.message_handler(content_types=['new_chat_members'])
def new_members(message):
    remember_group(message)
    # Welcome text/buttons are controlled centrally by the owner in the bot's private panel.
    c = cfg()
    if not c.get('welcome_enabled', True): return
    for member in message.new_chat_members:
        if member.is_bot and member.id == bot.get_me().id: continue
        name = member.first_name or 'دوست عزیز'
        text = format_text(c.get('welcome_text', DEFAULTS['welcome_text']), name, message.chat.title or 'گروه')
        try: bot.send_message(message.chat.id, text, reply_markup=welcome_markup(c), disable_web_page_preview=True)
        except Exception: log.exception('welcome send failed')

@bot.message_handler(content_types=['left_chat_member'])
def left_member(message):
    c = cfg(message.chat.id)
    member = message.left_chat_member
    if c.get('farewell_enabled'):
        try: bot.send_message(message.chat.id, format_text(c.get('farewell_text', DEFAULTS['farewell_text']), member.first_name or 'عضو', message.chat.title or 'گروه'))
        except Exception: log.exception('farewell failed')

@bot.message_handler(commands=['antilink'])
def anti_link_cmd(message):
    if message.chat.type not in ('group','supergroup'): return
    if not is_group_admin(message.chat.id, message.from_user.id):
        bot.reply_to(message, '⛔ فقط مدیر گروه می‌تواند این دستور را اجرا کند.'); return
    parts = (message.text or '').split()
    if len(parts) < 2 or parts[1].lower() not in ('on','off','روشن','خاموش'):
        bot.reply_to(message, 'استفاده: /antilink on یا /antilink off'); return
    cfg(message.chat.id)['anti_link'] = parts[1].lower() in ('on','روشن'); save_data()
    bot.reply_to(message, '✅ ضدلینک ' + ('روشن شد.' if cfg(message.chat.id)['anti_link'] else 'خاموش شد.'))

@bot.message_handler(commands=['warn'])
def warn_cmd(message):
    if message.chat.type not in ('group','supergroup'): return
    if not is_group_admin(message.chat.id, message.from_user.id): bot.reply_to(message, '⛔ فقط مدیر گروه.'); return
    if not message.reply_to_message: bot.reply_to(message, 'برای اخطار، روی پیام کاربر ریپلای کن و /warn بزن.'); return
    target = message.reply_to_message.from_user
    if target.is_bot or is_group_admin(message.chat.id, target.id): bot.reply_to(message, 'به مدیر یا ربات اخطار نمی‌دهم.'); return
    c = cfg(message.chat.id); warns = c.setdefault('warns', {}); k = str(target.id); warns[k] = warns.get(k, 0) + 1; save_data()
    if warns[k] >= 3:
        try: bot.ban_chat_member(message.chat.id, target.id); warns[k] = 0; save_data(); bot.reply_to(message, f'🚫 {esc(target.first_name)} پس از ۳ اخطار مسدود شد.')
        except Exception: bot.reply_to(message, f'⚠️ اخطار {warns[k]} از ۳؛ برای مسدودسازی به دسترسی حذف/مسدودکردن اعضا نیاز دارم.')
    else: bot.reply_to(message, f'⚠️ به {esc(target.first_name)} اخطار داده شد: {warns[k]}/3')

@bot.message_handler(commands=['mute'])
def mute_cmd(message):
    if message.chat.type not in ('group','supergroup'): return
    if not is_group_admin(message.chat.id, message.from_user.id): bot.reply_to(message, '⛔ فقط مدیر گروه.'); return
    if not message.reply_to_message: bot.reply_to(message, 'روی پیام کاربر ریپلای کن: /mute 10'); return
    try: minutes = max(1, min(10080, int((message.text or '').split()[1])))
    except Exception: minutes = 10
    target = message.reply_to_message.from_user
    if target.is_bot or is_group_admin(message.chat.id, target.id): bot.reply_to(message, 'به مدیر یا ربات محدودیت نمی‌دهم.'); return
    try:
        until = int(time.time()) + minutes * 60
        bot.restrict_chat_member(message.chat.id, target.id, until_date=until, permissions=types.ChatPermissions(can_send_messages=False, can_send_media_messages=False, can_send_polls=False, can_send_other_messages=False, can_add_web_page_previews=False))
        bot.reply_to(message, f'🔇 {esc(target.first_name)} به مدت {minutes} دقیقه محدود شد.')
    except Exception as e: log.warning('mute failed: %s', e); bot.reply_to(message, '❌ انجام نشد؛ دسترسی محدودکردن اعضا را به ربات بده.')

@bot.message_handler(commands=['ban'])
def ban_cmd(message):
    if message.chat.type not in ('group','supergroup'): return
    if not is_group_admin(message.chat.id, message.from_user.id): bot.reply_to(message, '⛔ فقط مدیر گروه.'); return
    if not message.reply_to_message: bot.reply_to(message, 'برای بن، روی پیام کاربر ریپلای کن و /ban بزن.'); return
    target = message.reply_to_message.from_user
    if target.is_bot or is_group_admin(message.chat.id, target.id): bot.reply_to(message, 'به مدیر یا ربات دسترسی نمی‌زنم.'); return
    try: bot.ban_chat_member(message.chat.id, target.id); bot.reply_to(message, f'🚫 {esc(target.first_name)} مسدود شد.')
    except Exception as e: log.warning('ban failed: %s', e); bot.reply_to(message, '❌ بن انجام نشد؛ دسترسی مسدودکردن اعضا را بررسی کن.')

@bot.message_handler(func=lambda m: m.chat.type in ('group','supergroup'), content_types=['text'])
def moderation(message):
    remember_group(message)
    if not message.from_user or message.from_user.is_bot or is_group_admin(message.chat.id, message.from_user.id): return
    c = cfg(message.chat.id); text = message.text or ''
    if c.get('anti_link') and re.search(r'(https?://|www\.|t\.me/|telegram\.me/)', text, re.I):
        try: bot.delete_message(message.chat.id, message.message_id); bot.send_message(message.chat.id, f'🚫 {esc(message.from_user.first_name)} ارسال لینک در این گروه مجاز نیست.')
        except Exception: log.exception('delete link failed')
        return
    bad = [w for w in c.get('bad_words', []) if w and w.casefold() in text.casefold()]
    if bad:
        try: bot.delete_message(message.chat.id, message.message_id)
        except Exception: log.exception('delete bad word failed')

@app.get('/')
def health(): return {'status':'ok','bot':'MASIH GUARD','version':VERSION}, 200
@app.get('/health')
def health2(): return 'OK', 200

def run_web():
    app.run(host='0.0.0.0', port=PORT, debug=False, use_reloader=False)

def run_bot():
    while True:
        try:
            log.info('Starting %s %s', BOT_NAME, VERSION)
            try: bot.remove_webhook()
            except Exception: log.exception('remove_webhook failed')
            me = bot.get_me()
            log.info('Connected to Telegram as @%s', me.username or me.first_name)
            bot.infinity_polling(skip_pending=True, timeout=30, long_polling_timeout=25, allowed_updates=['message','callback_query'])
        except Exception:
            log.exception('Polling failed; retrying in 5 seconds')
            time.sleep(5)

if __name__ == '__main__':
    threading.Thread(target=run_web, daemon=True).start()
    run_bot()
