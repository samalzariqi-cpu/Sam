import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes, PreCheckoutQueryHandler, ConversationHandler
from datetime import datetime, timedelta
import sqlite3
import random
import re

# إعداد التسجيل
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# معلومات البوت
TOKEN = '7606432428:AAFvvtU6WjmaByateXKb3QQz-vFYbsXZ4lE'
ADMIN_ID = 1058616316

# حالات المحادثة
WAITING_TRANSFER_AMOUNT, WAITING_TRANSFER_ID, WAITING_PRODUCT_NAME, WAITING_PRODUCT_PRICE, WAITING_PRODUCT_CONTENT, WAITING_BROADCAST, WAITING_CHANNEL, WAITING_GIFT_CODE_POINTS, WAITING_GIFT_CODE_USES, WAITING_STARS_AMOUNT = range(10)

# إعداد قاعدة البيانات
def init_db():
    conn = sqlite3.connect('points_bot.db')
    c = conn.cursor()
    
    # جدول المستخدمين
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id INTEGER PRIMARY KEY, username TEXT, points INTEGER DEFAULT 0, 
                  referrer_id INTEGER, join_date TEXT, last_gift_date TEXT)''')
    
    # جدول المنتجات
    c.execute('''CREATE TABLE IF NOT EXISTS products
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, price INTEGER, 
                  content_type TEXT, content TEXT)''')
    
    # جدول الإعدادات
    c.execute('''CREATE TABLE IF NOT EXISTS settings
                 (key TEXT PRIMARY KEY, value TEXT)''')
    
    # جدول القنوات الإجبارية
    c.execute('''CREATE TABLE IF NOT EXISTS channels
                 (channel_id TEXT PRIMARY KEY, channel_username TEXT)''')
    
    # جدول أكواد الهدايا
    c.execute('''CREATE TABLE IF NOT EXISTS gift_codes
                 (code TEXT PRIMARY KEY, points INTEGER, max_uses INTEGER, 
                  used_count INTEGER DEFAULT 0)''')
    
    # جدول استخدامات الأكواد
    c.execute('''CREATE TABLE IF NOT EXISTS code_users
                 (code TEXT, user_id INTEGER, PRIMARY KEY (code, user_id))''')
    
    # جدول سجل المعاملات
    c.execute('''CREATE TABLE IF NOT EXISTS transactions
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, 
                  type TEXT, amount INTEGER, description TEXT, date TEXT)''')
    
    # جدول طلبات الاسترداد
    c.execute('''CREATE TABLE IF NOT EXISTS refund_requests
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                  user_id INTEGER, 
                  charge_id TEXT, 
                  created_at TEXT)''')
    
    # الإعدادات الافتراضية
    default_settings = {
        'welcome_message': '👋 مرحباً بك في بوت تجميع النقاط!\n\n💎 اجمع النقاط واستبدلها بمنتجات رائعة',
        'referral_points': '1',
        'transfer_fee': '10',
        'daily_gift_points': '1',
        'daily_gift_mode': 'fixed',
        'daily_gift_min': '0',
        'daily_gift_max': '100',
        'stars_ratio': '3',
        'bot_status': 'active'
    }
    
    for key, value in default_settings.items():
        c.execute('INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)', (key, value))
    
    conn.commit()
    conn.close()

# دوال قاعدة البيانات
def get_setting(key):
    conn = sqlite3.connect('points_bot.db')
    c = conn.cursor()
    c.execute('SELECT value FROM settings WHERE key = ?', (key,))
    result = c.fetchone()
    conn.close()
    return result[0] if result else None

def set_setting(key, value):
    conn = sqlite3.connect('points_bot.db')
    c = conn.cursor()
    c.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', (key, value))
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = sqlite3.connect('points_bot.db')
    c = conn.cursor()
    c.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    user = c.fetchone()
    conn.close()
    return user

def add_user(user_id, username, referrer_id=None):
    conn = sqlite3.connect('points_bot.db')
    c = conn.cursor()
    join_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    c.execute('INSERT OR IGNORE INTO users (user_id, username, referrer_id, join_date) VALUES (?, ?, ?, ?)',
              (user_id, username, referrer_id, join_date))
    conn.commit()
    conn.close()

def update_points(user_id, points):
    conn = sqlite3.connect('points_bot.db')
    c = conn.cursor()
    c.execute('UPDATE users SET points = points + ? WHERE user_id = ?', (points, user_id))
    conn.commit()
    conn.close()

def add_transaction(user_id, trans_type, amount, description):
    conn = sqlite3.connect('points_bot.db')
    c = conn.cursor()
    date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    c.execute('INSERT INTO transactions (user_id, type, amount, description, date) VALUES (?, ?, ?, ?, ?)',
              (user_id, trans_type, amount, description, date))
    conn.commit()
    conn.close()

def get_products():
    conn = sqlite3.connect('points_bot.db')
    c = conn.cursor()
    c.execute('SELECT * FROM products ORDER BY price')
    products = c.fetchall()
    conn.close()
    return products

def add_product(name, price, content_type, content):
    conn = sqlite3.connect('points_bot.db')
    c = conn.cursor()
    c.execute('INSERT INTO products (name, price, content_type, content) VALUES (?, ?, ?, ?)',
              (name, price, content_type, content))
    conn.commit()
    conn.close()

def delete_product(product_id):
    conn = sqlite3.connect('points_bot.db')
    c = conn.cursor()
    c.execute('DELETE FROM products WHERE id = ?', (product_id,))
    conn.commit()
    conn.close()

def get_channels():
    conn = sqlite3.connect('points_bot.db')
    c = conn.cursor()
    c.execute('SELECT * FROM channels')
    channels = c.fetchall()
    conn.close()
    return channels

def add_channel(channel_id, channel_username):
    conn = sqlite3.connect('points_bot.db')
    c = conn.cursor()
    c.execute('INSERT OR REPLACE INTO channels (channel_id, channel_username) VALUES (?, ?)',
              (channel_id, channel_username))
    conn.commit()
    conn.close()

def remove_channel(channel_id):
    conn = sqlite3.connect('points_bot.db')
    c = conn.cursor()
    c.execute('DELETE FROM channels WHERE channel_id = ?', (channel_id,))
    conn.commit()
    conn.close()

# دالة التحقق من الاشتراك
async def check_subscription(user_id, context):
    channels = get_channels()
    if not channels:
        return True
    
    for channel in channels:
        try:
            member = await context.bot.get_chat_member(channel[0], user_id)
            if member.status in ['left', 'kicked']:
                return False
        except:
            pass
    return True

# دالة حساب الهدية اليومية
def calculate_daily_gift():
    mode = get_setting('daily_gift_mode')
    if mode == 'fixed':
        return int(get_setting('daily_gift_points'))
    else:
        min_points = int(get_setting('daily_gift_min'))
        max_points = int(get_setting('daily_gift_max'))
        
        # نظام الحظ
        rand = random.random()
        if rand < 0.80:
            return random.randint(min(min_points, 10), min(10, max_points))
        elif rand < 0.95:
            return random.randint(max(min_points, 11), min(20, max_points))
        elif rand < 0.98:
            return random.randint(max(min_points, 21), min(30, max_points))
        else:
            return random.randint(max(min_points, 31), max_points)

# الأزرار الرئيسية
def main_keyboard(user_id=None):
    keyboard = [
        [InlineKeyboardButton("🔥 المتجر - العروض 🔥", callback_data='shop')],
        [InlineKeyboardButton("💰 رصيدي", callback_data='my_points'),
         InlineKeyboardButton("🎁 هدية يومية", callback_data='daily_gift')],
        [InlineKeyboardButton("💸 تحويل نقاط", callback_data='transfer'),
         InlineKeyboardButton("⭐ شراء نقاط", callback_data='buy_stars')],
        [InlineKeyboardButton("👥 دعوة أصدقاء", callback_data='referral'),
         InlineKeyboardButton("📊 سجل المعاملات", callback_data='transactions')]
    ]
    
    if user_id == ADMIN_ID:
        keyboard.append([InlineKeyboardButton("🎛️ لوحة التحكم", callback_data='admin_panel')])
    
    return InlineKeyboardMarkup(keyboard)

def admin_keyboard():
    keyboard = [
        [InlineKeyboardButton("📊 الإحصائيات", callback_data='admin_stats')],
        [InlineKeyboardButton("⚙️ الإعدادات", callback_data='admin_settings')],
        [InlineKeyboardButton("➕ إضافة منتج", callback_data='add_product')],
        [InlineKeyboardButton("🗑️ حذف منتج", callback_data='delete_product')],
        [InlineKeyboardButton("📢 إذاعة", callback_data='broadcast')],
        [InlineKeyboardButton("📺 إدارة القنوات", callback_data='manage_channels')],
        [InlineKeyboardButton("🎫 إنشاء كود هدية", callback_data='create_gift_code')],
        [InlineKeyboardButton("🔄 حالة البوت", callback_data='toggle_bot_status')],
        [InlineKeyboardButton("🔙 رجوع", callback_data='back_to_main')]
    ]
    return InlineKeyboardMarkup(keyboard)

# أمر البدء
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    username = user.username or user.first_name
    
    bot_status = get_setting('bot_status')
    
    referrer_id = None
    gift_code = None
    
    if context.args:
        arg = context.args[0]
        if arg.startswith('ref'):
            try:
                referrer_id = int(arg[3:])
            except:
                pass
        elif arg.startswith('gift'):
            gift_code = arg[4:]
    
    existing_user = get_user(user_id)
    
    if not existing_user:
        add_user(user_id, username, referrer_id)
        
        if referrer_id and referrer_id != user_id:
            is_subscribed = await check_subscription(user_id, context)
            if is_subscribed:
                referral_points = int(get_setting('referral_points'))
                update_points(referrer_id, referral_points)
                add_transaction(referrer_id, 'referral', referral_points, f'دعوة {username}')
                try:
                    await context.bot.send_message(
                        referrer_id,
                        f"🎉 تهانينا! حصلت على {referral_points} نقطة من دعوة {username}"
                    )
                except:
                    pass
    
    if gift_code:
        conn = sqlite3.connect('points_bot.db')
        c = conn.cursor()
        
        c.execute('SELECT * FROM gift_codes WHERE code = ?', (gift_code,))
        code_data = c.fetchone()
        
        if code_data and code_data[3] < code_data[2]:
            c.execute('SELECT * FROM code_users WHERE code = ? AND user_id = ?', (gift_code, user_id))
            used_before = c.fetchone()
            
            if not used_before:
                update_points(user_id, code_data[1])
                add_transaction(user_id, 'gift_code', code_data[1], f'كود هدية: {gift_code}')
                
                c.execute('UPDATE gift_codes SET used_count = used_count + 1 WHERE code = ?', (gift_code,))
                c.execute('INSERT INTO code_users (code, user_id) VALUES (?, ?)', (gift_code, user_id))
                conn.commit()
                
                await update.message.reply_text(
                    f"🎁 تهانينا! حصلت على {code_data[1]} نقطة من كود الهدية!"
                )
            else:
                await update.message.reply_text("⚠️ لقد استخدمت هذا الكود من قبل!")
        elif code_data:
            await update.message.reply_text("⚠️ هذا الكود انتهى!")
        else:
            await update.message.reply_text("❌ كود غير صحيح!")
        
        conn.close()
    
    if not await check_subscription(user_id, context):
        channels = get_channels()
        keyboard = []
        for channel in channels:
            keyboard.append([InlineKeyboardButton(f"📢 اشترك في القناة", url=f"https://t.me/{channel[1]}")])
        keyboard.append([InlineKeyboardButton("✅ تحقق من الاشتراك", callback_data='check_subscription')])
        
        await update.message.reply_text(
            "⚠️ يجب عليك الاشتراك في القنوات التالية أولاً:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    if bot_status == 'maintenance' and user_id != ADMIN_ID:
        await update.message.reply_text(
            "🔧 البوت في وضع الصيانة حالياً\n\n"
            "سوف يتم إخبارك عند انتهاء الصيانة. شكراً لصبرك! 🙏"
        )
        return
    
    welcome_message = get_setting('welcome_message')
    await update.message.reply_text(welcome_message, reply_markup=main_keyboard(user_id))

# معالجة الأزرار
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    bot_status = get_setting('bot_status')
    
    if user_id != ADMIN_ID and bot_status == 'maintenance':
        if query.data != 'check_subscription':
            await query.message.reply_text(
                "🔧 البوت في وضع الصيانة حالياً\n\n"
                "سوف يتم إخبارك عند انتهاء الصيانة. شكراً لصبرك! 🙏"
            )
            return
    
    if query.data == 'my_points':
        user = get_user(user_id)
        points = user[2] if user else 0
        username = query.from_user.username or query.from_user.first_name
        
        conn = sqlite3.connect('points_bot.db')
        c = conn.cursor()
        c.execute('SELECT COUNT(*) FROM users WHERE referrer_id = ?', (user_id,))
        referrals = c.fetchone()[0]
        conn.close()
        
        await query.edit_message_text(
            f"👤 المستخدم: {username}\n"
            f"🆔 ID: `{user_id}`\n"
            f"💰 رصيدك الحالي: {points} نقطة\n"
            f"👥 عدد دعواتك: {referrals}",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data='back_to_main')]])
        )
    
    elif query.data == 'daily_gift':
        user = get_user(user_id)
        if not user:
            await query.message.reply_text("❌ حدث خطأ!")
            return
        
        last_gift = user[5]
        today = datetime.now().strftime('%Y-%m-%d')
        
        if last_gift == today:
            await query.answer("⚠️ لقد استلمت هديتك اليوم! ارجع غداً 🎁", show_alert=True)
            return
        
        gift_points = calculate_daily_gift()
        update_points(user_id, gift_points)
        add_transaction(user_id, 'gift', gift_points, 'هدية يومية')
        
        conn = sqlite3.connect('points_bot.db')
        c = conn.cursor()
        c.execute('UPDATE users SET last_gift_date = ? WHERE user_id = ?', (today, user_id))
        conn.commit()
        conn.close()
        
        await query.edit_message_text(
            f"🎁 تهانينا! حصلت على {gift_points} نقطة!\n\n"
            f"💰 رصيدك الجديد: {user[2] + gift_points} نقطة",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data='back_to_main')]])
        )
    
    elif query.data == 'shop' or query.data.startswith('shop_page_'):
        products = get_products()
        if not products:
            await query.edit_message_text(
                "🛒 المتجر فارغ حالياً",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data='back_to_main')]])
            )
            return
        
        user = get_user(user_id)
        user_points = user[2] if user else 0
        
        current_page = 0
        if query.data.startswith('shop_page_'):
            current_page = int(query.data.split('_')[2])
        
        items_per_page = 11
        total_pages = (len(products) - 1) // items_per_page + 1
        
        start_idx = current_page * items_per_page
        end_idx = min(start_idx + items_per_page, len(products))
        page_products = products[start_idx:end_idx]
        
        keyboard = []
        
        keyboard.append([
            InlineKeyboardButton("🔍 بحث", callback_data='search_product'),
            InlineKeyboardButton("💰 حسب نقاطي", callback_data='shop_by_points')
        ])
        
        for product in page_products:
            name = product[1][:25] + ".." if len(product[1]) > 25 else product[1]
            
            keyboard.append([
                InlineKeyboardButton(f"{name}", callback_data=f'buy_{product[0]}'),
                InlineKeyboardButton(f"💵{product[2]}", callback_data=f'buy_{product[0]}')
            ])
        
        nav_buttons = []
        if current_page > 0:
            nav_buttons.append(InlineKeyboardButton("⏮ السابق", callback_data=f'shop_page_{current_page - 1}'))
        if current_page < total_pages - 1:
            nav_buttons.append(InlineKeyboardButton("التالي ⏭", callback_data=f'shop_page_{current_page + 1}'))
        
        if nav_buttons:
            keyboard.append(nav_buttons)
        
        keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data='back_to_main')])
        
        await query.edit_message_text(
            f"🔥 العروض التي يقدمها البوت 🔥\n\n"
            f"━━━━━━━━━━━━━━━\n"
            f"💰 رصيدك: {user_points} نقطة\n"
            f"📦 المنتجات: {len(products)}\n"
            f"📄 الصفحة: {current_page + 1}/{total_pages}\n"
            f"━━━━━━━━━━━━━━━\n\n"
            "- العروض التي يمكنك شرائها -",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    elif query.data == 'search_product':
        context.user_data['state'] = 'search_product'
        await query.edit_message_text(
            "🔍 أرسل اسم المنتج للبحث:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ إلغاء", callback_data='shop')]])
        )
    
    elif query.data == 'transactions':
        conn = sqlite3.connect('points_bot.db')
        c = conn.cursor()
        c.execute('SELECT * FROM transactions WHERE user_id = ? ORDER BY id DESC LIMIT 10', (user_id,))
        transactions = c.fetchall()
        conn.close()
        
        if not transactions:
            await query.edit_message_text(
                "📊 لا توجد معاملات بعد!",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data='back_to_main')]])
            )
            return
        
        text = "📊 آخر 10 معاملات:\n\n"
        for trans in transactions:
            emoji = "➕" if trans[3] > 0 else "➖"
            text += f"{emoji} {abs(trans[3])} نقطة - {trans[4]}\n📅 {trans[5]}\n\n"
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data='back_to_main')]])
        )
    
    elif query.data == 'shop_by_points':
        user = get_user(user_id)
        user_points = user[2] if user else 0
        
        products = get_products()
        affordable = [p for p in products if p[2] <= user_points]
        
        if not affordable:
            await query.answer("❌ لا توجد منتجات يمكنك شراؤها حالياً", show_alert=True)
            return
        
        keyboard = []
        for product in affordable:
            keyboard.append([InlineKeyboardButton(
                f"✅ {product[1]} - {product[2]} نقطة",
                callback_data=f'buy_{product[0]}'
            )])
        keyboard.append([InlineKeyboardButton("🔙 رجوع للمتجر", callback_data='shop')])
        
        await query.edit_message_text(
            f"🛒 المنتجات المتاحة لك\n💰 رصيدك: {user_points} نقطة\n\n"
            f"عدد المنتجات: {len(affordable)}",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    elif query.data.startswith('buy_stars_'):
        if query.data == 'buy_stars_custom':
            context.user_data['state'] = 'buy_stars'
            stars_ratio = int(get_setting('stars_ratio'))
            await query.edit_message_text(
                f"⭐ كل نجمة = {stars_ratio} نقطة\n\n"
                "أرسل عدد النجوم التي تريد شراءها:",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ إلغاء", callback_data='buy_stars')]])
            )
            return WAITING_STARS_AMOUNT
        else:
            stars = int(query.data.split('_')[2])
            stars_ratio = int(get_setting('stars_ratio'))
            points = stars * stars_ratio
            
            try:
                invoice_link = await context.bot.create_invoice_link(
                    title=f"شراء {points} نقطة",
                    description=f"احصل على {points} نقطة مقابل {stars} نجمة",
                    payload=f"stars_{user_id}_{points}",
                    provider_token="",
                    currency="XTR",
                    prices=[LabeledPrice("نقاط", stars)]
                )
                
                await query.edit_message_text(
                    f"⭐ رابط الدفع جاهز!\n\n"
                    f"💫 النجوم: {stars}\n"
                    f"💎 النقاط: {points}\n\n"
                    f"🔗 اضغط على الرابط:\n{invoice_link}",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔙 رجوع للباقات", callback_data='buy_stars')],
                        [InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data='back_to_main')]
                    ])
                )
            except Exception as e:
                await query.answer(f"❌ خطأ: {str(e)}", show_alert=True)
    
    elif query.data.startswith('buy_') and not query.data.startswith('buy_stars'):
        try:
            product_id = int(query.data.split('_')[1])
        except ValueError:
            return
        
        conn = sqlite3.connect('points_bot.db')
        c = conn.cursor()
        c.execute('SELECT * FROM products WHERE id = ?', (product_id,))
        product = c.fetchone()
        conn.close()
        
        if not product:
            await query.answer("❌ المنتج غير موجود!", show_alert=True)
            return
        
        user = get_user(user_id)
        
        keyboard = []
        if user[2] >= product[2]:
            keyboard.append([InlineKeyboardButton("✅ تأكيد الشراء", callback_data=f'confirm_buy_{product_id}')])
        keyboard.append([InlineKeyboardButton("🔙 رجوع للمتجر", callback_data='shop')])
        
        status = "✅ يمكنك الشراء" if user[2] >= product[2] else "❌ رصيدك غير كافي"
        
        await query.edit_message_text(
            f"🛍️ تفاصيل المنتج\n"
            f"━━━━━━━━━━━━━━━\n"
            f"📦 الاسم: {product[1]}\n"
            f"💰 السعر: {product[2]} نقطة\n"
            f"💳 رصيدك: {user[2]} نقطة\n"
            f"━━━━━━━━━━━━━━━\n\n"
            f"{status}",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    elif query.data.startswith('confirm_buy_'):
        product_id = int(query.data.split('_')[2])
        conn = sqlite3.connect('points_bot.db')
        c = conn.cursor()
        c.execute('SELECT * FROM products WHERE id = ?', (product_id,))
        product = c.fetchone()
        conn.close()
        
        if not product:
            await query.answer("❌ المنتج غير موجود!", show_alert=True)
            return
        
        user = get_user(user_id)
        if user[2] < product[2]:
            await query.answer(f"❌ رصيدك غير كافي! تحتاج {product[2]} نقطة", show_alert=True)
            return
        
        update_points(user_id, -product[2])
        add_transaction(user_id, 'purchase', -product[2], f'شراء {product[1]}')
        
        try:
            if product[3] == 'text':
                await context.bot.send_message(user_id, f"✅ تم الشراء بنجاح!\n\n📝 المحتوى:\n{product[4]}")
            elif product[3] == 'photo':
                await context.bot.send_photo(user_id, product[4], caption="✅ تم الشراء بنجاح!")
            elif product[3] == 'file':
                await context.bot.send_document(user_id, product[4], caption="✅ تم الشراء بنجاح!")
        except Exception as e:
            update_points(user_id, product[2])
            await query.answer(f"❌ فشل إرسال المنتج: {str(e)}", show_alert=True)
            return
        
        try:
            buyer = query.from_user
            buyer_username = f"@{buyer.username}" if buyer.username else "لا يوجد"
            buyer_name = buyer.first_name + (" " + buyer.last_name if buyer.last_name else "")
            buyer_link = f"tg://user?id={user_id}"
            
            admin_notification = (
                f"🔔 عملية شراء جديدة!\n\n"
                f"👤 المشتري: {buyer_name}\n"
                f"🆔 ID: `{user_id}`\n"
                f"👁️ الرابط: [فتح الملف الشخصي]({buyer_link})\n"
                f"📱 المعرف: {buyer_username}\n\n"
                f"📦 المنتج: {product[1]}\n"
                f"💰 السعر: {product[2]} نقطة\n\n"
                f"🕐 الوقت: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
            
            await context.bot.send_message(
                ADMIN_ID,
                admin_notification,
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"فشل إرسال إشعار للمشرف: {e}")
        
        await query.edit_message_text(
            f"✅ تم الشراء بنجاح!\n\n"
            f"📦 المنتج: {product[1]}\n"
            f"💰 تم خصم: {product[2]} نقطة\n"
            f"💳 رصيدك الجديد: {user[2] - product[2]} نقطة",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data='back_to_main')]])
        )
        await query.answer("✅ تم الشراء بنجاح!", show_alert=True)
    
    elif query.data == 'transfer':
        context.user_data['state'] = 'transfer_amount'
        await query.edit_message_text(
            "💸 أرسل عدد النقاط التي تريد تحويلها:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ إلغاء", callback_data='cancel')]])
        )
        return WAITING_TRANSFER_AMOUNT
    
    elif query.data == 'buy_stars':
        user = get_user(user_id)
        user_points = user[2] if user else 0
        stars_ratio = int(get_setting('stars_ratio'))
        
        packages = [
            (1, 1 * stars_ratio, "⭐"),
            (5, 5 * stars_ratio, "⭐⭐"),
            (10, 10 * stars_ratio, "⭐⭐⭐"),
            (20, 20 * stars_ratio, "💫"),
            (50, 50 * stars_ratio, "🌟"),
            (100, 100 * stars_ratio, "✨")
        ]
        
        keyboard = []
        for stars, points, emoji in packages:
            keyboard.append([InlineKeyboardButton(
                f"{emoji} {stars} نجمة = {points} نقطة",
                callback_data=f'buystar_{stars}'
            )])
        
        keyboard.append([InlineKeyboardButton("💳 مبلغ مخصص", callback_data='buy_stars_custom')])
        keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data='back_to_main')])
        
        await query.edit_message_text(
            f"⭐ شراء نقاط بالنجوم\n\n"
            f"💰 رصيدك الحالي: {user_points} نقطة\n"
            f"📊 النسبة: كل نجمة = {stars_ratio} نقطة\n\n"
            f"اختر الباقة:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    elif query.data.startswith('buystar_'):
        stars = int(query.data.split('_')[1])
        stars_ratio = int(get_setting('stars_ratio'))
        points = stars * stars_ratio
        
        try:
            invoice_link = await context.bot.create_invoice_link(
                title=f"شراء {points} نقطة",
                description=f"احصل على {points} نقطة مقابل {stars} نجمة",
                payload=f"stars_{user_id}_{points}",
                provider_token="",
                currency="XTR",
                prices=[LabeledPrice("نقاط", stars)]
            )
            
            await query.edit_message_text(
                f"⭐ رابط الدفع جاهز!\n\n"
                f"💫 النجوم: {stars}\n"
                f"💎 النقاط: {points}\n\n"
                f"🔗 اضغط على الرابط:\n{invoice_link}",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 رجوع للباقات", callback_data='buy_stars')],
                    [InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data='back_to_main')]
                ])
            )
        except Exception as e:
            await query.answer(f"❌ خطأ: {str(e)}", show_alert=True)
    
    elif query.data == 'referral':
        bot_username = (await context.bot.get_me()).username
        ref_link = f"https://t.me/{bot_username}?start=ref{user_id}"
        referral_points = get_setting('referral_points')
        
        await query.edit_message_text(
            f"👥 رابط الدعوة الخاص بك:\n\n"
            f"`{ref_link}`\n\n"
            f"🎁 احصل على {referral_points} نقطة عن كل صديق يشترك!",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data='back_to_main')]])
        )
    
    elif query.data == 'admin_panel':
        if user_id != ADMIN_ID:
            await query.answer("❌ غير مصرح لك!", show_alert=True)
            return
        
        await query.edit_message_text(
            "🎛️ لوحة التحكم",
            reply_markup=admin_keyboard()
        )
    
    elif query.data == 'admin_stats':
        if user_id != ADMIN_ID:
            await query.answer("❌ غير مصرح لك!", show_alert=True)
            return
        
        conn = sqlite3.connect('points_bot.db')
        c = conn.cursor()
        c.execute('SELECT COUNT(*) FROM users')
        total_users = c.fetchone()[0]
        c.execute('SELECT SUM(points) FROM users')
        total_points = c.fetchone()[0] or 0
        c.execute('SELECT COUNT(*) FROM products')
        total_products = c.fetchone()[0]
        c.execute('SELECT COUNT(*) FROM channels')
        total_channels = c.fetchone()[0]
        c.execute('SELECT COUNT(*) FROM gift_codes')
        total_codes = c.fetchone()[0]
        conn.close()
        
        bot_status = get_setting('bot_status')
        status_emoji = "✅" if bot_status == 'active' else "🔧"
        
        await query.edit_message_text(
            f"📊 إحصائيات البوت:\n\n"
            f"{status_emoji} الحالة: {'نشط' if bot_status == 'active' else 'صيانة'}\n"
            f"👥 عدد المستخدمين: {total_users}\n"
            f"💎 إجمالي النقاط: {total_points}\n"
            f"🛒 عدد المنتجات: {total_products}\n"
            f"📺 عدد القنوات: {total_channels}\n"
            f"🎫 أكواد الهدايا: {total_codes}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data='admin_panel')]])
        )
    
    elif query.data == 'admin_settings':
        if user_id != ADMIN_ID:
            await query.answer("❌ غير مصرح لك!", show_alert=True)
            return
        
        keyboard = [
            [InlineKeyboardButton("📝 تعديل رسالة الترحيب", callback_data='edit_welcome')],
            [InlineKeyboardButton("🎁 نقاط الإحالة", callback_data='edit_referral_points')],
            [InlineKeyboardButton("💵 رسوم التحويل", callback_data='edit_transfer_fee')],
            [InlineKeyboardButton("🎁 الهدية اليومية", callback_data='edit_daily_gift')],
            [InlineKeyboardButton("⭐ نسبة النجوم", callback_data='edit_stars_ratio')],
            [InlineKeyboardButton("🔙 رجوع", callback_data='admin_panel')]
        ]
        await query.edit_message_text(
            "⚙️ الإعدادات",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    elif query.data == 'edit_daily_gift':
        if user_id != ADMIN_ID:
            await query.answer("❌ غير مصرح لك!", show_alert=True)
            return
        
        mode = get_setting('daily_gift_mode')
        keyboard = [
            [InlineKeyboardButton(f"{'✅' if mode == 'fixed' else '⬜'} ثابتة", callback_data='gift_mode_fixed')],
            [InlineKeyboardButton(f"{'✅' if mode == 'random' else '⬜'} عشوائية", callback_data='gift_mode_random')],
            [InlineKeyboardButton("🔙 رجوع", callback_data='admin_settings')]
        ]
        
        if mode == 'fixed':
            points = get_setting('daily_gift_points')
            text = f"🎁 الهدية اليومية: {points} نقطة (ثابتة)"
        else:
            min_p = get_setting('daily_gift_min')
            max_p = get_setting('daily_gift_max')
            text = f"🎁 الهدية اليومية: من {min_p} إلى {max_p} نقطة (عشوائية)"
        
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    
    elif query.data == 'gift_mode_fixed':
        if user_id != ADMIN_ID:
            return
        set_setting('daily_gift_mode', 'fixed')
        context.user_data['state'] = 'edit_fixed_gift'
        await query.edit_message_text(
            "أرسل عدد النقاط للهدية اليومية:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ إلغاء", callback_data='admin_settings')]])
        )
    
    elif query.data == 'gift_mode_random':
        if user_id != ADMIN_ID:
            return
        set_setting('daily_gift_mode', 'random')
        context.user_data['state'] = 'edit_random_gift_min'
        await query.edit_message_text(
            "أرسل الحد الأدنى للنقاط:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ إلغاء", callback_data='admin_settings')]])
        )
    
    elif query.data == 'toggle_bot_status':
        if user_id != ADMIN_ID:
            await query.answer("❌ غير مصرح لك!", show_alert=True)
            return
        
        current_status = get_setting('bot_status')
        new_status = 'maintenance' if current_status == 'active' else 'active'
        set_setting('bot_status', new_status)
        
        status_text = "🔧 وضع الصيانة" if new_status == 'maintenance' else "✅ البوت نشط"
        status_emoji = "🔧" if new_status == 'maintenance' else "✅"
        
        await query.answer(f"تم التغيير إلى: {status_text}", show_alert=True)
        await query.edit_message_text(
            f"🎛️ لوحة التحكم\n\n{status_emoji} حالة البوت: {status_text}",
            reply_markup=admin_keyboard()
        )
    
    elif query.data == 'add_product':
        if user_id != ADMIN_ID:
            await query.answer("❌ غير مصرح لك!", show_alert=True)
            return
        
        context.user_data['state'] = 'add_product_name'
        await query.edit_message_text(
            "أرسل اسم المنتج:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ إلغاء", callback_data='admin_panel')]])
        )
    
    elif query.data == 'delete_product':
        if user_id != ADMIN_ID:
            await query.answer("❌ غير مصرح لك!", show_alert=True)
            return
        
        products = get_products()
        if not products:
            await query.answer("لا توجد منتجات!", show_alert=True)
            return
        
        keyboard = []
        for product in products:
            keyboard.append([InlineKeyboardButton(
                f"🗑️ {product[1]} - {product[2]} نقطة",
                callback_data=f'delp_{product[0]}'
            )])
        keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data='admin_panel')])
        
        await query.edit_message_text(
            "اختر المنتج للحذف:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    elif query.data.startswith('delp_'):
        if user_id != ADMIN_ID:
            return
        
        product_id = int(query.data.split('_')[1])
        delete_product(product_id)
        await query.answer("✅ تم حذف المنتج!", show_alert=True)
        await query.edit_message_text("🎛️ لوحة التحكم", reply_markup=admin_keyboard())
    
    elif query.data == 'broadcast':
        if user_id != ADMIN_ID:
            await query.answer("❌ غير مصرح لك!", show_alert=True)
            return
        
        context.user_data['state'] = 'broadcast'
        await query.edit_message_text(
            "📢 أرسل الرسالة للإذاعة:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ إلغاء", callback_data='admin_panel')]])
        )
    
    elif query.data == 'manage_channels':
        if user_id != ADMIN_ID:
            await query.answer("❌ غير مصرح لك!", show_alert=True)
            return
        
        keyboard = [
            [InlineKeyboardButton("➕ إضافة قناة", callback_data='add_channel')],
            [InlineKeyboardButton("➖ حذف قناة", callback_data='remove_channel')],
            [InlineKeyboardButton("📋 عرض القنوات", callback_data='list_channels')],
            [InlineKeyboardButton("🔙 رجوع", callback_data='admin_panel')]
        ]
        await query.edit_message_text(
            "📺 إدارة القنوات",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    elif query.data == 'add_channel':
        if user_id != ADMIN_ID:
            return
        
        context.user_data['state'] = 'add_channel'
        await query.edit_message_text(
            "أرسل معرف القناة (مثال: @channel_name):",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ إلغاء", callback_data='manage_channels')]])
        )
    
    elif query.data == 'list_channels':
        if user_id != ADMIN_ID:
            return
        
        channels = get_channels()
        if not channels:
            await query.answer("لا توجد قنوات!", show_alert=True)
            return
        
        text = "📋 القنوات المسجلة:\n\n"
        for channel in channels:
            text += f"• @{channel[1]}\n"
        
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data='manage_channels')]])
        )
    
    elif query.data == 'remove_channel':
        if user_id != ADMIN_ID:
            return
        
        channels = get_channels()
        if not channels:
            await query.answer("لا توجد قنوات!", show_alert=True)
            return
        
        keyboard = []
        for channel in channels:
            keyboard.append([InlineKeyboardButton(
                f"🗑️ @{channel[1]}",
                callback_data=f'delch_{channel[0]}'
            )])
        keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data='manage_channels')])
        
        await query.edit_message_text(
            "اختر القناة للحذف:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    elif query.data.startswith('delch_'):
        if user_id != ADMIN_ID:
            return
        
        channel_id = query.data.split('_', 1)[1]
        remove_channel(channel_id)
        await query.answer("✅ تم حذف القناة!", show_alert=True)
        
        keyboard = [
            [InlineKeyboardButton("➕ إضافة قناة", callback_data='add_channel')],
            [InlineKeyboardButton("➖ حذف قناة", callback_data='remove_channel')],
            [InlineKeyboardButton("📋 عرض القنوات", callback_data='list_channels')],
            [InlineKeyboardButton("🔙 رجوع", callback_data='admin_panel')]
        ]
        await query.edit_message_text(
            "📺 إدارة القنوات",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    elif query.data == 'create_gift_code':
        if user_id != ADMIN_ID:
            await query.answer("❌ غير مصرح لك!", show_alert=True)
            return
        
        context.user_data['state'] = 'gift_code_points'
        await query.edit_message_text(
            "أرسل عدد النقاط في الكود:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ إلغاء", callback_data='admin_panel')]])
        )
    
    elif query.data == 'edit_welcome':
        if user_id != ADMIN_ID:
            return
        
        context.user_data['state'] = 'edit_welcome'
        await query.edit_message_text(
            "أرسل رسالة الترحيب الجديدة:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ إلغاء", callback_data='admin_settings')]])
        )
    
    elif query.data == 'edit_referral_points':
        if user_id != ADMIN_ID:
            return
        
        context.user_data['state'] = 'edit_referral_points'
        current = get_setting('referral_points')
        await query.edit_message_text(
            f"النقاط الحالية: {current}\n\nأرسل عدد النقاط الجديد:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ إلغاء", callback_data='admin_settings')]])
        )
    
    elif query.data == 'edit_transfer_fee':
        if user_id != ADMIN_ID:
            return
        
        context.user_data['state'] = 'edit_transfer_fee'
        current = get_setting('transfer_fee')
        await query.edit_message_text(
            f"الرسوم الحالية: {current}\n\nأرسل رسوم التحويل الجديدة:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ إلغاء", callback_data='admin_settings')]])
        )
    
    elif query.data == 'edit_stars_ratio':
        if user_id != ADMIN_ID:
            return
        
        context.user_data['state'] = 'edit_stars_ratio'
        current = get_setting('stars_ratio')
        await query.edit_message_text(
            f"النسبة الحالية: كل نجمة = {current} نقطة\n\nأرسل النسبة الجديدة:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ إلغاء", callback_data='admin_settings')]])
        )
    
    elif query.data == 'check_subscription':
        if await check_subscription(user_id, context):
            welcome_message = get_setting('welcome_message')
            await query.edit_message_text(welcome_message, reply_markup=main_keyboard(user_id))
        else:
            await query.answer("⚠️ لم تشترك في جميع القنوات بعد!", show_alert=True)
    
    elif query.data == 'back_to_main':
        context.user_data.clear()
        welcome_message = get_setting('welcome_message')
        await query.edit_message_text(welcome_message, reply_markup=main_keyboard(user_id))
    
    elif query.data == 'cancel':
        context.user_data.clear()
        await query.edit_message_text(
            "❌ تم الإلغاء",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data='back_to_main')]])
        )
        return ConversationHandler.END
    
    elif query.data.startswith('refund_'):
        if user_id != ADMIN_ID:
            await query.answer("❌ غير مصرح لك!", show_alert=True)
            return
        
        refund_id = int(query.data.split('_')[1])
        
        conn = sqlite3.connect('points_bot.db')
        c = conn.cursor()
        c.execute('SELECT user_id, charge_id FROM refund_requests WHERE id = ?', (refund_id,))
        refund_data = c.fetchone()
        conn.close()
        
        if not refund_data:
            await query.answer("❌ طلب الاسترداد غير موجود!", show_alert=True)
            return
        
        target_user_id = refund_data[0]
        charge_id = refund_data[1]
        
        await query.answer("⏳ جاري استرداد النجوم...", show_alert=True)
        
        try:
            await context.bot.refund_star_payment(
                user_id=target_user_id,
                telegram_payment_charge_id=charge_id
            )
            
            await query.edit_message_text(
                f"{query.message.text}\n\n"
                f"✅ تم استرداد النجوم بنجاح!\n"
                f"⏰ الوقت: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
            
            try:
                await context.bot.send_message(
                    target_user_id,
                    f"💰 تم إرجاع النجوم إلى حسابك!\n\n"
                    f"🆔 رقم المعاملة:\n`{charge_id}`\n\n"
                    f"شكراً لتعاملك معنا! 💫",
                    parse_mode='Markdown'
                )
            except:
                pass
                
        except Exception as e:
            error_msg = str(e)
            if "CHARGE_ALREADY_REFUNDED" in error_msg:
                await query.answer("⚠️ تم استرداد هذه المعاملة مسبقاً!", show_alert=True)
            else:
                await query.answer(f"❌ فشل الاسترداد: {error_msg}", show_alert=True)

# معالجة الرسائل النصية
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text if update.message.text else None
    user_id = update.effective_user.id
    state = context.user_data.get('state')
    
    if state == 'transfer_amount':
        if not text or not text.isdigit():
            await update.message.reply_text("❌ أرسل رقماً صحيحاً!")
            return WAITING_TRANSFER_AMOUNT
        
        amount = int(text)
        if amount < 1:
            await update.message.reply_text("❌ أقل مبلغ للتحويل هو 1 نقطة!")
            return WAITING_TRANSFER_AMOUNT
        
        user = get_user(user_id)
        transfer_fee = int(get_setting('transfer_fee'))
        total_needed = amount + transfer_fee
        
        if user[2] < total_needed:
            max_transfer = max(0, user[2] - transfer_fee)
            await update.message.reply_text(
                f"❌ رصيدك غير كافي!\n\n"
                f"💰 رصيدك: {user[2]} نقطة\n"
                f"📤 المبلغ المطلوب: {amount} نقطة\n"
                f"💵 العمولة: {transfer_fee} نقطة\n"
                f"💳 الإجمالي: {total_needed} نقطة\n\n"
                f"{'يمكنك تحويل ' + str(max_transfer) + ' نقطة كحد أقصى' if max_transfer > 0 else 'رصيدك غير كافي للتحويل'}",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data='back_to_main')]])
            )
            context.user_data.clear()
            return ConversationHandler.END
        
        context.user_data['transfer_amount'] = amount
        context.user_data['state'] = 'transfer_id'
        await update.message.reply_text(
            f"💸 سيتم تحويل {amount} نقطة\n"
            f"💵 عمولة التحويل: {transfer_fee} نقطة\n"
            f"💳 الإجمالي: {total_needed} نقطة\n\n"
            "أرسل ID المستخدم المستلم:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ إلغاء", callback_data='cancel')]])
        )
        return WAITING_TRANSFER_ID
    
    elif state == 'transfer_id':
        if not text or not text.isdigit():
            await update.message.reply_text("❌ أرسل ID صحيح!")
            return WAITING_TRANSFER_ID
        
        receiver_id = int(text)
        if receiver_id == user_id:
            await update.message.reply_text("❌ لا يمكنك التحويل لنفسك!")
            return WAITING_TRANSFER_ID
        
        receiver = get_user(receiver_id)
        if not receiver:
            await update.message.reply_text("❌ المستخدم غير موجود!")
            return WAITING_TRANSFER_ID
        
        amount = context.user_data['transfer_amount']
        transfer_fee = int(get_setting('transfer_fee'))
        
        update_points(user_id, -(amount + transfer_fee))
        update_points(receiver_id, amount)
        
        add_transaction(user_id, 'transfer_out', -(amount + transfer_fee), f'تحويل إلى {receiver_id}')
        add_transaction(receiver_id, 'transfer_in', amount, f'تحويل من {user_id}')
        
        await update.message.reply_text(
            f"✅ تم التحويل بنجاح!\n\n"
            f"📤 المبلغ المحول: {amount} نقطة\n"
            f"💵 العمولة: {transfer_fee} نقطة",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data='back_to_main')]])
        )
        
        try:
            await context.bot.send_message(
                receiver_id,
                f"💰 استلمت {amount} نقطة من مستخدم {user_id}"
            )
        except:
            pass
        
        context.user_data.clear()
        return ConversationHandler.END
    
    elif state == 'buy_stars':
        if not text or not text.isdigit():
            await update.message.reply_text("❌ أرسل رقماً صحيحاً!")
            return WAITING_STARS_AMOUNT
        
        stars = int(text)
        if stars < 1:
            await update.message.reply_text("❌ أقل عدد نجوم هو 1!")
            return WAITING_STARS_AMOUNT
        
        stars_ratio = int(get_setting('stars_ratio'))
        points = stars * stars_ratio
        
        try:
            invoice_link = await context.bot.create_invoice_link(
                title=f"شراء {points} نقطة",
                description=f"احصل على {points} نقطة مقابل {stars} نجمة",
                payload=f"stars_{user_id}_{points}",
                provider_token="",
                currency="XTR",
                prices=[LabeledPrice("نقاط", stars)]
            )
            
            await update.message.reply_text(
                f"⭐ اضغط على الرابط للدفع:\n\n"
                f"{invoice_link}\n\n"
                f"💎 ستحصل على {points} نقطة",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data='back_to_main')]])
            )
        except Exception as e:
            await update.message.reply_text(f"❌ حدث خطأ: {str(e)}")
        
        context.user_data.clear()
        return ConversationHandler.END
    
    elif state == 'add_product_name':
        if user_id != ADMIN_ID or not text:
            return
        
        context.user_data['product_name'] = text
        context.user_data['state'] = 'add_product_price'
        await update.message.reply_text(
            "أرسل سعر المنتج (بالنقاط):",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ إلغاء", callback_data='admin_panel')]])
        )
    
    elif state == 'add_product_price':
        if user_id != ADMIN_ID:
            return
        
        if not text or not text.isdigit():
            await update.message.reply_text("❌ أرسل رقماً صحيحاً!")
            return
        
        context.user_data['product_price'] = int(text)
        context.user_data['state'] = 'add_product_content'
        await update.message.reply_text(
            "أرسل محتوى المنتج (نص، صورة، أو ملف):",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ إلغاء", callback_data='admin_panel')]])
        )
    
    elif state == 'add_product_content':
        if user_id != ADMIN_ID:
            return
        
        name = context.user_data.get('product_name')
        price = context.user_data.get('product_price')
        
        if not name or not price:
            await update.message.reply_text("❌ حدث خطأ! ابدأ من جديد.")
            context.user_data.clear()
            return
        
        if update.message.text:
            add_product(name, price, 'text', text)
            await update.message.reply_text(
                "✅ تم إضافة المنتج بنجاح!",
                reply_markup=admin_keyboard()
            )
        elif update.message.photo:
            file_id = update.message.photo[-1].file_id
            add_product(name, price, 'photo', file_id)
            await update.message.reply_text(
                "✅ تم إضافة المنتج (صورة) بنجاح!",
                reply_markup=admin_keyboard()
            )
        elif update.message.document:
            file_id = update.message.document.file_id
            add_product(name, price, 'file', file_id)
            await update.message.reply_text(
                "✅ تم إضافة المنتج (ملف) بنجاح!",
                reply_markup=admin_keyboard()
            )
        else:
            await update.message.reply_text(
                "❌ نوع غير مدعوم! أرسل نص، صورة، أو ملف.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ إلغاء", callback_data='admin_panel')]])
            )
            return
        
        context.user_data.clear()
    
    elif state == 'broadcast':
        if user_id != ADMIN_ID or not text:
            return
        
        conn = sqlite3.connect('points_bot.db')
        c = conn.cursor()
        c.execute('SELECT user_id FROM users')
        users = c.fetchall()
        conn.close()
        
        success = 0
        failed = 0
        
        for user in users:
            try:
                await context.bot.send_message(user[0], text)
                success += 1
            except:
                failed += 1
        
        await update.message.reply_text(
            f"✅ تمت الإذاعة!\n\n"
            f"نجح: {success}\n"
            f"فشل: {failed}",
            reply_markup=admin_keyboard()
        )
        context.user_data.clear()
    
    elif state == 'add_channel':
        if user_id != ADMIN_ID or not text:
            return
        
        if not text.startswith('@'):
            await update.message.reply_text("❌ المعرف يجب أن يبدأ بـ @")
            return
        
        channel_username = text[1:]
        try:
            chat = await context.bot.get_chat(f"@{channel_username}")
            add_channel(str(chat.id), channel_username)
            await update.message.reply_text(
                f"✅ تم إضافة القناة @{channel_username}",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data='manage_channels')]])
            )
        except Exception as e:
            await update.message.reply_text(f"❌ خطأ: {str(e)}")
        
        context.user_data.clear()
    
    elif state == 'gift_code_points':
        if user_id != ADMIN_ID:
            return
        
        if not text or not text.isdigit():
            await update.message.reply_text("❌ أرسل رقماً صحيحاً!")
            return
        
        context.user_data['gift_points'] = int(text)
        context.user_data['state'] = 'gift_code_uses'
        await update.message.reply_text(
            "أرسل عدد مرات الاستخدام:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ إلغاء", callback_data='admin_panel')]])
        )
    
    elif state == 'gift_code_uses':
        if user_id != ADMIN_ID:
            return
        
        if not text or not text.isdigit():
            await update.message.reply_text("❌ أرسل رقماً صحيحاً!")
            return
        
        points = context.user_data['gift_points']
        max_uses = int(text)
        
        code = ''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789', k=8))
        
        conn = sqlite3.connect('points_bot.db')
        c = conn.cursor()
        c.execute('INSERT INTO gift_codes (code, points, max_uses) VALUES (?, ?, ?)',
                  (code, points, max_uses))
        conn.commit()
        conn.close()
        
        bot_username = (await context.bot.get_me()).username
        link = f"https://t.me/{bot_username}?start=gift{code}"
        
        await update.message.reply_text(
            f"✅ تم إنشاء الكود!\n\n"
            f"🎁 الكود: `{code}`\n"
            f"💎 النقاط: {points}\n"
            f"👥 الاستخدامات: {max_uses}\n\n"
            f"🔗 الرابط:\n`{link}`",
            parse_mode='Markdown',
            reply_markup=admin_keyboard()
        )
        context.user_data.clear()
    
    elif state == 'edit_referral_points':
        if user_id != ADMIN_ID:
            return
        
        if not text or not text.isdigit():
            await update.message.reply_text("❌ أرسل رقماً صحيحاً!")
            return
        
        set_setting('referral_points', text)
        await update.message.reply_text(
            f"✅ تم تحديث نقاط الإحالة إلى {text}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data='admin_settings')]])
        )
        context.user_data.clear()
    
    elif state == 'edit_transfer_fee':
        if user_id != ADMIN_ID:
            return
        
        if not text or not text.isdigit():
            await update.message.reply_text("❌ أرسل رقماً صحيحاً!")
            return
        
        set_setting('transfer_fee', text)
        await update.message.reply_text(
            f"✅ تم تحديث رسوم التحويل إلى {text}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data='admin_settings')]])
        )
        context.user_data.clear()
    
    elif state == 'edit_stars_ratio':
        if user_id != ADMIN_ID:
            return
        
        if not text or not text.isdigit():
            await update.message.reply_text("❌ أرسل رقماً صحيحاً!")
            return
        
        set_setting('stars_ratio', text)
        await update.message.reply_text(
            f"✅ تم تحديث نسبة النجوم إلى {text} نقطة لكل نجمة",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data='admin_settings')]])
        )
        context.user_data.clear()
    
    elif state == 'edit_welcome':
        if user_id != ADMIN_ID or not text:
            return
        
        set_setting('welcome_message', text)
        await update.message.reply_text(
            "✅ تم تحديث رسالة الترحيب",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data='admin_settings')]])
        )
        context.user_data.clear()
    
    elif state == 'edit_fixed_gift':
        if user_id != ADMIN_ID:
            return
        
        if not text or not text.isdigit():
            await update.message.reply_text("❌ أرسل رقماً صحيحاً!")
            return
        
        set_setting('daily_gift_points', text)
        await update.message.reply_text(
            f"✅ تم تحديث الهدية اليومية إلى {text} نقطة",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data='admin_settings')]])
        )
        context.user_data.clear()
    
    elif state == 'edit_random_gift_min':
        if user_id != ADMIN_ID:
            return
        
        if not text or not text.isdigit():
            await update.message.reply_text("❌ أرسل رقماً صحيحاً!")
            return
        
        context.user_data['gift_min'] = text
        context.user_data['state'] = 'edit_random_gift_max'
        await update.message.reply_text(
            "أرسل الحد الأقصى للنقاط:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ إلغاء", callback_data='admin_settings')]])
        )
    
    elif state == 'edit_random_gift_max':
        if user_id != ADMIN_ID:
            return
        
        if not text or not text.isdigit():
            await update.message.reply_text("❌ أرسل رقماً صحيحاً!")
            return
        
        min_val = context.user_data['gift_min']
        set_setting('daily_gift_min', min_val)
        set_setting('daily_gift_max', text)
        
        await update.message.reply_text(
            f"✅ تم تحديث الهدية العشوائية من {min_val} إلى {text} نقطة",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data='admin_settings')]])
        )
        context.user_data.clear()
    
    elif state == 'search_product':
        if not text:
            return
        
        search_term = text.lower()
        products = get_products()
        results = [p for p in products if search_term in p[1].lower()]
        
        if not results:
            await update.message.reply_text(
                "❌ لم يتم العثور على منتجات!",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع للمتجر", callback_data='shop')]])
            )
            context.user_data.clear()
            return
        
        user = get_user(user_id)
        user_points = user[2] if user else 0
        
        keyboard = []
        for product in results:
            emoji = "✅" if user_points >= product[2] else "❌"
            keyboard.append([InlineKeyboardButton(
                f"{emoji} {product[1]} - {product[2]} نقطة",
                callback_data=f'buy_{product[0]}'
            )])
        keyboard.append([InlineKeyboardButton("🔙 رجوع للمتجر", callback_data='shop')])
        
        await update.message.reply_text(
            f"🔍 نتائج البحث: {len(results)}\n💰 رصيدك: {user_points} نقطة",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        context.user_data.clear()

# معالجة الدفع
async def precheckout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.pre_checkout_query
    await query.answer(ok=True)

async def successful_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    payment = update.message.successful_payment
    payload = payment.invoice_payload
    
    if payload.startswith('stars_'):
        parts = payload.split('_')
        user_id = int(parts[1])
        points = int(parts[2])
        
        update_points(user_id, points)
        add_transaction(user_id, 'purchase_stars', points, f'شراء بـ {payment.total_amount} نجمة')
        
        await update.message.reply_text(
            f"✅ تم الدفع بنجاح!\n\n"
            f"💎 حصلت على {points} نقطة",
            reply_markup=main_keyboard(user_id)
        )
        
        try:
            buyer = update.message.from_user
            buyer_username = f"@{buyer.username}" if buyer.username else "لا يوجد"
            buyer_name = buyer.first_name + (" " + buyer.last_name if buyer.last_name else "")
            buyer_link = f"tg://user?id={user_id}"
            charge_id = payment.telegram_payment_charge_id
            
            conn = sqlite3.connect('points_bot.db')
            c = conn.cursor()
            created_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            c.execute('INSERT INTO refund_requests (user_id, charge_id, created_at) VALUES (?, ?, ?)',
                      (user_id, charge_id, created_at))
            conn.commit()
            refund_id = c.lastrowid
            conn.close()
            
            refund_keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("🔄 استرداد النجوم", callback_data=f'refund_{refund_id}')
            ]])
            
            admin_notification = (
                f"⭐ عملية شراء نجوم!\n\n"
                f"👤 المشتري: {buyer_name}\n"
                f"🆔 ID: `{user_id}`\n"
                f"👁️ الرابط: [فتح الملف الشخصي]({buyer_link})\n"
                f"📱 المعرف: {buyer_username}\n\n"
                f"💫 النجوم المشتراة: {payment.total_amount}\n"
                f"💎 النقاط المضافة: {points}\n"
                f"🔑 Charge ID:\n`{charge_id}`\n\n"
                f"🕐 الوقت: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                f"💡 للاسترداد اليدوي استخدم:\n"
                f"`/refund {user_id} {charge_id}`"
            )
            
            await context.bot.send_message(
                ADMIN_ID,
                admin_notification,
                parse_mode='Markdown',
                reply_markup=refund_keyboard
            )
        except Exception as e:
            logger.error(f"فشل إرسال إشعار للمشرف: {e}")

# أمر لوحة التحكم
async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ غير مصرح لك!")
        return
    
    await update.message.reply_text("🎛️ لوحة التحكم", reply_markup=admin_keyboard())

# أمر استرداد النجوم يدوياً
async def refund_stars(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    
    if user_id != ADMIN_ID:
        await update.message.reply_text("⛔ ليس لديك صلاحية استخدام هذا الأمر!")
        return
    
    if len(context.args) < 2:
        help_text = (
            "❌ **استخدام خاطئ!**\n\n"
            "**الصيغة الصحيحة:**\n"
            "`/refund <user_id> <charge_id>`\n\n"
            "**مثال:**\n"
            "`/refund 123456789 stxcOxjT5P_KLsQNzOYz...`\n\n"
            "**📝 كيف تحصل على المعلومات:**\n"
            "• **User ID**: من إشعار الشراء\n"
            "• **Charge ID**: رقم المعاملة من إشعار الدفع\n\n"
            "**⏰ ملاحظة:**\n"
            "يمكن إرجاع النجوم خلال 180 يومًا من تاريخ الدفع"
        )
        await update.message.reply_text(help_text, parse_mode='Markdown')
        return
    
    try:
        target_user_id = int(context.args[0])
        charge_id = " ".join(context.args[1:])
    except ValueError:
        await update.message.reply_text("❌ معرف المستخدم يجب أن يكون رقمًا!")
        return
    
    loading_msg = await update.message.reply_text("⏳ جاري محاولة إرجاع النجوم...")
    
    try:
        await context.bot.refund_star_payment(
            user_id=target_user_id,
            telegram_payment_charge_id=charge_id
        )
        
        success_text = (
            f"✅ **تم إرجاع النجوم بنجاح!**\n\n"
            f"👤 **معرف المستخدم:** `{target_user_id}`\n"
            f"🆔 **رقم المعاملة:**\n`{charge_id}`\n"
            f"⏰ **وقت الاسترداد:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            f"💡 تم إرجاع النجوم للمستخدم!"
        )
        await loading_msg.edit_text(success_text, parse_mode='Markdown')
        
        try:
            await context.bot.send_message(
                chat_id=target_user_id,
                text=(
                    f"💰 **تم إرجاع النجوم إلى حسابك!**\n\n"
                    f"🆔 رقم المعاملة:\n`{charge_id}`\n\n"
                    f"شكرًا لتعاملك معنا! 💫"
                ),
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.warning(f"لم يتم إرسال إشعار للمستخدم: {e}")
        
    except Exception as e:
        error_message = str(e)
        
        if "CHARGE_ALREADY_REFUNDED" in error_message:
            error_text = (
                f"⚠️ **تم إرجاع النجوم لهذه المعاملة مسبقًا!**\n\n"
                f"🆔 رقم المعاملة: `{charge_id}`"
            )
        elif "CHARGE_NOT_FOUND" in error_message or "not found" in error_message.lower():
            error_text = (
                f"❌ **رقم المعاملة غير صحيح!**\n\n"
                f"الأسباب المحتملة:\n"
                f"• رقم المعاملة خاطئ\n"
                f"• المعاملة قديمة (أكثر من 180 يوم)\n"
                f"• المعاملة لم تكتمل\n\n"
                f"🆔 الرقم المستخدم:\n`{charge_id}`"
            )
        elif "PAYMENT_EXPIRED" in error_message:
            error_text = (
                f"⏰ **انتهت صلاحية المعاملة!**\n\n"
                f"لا يمكن إرجاع النجوم لمعاملات أقدم من 180 يومًا."
            )
        else:
            error_text = (
                f"❌ **فشل إرجاع النجوم!**\n\n"
                f"**الخطأ:** `{error_message}`\n\n"
                f"👤 User ID: `{target_user_id}`\n"
                f"🆔 Charge ID: `{charge_id}`"
            )
        
        logger.error(f"فشل الاسترداد: {error_message}")
        await loading_msg.edit_text(error_text, parse_mode='Markdown')

# تشغيل البوت
def main():
    init_db()
    
    application = Application.builder().token(TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("admin", admin))
    application.add_handler(CommandHandler("refund", refund_stars))
    
    application.add_handler(CallbackQueryHandler(button_handler))
    
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    
    application.add_handler(MessageHandler((filters.PHOTO | filters.Document.ALL) & ~filters.COMMAND, message_handler))
    
    application.add_handler(PreCheckoutQueryHandler(precheckout_callback))
    application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment))
    
    print("🤖 البوت يعمل الآن...")
    print(f"✅ ID المشرف: {ADMIN_ID}")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
