#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🎯 بوت مسابقات تلجرام المتقدم - ملف واحد شامل
يحتوي على 3 أنواع مسابقات:
1. مسابقة التصويت (Voting Contest)
2. عجلة الحظ (Lucky Wheel)
3. مسابقة الإحالات (Referral Contest)

المتطلبات:
pip install python-telegram-bot==20.7 aiosqlite

طريقة التشغيل:
1. ضع التوكن الخاص بك في TELEGRAM_BOT_TOKEN
2. ضع معرف قناتك الرسمية في OFFICIAL_CHANNEL
3. شغل البوت: python config.py
"""

import asyncio
import logging
import random
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple
import json
import aiosqlite
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ChatMember
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    ContextTypes, MessageHandler, filters
)
from telegram.error import TelegramError

# التوافق مع الإصدارات المختلفة
try:
    from telegram.constants import ParseMode
except ImportError:
    # للإصدارات القديمة
    class ParseMode:
        MARKDOWN = "Markdown"
        MARKDOWN_V2 = "MarkdownV2"
        HTML = "HTML"

# التوافق مع ChatMemberStatus
try:
    from telegram import ChatMemberStatus
except ImportError:
    # للإصدارات القديمة
    class ChatMemberStatus:
        MEMBER = "member"
        ADMINISTRATOR = "administrator"
        OWNER = "creator"
        LEFT = "left"
        KICKED = "kicked"

# ═══════════════════════════════════════════════════════════════
# ⚙️ الإعدادات الأساسية
# ═══════════════════════════════════════════════════════════════

# ضع توكن البوت هنا
TELEGRAM_BOT_TOKEN = "8415034792:AAHuEHGs3CaNMq3KtUWNEKmqTljJ3jFc_mM"

# معرف قناتك الرسمية (بدون @)
OFFICIAL_CHANNEL = "@WhatIOwnQBot1"

# اسم قاعدة البيانات
DATABASE_NAME = "contests.db"

# فترة التحقق من الاشتراك (بالساعات)
CHECK_SUBSCRIPTION_INTERVAL = 3

# تفعيل السجلات
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
# 🗄️ قاعدة البيانات
# ═══════════════════════════════════════════════════════════════

class Database:
    """إدارة قاعدة البيانات SQLite"""
    
    def __init__(self, db_name: str):
        self.db_name = db_name
    
    async def init_db(self):
        """إنشاء الجداول الأساسية"""
        async with aiosqlite.connect(self.db_name) as db:
            # جدول المسابقات
            await db.execute('''
                CREATE TABLE IF NOT EXISTS contests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    owner_id INTEGER NOT NULL,
                    channel_id TEXT NOT NULL,
                    contest_type TEXT NOT NULL,
                    status TEXT DEFAULT 'active',
                    settings TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    ended_at TIMESTAMP
                )
            ''')
            
            # جدول المتسابقين في مسابقة التصويت
            await db.execute('''
                CREATE TABLE IF NOT EXISTS voting_participants (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    contest_id INTEGER,
                    name TEXT NOT NULL,
                    message_id INTEGER,
                    votes INTEGER DEFAULT 0,
                    FOREIGN KEY(contest_id) REFERENCES contests(id)
                )
            ''')
            
            # جدول الأصوات
            await db.execute('''
                CREATE TABLE IF NOT EXISTS votes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    participant_id INTEGER,
                    user_id INTEGER,
                    voted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(participant_id) REFERENCES voting_participants(id)
                )
            ''')
            
            # جدول المشتركين في عجلة الحظ
            await db.execute('''
                CREATE TABLE IF NOT EXISTS lucky_participants (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    contest_id INTEGER,
                    user_id INTEGER,
                    username TEXT,
                    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(contest_id) REFERENCES contests(id)
                )
            ''')
            
            # حذف الجدول القديم إذا كان موجوداً بالقيد الخاطئ
            try:
                # محاولة التحقق من البنية
                async with db.execute("PRAGMA table_info(referral_participants)") as cursor:
                    columns = await cursor.fetchall()
                    # التحقق إذا كان user_id لديه قيد UNIQUE خاطئ
                    needs_recreation = False
                    async with db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='referral_participants'") as cursor:
                        result = await cursor.fetchone()
                        if result and 'user_id INTEGER UNIQUE' in result[0]:
                            needs_recreation = True
                    
                    if needs_recreation:
                        # نسخ البيانات القديمة
                        await db.execute('''
                            CREATE TABLE IF NOT EXISTS referral_participants_backup AS 
                            SELECT * FROM referral_participants
                        ''')
                        
                        # حذف الجدول القديم
                        await db.execute('DROP TABLE IF EXISTS referral_participants')
            except:
                pass
            
            # جدول مسابقة الإحالات
            await db.execute('''
                CREATE TABLE IF NOT EXISTS referral_participants (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    contest_id INTEGER,
                    user_id INTEGER,
                    username TEXT,
                    referral_code TEXT UNIQUE,
                    referred_by INTEGER,
                    referral_count INTEGER DEFAULT 0,
                    message_id INTEGER,
                    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(contest_id, user_id),
                    FOREIGN KEY(contest_id) REFERENCES contests(id)
                )
            ''')
            
            # محاولة استرجاع البيانات القديمة
            try:
                async with db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='referral_participants_backup'") as cursor:
                    if await cursor.fetchone():
                        await db.execute('''
                            INSERT OR IGNORE INTO referral_participants 
                            SELECT * FROM referral_participants_backup
                        ''')
                        await db.execute('DROP TABLE referral_participants_backup')
            except:
                pass
            
            # جدول التحقق من الاشتراك
            await db.execute('''
                CREATE TABLE IF NOT EXISTS subscription_checks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    channel_id TEXT,
                    is_subscribed INTEGER DEFAULT 1,
                    last_check TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            await db.commit()
    
    async def create_contest(self, owner_id: int, channel_id: str, 
                           contest_type: str, settings: dict) -> int:
        """إنشاء مسابقة جديدة"""
        async with aiosqlite.connect(self.db_name) as db:
            cursor = await db.execute('''
                INSERT INTO contests (owner_id, channel_id, contest_type, settings)
                VALUES (?, ?, ?, ?)
            ''', (owner_id, channel_id, contest_type, json.dumps(settings)))
            await db.commit()
            return cursor.lastrowid
    
    async def get_contest(self, contest_id: int) -> Optional[dict]:
        """الحصول على معلومات مسابقة"""
        async with aiosqlite.connect(self.db_name) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                'SELECT * FROM contests WHERE id = ?', (contest_id,)
            ) as cursor:
                row = await cursor.fetchone()
                if row:
                    return dict(row)
                return None
    
    async def get_active_contests_by_owner(self, owner_id: int) -> List[dict]:
        """الحصول على جميع المسابقات النشطة للمستخدم"""
        async with aiosqlite.connect(self.db_name) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute('''
                SELECT * FROM contests 
                WHERE owner_id = ? AND status = 'active'
            ''', (owner_id,)) as cursor:
                return [dict(row) for row in await cursor.fetchall()]
    
    async def end_contest(self, contest_id: int):
        """إنهاء المسابقة"""
        async with aiosqlite.connect(self.db_name) as db:
            await db.execute('''
                UPDATE contests 
                SET status = 'ended', ended_at = CURRENT_TIMESTAMP
                WHERE id = ?
            ''', (contest_id,))
            await db.commit()

# ═══════════════════════════════════════════════════════════════
# 🔍 وظائف التحقق من الاشتراك
# ═══════════════════════════════════════════════════════════════

async def check_user_subscription(
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    channel_id: str
) -> bool:
    """التحقق من اشتراك المستخدم في القناة"""
    try:
        # إزالة @ إذا كان موجوداً
        clean_channel_id = channel_id.replace('@', '')
        
        # محاولة مع @
        try:
            member = await context.bot.get_chat_member(f"@{clean_channel_id}", user_id)
            return member.status in [
                ChatMemberStatus.MEMBER,
                ChatMemberStatus.ADMINISTRATOR,
                ChatMemberStatus.OWNER
            ]
        except TelegramError as e:
            # إذا فشل، جرب بدون @
            if 'Chat not found' in str(e) or 'Bad Request' in str(e):
                try:
                    member = await context.bot.get_chat_member(clean_channel_id, user_id)
                    return member.status in [
                        ChatMemberStatus.MEMBER,
                        ChatMemberStatus.ADMINISTRATOR,
                        ChatMemberStatus.OWNER
                    ]
                except TelegramError:
                    return False
            return False
    except Exception:
        return False

async def check_multiple_subscriptions(
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    channels: List[str]
) -> Tuple[bool, List[str]]:
    """التحقق من اشتراك المستخدم في عدة قنوات"""
    not_subscribed = []
    
    for channel in channels:
        # تجاهل القنوات الفارغة
        if not channel or channel.strip() == '':
            continue
            
        is_subscribed = await check_user_subscription(context, user_id, channel)
        if not is_subscribed:
            not_subscribed.append(channel)
    
    return len(not_subscribed) == 0, not_subscribed

# ═══════════════════════════════════════════════════════════════
# 🗳️ مسابقة التصويت (Voting Contest)
# ═══════════════════════════════════════════════════════════════

class VotingContest:
    """إدارة مسابقة التصويت"""
    
    def __init__(self, db: Database):
        self.db = db
    
    async def create(self, owner_id: int, channel_id: str, 
                    participants: List[str]) -> int:
        """إنشاء مسابقة تصويت"""
        settings = {
            'check_interval_hours': CHECK_SUBSCRIPTION_INTERVAL
        }
        contest_id = await self.db.create_contest(
            owner_id, channel_id, 'voting', settings
        )
        
        # إضافة المتسابقين إذا كانوا موجودين
        if participants:
            async with aiosqlite.connect(self.db.db_name) as db:
                for name in participants:
                    await db.execute('''
                        INSERT INTO voting_participants (contest_id, name)
                        VALUES (?, ?)
                    ''', (contest_id, name))
                await db.commit()
        
        return contest_id
    
    async def publish_participants(
        self,
        context: ContextTypes.DEFAULT_TYPE,
        contest_id: int,
        channel_id: str
    ):
        """نشر المتسابقين في القناة"""
        async with aiosqlite.connect(self.db.db_name) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute('''
                SELECT * FROM voting_participants WHERE contest_id = ?
            ''', (contest_id,)) as cursor:
                participants = await cursor.fetchall()
        
        for participant in participants:
            keyboard = [[
                InlineKeyboardButton(
                    "❤️ صوّت", 
                    callback_data=f"vote_{participant['id']}"
                )
            ]]
            
            message = await context.bot.send_message(
                chat_id=channel_id,
                text=f"🎯 المتسابق: {participant['name']}\n\n"
                     f"❤️ عدد الأصوات: 0",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            
            # حفظ معرف الرسالة
            async with aiosqlite.connect(self.db.db_name) as db:
                await db.execute('''
                    UPDATE voting_participants 
                    SET message_id = ? 
                    WHERE id = ?
                ''', (message.message_id, participant['id']))
                await db.commit()
    
    async def handle_vote(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ):
        """معالجة التصويت"""
        query = update.callback_query
        
        participant_id = int(query.data.split('_')[1])
        user_id = query.from_user.id
        
        # الحصول على معلومات المسابقة
        async with aiosqlite.connect(self.db.db_name) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute('''
                SELECT vp.*, c.channel_id, c.status
                FROM voting_participants vp
                JOIN contests c ON vp.contest_id = c.id
                WHERE vp.id = ?
            ''', (participant_id,)) as cursor:
                participant = await cursor.fetchone()
        
        if not participant or participant['status'] != 'active':
            await query.answer("❌ المسابقة منتهية!", show_alert=True)
            return
        
        channel_id = participant['channel_id']
        
        # التحقق من الاشتراك في القناتين
        channels_to_check = [OFFICIAL_CHANNEL, channel_id]
        not_subscribed = []
        
        for channel in channels_to_check:
            is_subscribed = await check_user_subscription(context, user_id, channel)
            if not is_subscribed:
                not_subscribed.append(channel)
        
        if not_subscribed:
            # إنشاء أزرار الاشتراك
            keyboard = []
            for channel in not_subscribed:
                keyboard.append([
                    InlineKeyboardButton(
                        f"📢 اشترك في {channel}",
                        url=f"https://t.me/{channel.replace('@', '')}"
                    )
                ])
            
            keyboard.append([
                InlineKeyboardButton(
                    "✅ تحقق من الاشتراك",
                    callback_data=f"check_vote_{participant_id}"
                )
            ])
            
            await query.answer()
            await context.bot.send_message(
                chat_id=user_id,
                text="⚠️ *يجب الاشتراك في القنوات التالية للتصويت:*\n\n"
                     "اضغط على الأزرار أدناه للاشتراك، ثم اضغط 'تحقق من الاشتراك'",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        # التحقق من عدم التصويت سابقاً
        async with aiosqlite.connect(self.db.db_name) as db:
            async with db.execute('''
                SELECT id FROM votes 
                WHERE participant_id = ? AND user_id = ?
            ''', (participant_id, user_id)) as cursor:
                existing_vote = await cursor.fetchone()
        
        if existing_vote:
            await query.answer("✅ لقد صوّت بالفعل!", show_alert=True)
            return
        
        # إضافة الصوت
        async with aiosqlite.connect(self.db.db_name) as db:
            await db.execute('''
                INSERT INTO votes (participant_id, user_id)
                VALUES (?, ?)
            ''', (participant_id, user_id))
            
            await db.execute('''
                UPDATE voting_participants 
                SET votes = votes + 1 
                WHERE id = ?
            ''', (participant_id,))
            
            await db.commit()
            
            # الحصول على عدد الأصوات الجديد
            async with db.execute('''
                SELECT votes FROM voting_participants WHERE id = ?
            ''', (participant_id,)) as cursor:
                new_votes = (await cursor.fetchone())[0]
        
        # تحديث الرسالة
        try:
            await context.bot.edit_message_text(
                chat_id=channel_id,
                message_id=participant['message_id'],
                text=f"🎯 المتسابق: {participant['name']}\n\n"
                     f"❤️ عدد الأصوات: {new_votes}",
                reply_markup=query.message.reply_markup
            )
        except TelegramError:
            pass
        
        await query.answer("✅ تم التصويت بنجاح!", show_alert=True)
        
        # حفظ معلومات التحقق من الاشتراك
        async with aiosqlite.connect(self.db.db_name) as db:
            await db.execute('''
                INSERT OR REPLACE INTO subscription_checks 
                (user_id, channel_id, is_subscribed)
                VALUES (?, ?, 1)
            ''', (user_id, channel_id))
            await db.commit()
    
    async def check_subscriptions_task(
        self,
        context: ContextTypes.DEFAULT_TYPE
    ):
        """مهمة دورية للتحقق من الاشتراكات"""
        async with aiosqlite.connect(self.db.db_name) as db:
            db.row_factory = aiosqlite.Row
            
            # الحصول على جميع الأصوات النشطة
            async with db.execute('''
                SELECT v.*, vp.contest_id, c.channel_id
                FROM votes v
                JOIN voting_participants vp ON v.participant_id = vp.id
                JOIN contests c ON vp.contest_id = c.id
                WHERE c.status = 'active'
            ''') as cursor:
                votes = await cursor.fetchall()
        
        for vote in votes:
            user_id = vote['user_id']
            channel_id = vote['channel_id']
            
            # التحقق من الاشتراك
            is_subscribed = await check_user_subscription(
                context, user_id, channel_id
            )
            
            if not is_subscribed:
                # حذف الصوت
                async with aiosqlite.connect(self.db.db_name) as db:
                    await db.execute(
                        'DELETE FROM votes WHERE id = ?',
                        (vote['id'],)
                    )
                    await db.execute('''
                        UPDATE voting_participants 
                        SET votes = votes - 1 
                        WHERE id = ?
                    ''', (vote['participant_id'],))
                    await db.commit()
                
                logger.info(
                    f"Removed vote from user {user_id} "
                    f"for leaving channel {channel_id}"
                )
    
    async def end_contest(
        self,
        context: ContextTypes.DEFAULT_TYPE,
        contest_id: int
    ):
        """إنهاء المسابقة ونشر النتائج"""
        contest = await self.db.get_contest(contest_id)
        if not contest:
            return
        
        channel_id = contest['channel_id']
        
        logger.info(f"Starting final subscription check for voting contest {contest_id}")
        
        # الفحص النهائي: حذف جميع الأصوات من المستخدمين غير المشتركين
        async with aiosqlite.connect(self.db.db_name) as db:
            db.row_factory = aiosqlite.Row
            
            # الحصول على جميع الأصوات
            async with db.execute('''
                SELECT DISTINCT v.user_id, v.participant_id
                FROM votes v
                JOIN voting_participants vp ON v.participant_id = vp.id
                WHERE vp.contest_id = ?
            ''', (contest_id,)) as cursor:
                all_votes = await cursor.fetchall()
        
        # التحقق من اشتراك كل مصوت
        removed_votes_count = 0
        for vote in all_votes:
            user_id = vote['user_id']
            
            # التحقق من الاشتراك في القناتين
            channels = [OFFICIAL_CHANNEL, channel_id]
            is_subscribed, _ = await check_multiple_subscriptions(
                context, user_id, channels
            )
            
            if not is_subscribed:
                # حذف الصوت
                async with aiosqlite.connect(self.db.db_name) as db:
                    await db.execute('''
                        DELETE FROM votes 
                        WHERE user_id = ? AND participant_id = ?
                    ''', (user_id, vote['participant_id']))
                    
                    await db.execute('''
                        UPDATE voting_participants 
                        SET votes = votes - 1 
                        WHERE id = ?
                    ''', (vote['participant_id'],))
                    
                    await db.commit()
                
                removed_votes_count += 1
                logger.info(f"Removed vote from user {user_id} (not subscribed)")
        
        if removed_votes_count > 0:
            logger.info(f"Removed {removed_votes_count} votes from unsubscribed users")
        
        # الحصول على جميع المتسابقين مع message_id والأصوات النهائية
        async with aiosqlite.connect(self.db.db_name) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute('''
                SELECT name, votes, message_id
                FROM voting_participants 
                WHERE contest_id = ?
                ORDER BY votes DESC
            ''', (contest_id,)) as cursor:
                results = await cursor.fetchall()
        
        # حذف أزرار التصويت من جميع المنشورات
        for result in results:
            if result['message_id']:
                try:
                    await context.bot.edit_message_text(
                        chat_id=channel_id,
                        message_id=result['message_id'],
                        text=f"🎯 المتسابق: {result['name']}\n\n"
                             f"❤️ عدد الأصوات النهائي: {result['votes']}"
                    )
                except TelegramError:
                    pass
        
        # تنسيق النتائج
        results_text = "🏆 *انتهت المسابقة!*\n\n"
        results_text += "📊 *النتائج النهائية:*\n\n"
        
        for i, result in enumerate(results, 1):
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "▫️"
            results_text += (
                f"{medal} {result['name']}: "
                f"{result['votes']} صوت\n"
            )
        
        # نشر النتائج
        await context.bot.send_message(
            chat_id=channel_id,
            text=results_text,
            parse_mode=ParseMode.MARKDOWN
        )
        
        # إنهاء المسابقة في قاعدة البيانات
        await self.db.end_contest(contest_id)
        
        logger.info(f"Voting contest {contest_id} ended successfully")

# ═══════════════════════════════════════════════════════════════
# 🎰 عجلة الحظ (Lucky Wheel)
# ═══════════════════════════════════════════════════════════════

class LuckyWheelContest:
    """إدارة مسابقة عجلة الحظ"""
    
    def __init__(self, db: Database):
        self.db = db
    
    async def create(
        self,
        owner_id: int,
        channel_id: str,
        max_participants: int,
        winners_count: int,
        custom_message: str = None
    ) -> int:
        """إنشاء مسابقة عجلة حظ"""
        settings = {
            'max_participants': max_participants,
            'winners_count': winners_count,
            'custom_message': custom_message or ""
        }
        
        contest_id = await self.db.create_contest(
            owner_id, channel_id, 'lucky_wheel', settings
        )
        
        return contest_id
    
    async def publish_contest(
        self,
        context: ContextTypes.DEFAULT_TYPE,
        contest_id: int,
        channel_id: str,
        max_participants: int,
        custom_message: str = None
    ) -> int:
        """نشر مسابقة عجلة الحظ"""
        keyboard = [[
            InlineKeyboardButton(
                "🎫 الانضمام للمسابقة",
                callback_data=f"lucky_join_{contest_id}"
            )
        ]]
        
        # النص الأساسي
        base_text = f"🎰 *مسابقة عجلة الحظ!*\n\n"
        
        # إضافة النص المخصص إذا وجد
        if custom_message:
            base_text += f"{custom_message}\n\n"
        
        base_text += f"👥 المشتركون: 0/{max_participants}\n\n"
        base_text += "اضغط للانضمام والحصول على فرصتك!"
        
        message = await context.bot.send_message(
            chat_id=channel_id,
            text=base_text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
        
        # حفظ معرف الرسالة
        async with aiosqlite.connect(self.db.db_name) as db:
            await db.execute('''
                UPDATE contests 
                SET settings = json_set(settings, '$.message_id', ?)
                WHERE id = ?
            ''', (message.message_id, contest_id))
            await db.commit()
        
        return message.message_id
    
    async def handle_join(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ):
        """معالجة الانضمام للمسابقة"""
        query = update.callback_query
        
        contest_id = int(query.data.split('_')[2])
        user_id = query.from_user.id
        username = query.from_user.username or f"user_{user_id}"
        
        # الحصول على معلومات المسابقة
        contest = await self.db.get_contest(contest_id)
        if not contest or contest['status'] != 'active':
            await query.answer("❌ المسابقة منتهية!", show_alert=True)
            return
        
        channel_id = contest['channel_id']
        settings = json.loads(contest['settings'])
        max_participants = settings['max_participants']
        
        # التحقق من الاشتراك في قناة المسابقة فقط (بدون القناة الرسمية)
        is_subscribed = await check_user_subscription(context, user_id, channel_id)
        
        if not is_subscribed:
            await query.answer(
                f"⚠️ يجب الاشتراك في القناة {channel_id} للانضمام!",
                show_alert=True
            )
            return
        
        # التحقق من عدم الانضمام سابقاً
        async with aiosqlite.connect(self.db.db_name) as db:
            async with db.execute('''
                SELECT id FROM lucky_participants 
                WHERE contest_id = ? AND user_id = ?
            ''', (contest_id, user_id)) as cursor:
                existing = await cursor.fetchone()
        
        if existing:
            await query.answer("✅ أنت مشترك بالفعل في المسابقة!", show_alert=True)
            return
        
        # الحصول على عدد المشتركين الحالي
        async with aiosqlite.connect(self.db.db_name) as db:
            async with db.execute('''
                SELECT COUNT(*) FROM lucky_participants 
                WHERE contest_id = ?
            ''', (contest_id,)) as cursor:
                current_count = (await cursor.fetchone())[0]
        
        if current_count >= max_participants:
            await query.answer(
                "❌ المسابقة مكتملة! العدد الأقصى تم الوصول إليه",
                show_alert=True
            )
            return
        
        # إضافة المشترك
        async with aiosqlite.connect(self.db.db_name) as db:
            await db.execute('''
                INSERT INTO lucky_participants (contest_id, user_id, username)
                VALUES (?, ?, ?)
            ''', (contest_id, user_id, username))
            await db.commit()
        
        new_count = current_count + 1
        
        # تحديث الرسالة
        try:
            message_id = settings.get('message_id')
            custom_message = settings.get('custom_message', '')
            
            if message_id:
                # النص الأساسي
                base_text = f"🎰 *مسابقة عجلة الحظ!*\n\n"
                
                # إضافة النص المخصص إذا وجد
                if custom_message:
                    base_text += f"{custom_message}\n\n"
                
                base_text += f"👥 المشتركون: {new_count}/{max_participants}\n\n"
                base_text += "اضغط للانضمام والحصول على فرصتك!"
                
                await context.bot.edit_message_text(
                    chat_id=channel_id,
                    message_id=message_id,
                    text=base_text,
                    reply_markup=query.message.reply_markup,
                    parse_mode=ParseMode.MARKDOWN
                )
        except TelegramError:
            pass
        
        await query.answer("✅ تم الانضمام بنجاح! حظاً موفقاً 🍀", show_alert=True)
        
        # إذا اكتمل العدد، إجراء السحب تلقائياً
        if new_count >= max_participants:
            await self.draw_winners(context, contest_id)
    
    async def draw_winners(
        self,
        context: ContextTypes.DEFAULT_TYPE,
        contest_id: int
    ):
        """إجراء السحب واختيار الفائزين"""
        contest = await self.db.get_contest(contest_id)
        if not contest:
            return
        
        settings = json.loads(contest['settings'])
        winners_count = settings['winners_count']
        channel_id = contest['channel_id']
        
        logger.info(f"Starting final subscription check for lucky wheel contest {contest_id}")
        
        # الفحص النهائي: حذف المشتركين غير المشتركين في القناة
        async with aiosqlite.connect(self.db.db_name) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute('''
                SELECT user_id, username 
                FROM lucky_participants 
                WHERE contest_id = ?
            ''', (contest_id,)) as cursor:
                all_participants = await cursor.fetchall()
        
        # التحقق من اشتراك كل مشارك
        removed_count = 0
        valid_participants = []
        
        for participant in all_participants:
            user_id = participant['user_id']
            
            # التحقق من الاشتراك في القناتين
            channels = [OFFICIAL_CHANNEL, channel_id]
            is_subscribed, _ = await check_multiple_subscriptions(
                context, user_id, channels
            )
            
            if is_subscribed:
                valid_participants.append(participant)
            else:
                # حذف المشترك
                async with aiosqlite.connect(self.db.db_name) as db:
                    await db.execute('''
                        DELETE FROM lucky_participants 
                        WHERE contest_id = ? AND user_id = ?
                    ''', (contest_id, user_id))
                    await db.commit()
                
                removed_count += 1
                logger.info(f"Removed participant {user_id} (not subscribed)")
        
        if removed_count > 0:
            logger.info(f"Removed {removed_count} participants from unsubscribed users")
        
        # اختيار الفائزين من المشتركين الصالحين فقط
        if not valid_participants:
            await context.bot.send_message(
                chat_id=channel_id,
                text="❌ لا يوجد مشتركون صالحون للسحب!",
                parse_mode=ParseMode.MARKDOWN
            )
            await self.db.end_contest(contest_id)
            return
        
        winners = random.sample(
            valid_participants,
            min(winners_count, len(valid_participants))
        )
        
        # تنسيق النتائج
        results_text = "🎊 *نتائج السحب!*\n\n"
        results_text += "🏆 *الفائزون:*\n\n"
        
        for i, winner in enumerate(winners, 1):
            username = winner['username']
            user_id = winner['user_id']
            
            if username.startswith('user_'):
                results_text += f"{i}. ID: `{user_id}`\n"
            else:
                results_text += f"{i}. @{username} (ID: `{user_id}`)\n"
        
        results_text += "\n🎉 مبروك للفائزين!"
        
        # نشر النتائج
        try:
            message_id = settings.get('message_id')
            if message_id:
                await context.bot.edit_message_text(
                    chat_id=channel_id,
                    message_id=message_id,
                    text=results_text,
                    parse_mode=ParseMode.MARKDOWN
                )
        except TelegramError:
            await context.bot.send_message(
                chat_id=channel_id,
                text=results_text,
                parse_mode=ParseMode.MARKDOWN
            )
        
        # إنهاء المسابقة
        await self.db.end_contest(contest_id)
        
        # إرسال إشعارات للفائزين
        for winner in winners:
            try:
                await context.bot.send_message(
                    chat_id=winner['user_id'],
                    text="🎉 مبروك! لقد فزت في المسابقة!"
                )
            except TelegramError:
                pass
        
        logger.info(f"Lucky wheel contest {contest_id} ended successfully")

# ═══════════════════════════════════════════════════════════════
# 🔗 مسابقة الإحالات (Referral Contest)
# ═══════════════════════════════════════════════════════════════

class ReferralContest:
    """إدارة مسابقة الإحالات"""
    
    def __init__(self, db: Database):
        self.db = db
    
    async def create(
        self,
        owner_id: int,
        channel_id: str,
        message_text: str
    ) -> int:
        """إنشاء مسابقة إحالات"""
        settings = {
            'message_text': message_text
        }
        
        contest_id = await self.db.create_contest(
            owner_id, channel_id, 'referral', settings
        )
        
        return contest_id
    
    async def publish_contest(
        self,
        context: ContextTypes.DEFAULT_TYPE,
        contest_id: int,
        channel_id: str,
        message_text: str
    ) -> int:
        """نشر مسابقة الإحالات"""
        keyboard = [[
            InlineKeyboardButton(
                "🚀 الانضمام للمسابقة",
                url=f"https://t.me/{context.bot.username}?start=ref_{contest_id}"
            )
        ]]
        
        message = await context.bot.send_message(
            chat_id=channel_id,
            text=f"{message_text}\n\n"
                 f"👇 اضغط للانضمام والحصول على رابط الإحالة الخاص بك!",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
        
        # حفظ رابط المنشور في إعدادات المسابقة
        async with aiosqlite.connect(self.db.db_name) as db:
            # الحصول على الإعدادات الحالية
            async with db.execute(
                'SELECT settings FROM contests WHERE id = ?', (contest_id,)
            ) as cursor:
                result = await cursor.fetchone()
                if result:
                    settings = json.loads(result[0])
                else:
                    settings = {}
            
            # إضافة معرف الرسالة ورابط المنشور
            settings['contest_message_id'] = message.message_id
            
            # تكوين رابط المنشور
            clean_channel = channel_id.replace('@', '')
            contest_post_link = f"https://t.me/{clean_channel}/{message.message_id}"
            settings['contest_post_link'] = contest_post_link
            
            await db.execute('''
                UPDATE contests 
                SET settings = ?
                WHERE id = ?
            ''', (json.dumps(settings), contest_id))
            await db.commit()
        
        return message.message_id
    
    async def handle_referral_join(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        contest_id: int,
        referrer_id: Optional[int] = None
    ):
        """معالجة الانضمام عبر رابط الإحالة"""
        user_id = update.effective_user.id
        username = update.effective_user.username or f"user_{user_id}"
        
        # تحديد ما إذا كان callback أم message
        is_callback = update.callback_query is not None
        
        # الحصول على معلومات المسابقة
        contest = await self.db.get_contest(contest_id)
        if not contest or contest['status'] != 'active':
            if is_callback:
                await update.callback_query.answer("❌ المسابقة منتهية!", show_alert=True)
            else:
                await update.message.reply_text("❌ المسابقة منتهية!")
            return
        
        channel_id = contest['channel_id']
        
        # سجل للتحقق
        logger.info(f"Checking subscriptions for user {user_id}")
        logger.info(f"Official channel: {OFFICIAL_CHANNEL}")
        logger.info(f"Contest channel: {channel_id}")
        logger.info(f"Referrer ID: {referrer_id}")
        
        # التحقق من الاشتراك في القناتين
        channels = [OFFICIAL_CHANNEL, channel_id]
        is_subscribed, not_subscribed = await check_multiple_subscriptions(
            context, user_id, channels
        )
        
        logger.info(f"Not subscribed to: {not_subscribed}")
        
        if not_subscribed:
            keyboard = []
            
            # إضافة أزرار الاشتراك لكل قناة غير مشترك فيها
            for channel in not_subscribed:
                clean_channel = channel.replace('@', '')
                keyboard.append([
                    InlineKeyboardButton(
                        f"📢 اشترك في {channel}",
                        url=f"https://t.me/{clean_channel}"
                    )
                ])
            
            keyboard.append([
                InlineKeyboardButton(
                    "✅ تحقق من الاشتراك",
                    callback_data=f"check_ref_{contest_id}_{referrer_id or 0}"
                )
            ])
            
            # إنشاء قائمة القنوات المطلوبة
            channels_list = "\n".join([f"• {ch}" for ch in not_subscribed])
            
            message_text = (
                "⚠️ يجب الاشتراك في القنوات التالية أولاً:\n\n"
                f"{channels_list}\n\n"
                "اضغط على الأزرار أدناه للاشتراك، ثم اضغط 'تحقق من الاشتراك'"
            )
            
            if is_callback:
                await update.callback_query.answer()
                await context.bot.send_message(
                    chat_id=user_id,
                    text=message_text,
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            else:
                await update.message.reply_text(
                    message_text,
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
            return
        
        # التحقق من وجود المستخدم في المسابقة
        async with aiosqlite.connect(self.db.db_name) as db:
            async with db.execute('''
                SELECT id, referral_code, referral_count, referred_by 
                FROM referral_participants 
                WHERE contest_id = ? AND user_id = ?
            ''', (contest_id, user_id)) as cursor:
                existing = await cursor.fetchone()
        
        # إذا دخل برابط شخص آخر (referrer_id موجود)
        if referrer_id:
            if existing:
                # المستخدم موجود بالفعل - أرسل له رابطه
                is_temp = existing[1] and existing[1].endswith('_temp')
                
                if is_temp:
                    # لا يزال "إحالة فقط" - أخبره بالدخول من رابط المسابقة
                    # الحصول على رابط المنشور
                    contest_info = await self.db.get_contest(contest_id)
                    settings = json.loads(contest_info['settings'])
                    contest_post_link = settings.get('contest_post_link', f"https://t.me/{context.bot.username}?start=ref_{contest_id}")
                    
                    # تجنب مشاكل Markdown مع الروابط
                    message_text = (
                        f"✅ تم تسجيل دخولك!\n\n"
                        f"💡 للحصول على رابط إحالة خاص بك والمشاركة في المسابقة،\n"
                        f"يجب عليك الدخول من رابط المسابقة في القناة:\n\n"
                        f"{contest_post_link}"
                    )
                else:
                    # مشارك كامل
                    referral_link = (
                        f"https://t.me/{context.bot.username}"
                        f"?start=ref_{contest_id}_{user_id}"
                    )
                    
                    message_text = (
                        f"✅ أنت مشترك بالفعل في المسابقة!\n\n"
                        f"🔗 رابط الإحالة الخاص بك:\n"
                        f"`{referral_link}`\n\n"
                        f"👥 عدد إحالاتك: {existing[2]}"
                    )
            else:
                # المستخدم جديد - سجله كإحالة فقط (بدون رابط أو منشور)
                referral_code = f"ref_{contest_id}_{user_id}_temp"
                
                async with aiosqlite.connect(self.db.db_name) as db:
                    await db.execute('''
                        INSERT INTO referral_participants 
                        (contest_id, user_id, username, referral_code, referred_by)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (contest_id, user_id, username, referral_code, referrer_id))
                    await db.commit()
                
                # زيادة عداد المُحيل
                async with aiosqlite.connect(self.db.db_name) as db:
                    await db.execute('''
                        UPDATE referral_participants 
                        SET referral_count = referral_count + 1 
                        WHERE user_id = ? AND contest_id = ?
                    ''', (referrer_id, contest_id))
                    await db.commit()
                
                # تحديث منشور المُحيل
                await self.update_user_post(context, contest_id, referrer_id)
                
                # إشعار المُحيل
                try:
                    await context.bot.send_message(
                        chat_id=referrer_id,
                        text=f"🎉 مبروك! حصلت على إحالة جديدة!\n"
                             f"👤 المستخدم: @{username}"
                    )
                except TelegramError:
                    pass
                
                # رسالة للمستخدم الجديد - استخدام رابط المنشور
                contest_info = await self.db.get_contest(contest_id)
                settings = json.loads(contest_info['settings'])
                contest_post_link = settings.get('contest_post_link', f"https://t.me/{context.bot.username}?start=ref_{contest_id}")
                
                # تجنب مشاكل Markdown
                message_text = (
                    f"✅ تم تسجيل دخولك!\n\n"
                    f"💡 للحصول على رابط إحالة خاص بك والمشاركة في المسابقة،\n"
                    f"يجب عليك الدخول من رابط المسابقة في القناة:\n\n"
                    f"{contest_post_link}"
                )
            
            if is_callback:
                await update.callback_query.answer()
                await context.bot.send_message(
                    chat_id=user_id,
                    text=message_text
                )
            else:
                await update.message.reply_text(
                    message_text
                )
            return
        
        # إذا دخل من الرابط الأساسي (بدون referrer_id)
        if existing:
            # المستخدم موجود - التحقق إذا كان "إحالة فقط" أو "مشارك كامل"
            is_temp = existing[1] and existing[1].endswith('_temp')  # referral_code
            
            if is_temp:
                # ترقية من "إحالة فقط" إلى "مشارك كامل"
                new_referral_code = f"ref_{contest_id}_{user_id}"
                
                async with aiosqlite.connect(self.db.db_name) as db:
                    await db.execute('''
                        UPDATE referral_participants 
                        SET referral_code = ?
                        WHERE contest_id = ? AND user_id = ?
                    ''', (new_referral_code, contest_id, user_id))
                    await db.commit()
                
                # نشر منشور في القناة
                await self.publish_user_post(context, contest_id, user_id, username, channel_id)
                
                # إرسال رابط الإحالة
                referral_link = (
                    f"https://t.me/{context.bot.username}"
                    f"?start=ref_{contest_id}_{user_id}"
                )
                
                message_text = (
                    f"🎉 مبروك! تمت ترقيتك إلى مشارك رسمي!\n\n"
                    f"🔗 رابط الإحالة الخاص بك:\n"
                    f"`{referral_link}`\n\n"
                    f"👥 عدد إحالاتك: {existing[2]}\n\n"
                    f"شارك هذا الرابط مع أصدقائك للحصول على نقاط!"
                )
            else:
                # مشارك كامل بالفعل
                referral_link = (
                    f"https://t.me/{context.bot.username}"
                    f"?start=ref_{contest_id}_{user_id}"
                )
                
                message_text = (
                    f"✅ أنت مشترك بالفعل!\n\n"
                    f"🔗 رابط الإحالة الخاص بك:\n"
                    f"`{referral_link}`\n\n"
                    f"👥 عدد إحالاتك: {existing[2]}"
                )
            
            if is_callback:
                await update.callback_query.answer()
                await context.bot.send_message(
                    chat_id=user_id,
                    text=message_text,
                    parse_mode=ParseMode.MARKDOWN
                )
            else:
                await update.message.reply_text(
                    message_text,
                    parse_mode=ParseMode.MARKDOWN
                )
            return
        
        # مستخدم جديد - إنشاء حساب كامل مع رابط ومنشور
        referral_code = f"ref_{contest_id}_{user_id}"
        
        async with aiosqlite.connect(self.db.db_name) as db:
            await db.execute('''
                INSERT INTO referral_participants 
                (contest_id, user_id, username, referral_code, referred_by)
                VALUES (?, ?, ?, ?, NULL)
            ''', (contest_id, user_id, username, referral_code))
            await db.commit()
        
        # نشر منشور في القناة
        await self.publish_user_post(context, contest_id, user_id, username, channel_id)
        
        # إرسال رابط الإحالة
        referral_link = (
            f"https://t.me/{context.bot.username}"
            f"?start=ref_{contest_id}_{user_id}"
        )
        
        message_text = (
            f"✅ تم الانضمام بنجاح!\n\n"
            f"🔗 رابط الإحالة الخاص بك:\n"
            f"`{referral_link}`\n\n"
            f"شارك هذا الرابط مع أصدقائك للحصول على نقاط!"
        )
        
        if is_callback:
            await update.callback_query.answer()
            await context.bot.send_message(
                chat_id=user_id,
                text=message_text,
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await update.message.reply_text(
                message_text,
                parse_mode=ParseMode.MARKDOWN
            )
    
    async def publish_user_post(
        self,
        context: ContextTypes.DEFAULT_TYPE,
        contest_id: int,
        user_id: int,
        username: str,
        channel_id: str
    ):
        """نشر منشور المشترك في القناة"""
        keyboard = [[
            InlineKeyboardButton(
                "👥 عدد الإحالات: 0",
                callback_data=f"ref_count_{contest_id}_{user_id}"
            )
        ]]
        
        display_name = f"@{username}" if not username.startswith('user_') else f"ID: {user_id}"
        
        message = await context.bot.send_message(
            chat_id=channel_id,
            text=f"🎯 {display_name} انضم للمسابقة!",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        # حفظ معرف الرسالة
        async with aiosqlite.connect(self.db.db_name) as db:
            await db.execute('''
                UPDATE referral_participants 
                SET message_id = ? 
                WHERE user_id = ? AND contest_id = ?
            ''', (message.message_id, user_id, contest_id))
            await db.commit()
    
    async def update_user_post(
        self,
        context: ContextTypes.DEFAULT_TYPE,
        contest_id: int,
        user_id: int
    ):
        """تحديث منشور المستخدم"""
        async with aiosqlite.connect(self.db.db_name) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute('''
                SELECT rp.*, c.channel_id 
                FROM referral_participants rp
                JOIN contests c ON rp.contest_id = c.id
                WHERE rp.user_id = ? AND rp.contest_id = ?
            ''', (user_id, contest_id)) as cursor:
                participant = await cursor.fetchone()
        
        if not participant or not participant['message_id']:
            return
        
        keyboard = [[
            InlineKeyboardButton(
                f"👥 عدد الإحالات: {participant['referral_count']}",
                callback_data=f"ref_count_{contest_id}_{user_id}"
            )
        ]]
        
        username = participant['username']
        display_name = f"@{username}" if not username.startswith('user_') else f"ID: {user_id}"
        
        try:
            await context.bot.edit_message_text(
                chat_id=participant['channel_id'],
                message_id=participant['message_id'],
                text=f"🎯 {display_name} انضم للمسابقة!",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except TelegramError:
            pass
    
    async def check_subscriptions_task(
        self,
        context: ContextTypes.DEFAULT_TYPE
    ):
        """مهمة دورية للتحقق من الاشتراكات"""
        async with aiosqlite.connect(self.db.db_name) as db:
            db.row_factory = aiosqlite.Row
            
            # الحصول على جميع المشتركين النشطين
            async with db.execute('''
                SELECT rp.*, c.channel_id
                FROM referral_participants rp
                JOIN contests c ON rp.contest_id = c.id
                WHERE c.status = 'active'
            ''') as cursor:
                participants = await cursor.fetchall()
        
        for participant in participants:
            user_id = participant['user_id']
            contest_id = participant['contest_id']
            channel_id = participant['channel_id']
            
            # التحقق من الاشتراك في القناتين
            channels = [OFFICIAL_CHANNEL, channel_id]
            is_subscribed, _ = await check_multiple_subscriptions(
                context, user_id, channels
            )
            
            if not is_subscribed:
                # حذف إحالاته من المُحيل
                if participant['referred_by']:
                    async with aiosqlite.connect(self.db.db_name) as db:
                        await db.execute('''
                            UPDATE referral_participants 
                            SET referral_count = referral_count - 1 
                            WHERE user_id = ? AND contest_id = ?
                        ''', (participant['referred_by'], contest_id))
                        await db.commit()
                    
                    # تحديث منشور المُحيل
                    await self.update_user_post(
                        context, contest_id, participant['referred_by']
                    )
                
                # حذف المستخدم
                async with aiosqlite.connect(self.db.db_name) as db:
                    await db.execute('''
                        DELETE FROM referral_participants 
                        WHERE id = ?
                    ''', (participant['id'],))
                    await db.commit()
                
                logger.info(
                    f"Removed user {user_id} from referral contest "
                    f"{contest_id} for leaving channels"
                )
    
    async def publish_leaderboard(
        self,
        context: ContextTypes.DEFAULT_TYPE,
        contest_id: int
    ):
        """نشر لوحة المتصدرين"""
        contest = await self.db.get_contest(contest_id)
        if not contest:
            return
        
        channel_id = contest['channel_id']
        
        # الحصول على أفضل 10
        async with aiosqlite.connect(self.db.db_name) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute('''
                SELECT user_id, username, referral_count 
                FROM referral_participants 
                WHERE contest_id = ?
                ORDER BY referral_count DESC
                LIMIT 10
            ''', (contest_id,)) as cursor:
                top_participants = await cursor.fetchall()
        
        if not top_participants:
            return
        
        # تنسيق اللوحة
        leaderboard_text = "🏆 *لوحة المتصدرين*\n\n"
        
        for i, participant in enumerate(top_participants, 1):
            username = participant['username']
            user_id = participant['user_id']
            count = participant['referral_count']
            
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
            
            if username.startswith('user_'):
                leaderboard_text += f"{medal} ID: `{user_id}` - {count} إحالة\n"
            else:
                leaderboard_text += f"{medal} @{username} - {count} إحالة\n"
        
        # نشر اللوحة
        await context.bot.send_message(
            chat_id=channel_id,
            text=leaderboard_text,
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def end_contest(
        self,
        context: ContextTypes.DEFAULT_TYPE,
        contest_id: int
    ):
        """إنهاء المسابقة ونشر النتائج"""
        contest = await self.db.get_contest(contest_id)
        if not contest:
            return
        
        channel_id = contest['channel_id']
        
        logger.info(f"Starting final subscription check for referral contest {contest_id}")
        
        # الفحص النهائي: حذف جميع المشاركين غير المشتركين
        async with aiosqlite.connect(self.db.db_name) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute('''
                SELECT id, user_id, referred_by, referral_count
                FROM referral_participants 
                WHERE contest_id = ?
            ''', (contest_id,)) as cursor:
                all_participants = await cursor.fetchall()
        
        # التحقق من اشتراك كل مشارك
        removed_count = 0
        for participant in all_participants:
            user_id = participant['user_id']
            
            # التحقق من الاشتراك في القناتين
            channels = [OFFICIAL_CHANNEL, channel_id]
            is_subscribed, _ = await check_multiple_subscriptions(
                context, user_id, channels
            )
            
            if not is_subscribed:
                # إذا كان لديه من أحاله، خصم الإحالة من المُحيل
                if participant['referred_by']:
                    async with aiosqlite.connect(self.db.db_name) as db:
                        await db.execute('''
                            UPDATE referral_participants 
                            SET referral_count = referral_count - 1 
                            WHERE user_id = ? AND contest_id = ?
                        ''', (participant['referred_by'], contest_id))
                        await db.commit()
                
                # خصم إحالاته من العداد (لأنهم سيُحذفون أيضاً إذا لم يكونوا مشتركين)
                # لكن لن نفعل شيء هنا لأن الحلقة ستتعامل مع كل مشارك
                
                # حذف المشارك
                async with aiosqlite.connect(self.db.db_name) as db:
                    await db.execute('''
                        DELETE FROM referral_participants 
                        WHERE id = ?
                    ''', (participant['id'],))
                    await db.commit()
                
                removed_count += 1
                logger.info(f"Removed participant {user_id} (not subscribed)")
        
        if removed_count > 0:
            logger.info(f"Removed {removed_count} participants from unsubscribed users")
            
            # تحديث عدادات الإحالات بعد الحذف
            # حساب العدد الصحيح لكل مشارك
            async with aiosqlite.connect(self.db.db_name) as db:
                # الحصول على جميع المشاركين المتبقين
                async with db.execute('''
                    SELECT user_id 
                    FROM referral_participants 
                    WHERE contest_id = ?
                ''', (contest_id,)) as cursor:
                    remaining = await cursor.fetchall()
                
                # إعادة حساب عدد الإحالات لكل مشارك
                for participant in remaining:
                    async with db.execute('''
                        SELECT COUNT(*) 
                        FROM referral_participants 
                        WHERE contest_id = ? AND referred_by = ?
                    ''', (contest_id, participant['user_id'])) as cursor:
                        count = (await cursor.fetchone())[0]
                    
                    await db.execute('''
                        UPDATE referral_participants 
                        SET referral_count = ? 
                        WHERE contest_id = ? AND user_id = ?
                    ''', (count, contest_id, participant['user_id']))
                
                await db.commit()
        
        # نشر لوحة المتصدرين النهائية
        await self.publish_leaderboard(context, contest_id)
        
        # إنهاء المسابقة
        await self.db.end_contest(contest_id)
        
        logger.info(f"Referral contest {contest_id} ended successfully")

# ═══════════════════════════════════════════════════════════════
# 🎮 معالجات الأوامر والرسائل
# ═══════════════════════════════════════════════════════════════

# متغيرات عامة
db = Database(DATABASE_NAME)
voting_contest = VotingContest(db)
lucky_wheel = LuckyWheelContest(db)
referral_contest = ReferralContest(db)

# حالات المحادثة
user_states: Dict[int, dict] = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج أمر /start"""
    user_id = update.effective_user.id
    
    # التحقق من وجود معامل (رابط إحالة)
    if context.args:
        param = context.args[0]
        
        if param.startswith('ref_'):
            parts = param.split('_')
            if len(parts) >= 2:
                contest_id = int(parts[1])
                referrer_id = int(parts[2]) if len(parts) > 2 else None
                
                await referral_contest.handle_referral_join(
                    update, context, contest_id, referrer_id
                )
                return
    
    # الرسالة الترحيبية
    keyboard = [
        [InlineKeyboardButton("🗳️ مسابقة تصويت", callback_data="create_voting")],
        [InlineKeyboardButton("🎰 عجلة الحظ", callback_data="create_lucky")],
        [InlineKeyboardButton("🔗 مسابقة إحالات", callback_data="create_referral")],
        [InlineKeyboardButton("📋 مسابقاتي", callback_data="my_contests")],
        [InlineKeyboardButton("❌ إيقاف مسابقة", callback_data="end_contest")],
    ]
    
    await update.message.reply_text(
        "🎯 *مرحباً في بوت المسابقات المتقدم!*\n\n"
        "اختر نوع المسابقة التي تريد إنشاءها:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN
    )

