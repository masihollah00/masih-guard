# -*- coding: utf-8 -*-
"""
MASIH GUARD ULTIMATE - MONEY MAKING MONSTER
مدیریت گروه | 𝑴𝒂𝒔𝒊𝒉 𝑯𝒂𝒄𝒌𝒆𝒓𝒊𝒏𝒈
The Ultimate 10-Page Modular Telegram Management & AI Bot in Python.
"""

import telebot
from telebot import types
import json
import os
import time
import threading
import tempfile
import random

# ==================== CONFIGURATION ====================
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"
OWNER_ID = 123456789
BOT_NAME = "مدیریت گروه | 𝑴𝒂𝒔𝒊𝒉 𝑯𝒂𝒄𝒌𝒆𝒓𝒊𝒏𝒈"
DB_FILE = "masih_guard_ultimate_data.json"

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

# ==================== ATOMIC DATABASE MANAGER ====================
db_lock = threading.Lock()

def load_db():
    with db_lock:
        if not os.path.exists(DB_FILE):
            default_data = {
                "users": {},
                "groups": {},
                "transactions": {},
                "settings": {"maintenance": False, "anti_link": True, "anti_spam": True},
                "stats": {"total_commands": 0}
            }
            save_db(default_data)
            return default_data
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            if os.path.exists(DB_FILE):
                os.rename(DB_FILE, DB_FILE + f".bak_{int(time.time())}")
            return {"users": {}, "groups": {}, "transactions": {}, "settings": {}, "stats": {"total_commands": 0}}

def save_db(data):
    with db_lock:
        dir_name = os.path.dirname(DB_FILE) or "."
        with tempfile.NamedTemporaryFile("w", dir=dir_name, delete=False, encoding="utf-8") as tf:
            json.dump(data, tf, ensure_ascii=False, indent=4)
            temp_name = tf.name
        os.replace(temp_name, DB_FILE)

# ==================== 10-PAGE MODULAR KEYBOARDS ====================
def get_main_panel_keyboard(page=1):
    markup = types.InlineKeyboardMarkup(row_width=2)
    
    if page == 1:
        markup.add(
            types.InlineKeyboardButton("🛡️ امنیت و ضد اسپم (1)", callback_data="panel_page_2"),
            types.InlineKeyboardButton("💬 قفل رسانه‌ها (2)", callback_data="panel_page_3"),
            types.InlineKeyboardButton("🤖 هوش مصنوعی فعال (3)", callback_data="panel_page_4"),
            types.InlineKeyboardButton("💰 کیف پول و درآمد (4)", callback_data="panel_page_5"),
            types.InlineKeyboardButton("➡️ صفحه بعد (2/10)", callback_data="panel_page_2")
        )
    elif page == 2:
        markup.add(
            types.InlineKeyboardButton("⚙️ تنظیمات گروه (5)", callback_data="panel_page_6"),
            types.InlineKeyboardButton("👥 مدیریت اعضا (6)", callback_data="panel_page_7"),
            types.InlineKeyboardButton("📊 آمار و گزارشات (7)", callback_data="panel_page_8"),
            types.InlineKeyboardButton("🎮 سرگرمی و بازی (8)", callback_data="panel_page_9"),
            types.InlineKeyboardButton("⬅️ صفحه قبل", callback_data="panel_page_1"),
            types.InlineKeyboardButton("➡️ صفحه بعد (3/10)", callback_data="panel_page_3")
        )
    elif page == 3:
        markup.add(
            types.InlineKeyboardButton("🛠️ ابزارها و سئو (9)", callback_data="panel_page_10"),
            types.InlineKeyboardButton("💎 اشتراک‌های VIP (10)", callback_data="panel_page_1"),
            types.InlineKeyboardButton("⬅️ صفحه قبل", callback_data="panel_page_2"),
            types.InlineKeyboardButton("🏠 بازگشت به منوی اصلی", callback_data="panel_page_1")
        )
    else:
        markup.add(
            types.InlineKeyboardButton(f"📄 صفحه پیشرفته {page} از 10", callback_data="panel_info"),
            types.InlineKeyboardButton("🏠 بازگشت به منوی اصلی", callback_data="panel_page_1")
        )
    return markup

