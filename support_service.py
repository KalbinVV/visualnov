#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import uuid
import shutil
import threading
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SupportService:
    CLEANUP_INTERVAL = 60

    def __init__(self, bot_token: str, group_chat_id: int, temp_folder: str = 'static/temp_support'):
        self.bot_token = bot_token
        self.group_chat_id = group_chat_id
        self.temp_folder = temp_folder
        self.conversations: Dict[int, Dict[str, Any]] = {}
        self.app: Optional[Application] = None
        self._lock = threading.Lock()
        self._cleanup_thread: Optional[threading.Thread] = None
        self._bot_thread: Optional[threading.Thread] = None
        self._running = False
        self._bot_initialized = threading.Event()
        self._bot_loop: Optional[asyncio.AbstractEventLoop] = None

        os.makedirs(self.temp_folder, exist_ok=True)

    def start(self):
        if self._running:
            return

        self._running = True

        if self.bot_token and self.group_chat_id:
            self._start_telegram_bot()
        else:
            logger.warning("Telegram bot NOT started: missing TOKEN or GROUP_CHAT_ID")

        self._cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        self._cleanup_thread.start()

        logger.info("SupportService started")

    def _start_telegram_bot(self):
        def run_bot_async():
            self._bot_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._bot_loop)

            try:
                self.app = Application.builder().token(self.bot_token).build()
                self.app.add_handler(CommandHandler("start", self._cmd_start))
                self.app.add_handler(MessageHandler(
                    filters.PHOTO | filters.TEXT | filters.CAPTION,
                    self._handle_admin_reply
                ))

                async def start_polling_safe():
                    await self.app.initialize()
                    await self.app.start()
                    await self.app.updater.start_polling(drop_pending_updates=True)

                    self._bot_initialized.set()
                    logger.info("Telegram bot ready and polling")

                    while self._running:
                        await asyncio.sleep(1)

                    await self.app.updater.stop()
                    await self.app.stop()
                    await self.app.shutdown()

                self._bot_loop.run_until_complete(start_polling_safe())

            except asyncio.CancelledError:
                logger.info("Bot polling cancelled")
            except Exception as e:
                logger.error(f"Bot error: {e}")
                self._bot_initialized.set()
            finally:
                try:
                    if self._bot_loop and self._bot_loop.is_running():
                        self._bot_loop.run_until_complete(self.app.shutdown())
                except:
                    pass
                self._bot_loop.close()
                logger.info("Bot thread cleaned up")

        self._bot_thread = threading.Thread(target=run_bot_async, daemon=True)
        self._bot_thread.start()

        if not self._bot_initialized.wait(timeout=10):
            logger.warning("Bot initialization timeout")

    async def _cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "🤖 USSC Romance — Поддержка.\n"
            "Отвечайте на сообщения пользователей для ответа."
        )

    async def _handle_admin_reply(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            if update.effective_chat.id != self.group_chat_id:
                return

            if not update.message.reply_to_message:
                return

            forwarded = update.message.reply_to_message

            if not forwarded or not forwarded.caption:
                return

            if not forwarded.caption.startswith("💬 USER#"):
                return

            user_id = int(forwarded.caption.split('#')[1].split()[0])
            reply_text = update.message.text or update.message.caption
            has_photo = update.message.photo is not None
            photo_file_id = None

            if has_photo:
                photo = update.message.photo[-1]
                photo_file = await self.app.bot.get_file(photo.file_id)
                photo_path = os.path.join(self.temp_folder, f"reply_{user_id}_{uuid.uuid4().hex[:8]}.jpg")
                await photo_file.download_to_drive(photo_path)
                photo_file_id = photo_path

            logger.info(f"Processing reply for user {user_id}")

            with self._lock:
                if user_id in self.conversations:
                    message = {
                        'id': str(uuid.uuid4())[:8],
                        'from': 'admin',
                        'text': reply_text if reply_text else '',
                        'photo': f'/static/temp_support/{os.path.basename(photo_path)}' if photo_path else None,
                        'timestamp': datetime.utcnow().isoformat()
                    }
                    self.conversations[user_id]['messages'].append(message)
                    self.conversations[user_id]['last_activity'] = datetime.utcnow()
                    self.conversations[user_id]['has_reply'] = True

                    logger.info(f"✅ Reply added for user {user_id}")
                    await update.message.reply_text("✅ Ответ отправлен пользователю")
                else:
                    await update.message.reply_text(f"⚠️ Пользователь {user_id} не найден")

        except Exception as e:
            logger.error(f"Error handling reply: {e}")
            try:
                await update.message.reply_text("❌ Ошибка обработки")
            except:
                pass

    def start_conversation(self, user_id: int, username: str, message_text: str = '', photo_path: str = None) -> bool:
        with self._lock:
            if user_id not in self.conversations:
                self.conversations[user_id] = {
                    'user_id': user_id,
                    'username': username,
                    'created_at': datetime.utcnow(),
                    'last_activity': datetime.utcnow(),
                    'has_reply': False,
                    'messages': []
                }

            message = {
                'id': str(uuid.uuid4())[:8],
                'from': 'user',
                'text': message_text,
                'photo': f'/static/temp_support/{os.path.basename(photo_path)}' if photo_path else None,
                'timestamp': datetime.utcnow().isoformat()
            }

            self.conversations[user_id]['messages'].append(message)
            self.conversations[user_id]['last_activity'] = datetime.utcnow()
            logger.info(f"Message from user {user_id}")

        if photo_path:
            temp_photo = os.path.join(self.temp_folder, os.path.basename(photo_path))
            if os.path.exists(photo_path):
                shutil.copy2(photo_path, temp_photo)

        if self.app and self.app.bot and self._bot_loop:
            caption = (
                f"💬 USER#{user_id}\n"
                f"👤 @{username}\n"
                f"💬 {message_text or 'Без текста'}\n\n"
                f"↩️ Ответьте на это сообщение"
            )

            async def send_to_telegram():
                try:
                    if photo_path and os.path.exists(temp_photo):
                        await self.app.bot.send_photo(
                            chat_id=self.group_chat_id,
                            photo=open(temp_photo, 'rb'),
                            caption=caption
                        )
                    else:
                        await self.app.bot.send_message(
                            chat_id=self.group_chat_id,
                            text=caption
                        )
                    logger.info(f"Sent message to Telegram for user {user_id}")
                except Exception as e:
                    logger.error(f"Failed to send to Telegram: {e}")

            try:
                if self._bot_loop.is_running():
                    asyncio.run_coroutine_threadsafe(send_to_telegram(), self._bot_loop)
                else:
                    self._bot_loop.run_until_complete(send_to_telegram())
            except Exception as e:
                logger.error(f"Error sending to Telegram: {e}")

        return True

    def add_message(self, user_id: int, message_text: str = '', photo_path: str = None) -> bool:
        with self._lock:
            if user_id not in self.conversations:
                return False

            message = {
                'id': str(uuid.uuid4())[:8],
                'from': 'user',
                'text': message_text,
                'photo': f'/static/temp_support/{os.path.basename(photo_path)}' if photo_path else None,
                'timestamp': datetime.utcnow().isoformat()
            }

            self.conversations[user_id]['messages'].append(message)
            self.conversations[user_id]['last_activity'] = datetime.utcnow()
            self.conversations[user_id]['has_reply'] = False

        if photo_path:
            temp_photo = os.path.join(self.temp_folder, os.path.basename(photo_path))
            if os.path.exists(photo_path):
                shutil.copy2(photo_path, temp_photo)

        if self.app and self.app.bot and self._bot_loop:
            user_data = self.conversations[user_id]
            caption = (
                f"💬 USER#{user_id}\n"
                f"👤 @{user_data['username']}\n"
                f"💬 {message_text or 'Без текста'}\n\n"
                f"↩️ Ответьте на это сообщение"
            )

            async def forward_to_telegram():
                try:
                    if photo_path and os.path.exists(temp_photo):
                        await self.app.bot.send_photo(
                            chat_id=self.group_chat_id,
                            photo=open(temp_photo, 'rb'),
                            caption=caption
                        )
                    else:
                        await self.app.bot.send_message(
                            chat_id=self.group_chat_id,
                            text=caption
                        )
                except Exception as e:
                    logger.error(f"Failed to forward to Telegram: {e}")

            try:
                if self._bot_loop.is_running():
                    asyncio.run_coroutine_threadsafe(forward_to_telegram(), self._bot_loop)
                else:
                    self._bot_loop.run_until_complete(forward_to_telegram())
            except Exception as e:
                logger.error(f"Error forwarding to Telegram: {e}")

        return True

    def get_conversation(self, user_id: int) -> Optional[Dict[str, Any]]:
        with self._lock:
            conv = self.conversations.get(user_id)
            if not conv:
                return None
            return {
                'user_id': conv['user_id'],
                'username': conv['username'],
                'has_reply': conv['has_reply'],
                'created_at': conv['created_at'].isoformat(),
                'last_activity': conv['last_activity'].isoformat(),
                'messages': conv['messages'].copy()
            }

    def _cleanup_loop(self):
        while True:
            try:
                now = datetime.utcnow()
                with self._lock:
                    expired = []
                    for uid, data in self.conversations.items():
                        if now - data['last_activity'] > timedelta(hours=24):
                            expired.append(uid)

                    for uid in expired:
                        for msg in self.conversations[uid]['messages']:
                            if msg.get('photo'):
                                photo_path = os.path.join(self.temp_folder, os.path.basename(msg['photo']))
                                if os.path.exists(photo_path):
                                    os.remove(photo_path)
                        del self.conversations[uid]
                        logger.info(f"Cleaned up conversation for user {uid}")
            except Exception as e:
                logger.error(f"Cleanup error: {e}")
            threading.Event().wait(self.CLEANUP_INTERVAL)