async def done_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج أمر /done لإنهاء إضافة المتسابقين"""
    user_id = update.effective_user.id
    
    if user_id not in user_states:
        return
    
    state_info = user_states[user_id]
    
    if state_info.get('state') == 'waiting_voting_participants':
        if 'contest_id' not in state_info:
            await update.message.reply_text("❌ لم تقم بإضافة أي متسابقين بعد!")
            return
        
        # التحقق من وجود متسابقين
        async with aiosqlite.connect(db.db_name) as db_conn:
            async with db_conn.execute('''
                SELECT COUNT(*) FROM voting_participants 
                WHERE contest_id = ?
            ''', (state_info['contest_id'],)) as cursor:
                count = (await cursor.fetchone())[0]
        
        if count < 2:
            await update.message.reply_text(
                "❌ يجب إضافة متسابقين على الأقل!\n"
                "أرسل أسماء إضافية أو /cancel للإلغاء"
            )
            return
        
        await update.message.reply_text(
            f"✅ تم إنشاء مسابقة التصويت بنجاح!\n"
            f"📊 عدد المتسابقين: {count}\n"
            f"تم نشرهم جميعًا في القناة."
        )
        
        del user_states[user_id]

async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج أمر /cancel لإلغاء العملية الحالية"""
    user_id = update.effective_user.id
    
    if user_id in user_states:
        state_info = user_states[user_id]
        
        # حذف المسابقة إذا كانت قيد الإنشاء
        if 'contest_id' in state_info:
            contest_id = state_info['contest_id']
            async with aiosqlite.connect(db.db_name) as db_conn:
                await db_conn.execute('DELETE FROM contests WHERE id = ?', (contest_id,))
                await db_conn.execute('DELETE FROM voting_participants WHERE contest_id = ?', (contest_id,))
                await db_conn.commit()
        
        del user_states[user_id]
        await update.message.reply_text("❌ تم إلغاء العملية.")
    else:
        await update.message.reply_text("لا توجد عملية جارية للإلغاء.")

