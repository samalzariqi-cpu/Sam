import requests
import time
import sqlite3
import asyncio
import os
import tempfile
import shutil
from pathlib import Path
from typing import Optional
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

# ==================== الإعدادات الثابتة ====================
TELEGRAM_BOT_TOKEN = "7871583760:AAEAj1NMlgMU7H8Y3To3a7lGvShVZ74BvzU"
ADMIN_ID = 1058616316
TELEGRAM_API_LIMIT = 20 * 1024 * 1024  # 20MB
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB الحد الأقصى الجديد

# مجلد التخزين المؤقت
TEMP_STORAGE_DIR = "temp_videos"

# طابور المعالجة
processing_queue = asyncio.Queue()
is_processing = False

# ==================== إدارة الملفات ====================
def init_temp_storage():
    """إنشاء مجلد التخزين المؤقت"""
    if not os.path.exists(TEMP_STORAGE_DIR):
        os.makedirs(TEMP_STORAGE_DIR)
    print(f"✅ مجلد التخزين المؤقت: {TEMP_STORAGE_DIR}")

def cleanup_old_files():
    """حذف جميع الملفات القديمة عند بدء التشغيل"""
    try:
        if os.path.exists(TEMP_STORAGE_DIR):
            for file in os.listdir(TEMP_STORAGE_DIR):
                file_path = os.path.join(TEMP_STORAGE_DIR, file)
                try:
                    if os.path.isfile(file_path):
                        os.unlink(file_path)
                        print(f"🗑️ حذف ملف قديم: {file}")
                except Exception as e:
                    print(f"⚠️ فشل حذف {file}: {e}")
        print("✅ تم تنظيف المجلد من الملفات القديمة")
    except Exception as e:
        print(f"❌ خطأ في التنظيف: {e}")

def delete_file_safe(file_path: str):
    """حذف ملف بشكل آمن"""
    try:
        if os.path.exists(file_path):
            os.unlink(file_path)
            print(f"🗑️ تم حذف الملف: {file_path}")
            return True
    except Exception as e:
        print(f"⚠️ فشل حذف الملف {file_path}: {e}")
    return False

def get_storage_info():
    """الحصول على معلومات المساحة التخزينية"""
    try:
        total_size = 0
        file_count = 0
        files_list = []
        
        if os.path.exists(TEMP_STORAGE_DIR):
            for file in os.listdir(TEMP_STORAGE_DIR):
                file_path = os.path.join(TEMP_STORAGE_DIR, file)
                if os.path.isfile(file_path):
                    size = os.path.getsize(file_path)
                    total_size += size
                    file_count += 1
                    files_list.append({
                        'name': file,
                        'size': size,
                        'path': file_path
                    })
        
        return {
            'total_size': total_size,
            'file_count': file_count,
            'files': files_list
        }
    except Exception as e:
        print(f"❌ خطأ في الحصول على معلومات التخزين: {e}")
        return {'total_size': 0, 'file_count': 0, 'files': []}

