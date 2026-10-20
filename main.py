import os
import time
import logging
import telebot
from telebot import types, apihelper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s"
)
logger = logging.getLogger("MASIH_GUARD")

TOKEN = os.getenv("BOT_TOKEN", "").strip()

if not TOKEN:
    raise RuntimeError(
        "BOT_TOKEN is missing. Set it in FadeHost Environment."
    )

# مدیریت اتصال و بازسازی نشست‌های قدیمی
apihelper.SESSION_TIME_TO_LIVE = 300
apihelper.RETRY_ON_ERROR = True
apihelper.MAX_RETRIES = 3
apihelper.RETRY_TIMEOUT = 2

bot = telebot.TeleBot(TOKEN, threaded=False)


def make_panel():
    keyboard = types.InlineKeyboardMarkup(row_width=2)

    keyboard.add(
        types.InlineKeyboardButton(
            "🔴 مدیریت", callback_data="manage"
        ),
        types.InlineKeyboardButton(
            "🟠 امنیت", callback_data="security"
        ),
        types.InlineKeyboardButton(
            "🟡 قوانین", callback_data="rules"
        ),
        types.InlineKeyboardButton(
            "🟢 راهنما", callback_data="help"
        ),
        types.InlineKeyboardButton(
            "🔵 وضعیت", callback_data="status"
        ),
        types.InlineKeyboardButton(
            "🟣 سازنده", callback_data="owner"
        ),
        types.InlineKeyboardButton(
            "🌈 پنل هفت‌رنگ", callback_data="rainbow"
        )
    )
    return keyboard


@bot.message_handler(commands=["start", "panel"])
def start(message):
    bot.send_message(
        message.chat.id,
        "🌈🛡️ به MASIH GUARD خوش آمدی!\n\n"
        "از دکمه‌های رنگارنگ زیر استفاده کن.",
        reply_markup=make_panel()
    )


@bot.callback_query_handler(func=lambda call: True)
def handle_buttons(call):
    answers = {
        "manage": "🔴 بخش مدیریت در نسخه‌های بعدی تکمیل می‌شود.",
        "security": "🟠 بخش امنیت گروه انتخاب شد.",
        "rules": "🟡 بخش قوانین انتخاب شد.",
        "help": "🟢 برای نمایش پنل دستور /panel را بفرست.",
        "status": "🔵 ربات در حال پاسخ‌گویی به این درخواست است.",
        "owner": "🟣 سازنده: Masih Hackring",
        "rainbow": "🌈 MASIH GUARD | پنل هفت‌رنگ"
    }

    try:
        bot.answer_callback_query(call.id)
        bot.send_message(
            call.message.chat.id,
            answers.get(call.data, "این گزینه شناخته نشد.")
        )
    except Exception:
        logger.exception("Button handler failed")


def main():
    logger.info("Starting MASIH GUARD")

    while True:
        try:
            bot.infinity_polling(
                timeout=30,
                long_polling_timeout=20,
                skip_pending=False
            )
        except KeyboardInterrupt:
            logger.info("Bot stopped manually")
            break
        except Exception:
            logger.exception("Polling failed; retrying in 5 seconds")
            time.sleep(5)


if __name__ == "__main__":
    main()