async def skip_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج أمر /skip للتخطي"""
    user_id = update.effective_user.id
    
    if user_id not in user_states:
        return
    
    state_info = user_states[user_id]
    
    # معالجة التخطي حسب الحالة
    if state_info.get('state') == 'waiting_lucky_message':
        state_info['custom_message'] = None
        state_info['state'] = 'waiting_lucky_max'
        
        await update.message.reply_text(
            "⏭️ تم التخطي\n\n"
            "🔢 أرسل العدد الأقصى للمشتركين:\n"
            "(مثال: 100)"
        )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج الأزرار"""
    query = update.callback_query
    data = query.data
    user_id = query.from_user.id
    
    # مسابقة التصويت
    if data.startswith('vote_'):
        await voting_contest.handle_vote(update, context)
        return
    
    # عجلة الحظ
    if data.startswith('lucky_join_'):
        await lucky_wheel.handle_join(update, context)
        return
    
    # التحقق من الاشتراك للإحالة
    if data.startswith('check_ref_'):
        parts = data.split('_')
        contest_id = int(parts[2])
        referrer_id = int(parts[3]) if parts[3] != '0' else None
        
        # إعادة محاولة الانضمام
        await referral_contest.handle_referral_join(
            update, context, contest_id, referrer_id
        )
        return
    
    # إنشاء مسابقة تصويت
    if data == 'create_voting':
        await query.answer()
        user_states[user_id] = {'state': 'waiting_voting_channel'}
        await query.message.reply_text(
            "📢 أرسل معرف القناة (مثال: @channelname)\n"
            "تأكد من رفع البوت كمشرف مع صلاحية النشر!"
        )
        return
    
    # إنشاء عجلة حظ
    if data == 'create_lucky':
        await query.answer()
        user_states[user_id] = {'state': 'waiting_lucky_channel'}
        await query.message.reply_text(
            "📢 أرسل معرف القناة (مثال: @channelname)\n"
            "تأكد من رفع البوت كمشرف مع صلاحية النشر!"
        )
        return
    
    # إنشاء مسابقة إحالات
    if data == 'create_referral':
        await query.answer()
        user_states[user_id] = {'state': 'waiting_referral_channel'}
        await query.message.reply_text(
            "📢 أرسل معرف القناة (مثال: @channelname)\n"
            "تأكد من رفع البوت كمشرف مع صلاحية النشر!"
        )
        return
    
    # عرض المسابقات
    if data == 'my_contests':
        await query.answer()
        contests = await db.get_active_contests_by_owner(user_id)
        
        if not contests:
            await query.message.reply_text("ليس لديك مسابقات نشطة حالياً.")
            return
        
        text = "📋 مسابقاتك النشطة:\n\n"
        for contest in contests:
            contest_type = {
                'voting': '🗳️ تصويت',
                'lucky_wheel': '🎰 عجلة حظ',
                'referral': '🔗 إحالات'
            }.get(contest['contest_type'], contest['contest_type'])
            
            text += f"• {contest_type} - القناة: {contest['channel_id']}\n"
        
        await query.message.reply_text(text)
        return
    
    # إيقاف مسابقة
    if data == 'end_contest':
        await query.answer()
        contests = await db.get_active_contests_by_owner(user_id)
        
        if not contests:
            await query.message.reply_text("ليس لديك مسابقات نشطة لإيقافها.")
            return
        
        keyboard = []
        for contest in contests:
            contest_type = {
                'voting': '🗳️',
                'lucky_wheel': '🎰',
                'referral': '🔗'
            }.get(contest['contest_type'], '')
            
            keyboard.append([
                InlineKeyboardButton(
                    f"{contest_type} {contest['channel_id']}",
                    callback_data=f"confirm_end_{contest['id']}"
                )
            ])
        
        await query.message.reply_text(
            "اختر المسابقة التي تريد إيقافها:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    # تأكيد إيقاف المسابقة
    if data.startswith('confirm_end_'):
        await query.answer()
        contest_id = int(data.split('_')[2])
        
        contest = await db.get_contest(contest_id)
        if not contest or contest['owner_id'] != user_id:
            await query.message.reply_text("❌ غير مسموح!")
            return
        
        # إنهاء حسب النوع
        if contest['contest_type'] == 'voting':
            await voting_contest.end_contest(context, contest_id)
        elif contest['contest_type'] == 'lucky_wheel':
            await lucky_wheel.draw_winners(context, contest_id)
        elif contest['contest_type'] == 'referral':
            await referral_contest.end_contest(context, contest_id)
        
        await query.message.reply_text("✅ تم إنهاء المسابقة بنجاح!")
        return

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """معالج الرسائل النصية"""
    user_id = update.effective_user.id
    text = update.message.text
    
    if user_id not in user_states:
        return
    
    state_info = user_states[user_id]
    state = state_info.get('state')
    
    # ══════ مسابقة التصويت ══════
    if state == 'waiting_voting_channel':
        if not text.startswith('@'):
            await update.message.reply_text("❌ يجب أن يبدأ المعرف بـ @")
            return
        
        state_info['channel_id'] = text
        state_info['state'] = 'waiting_voting_participants'
        
        await update.message.reply_text(
            "👥 أرسل اسم المتسابق الأول:\n\n"
            "💡 بعد كل اسم سيتم نشره مباشرة في القناة\n"
            "استخدم /done عند الانتهاء من إضافة جميع المتسابقين"
        )
        return
    
    if state == 'waiting_voting_participants':
        # إنشاء المسابقة إذا لم تكن موجودة
        if 'contest_id' not in state_info:
            contest_id = await voting_contest.create(
                user_id, state_info['channel_id'], []
            )
            state_info['contest_id'] = contest_id
            await update.message.reply_text(
                "✅ تم إنشاء المسابقة!\n\n"
                "📝 يمكنك الآن إرسال أسماء المتسابقين واحدًا تلو الآخر\n"
                "أرسل /done عندما تنتهي"
            )
            return
        
        # إضافة المتسابق الجديد
        participant_name = text.strip()
        if not participant_name:
            return
        
        contest_id = state_info['contest_id']
        
        # إضافة المتسابق للقاعدة
        async with aiosqlite.connect(db.db_name) as db_conn:
            cursor = await db_conn.execute('''
                INSERT INTO voting_participants (contest_id, name)
                VALUES (?, ?)
            ''', (contest_id, participant_name))
            await db_conn.commit()
            participant_id = cursor.lastrowid
        
        # نشر المتسابق في القناة
        keyboard = [[
            InlineKeyboardButton(
                "❤️ صوّت", 
                callback_data=f"vote_{participant_id}"
            )
        ]]
        
        message = await context.bot.send_message(
            chat_id=state_info['channel_id'],
            text=f"🎯 المتسابق: {participant_name}\n\n"
                 f"❤️ عدد الأصوات: 0",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        # حفظ معرف الرسالة
        async with aiosqlite.connect(db.db_name) as db_conn:
            await db_conn.execute('''
                UPDATE voting_participants 
                SET message_id = ? 
                WHERE id = ?
            ''', (message.message_id, participant_id))
            await db_conn.commit()
        
        await update.message.reply_text(
            f"✅ تمت إضافة: {participant_name}\n\n"
            "📝 أرسل اسم متسابق آخر أو /done للإنهاء"
        )
        return
    
    # ══════ عجلة الحظ ══════
    if state == 'waiting_lucky_channel':
        if not text.startswith('@'):
            await update.message.reply_text("❌ يجب أن يبدأ المعرف بـ @")
            return
        
        state_info['channel_id'] = text
        state_info['state'] = 'waiting_lucky_message'
        
        await update.message.reply_text(
            "📝 أرسل نص المسابقة (اختياري):\n\n"
            "مثال: 🎁 الجائزة: 100 دولار\n\n"
            "أو أرسل /skip للتخطي"
        )
        return
    
    if state == 'waiting_lucky_message':
        custom_message = text.strip() if text.strip() != '/skip' else None
        state_info['custom_message'] = custom_message
        state_info['state'] = 'waiting_lucky_max'
        
        await update.message.reply_text(
            "🔢 أرسل العدد الأقصى للمشتركين:\n"
            "(مثال: 100)"
        )
        return
    
    if state == 'waiting_lucky_max':
        try:
            max_participants = int(text)
            if max_participants < 2:
                raise ValueError()
        except ValueError:
            await update.message.reply_text("❌ يجب إدخال رقم صحيح أكبر من 1!")
            return
        
        state_info['max_participants'] = max_participants
        state_info['state'] = 'waiting_lucky_winners'
        
        await update.message.reply_text(
            "🏆 أرسل عدد الفائزين:\n"
            "(مثال: 3)"
        )
        return
    
    if state == 'waiting_lucky_winners':
        try:
            winners_count = int(text)
            if winners_count < 1 or winners_count > state_info['max_participants']:
                raise ValueError()
        except ValueError:
            await update.message.reply_text(
                f"❌ يجب إدخال رقم بين 1 و {state_info['max_participants']}!"
            )
            return
        
        # إنشاء المسابقة
        contest_id = await lucky_wheel.create(
            user_id,
            state_info['channel_id'],
            state_info['max_participants'],
            winners_count,
            state_info.get('custom_message')
        )
        
        # نشر المسابقة
        await lucky_wheel.publish_contest(
            context,
            contest_id,
            state_info['channel_id'],
            state_info['max_participants'],
            state_info.get('custom_message')
        )
        
        await update.message.reply_text(
            "✅ تم إنشاء مسابقة عجلة الحظ بنجاح!\n"
            "تم نشر المسابقة في القناة."
        )
        
        del user_states[user_id]
        return
    
    # ══════ مسابقة الإحالات ══════
    if state == 'waiting_referral_channel':
        if not text.startswith('@'):
            await update.message.reply_text("❌ يجب أن يبدأ المعرف بـ @")
            return
        
        state_info['channel_id'] = text
        state_info['state'] = 'waiting_referral_message'
        
        await update.message.reply_text(
            "📝 أرسل رسالة المسابقة التي ستُنشر في القناة:\n\n"
            "يمكنك استخدام Markdown للتنسيق."
        )
        return
    
    if state == 'waiting_referral_message':
        # إنشاء المسابقة
        contest_id = await referral_contest.create(
            user_id, state_info['channel_id'], text
        )
        
        # نشر المسابقة
        await referral_contest.publish_contest(
            context, contest_id, state_info['channel_id'], text
        )
        
        await update.message.reply_text(
            "✅ تم إنشاء مسابقة الإحالات بنجاح!\n"
            "تم نشر المسابقة في القناة."
        )
        
        del user_states[user_id]
        return

# ═══════════════════════════════════════════════════════════════
# ⏰ المهام الدورية
# ═══════════════════════════════════════════════════════════════

async def periodic_subscription_check(context: ContextTypes.DEFAULT_TYPE):
    """التحقق الدوري من الاشتراكات"""
    logger.info("Running periodic subscription check...")
    
    # التحقق من اشتراكات التصويت
    await voting_contest.check_subscriptions_task(context)
    
    # التحقق من اشتراكات الإحالات
    await referral_contest.check_subscriptions_task(context)
    
    logger.info("Subscription check completed.")

# ═══════════════════════════════════════════════════════════════
# 🚀 نقطة البداية
# ═══════════════════════════════════════════════════════════════

async def post_init(application: Application):
    """إعدادات ما بعد التهيئة"""
    await db.init_db()
    logger.info("Database initialized successfully!")
    
    # جدولة المهمة الدورية (كل 3 ساعات)
    job_queue = application.job_queue
    job_queue.run_repeating(
        periodic_subscription_check,
        interval=CHECK_SUBSCRIPTION_INTERVAL * 3600,
        first=10
    )

def main():
    """الدالة الرئيسية"""
    # التحقق من التوكن
    if TELEGRAM_BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("❌ يرجى وضع توكن البوت في TELEGRAM_BOT_TOKEN")
        return
    
    if OFFICIAL_CHANNEL == "@YourOfficialChannel":
        print("⚠️ يرجى وضع معرف قناتك الرسمية في OFFICIAL_CHANNEL")
    
    # إنشاء التطبيق
    application = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .post_init(post_init)
        .build()
    )
    
    # إضافة المعالجات
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("done", done_command))
    application.add_handler(CommandHandler("cancel", cancel_command))
    application.add_handler(CommandHandler("skip", skip_command))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler)
    )
    
    # بدء البوت
    logger.info("🚀 Starting bot...")
    print("✅ البوت يعمل الآن!")
    print(f"📢 القناة الرسمية: {OFFICIAL_CHANNEL}")
    print(f"⏰ فترة التحقق: {CHECK_SUBSCRIPTION_INTERVAL} ساعات")
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