def format_size(size_bytes):
    """تحويل الحجم إلى صيغة قابلة للقراءة"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.2f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.2f} TB"

# ==================== قاعدة البيانات ====================
def init_database():
    """إنشاء قاعدة البيانات وجداول المستخدمين والإعدادات"""
    conn = sqlite3.connect('video_bot.db')
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        total_videos INTEGER DEFAULT 0,
        joined_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )''')
    
    c.execute("SELECT value FROM settings WHERE key = 'api_key'")
    if c.fetchone() is None:
        default_api_key = "eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9.eyJhdWQiOiIxIiwianRpIjoiZjE0N2NmNDU0ZjAzZTMzNDAwNTFlZGQ4MzFmY2JhZDMyOTM0N2FiMWM0M2RkMTRmMGNmZjlkZDAzNzQxNzE2NzdmMmY5M2EyNmFmYzI2YTgiLCJpYXQiOjE3NjQxNTUxMzQuMjkyNjQ0LCJuYmYiOjE3NjQxNTUxMzQuMjkyNjQ1LCJleHAiOjQ5MTk4Mjg3MzQuMjg1MTA3LCJzdWIiOiI3MzU3NTUyMSIsInNjb3BlcyI6WyJ0YXNrLndyaXRlIiwidGFzay5yZWFkZCJ9.ggolEBtldJIZq74R1H3SI61AHTPc4iJRvugBAWY9mAoQOW3rbaUrQHf8CTDuRYNf6pm0xpmAgcFn6SrTbw16-zEERYc11qvOHGY5qXQok_aiFyj2GokGTzbf3nhdhswZPmtAj69WljWcggt6X-9iwTyChDXKqC7U6EjeA2aW6XptX5RtuK9xXF_NASJetc7qiWX1r8KzdiwhbFJok4bI3i9d8VV-dItDWXZJ3euFfPc-lzOhqwDf2ZEA1wPg20Bi6gd0IE2PgVQpKynZyFktu8WNPNVzhnOH0yE1Ya6oehvJagX4tmn7gx1mfjrOJjtqAD2Eg2F-8Dl7gd86fhexOKe0BewfLNU1FU6rniUH3jTdLJfAjL8O6QsuuLeJXG9E2s5mFpGsqxqB7LMC_GXN27Dm44kjmHoB48m6zWYQsZ751DHSJ8rjVR-BzcS9AjQegYW08nInRhY2UfINrqNbfu7U69sdl4L09ZuVIEAGljE2ktcQCqyHCqxi4kHipLa6q-WRFv_5bDIpWkF6BHUjeEQYVN0_F-bze1c8qiX6m7nQNHbmGhIaCUim7NHEI9sz5bvJNLKc98VctRanyeJvy-YL9ZcP--16Sw-kj1ydT743mB4Nt0AKSf7A9KwMpKWciPWkvq6Cesj6eMTtS3HSN0WvwhhOQ20zcDCxWjnm16k"
        c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('api_key', ?)", (default_api_key,))
    
    conn.commit()
    conn.close()

def get_api_key():
    """الحصول على مفتاح API من قاعدة البيانات"""
    conn = sqlite3.connect('video_bot.db')
    c = conn.cursor()
    c.execute("SELECT value FROM settings WHERE key = 'api_key'")
    result = c.fetchone()
    conn.close()
    return result[0] if result else None

def set_api_key(new_key):
    """حفظ مفتاح API جديد في قاعدة البيانات"""
    conn = sqlite3.connect('video_bot.db')
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('api_key', ?)", (new_key,))
    conn.commit()
    conn.close()

def get_user(user_id):
    """الحصول على معلومات المستخدم"""
    conn = sqlite3.connect('video_bot.db')
    c = conn.cursor()
    c.execute('SELECT user_id, username, total_videos, joined_date FROM users WHERE user_id = ?', (user_id,))
    user = c.fetchone()
    conn.close()
    return user

def create_user(user_id, username):
    """إنشاء مستخدم جديد"""
    conn = sqlite3.connect('video_bot.db')
    c = conn.cursor()
    c.execute('INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)', (user_id, username))
    conn.commit()
    conn.close()

def increment_video_count(user_id):
    """زيادة عداد الفيديوهات"""
    conn = sqlite3.connect('video_bot.db')
    c = conn.cursor()
    c.execute('UPDATE users SET total_videos = total_videos + 1 WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()

# ==================== دوال تليجرام ====================
async def send_message(chat_id: str, text: str, context=None):
    """إرسال رسالة نصية"""
    try:
        if context:
            await context.bot.send_message(chat_id=chat_id, text=text, parse_mode='Markdown')
        else:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            requests.post(url, data={"chat_id": chat_id, "text": text, "parse_mode": 'Markdown'})
    except Exception as e:
        print(f"خطأ في إرسال الرسالة: {e}")

# ==================== أوامر البوت ====================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """أمر /start"""
    user = update.effective_user
    create_user(user.id, user.username)
    
    keyboard_rows = [
        [InlineKeyboardButton("📊 حسابي وإحصائياتي", callback_data="my_account")],
        [InlineKeyboardButton("ℹ️ المساعدة", callback_data="help")]
    ]
    
    if user.id == ADMIN_ID:
        keyboard_rows.append([InlineKeyboardButton("⚙️ إعدادات المشرف", callback_data="admin_settings")])

    reply_markup = InlineKeyboardMarkup(keyboard_rows)
    
    welcome_text = f"""
🎬 مرحباً {user.first_name}!

أنا بوت ضغط الفيديوهات. الآن أنا **مجاني بالكامل وبدون قيود**! 🚀

**🎯 المميزات:**
✨ معالجة ملفات حتى 100MB مباشرة
✨ دعم ملفات تيليجرام والروابط الخارجية
✨ 3 مستويات جودة (1080p / 720p / 480p)
✨ حذف تلقائي للملفات بعد الإرسال

📤 أرسل فيديو (حتى 100MB) أو رابط فيديو وسأقوم بضغطه!
"""
    
    await update.message.reply_text(welcome_text, reply_markup=reply_markup)

async def my_account_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معلومات الحساب"""
    user_id = update.effective_user.id
    user_data = get_user(user_id)
    
    if not user_data:
        await update.message.reply_text("يرجى البدء بالأمر /start أولاً")
        return
    
    user_id_db, username, total_videos, joined = user_data
    
    account_text = f"""
👤 **معلومات حسابك**

📝 معرف المستخدم: `{user_id}`
🎬 إجمالي الفيديوهات المعالجة: {total_videos}
📅 تاريخ الانضمام: {joined.split()[0]}
"""
    
    await update.message.reply_text(account_text, parse_mode='Markdown')