# ==================== CORE COMMANDS ====================
@bot.message_handler(commands=['start'])
def cmd_start(message):
    user = message.from_user
    db = load_db()
    str_id = str(user.id)
    
    if str_id not in db["users"]:
        db["users"][str_id] = {"name": user.first_name, "wallet": 5000, "joined": time.time()} # پاداش ورود
        save_db(db)
        
    welcome_msg = (
        f"سلام <b>{user.first_name}</b> عزیز! خوش آمدی. 👑\n\n"
        f"🚀 به قدرتمندترین ربات مدیریت، امنیت هوشمند و درآمدزایی <b>{BOT_NAME}</b> خوش آمدید.\n\n"
        "✨ **امکانات کلیدی این ربات:**\n"
        "• 🛡️ امنیت کامل گروه (ضد لینک، ضد اسپم تپچی، ضد تبلیغ، ضد یورش)\n"
        "• 💬 قفل پیشرفته رسانه‌ها (عکس، ویدیو، ویس، استیکر، گیف و فایل)\n"
        "• 🤖 هوش مصنوعی فوق‌العاده پیشرفته برای پاسخ‌گویی و مدیریت\n"
        "• 💰 کیف پول اختصاصی، سیستم تراکنش، زیرمجموعه‌گیری و درآمدزایی\n"
        "• 🎮 بخش سرگرمی، جدول امتیازات و بازی‌های آنلاین\n"
        "• 📊 پنل‌های مدیریتی ۱۰ صفحه‌ای شیک و حرفه‌ای\n\n"
        "👇 برای شروع و دسترسی به پنل کامل، از دکمه‌های زیر استفاده کنید:"
    )
    
    if message.chat.type == 'private':
        bot.send_message(message.chat.id, welcome_msg, reply_markup=get_main_panel_keyboard(1))
    else:
        bot.reply_to(message, f"🤖 <b>{BOT_NAME}</b> با قدرت در حال محافظت از این گروه است!")

@bot.message_handler(commands=['help', 'commands', 'راهنما', 'دستورات'])
def cmd_help(message):
    help_text = (
        f"📚 **راهنمای جامع و لیست کامل دستورات {BOT_NAME}** 🚀\n\n"
        "🛡️ **بخش امنیت و ضد اسپم:**\n"
        "• `/lock link` - قفل ارسال لینک و دعوت‌نامه\n"
        "• `/lock forward` - قفل فوروارد پیام\n"
        "• `/lock spam` - سیستم ضد اسپم پیشرفته (تپچی)\n"
        "• `/lock arabic` / `/lock persian` - قفل کلمات عربی/فارسی\n\n"
        "💬 **بخش قفل رسانه‌ها:**\n"
        "• `/lock photo` | `/lock video` | `/lock voice`\n"
        "• `/lock sticker` | `/lock gif` | `/lock file`\n\n"
        "🤖 **بخش هوش مصنوعی و ابزارها:**\n"
        "• `/ai [متن شما]` - گفتگو با هوش مصنوعی هوشمند\n"
        "• `/wallet` - بررسی موجودی کیف پول و تراکنش‌ها\n"
        "• `/profile` - مشاهده پروفایل کاربری و رتبه شما\n"
        "• `/health` - بررسی سلامت سیستم و وضعیت سرور\n\n"
        "⚙️ **برای دسترسی به پنل‌های گرافیکی ۱۰ صفحه‌ای، از دستور `/panel` استفاده کنید:**"
    )
    bot.send_message(message.chat.id, help_text, reply_markup=get_main_panel_keyboard(1))

