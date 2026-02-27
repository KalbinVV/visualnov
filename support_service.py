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
    """Сервис полноценной техподдержки с чатом"""

    CLEANUP_INTERVAL = 60
    MAX_MESSAGES_PER_TICKET = 50

    def __init__(self, bot_token: str, group_chat_id: int, temp_folder: str = 'static/temp_support'):
        self.bot_token = bot_token
        self.group_chat_id = group_chat_id
        self.temp_folder = temp_folder
        self.tickets: Dict[str, Dict[str, Any]] = {}
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
            "🤖 USSC Romance — Техподдержка.\n"
            "Отвечайте на сообщения из тикетов для ответа пользователю."
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

            if not forwarded.caption.startswith("🎫 TICKET#"):
                return

            ticket_id = forwarded.caption.split('#')[1].split('\n')[0].strip()

            reply_text = update.message.text or update.message.caption
            has_photo = update.message.photo is not None
            photo_file_id = None

            if has_photo:
                photo = update.message.photo[-1]
                photo_file = await self.app.bot.get_file(photo.file_id)
                photo_path = os.path.join(self.temp_folder, f"reply_{ticket_id}_{uuid.uuid4().hex[:8]}.jpg")
                await photo_file.download_to_drive(photo_path)
                photo_file_id = photo_path

            logger.info(f"Processing reply for TICKET#{ticket_id}")

            with self._lock:
                if ticket_id in self.tickets:
                    message = {
                        'id': str(uuid.uuid4())[:8],
                        'from': 'admin',
                        'text': reply_text if reply_text else '',
                        'photo': photo_file_id,
                        'timestamp': datetime.utcnow().isoformat()
                    }
                    self.tickets[ticket_id]['messages'].append(message)
                    self.tickets[ticket_id]['last_activity'] = datetime.utcnow()
                    self.tickets[ticket_id]['status'] = 'open'

                    logger.info(
                        f"✅ Reply added to ticket {ticket_id} from @{update.effective_user.username or update.effective_user.id}")
                    await update.message.reply_text("✅ Ответ отправлен пользователю")
                else:
                    await update.message.reply_text(f"⚠️ Тикет #{ticket_id} не найден или закрыт")

        except Exception as e:
            logger.error(f"Error handling reply: {e}")
            try:
                await update.message.reply_text("❌ Ошибка обработки")
            except:
                pass

    def create_ticket(self, user_id: int, username: str, message_text: str = '', photo_path: str = None) -> str:
        ticket_id = str(uuid.uuid4())[:8]

        with self._lock:
            message = {
                'id': str(uuid.uuid4())[:8],
                'from': 'user',
                'text': message_text,
                'photo': f'/static/temp_support/{os.path.basename(photo_path)}' if photo_path else None,
                'timestamp': datetime.utcnow().isoformat()
            }

            self.tickets[ticket_id] = {
                'user_id': user_id,
                'username': username,
                'created_at': datetime.utcnow(),
                'last_activity': datetime.utcnow(),
                'status': 'open',
                'messages': [message],
                'telegram_msg_id': None
            }
            logger.info(f"Created ticket {ticket_id} for user {username}")

        if photo_path:
            temp_photo = os.path.join(self.temp_folder, os.path.basename(photo_path))
            shutil.copy2(photo_path, temp_photo)

        if self.app and self.app.bot and self._bot_loop:
            caption = (
                f"🎫 TICKET#{ticket_id}\n"
                f"👤 @{username} (UID: {user_id})\n"
                f"💬 {message_text or 'Без текста'}\n\n"
                f"↩️ Ответьте на это сообщение"
            )

            async def send_to_telegram():
                try:
                    if photo_path and os.path.exists(temp_photo):
                        message = await self.app.bot.send_photo(
                            chat_id=self.group_chat_id,
                            photo=open(temp_photo, 'rb'),
                            caption=caption
                        )
                    else:
                        message = await self.app.bot.send_message(
                            chat_id=self.group_chat_id,
                            text=caption
                        )
                    self.tickets[ticket_id]['telegram_msg_id'] = message.message_id
                    logger.info(f"Sent ticket {ticket_id} to Telegram, message_id: {message.message_id}")
                except Exception as e:
                    logger.error(f"Failed to send to Telegram: {e}")

            try:
                if self._bot_loop.is_running():
                    asyncio.run_coroutine_threadsafe(send_to_telegram(), self._bot_loop)
                else:
                    self._bot_loop.run_until_complete(send_to_telegram())
            except Exception as e:
                logger.error(f"Error sending to Telegram: {e}")

        return ticket_id

    def add_message(self, ticket_id: str, user_id: int, message_text: str = '', photo_path: str = None) -> bool:
        with self._lock:
            if ticket_id not in self.tickets:
                return False

            ticket = self.tickets[ticket_id]
            if ticket['user_id'] != user_id:
                return False

            if ticket['status'] == 'closed':
                return False

            message = {
                'id': str(uuid.uuid4())[:8],
                'from': 'user',
                'text': message_text,
                'photo': f'/static/temp_support/{os.path.basename(photo_path)}' if photo_path else None,
                'timestamp': datetime.utcnow().isoformat()
            }

            ticket['messages'].append(message)
            ticket['last_activity'] = datetime.utcnow()
            ticket['status'] = 'open'

            if len(ticket['messages']) > self.MAX_MESSAGES_PER_TICKET:
                ticket['messages'] = ticket['messages'][-self.MAX_MESSAGES_PER_TICKET:]

            logger.info(f"Message added to ticket {ticket_id}")

        if photo_path:
            temp_photo = os.path.join(self.temp_folder, os.path.basename(photo_path))
            if os.path.exists(photo_path):
                shutil.copy2(photo_path, temp_photo)

        if self.app and self.app.bot and self._bot_loop:
            caption = (
                f"🎫 TICKET#{ticket_id}\n"
                f"👤 @{ticket['username']} (UID: {user_id})\n"
                f"💬 {message_text or 'Без текста'}\n\n"
                f"↩️ Ответьте на это сообщение"
            )

            async def forward_to_telegram():
                try:
                    if photo_path and os.path.exists(temp_photo):
                        await self.app.bot.send_photo(
                            chat_id=self.group_chat_id,
                            photo=open(temp_photo, 'rb'),
                            caption=caption,
                            reply_to_message_id=ticket.get('telegram_msg_id')
                        )
                    else:
                        await self.app.bot.send_message(
                            chat_id=self.group_chat_id,
                            text=caption,
                            reply_to_message_id=ticket.get('telegram_msg_id')
                        )
                    logger.info(f"Forwarded message to Telegram for ticket {ticket_id}")
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

    def get_ticket(self, ticket_id: str, user_id: int = None) -> Optional[Dict[str, Any]]:
        with self._lock:
            ticket = self.tickets.get(ticket_id)
            if not ticket:
                return None

            if user_id and ticket['user_id'] != user_id:
                return None

            return {
                'ticket_id': ticket_id,
                'user_id': ticket['user_id'],
                'username': ticket['username'],
                'status': ticket['status'],
                'created_at': ticket['created_at'].isoformat(),
                'last_activity': ticket['last_activity'].isoformat(),
                'messages': ticket['messages'].copy()
            }

    def get_user_tickets(self, user_id: int) -> List[Dict[str, Any]]:
        with self._lock:
            tickets = []
            for ticket_id, ticket in self.tickets.items():
                if ticket['user_id'] == user_id:
                    tickets.append({
                        'ticket_id': ticket_id,
                        'status': ticket['status'],
                        'created_at': ticket['created_at'].isoformat(),
                        'last_activity': ticket['last_activity'].isoformat(),
                        'messages_count': len(ticket['messages'])
                    })
            return sorted(tickets, key=lambda x: x['last_activity'], reverse=True)

    def close_ticket(self, ticket_id: str, user_id: int) -> bool:
        with self._lock:
            if ticket_id not in self.tickets:
                return False

            ticket = self.tickets[ticket_id]
            if ticket['user_id'] != user_id:
                return False

            ticket['status'] = 'closed'
            ticket['last_activity'] = datetime.utcnow()
            logger.info(f"Ticket {ticket_id} closed")
            return True

    def _cleanup_loop(self):
        while True:
            try:
                now = datetime.utcnow()
                with self._lock:
                    expired = []
                    for sid, data in self.tickets.items():
                        if data['status'] == 'closed' and now - data['last_activity'] > timedelta(hours=1):
                            expired.append(sid)
                        elif now - data['created_at'] > timedelta(hours=24):
                            expired.append(sid)

                    for sid in expired:
                        for msg in self.tickets[sid]['messages']:
                            if msg.get('photo'):
                                photo_path = os.path.join(self.temp_folder, os.path.basename(msg['photo']))
                                if os.path.exists(photo_path):
                                    os.remove(photo_path)
                        del self.tickets[sid]
                        logger.info(f"Cleaned up ticket {sid}")
            except Exception as e:
                logger.error(f"Cleanup error: {e}")
            threading.Event().wait(self.CLEANUP_INTERVAL)