async def setapikey_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """أمر المشرف لتغيير مفتاح API"""
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ هذا الأمر متاح للمشرف فقط.")
        return

    args = context.args
    if args:
        new_key = args[0]
        set_api_key(new_key)
        await update.message.reply_text(f"✅ تم تحديث مفتاح CloudConvert API بنجاح.", parse_mode='Markdown')
    else:
        current_key = get_api_key()
        if current_key:
            masked_key = '*' * 4 + current_key[-4:] if len(current_key) > 4 else current_key
            await update.message.reply_text(f"🔑 مفتاح API الحالي ينتهي بـ: `{masked_key}`\n\n**لتغيير المفتاح:**\n`/setapikey YOUR_NEW_KEY`", parse_mode='Markdown')
        else:
            await update.message.reply_text("❌ لم يتم تعيين مفتاح API")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إحصائيات البوت"""
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ هذا الأمر متاح للمشرف فقط.")
        return

    conn = sqlite3.connect('video_bot.db')
    c = conn.cursor()
    
    c.execute('SELECT COUNT(*) FROM users')
    total_users = c.fetchone()[0]
    
    c.execute('SELECT SUM(total_videos) FROM users')
    total_videos_processed = c.fetchone()[0] or 0
    
    conn.close()
    
    storage_info = get_storage_info()
    
    stats_text = f"""
📊 **إحصائيات البوت**

👤 إجمالي المستخدمين: {total_users}
🎬 إجمالي الفيديوهات المعالجة: {total_videos_processed}

