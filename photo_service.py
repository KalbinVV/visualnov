#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import uuid
import shutil
import threading
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TemporaryPhotoService:
    CLEANUP_INTERVAL = 300

    def __init__(self, bot_token: str, group_chat_id: int, temp_folder: str = 'static/temp_photos'):
        self.bot_token = bot_token
        self.group_chat_id = group_chat_id
        self.temp_folder = temp_folder
        self.submissions: Dict[str, Dict[str, Any]] = {}
        self.app: Optional[Application] = None
        self._lock = threading.Lock()
        self._cleanup_thread: Optional[threading.Thread] = None
        self._bot_thread: Optional[threading.Thread] = None
        self._running = False
        self._bot_initialized = threading.Event()

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

        logger.info("PhotoService started")

    def _start_telegram_bot(self):
        def run_bot_async():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            try:
                self.app = Application.builder().token(self.bot_token).build()
                self.app.add_handler(CommandHandler("start", self._cmd_start))
                self.app.add_handler(MessageHandler(filters.PHOTO | filters.TEXT, self._handle_admin_reply))

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

                loop.run_until_complete(start_polling_safe())

            except asyncio.CancelledError:
                logger.info("Bot polling cancelled")
            except Exception as e:
                logger.error(f"Bot error: {e}")
                self._bot_initialized.set()
            finally:
                try:
                    loop.run_until_complete(self.app.shutdown())
                except:
                    pass
                loop.close()
                logger.info("Bot thread cleaned up")

        self._bot_thread = threading.Thread(target=run_bot_async, daemon=True)
        self._bot_thread.start()

        if not self._bot_initialized.wait(timeout=10):
            logger.warning("Bot initialization timeout")

    async def _cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "🤖 USSC Romance — Бот поддержки.\n"
            "Отвечайте на пересланные сообщения, чтобы отправить ответ пользователю."
        )

    async def _handle_admin_reply(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_chat.id != self.group_chat_id:
            return

        if not update.message.reply_to_message:
            return

        forwarded = update.message.reply_to_message

        if not forwarded or not forwarded.caption or not forwarded.caption.startswith("📸 SUB#"):
            return

        try:
            sub_id = forwarded.caption.split('#')[1].split()[0]
            reply_text = update.message.text or update.message.caption or "✓ Получено"

            with self._lock:
                if sub_id in self.submissions:
                    self.submissions[sub_id]['reply'] = reply_text
                    self.submissions[sub_id]['replied_at'] = datetime.utcnow()
                    logger.info(f"Reply received for submission {sub_id} from {update.effective_user.username}")
                    await update.message.reply_text("✅ Ответ доставлен пользователю")
                else:
                    await update.message.reply_text("⚠️ Обращение уже удалено или истекло")

        except Exception as e:
            logger.error(f"Error handling reply: {e}")
            await update.message.reply_text("❌ Ошибка обработки")

    def create_submission(self, file_path: str, description: str, user_id: int, username: str) -> str:
        sub_id = str(uuid.uuid4())[:8]
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        temp_name = f"{sub_id}_{timestamp}.jpg"
        dest_path = os.path.join(self.temp_folder, temp_name)

        shutil.copy2(file_path, dest_path)

        with self._lock:
            self.submissions[sub_id] = {
                'file_path': dest_path,
                'description': description,
                'user_id': user_id,
                'username': username,
                'created_at': datetime.utcnow(),
                'replied_at': None,
                'reply': None,
                'telegram_msg_id': None
            }

        if self.app and self.app.bot:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                caption = (
                    f"📸 SUB#{sub_id}\n"
                    f"👤 @{username} (UID: {user_id})\n"
                    f"💬 {description or 'Без описания'}\n\n"
                    f"↩️ Любой участник группы может ответить на это сообщение"
                )
                loop.run_until_complete(
                    self.app.bot.send_photo(
                        chat_id=self.group_chat_id,
                        photo=open(dest_path, 'rb'),
                        caption=caption
                    )
                )
            except Exception as e:
                logger.error(f"Failed to send to Telegram: {e}")
            finally:
                loop.close()

        return sub_id

    def get_submission(self, sub_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            sub = self.submissions.get(sub_id)
            if not sub:
                return None
            return {
                'has_reply': sub['reply'] is not None,
                'reply': sub['reply'],
                'created_at': sub['created_at'].isoformat(),
                'replied_at': sub['replied_at'].isoformat() if sub['replied_at'] else None
            }

    def _cleanup_loop(self):
        while True:
            try:
                now = datetime.utcnow()
                with self._lock:
                    expired = [
                        sid for sid, data in self.submissions.items()
                        if now - data['created_at'] > timedelta(hours=24)
                        or (data['reply'] and now - data['replied_at'] > timedelta(hours=1))
                    ]
                    for sid in expired:
                        path = self.submissions[sid]['file_path']
                        if os.path.exists(path):
                            os.remove(path)
                        del self.submissions[sid]
                        logger.info(f"Cleaned up submission {sid}")
            except Exception as e:
                logger.error(f"Cleanup error: {e}")
            threading.Event().wait(self.CLEANUP_INTERVAL)