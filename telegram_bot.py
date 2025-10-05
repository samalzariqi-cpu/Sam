# -*- coding: utf-8 -*-

import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# تفعيل تسجيل الأخطاء
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# تعريف دالة الأمر /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """إرسال رسالة عند إرسال الأمر /start."""
    user = update.effective_user
    await update.message.reply_html(
        rf"أهلاً بك {user.mention_html()}!",
    )

def main() -> None:
    """تشغيل البوت."""
    # إنشاء التطبيق وتمرير توكن البوت الخاص بك
    # استبدل "YOUR_BOT_TOKEN" بالتوكن الحقيقي الذي حصلت عليه من BotFather
    application = Application.builder().token("YOUR_BOT_TOKEN").build()

    # تسجيل معالج الأمر /start
    application.add_handler(CommandHandler("start", start))

    # بدء تشغيل البوت
    application.run_polling()

if __name__ == "__main__":
    main()