💾 **التخزين المؤقت:**
📁 عدد الملفات: {storage_info['file_count']}
📦 المساحة المستخدمة: {format_size(storage_info['total_size'])}
"""
    
    await update.message.reply_text(stats_text)

async def files_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """عرض الملفات المؤقتة (للمشرف فقط)"""
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ هذا الأمر متاح للمشرف فقط.")
        return
    
    storage_info = get_storage_info()
    
    if storage_info['file_count'] == 0:
        await update.message.reply_text("✅ لا توجد ملفات مؤقتة. المجلد نظيف! 🧹")
        return
    
    files_text = f"📁 **الملفات المؤقتة ({storage_info['file_count']}):**\n"
    files_text += f"📦 المساحة الإجمالية: {format_size(storage_info['total_size'])}\n\n"
    
    keyboard = []
    for idx, file_info in enumerate(storage_info['files'][:20]):  # عرض أول 20 ملف
        file_name = file_info['name']
        file_size = format_size(file_info['size'])
        files_text += f"{idx+1}. `{file_name}` - {file_size}\n"
        
        # إضافة زر حذف لكل ملف
        keyboard.append([InlineKeyboardButton(
            f"🗑️ حذف {file_name[:20]}...",
            callback_data=f"delete_file_{file_name}"
        )])
    
    # زر حذف الكل
    keyboard.append([InlineKeyboardButton("🗑️ حذف جميع الملفات", callback_data="delete_all_files")])
    keyboard.append([InlineKeyboardButton("عودة", callback_data="admin_settings")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(files_text, reply_markup=reply_markup, parse_mode='Markdown')

async def cleanup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """حذف جميع الملفات المؤقتة (للمشرف)"""
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        await update.message.reply_text("❌ هذا الأمر متاح للمشرف فقط.")
        return
    
    storage_info = get_storage_info()
    deleted_count = 0
    
    for file_info in storage_info['files']:
        if delete_file_safe(file_info['path']):
            deleted_count += 1
    
    await update.message.reply_text(f"✅ تم حذف {deleted_count} ملف من المجلد المؤقت! 🧹")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج الأزرار"""
    query = update.callback_query
    await query.answer()
    
    # حذف ملف محدد
    if query.data.startswith("delete_file_"):
        if query.from_user.id != ADMIN_ID:
            await query.edit_message_text("❌ هذه الوظيفة للمشرف فقط.")
            return
        
        file_name = query.data.replace("delete_file_", "")
        file_path = os.path.join(TEMP_STORAGE_DIR, file_name)
        
        if delete_file_safe(file_path):
            await query.edit_message_text(f"✅ تم حذف الملف: {file_name}")
        else:
            await query.edit_message_text(f"❌ فشل حذف الملف: {file_name}")
        return
    
    # حذف جميع الملفات
    if query.data == "delete_all_files":
        if query.from_user.id != ADMIN_ID:
            await query.edit_message_text("❌ هذه الوظيفة للمشرف فقط.")
            return
        
        storage_info = get_storage_info()
        deleted_count = 0
        
        for file_info in storage_info['files']:
            if delete_file_safe(file_info['path']):
                deleted_count += 1
        
        await query.edit_message_text(f"✅ تم حذف {deleted_count} ملف! 🧹")
        return
    
    # معالجة اختيار الجودة للفيديوهات المرسلة كملف
    if query.data.startswith("quality_") and not query.data.startswith("quality_url_"):
        quality = query.data.replace("quality_", "")
        
        if 'pending_video' not in context.user_data:
            await query.edit_message_text("❌ لم يتم العثور على فيديو.")
            return
        
        video_info = context.user_data['pending_video']
        chat_id = video_info['chat_id']
        file_id = video_info['file_id']
        file_size = video_info['file_size']
        
        del context.user_data['pending_video']
        
        quality_names = {
            'high': '🔥 عالية (1080p)',
            'medium': '⚖️ متوسطة (720p)',
            'low': '💾 منخفضة (480p)'
        }
        
        queue_size = processing_queue.qsize()
        status_text = f"✅ تم اختيار الجودة: {quality_names.get(quality, 'عادية')}\n\n"
        if queue_size > 0:
            status_text += f"⏳ يوجد {queue_size} فيديو في الطابور..."
        else:
            status_text += f"⏳ جاري معالجة الفيديو..."
            
        await query.edit_message_text(status_text)
        
        await processing_queue.put({
            'chat_id': chat_id,
            'source': file_id,
            'type': 'file_id',
            'file_size': file_size,
            'quality': quality
        })
        return
    
    # معالجة اختيار جودة الروابط
    if query.data.startswith("quality_url_"):
        quality = query.data.replace("quality_url_", "")
        
        if 'pending_video' not in context.user_data or 'url' not in context.user_data['pending_video']:
            await query.edit_message_text("❌ لم يتم العثور على رابط.")
            return
        
        video_info = context.user_data['pending_video']
        chat_id = video_info['chat_id']
        url = video_info['url']
        
        del context.user_data['pending_video']
        
        quality_names = {
            'high': '🔥 عالية (1080p)',
            'medium': '⚖️ متوسطة (720p)',
            'low': '💾 منخفضة (480p)'
        }
        
        queue_size = processing_queue.qsize()
        status_text = f"✅ تم اختيار الجودة: {quality_names.get(quality, 'عادية')}\n\n"
        if queue_size > 0:
            status_text += f"⏳ يوجد {queue_size} فيديو في الطابور..."
        else:
            status_text += f"⏳ جاري معالجة الرابط..."

        await query.edit_message_text(status_text)
        
        await processing_queue.put({
            'chat_id': chat_id,
            'source': url,
            'type': 'url',
            'file_size': 0,
            'quality': quality
        })
        return
    
    if query.data == "my_account":
        user_id = query.from_user.id
        user_data = get_user(user_id)
        
        if not user_data:
            await query.edit_message_text("يرجى البدء بالأمر /start أولاً")
            return
        
        user_id_db, username, total_videos, joined = user_data
        
        account_text = f"""
👤 **معلومات حسابك**

📝 معرف المستخدم: `{user_id}`
🎬 إجمالي الفيديوهات المعالجة: {total_videos}
📅 تاريخ الانضمام: {joined.split()[0]}
"""
        keyboard_rows = [[InlineKeyboardButton("عودة", callback_data="start_menu")]]
        if query.from_user.id == ADMIN_ID:
             keyboard_rows.insert(0, [InlineKeyboardButton("⚙️ إعدادات المشرف", callback_data="admin_settings")])
        
        reply_markup = InlineKeyboardMarkup(keyboard_rows)
        await query.edit_message_text(account_text, reply_markup=reply_markup, parse_mode='Markdown')
    
    elif query.data == "help":
        help_text = """
ℹ️ **كيفية الاستخدام:**

**1. ملفات تيليجرام (حتى 100MB):**
1️⃣ أرسل فيديو مباشرة للبوت
2️⃣ اختر جودة الضغط
3️⃣ انتظر حتى يتم الضغط والإرسال

**2. الروابط الخارجية:**
1️⃣ أرسل رابط مباشر للفيديو
2️⃣ اختر جودة الضغط
3️⃣ انتظر المعالجة

🎬 **مستويات الجودة:**
🔥 عالية: 1080p - أفضل جودة
⚖️ متوسطة: 720p - توازن مثالي
💾 منخفضة: 480p - أقل حجم

🗑️ **ملاحظة:** يتم حذف جميع الملفات تلقائياً بعد الإرسال لتوفير المساحة.
"""
        await query.edit_message_text(help_text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("عودة", callback_data="start_menu")]]))
    
    elif query.data == "admin_settings" and query.from_user.id == ADMIN_ID:
        storage_info = get_storage_info()
        admin_text = f"""
👑 **لوحة تحكم المشرف**

💾 **التخزين المؤقت:**
📁 عدد الملفات: {storage_info['file_count']}
📦 المساحة: {format_size(storage_info['total_size'])}

يمكنك إدارة الملفات والإعدادات من هنا.
"""
        keyboard = [
            [InlineKeyboardButton("📁 عرض الملفات المؤقتة", callback_data="admin_view_files")],
            [InlineKeyboardButton("🔑 إعدادات API", callback_data="admin_set_api_key")],
            [InlineKeyboardButton("📊 الإحصائيات", callback_data="admin_stats")],
            [InlineKeyboardButton("عودة", callback_data="start_menu")]
        ]
        await query.edit_message_text(admin_text, reply_markup=InlineKeyboardMarkup(keyboard))
    
    elif query.data == "admin_view_files" and query.from_user.id == ADMIN_ID:
        storage_info = get_storage_info()
        
        if storage_info['file_count'] == 0:
            await query.edit_message_text(
                "✅ لا توجد ملفات مؤقتة. المجلد نظيف! 🧹",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("عودة", callback_data="admin_settings")]])
            )
            return
        
        files_text = f"📁 **الملفات المؤقتة ({storage_info['file_count']}):**\n"
        files_text += f"📦 المساحة: {format_size(storage_info['total_size'])}\n\n"
        
        keyboard = []
        for idx, file_info in enumerate(storage_info['files'][:10]):
            file_name = file_info['name']
            file_size = format_size(file_info['size'])
            files_text += f"{idx+1}. `{file_name[:30]}...` - {file_size}\n"
            
            keyboard.append([InlineKeyboardButton(
                f"🗑️ {file_name[:25]}...",
                callback_data=f"delete_file_{file_name}"
            )])
        
        keyboard.append([InlineKeyboardButton("🗑️ حذف الكل", callback_data="delete_all_files")])
        keyboard.append([InlineKeyboardButton("عودة", callback_data="admin_settings")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(files_text, reply_markup=reply_markup, parse_mode='Markdown')
        
    elif query.data == "admin_set_api_key" and query.from_user.id == ADMIN_ID:
        current_key = get_api_key()
        if current_key:
            masked_key = '*' * 4 + current_key[-4:] if len(current_key) > 4 else current_key
            response_text = f"🔑 مفتاح CloudConvert API الحالي ينتهي بـ:\n`{masked_key}`\n\n**لتغيير المفتاح:**\n`/setapikey YOUR_NEW_KEY`"
        else:
            response_text = "❌ لم يتم تعيين مفتاح API\n\n**لتعيين المفتاح:**\n`/setapikey YOUR_NEW_KEY`"
            
        keyboard = [[InlineKeyboardButton("عودة", callback_data="admin_settings")]]
        await query.edit_message_text(response_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

    elif query.data == "admin_stats" and query.from_user.id == ADMIN_ID:
        conn = sqlite3.connect('video_bot.db')
        c = conn.cursor()
        c.execute('SELECT COUNT(*) FROM users')
        total_users = c.fetchone()[0]
        c.execute('SELECT SUM(total_videos) FROM users')
        total_videos_processed = c.fetchone()[0] or 0
        conn.close()
        
        storage_info = get_storage_info()
        
        stats_text = f"""
📊 **إحصائيات البوت**

👤 إجمالي المستخدمين: {total_users}
🎬 إجمالي الفيديوهات: {total_videos_processed}

💾 **التخزين:**
📁 الملفات المؤقتة: {storage_info['file_count']}
📦 المساحة المستخدمة: {format_size(storage_info['total_size'])}
"""
        keyboard = [[InlineKeyboardButton("عودة", callback_data="admin_settings")]]
        await query.edit_message_text(stats_text, reply_markup=InlineKeyboardMarkup(keyboard))

    elif query.data == "start_menu":
        user = query.from_user
        keyboard_rows = [
            [InlineKeyboardButton("📊 حسابي وإحصائياتي", callback_data="my_account")],
            [InlineKeyboardButton("ℹ️ المساعدة", callback_data="help")]
        ]
        
        if user.id == ADMIN_ID:
            keyboard_rows.append([InlineKeyboardButton("⚙️ إعدادات المشرف", callback_data="admin_settings")])

        reply_markup = InlineKeyboardMarkup(keyboard_rows)
        
        welcome_text = f"""
🎬 مرحباً {user.first_name}!

أنا بوت ضغط الفيديوهات - **مجاني بالكامل** 🚀

**🎯 المميزات:**
✨ معالجة ملفات حتى 100MB
✨ دعم الروابط الخارجية
✨ 3 مستويات جودة
✨ حذف تلقائي للملفات

📤 أرسل فيديو أو رابط للبدء!
"""
        await query.edit_message_text(welcome_text, reply_markup=reply_markup)

# ==================== معالجة الفيديو ====================
async def download_file_from_telegram(context, file_id: str, file_size: int) -> Optional[str]:
    """تحميل ملف من تليجرام إلى التخزين المؤقت"""
    try:
        print(f"📥 تحميل من Telegram... الحجم: {file_size / (1024*1024):.2f} MB")
        
        file = await context.bot.get_file(file_id)
        
        # حفظ في مجلد التخزين المؤقت
        timestamp = int(time.time())
        temp_filename = f"video_{timestamp}_{file_id[:10]}.mp4"
        temp_path = os.path.join(TEMP_STORAGE_DIR, temp_filename)
        
        await file.download_to_drive(temp_path)
        print(f"✅ تم التحميل: {temp_path}")
        
        return temp_path
        
    except Exception as e:
        print(f"❌ خطأ في التحميل: {e}")
        return None

def get_quality_settings(quality: str) -> dict:
    """الحصول على إعدادات الجودة"""
    if quality == 'high':
        return {
            "crf": 23,
            "preset": "medium",
            "width": 1920,
            "height": 1080,
            "audio_bitrate": 128,
            "audio_frequency": 44100,
            "audio_channels": 2,
            "fps": 30
        }
    elif quality == 'medium':
        return {
            "crf": 28,
            "preset": "slow",
            "width": 1280,
            "height": 720,
            "audio_bitrate": 96,
            "audio_frequency": 44100,
            "audio_channels": 2,
            "fps": 30
        }
    else:  # low
        return {
            "crf": 40,
            "preset": "veryslow",
            "width": 854,
            "height": 480,
            "audio_bitrate": 48,
            "audio_frequency": 22050,
            "audio_channels": 1,
            "fps": 24
        }

def compress_video(video_source: str, chat_id: str, context, quality: str = 'low', is_url: bool = True) -> Optional[str]:
    """ضغط الفيديو باستخدام CloudConvert"""
    api_key = get_api_key()
    if not api_key:
        return "NO_API_KEY_SET"

    try:
        headers = {"Authorization": f"Bearer {api_key}"}
        settings = get_quality_settings(quality)
        
        # تحديد حمولة Job
        if is_url:
            job_payload = {
                "tasks": {
                    "import-video": {"operation": "import/url", "url": video_source, "filename": "video.mp4"},
                    "compress-video": {
                        "operation": "convert", "input": "import-video", "output_format": "mp4",
                        "video_codec": "x264", "crf": settings["crf"], "preset": settings["preset"],
                        "width": settings["width"], "height": settings["height"],
                        "audio_codec": "aac", "audio_bitrate": settings["audio_bitrate"], 
                        "audio_frequency": settings["audio_frequency"], "audio_channels": settings["audio_channels"], 
                        "strip_metadata": True, "fps": settings["fps"]
                    },
                    "export-video": {"operation": "export/url", "input": "compress-video"}
                }
            }
        else:
            job_payload = {
                "tasks": {
                    "import-video": {"operation": "import/upload"},
                    "compress-video": {
                        "operation": "convert", "input": "import-video", "output_format": "mp4",
                        "video_codec": "x264", "crf": settings["crf"], "preset": settings["preset"],
                        "width": settings["width"], "height": settings["height"],
                        "audio_codec": "aac", "audio_bitrate": settings["audio_bitrate"], 
                        "audio_frequency": settings["audio_frequency"], "audio_channels": settings["audio_channels"], 
                        "strip_metadata": True, "fps": settings["fps"]
                    },
                    "export-video": {"operation": "export/url", "input": "compress-video"}
                }
            }
        
        response = requests.post(
            "https://api.cloudconvert.com/v2/jobs",
            json=job_payload,
            headers=headers
        )
        
        if response.status_code != 201:
            print(f"❌ فشل إنشاء Job: {response.text}")
            return None
            
        job_data = response.json()["data"]
        job_id = job_data["id"]
        
        # رفع الملف إذا كان محلياً
        if not is_url:
            import_task = next((t for t in job_data["tasks"] if t["name"] == "import-video"), None)
            if not import_task:
                return None
            
            upload_url = import_task["result"]["form"]["url"]
            upload_params = import_task["result"]["form"]["parameters"]
            
            with open(video_source, 'rb') as f:
                files = {'file': f}
                upload_response = requests.post(upload_url, data=upload_params, files=files)
            
            if upload_response.status_code not in [200, 201]:
                print(f"❌ فشل رفع الملف: {upload_response.text}")
                return None
            
            print("✅ تم رفع الملف لـ CloudConvert")
            
            # حذف الملف المحلي فوراً بعد الرفع
            delete_file_safe(video_source)
        
        # انتظار اكتمال المعالجة
        max_attempts = 180
        attempt = 0
        
        while attempt < max_attempts:
            job_status = requests.get(
                f"https://api.cloudconvert.com/v2/jobs/{job_id}",
                headers=headers
            ).json()
            
            status = job_status["data"]["status"]
            
            if status == "finished":
                tasks = job_status["data"]["tasks"]
                export_task = next((t for t in tasks if t["name"] == "export-video"), None)
                
                if export_task and export_task.get("result") and export_task["result"].get("files"):
                    download_url = export_task["result"]["files"][0]["url"]
                    file_size = export_task["result"]["files"][0].get("size", 0)
                    file_size_mb = file_size / (1024*1024)
                    print(f"✅ اكتمل الضغط! الحجم: {file_size_mb:.2f} MB")
                    return download_url
                    
            elif status == "error":
                print(f"❌ خطأ في المعالجة: {job_status}")
                return None
                
            time.sleep(5)
            attempt += 1
        
        print("❌ انتهى الوقت")
        return None
        
    except Exception as e:
        print(f"❌ خطأ: {e}")
        return None

def send_compressed_video_advanced(chat_id: str, video_url: str, caption: str = "✅ تم ضغط الفيديو!") -> tuple:
    """إرسال الفيديو المضغوط مع حذف تلقائي"""
    temp_file_path = None
    max_retries = 3
    
    for attempt in range(max_retries):
        try:
            print(f"📤 محاولة الإرسال ({attempt + 1}/{max_retries})...")
            send_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendVideo"
            
            # محاولة الإرسال المباشر أولاً
            response = requests.post(
                send_url,
                data={
                    "chat_id": chat_id,
                    "video": video_url,
                    "caption": caption,
                    "supports_streaming": True
                },
                timeout=600
            )
            
            if response.status_code == 200:
                print(f"✅ نجح الإرسال المباشر")
                return True, None
            else:
                print(f"⚠️ فشل الإرسال المباشر: {response.status_code}")
                
        except Exception as e:
            print(f"❌ خطأ في الإرسال المباشر: {e}")
        
        # التحميل والإرسال المحلي
        if attempt == max_retries - 1:
            try:
                print("🔄 جاري التحميل المحلي...")
                
                # تحميل الفيديو
                video_response = requests.get(video_url, timeout=300, stream=True)
                
                if video_response.status_code != 200:
                    print(f"❌ فشل تحميل الفيديو: {video_response.status_code}")
                    return False, None
                
                # حفظ في المجلد المؤقت
                timestamp = int(time.time())
                temp_filename = f"compressed_{timestamp}.mp4"
                temp_file_path = os.path.join(TEMP_STORAGE_DIR, temp_filename)
                
                with open(temp_file_path, 'wb') as temp_file:
                    for chunk in video_response.iter_content(chunk_size=8192):
                        if chunk:
                            temp_file.write(chunk)
                
                file_size_mb = os.path.getsize(temp_file_path) / (1024*1024)
                print(f"✅ تم التحميل المحلي: {file_size_mb:.2f} MB")
                
                # إرسال الملف
                print("📤 جاري إرسال الملف المحلي...")
                with open(temp_file_path, 'rb') as video_file:
                    files = {'video': video_file}
                    data = {'chat_id': chat_id, 'caption': caption, 'supports_streaming': True}
                    
                    response = requests.post(send_url, data=data, files=files, timeout=600)
                
                if response.status_code == 200:
                    print("✅ نجح إرسال الملف المحلي!")
                    return True, temp_file_path
                else:
                    print(f"❌ فشل إرسال الملف: {response.status_code}")
                    return False, temp_file_path
                    
            except Exception as e:
                print(f"❌ خطأ في الإرسال المحلي: {e}")
                return False, temp_file_path
        
        if attempt < max_retries - 1:
            time.sleep(5)
    
    return False, temp_file_path

async def process_video_queue(context):
    """معالج طابور الفيديو"""
    global is_processing
    
    while True:
        try:
            video_data = await processing_queue.get()
            
            is_processing = True
            chat_id = video_data['chat_id']
            user_id = int(chat_id)
            video_source = video_data['source']
            source_type = video_data['type']
            file_size = video_data.get('file_size', 0)
            quality = video_data.get('quality', 'low')
            
            print(f"🎬 بدء معالجة: {chat_id} - {source_type} - {quality}")
            
            compressed_url = None
            local_file_to_delete = None
            
            # معالجة حسب النوع
            if source_type == 'url':
                await send_message(chat_id, "⏳ جاري معالجة الرابط...", context)
                compressed_url = compress_video(video_source, chat_id, context, quality, is_url=True)
                
            elif source_type == 'file_id':
                if file_size <= MAX_FILE_SIZE:
                    await send_message(chat_id, "📥 جاري تحميل الفيديو...", context)
                    local_file = await download_file_from_telegram(context, video_source, file_size)
                    
                    if local_file:
                        local_file_to_delete = local_file
                        await send_message(chat_id, "⏳ جاري ضغط الفيديو...", context)
                        compressed_url = compress_video(local_file, chat_id, context, quality, is_url=False)
                    else:
                        await send_message(chat_id, "❌ فشل تحميل الفيديو.", context)
                else:
                    await send_message(chat_id, f"❌ الملف كبير جداً ({file_size/(1024*1024):.2f} MB). الحد الأقصى 100MB.", context)
            
            # إرسال النتيجة
            if compressed_url == "NO_API_KEY_SET":
                await send_message(chat_id, "❌ لم يتم تعيين مفتاح API. أبلغ المشرف.", context)
                
            elif compressed_url:
                quality_names = {'high': '🔥 عالية', 'medium': '⚖️ متوسطة', 'low': '💾 منخفضة'}
                caption = f"✅ تم الضغط بنجاح!\n🎬 الجودة: {quality_names.get(quality, 'عادية')}"
                
                await send_message(chat_id, "📤 جاري إرسال الفيديو...", context)
                
                send_success, temp_file = send_compressed_video_advanced(chat_id, compressed_url, caption)
                
                # حذف الملف المؤقت فوراً بعد الإرسال
                if temp_file:
                    delete_file_safe(temp_file)
                
                if send_success:
                    increment_video_count(user_id)
                    print(f"✅ تم إرسال الفيديو إلى {chat_id}")
                    
                    # تنظيف أي ملفات متبقية
                    await asyncio.sleep(2)
                    storage_info = get_storage_info()
                    if storage_info['file_count'] > 5:
                        print("🧹 تنظيف الملفات القديمة...")
                        for file_info in storage_info['files'][:3]:
                            delete_file_safe(file_info['path'])
                else:
                    await send_message(chat_id, "❌ فشل إرسال الفيديو. حاول مرة أخرى.", context)
            else:
                await send_message(chat_id, "❌ فشل ضغط الفيديو. تحقق من الإعدادات.", context)
            
            # حذف أي ملفات محلية متبقية
            if local_file_to_delete:
                delete_file_safe(local_file_to_delete)
            
            processing_queue.task_done()
            is_processing = False
            
        except Exception as e:
            print(f"❌ خطأ في المعالجة: {e}")
            is_processing = False
            await asyncio.sleep(1)

async def handle_video(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج الفيديو"""
    user_id = update.effective_user.id
    chat_id = str(update.effective_chat.id)
    
    if update.message.video:
        file_id = update.message.video.file_id
        file_size = update.message.video.file_size
    elif update.message.document and update.message.document.mime_type and update.message.document.mime_type.startswith("video/"):
        file_id = update.message.document.file_id
        file_size = update.message.document.file_size
    else:
        return
    
    file_size_mb = file_size / (1024 * 1024)
    print(f"📹 فيديو من {user_id} - {file_size_mb:.2f} MB")
    
    if file_size > MAX_FILE_SIZE:
        await update.message.reply_text(f"❌ الملف كبير جداً ({file_size_mb:.2f} MB)\n\n📏 الحد الأقصى: 100MB\n💡 استخدم رابط خارجي للملفات الأكبر.")
        return
    
    context.user_data['pending_video'] = {
        'file_id': file_id,
        'file_size': file_size,
        'chat_id': chat_id
    }
    
    keyboard = [
        [InlineKeyboardButton("🔥 عالية (1080p)", callback_data="quality_high")],
        [InlineKeyboardButton("⚖️ متوسطة (720p)", callback_data="quality_medium")],
        [InlineKeyboardButton("💾 منخفضة (480p)", callback_data="quality_low")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    quality_text = f"""
🎬 **اختر جودة الضغط:**

📹 حجم الفيديو: {file_size_mb:.2f} MB

اختر الجودة المناسبة 👇
"""
    
    await update.message.reply_text(quality_text, reply_markup=reply_markup)

async def handle_url(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج الروابط"""
    user_id = update.effective_user.id
    chat_id = str(update.effective_chat.id)
    url = update.message.text.strip()
    
    if not url.startswith(('http://', 'https://')):
        return
    
    video_sites = ['.mp4', '.avi', '.mov', 'drive.google.com', 'dropbox.com', 'mega.nz']
    is_likely_video = any(site in url.lower() for site in video_sites)
    
    if not is_likely_video:
        return
    
    print(f"🔗 رابط من {user_id}: {url}")
    
    context.user_data['pending_video'] = {
        'url': url,
        'chat_id': chat_id
    }
    
    keyboard = [
        [InlineKeyboardButton("🔥 عالية (1080p)", callback_data="quality_url_high")],
        [InlineKeyboardButton("⚖️ متوسطة (720p)", callback_data="quality_url_medium")],
        [InlineKeyboardButton("💾 منخفضة (480p)", callback_data="quality_url_low")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text("🎬 **اختر جودة الضغط:**", reply_markup=reply_markup)

# ==================== البرنامج الرئيسي ====================
def main():
    """البرنامج الرئيسي"""
    print("🚀 تهيئة البوت...")
    
    # إنشاء المجلدات والقواعد
    init_temp_storage()
    init_database()
    
    # تنظيف الملفات القديمة
    cleanup_old_files()
    
    print("✅ النظام جاهز")
    
    # إنشاء التطبيق
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # المعالجات
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("account", my_account_command))
    application.add_handler(CommandHandler("setapikey", setapikey_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("files", files_command))
    application.add_handler(CommandHandler("cleanup", cleanup_command))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.VIDEO | filters.Document.VIDEO, handle_video))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_url))
    
    # بدء معالج الطابور
    application.job_queue.run_once(
        lambda context: asyncio.create_task(process_video_queue(context)),
        when=0
    )
    
    print("✅ البوت يعمل الآن...")
    print(f"👑 معرف المشرف: {ADMIN_ID}")
    print(f"📦 الحد الأقصى للملفات: {MAX_FILE_SIZE/(1024*1024):.0f} MB")
    
    # تشغيل البوت
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