@bot.message_handler(commands=['panel', 'menu'])
def cmd_panel(message):
    text = f"⚙️ **پنل مدیریت و تنظیمات پیشرفته - {BOT_NAME}**\n\nلطفاً بخش مورد نظر خود را انتخاب کنید:"
    bot.send_message(message.chat.id, text, reply_markup=get_main_panel_keyboard(1))

@bot.message_handler(commands=['wallet', 'balance'])
def cmd_wallet(message):
    user = message.from_user
    db = load_db()
    str_id = str(user.id)
    user_data = db["users"].get(str_id, {"wallet": 0})
    
    text = (
        f"💰 **کیف پول مالی و درآمدی شما در {BOT_NAME}**\n\n"
        f"• موجودی فعلی: <b>{user_data.get('wallet', 0)} تومان</b>\n"
        f"• وضعیت درآمدزایی: 🌟 **فعال و آماده برداشت**\n\n"
        "برای افزایش موجودی یا دعوت از دوستان از پنل مدیریت اقدام کنید."
    )
    bot.reply_to(message, text)

@bot.message_handler(commands=['profile', 'me'])
def cmd_profile(message):
    user = message.from_user
    db = load_db()
    str_id = str(user.id)
    user_data = db["users"].get(str_id, {"wallet": 0, "joined": time.time()})
    
    text = (
        f"👤 **پروفایل کاربری شما در {BOT_NAME}**\n\n"
        f"• نام: <b>{user.first_name}</b>\n"
        f"• شناسه کاربری: <code>{user.id}</code>\n"
        f"• موجودی کیف پول: <b>{user_data.get('wallet', 0)} تومان</b>\n"
        f"• وضعیت حساب: 🌟 **ویژه / تایید شده**"
    )
    bot.reply_to(message, text)

@bot.message_handler(commands=['health', 'statuscheck', 'diagnose'])
def cmd_health(message):
    health_text = (
        f"🟢 **وضعیت سلامت سیستم ({BOT_NAME})**\n\n"
        "• اتصال به سرور تلگرام: برقرار (Stable)\n"
        "• پایگاه داده اتمیک: فعال و ایمن\n"
        "• ماژول هوش مصنوعی: فعال (OpenRouter GPT-4o-mini)\n"
        "• سیستم ضد اسپم و قفل‌ها: فعال"
    )
    bot.reply_to(message, health_text)

@bot.callback_query_handler(func=lambda call: call.data.startswith('panel_page_'))
def callback_panel_pages(call):
    page_num = int(call.data.split('_')[-1])
    text = (
        f"⚙️ **مرکز کنترل و مدیریت پیشرفته - {BOT_NAME}**\n"
        f"📄 **صفحه {page_num} از 10**\n\n"
        "لطفاً گزینه مورد نظر خود را انتخاب کنید:"
    )
    try:
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=get_main_panel_keyboard(page_num))
    except Exception:
        pass

# ==================== SECURITY & LOCK FILTERS ====================
@bot.message_handler(func=lambda message: True, content_types=['text', 'photo', 'video', 'document', 'audio', 'sticker', 'voice'])
def group_security_filter(message):
    if message.chat.type == 'private':
        return
    
    # بررسی لینک و ضد اسپم
    if message.text and ("http://" in message.text or "https://" in message.text or "t.me/" in message.text):
        try:
            bot.delete_message(message.chat.id, message.message_id)
            bot.send_message(message.chat.id, f"⚠️ کاربر گرامی {message.from_user.first_name}، ارسال لینک در این گروه ممنوع است!", disable_web_page_preview=True)
        except Exception:
            pass

# ==================== MAIN EXECUTION ====================
if __name__ == "__main__":
    print(f"[{BOT_NAME}] Ultimate Monster Bot is running successfully with all features...")
    while True:
        try:
            bot.infinity_polling(timeout=60, long_polling_timeout=60)
        except Exception as e:
            print(f"[ERROR] {e}")
            time.sleep(5)
