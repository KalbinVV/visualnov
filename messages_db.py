# -*- coding: utf-8 -*-
"""
База данных для системы сообщений (отдельная БД - SQLite)
"""

from datetime import datetime
from typing import Optional, List
from pathlib import Path

from sqlalchemy import (
    create_engine, String, Text, Boolean, Integer, ForeignKey, DateTime, func, select, delete,
)
from sqlalchemy.orm import (
    DeclarativeBase, Mapped, mapped_column, relationship, Session, sessionmaker,
)
from contextlib import contextmanager


class MessageBase(DeclarativeBase):
    pass


class Message(MessageBase):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    username: Mapped[str] = mapped_column(String(80), nullable=False)
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    image_path: Mapped[Optional[str]] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    is_responded: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), default="pending")

    responses: Mapped[List["MessageResponse"]] = relationship(
        "MessageResponse", back_populates="message", cascade="all, delete-orphan"
    )


class MessageResponse(MessageBase):
    __tablename__ = "message_responses"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    message_id: Mapped[int] = mapped_column(
        ForeignKey("messages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    admin_id: Mapped[int] = mapped_column(Integer, nullable=True)
    admin_username: Mapped[str] = mapped_column(String(80), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    image_path: Mapped[Optional[str]] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    is_visible: Mapped[bool] = mapped_column(Boolean, default=True)

    message: Mapped["Message"] = relationship("Message", back_populates="responses")


class MessagesDatabase:
    def __init__(self, db_url: str):
        self.db_url = db_url
        self.engine = create_engine(self.db_url, echo=False)
        self.SessionLocal = sessionmaker(bind=self.engine, class_=Session, expire_on_commit=False)
        self.init_database()

    def init_database(self):
        MessageBase.metadata.create_all(self.engine)

    @contextmanager
    def get_session(self):
        db_session = self.SessionLocal()
        try:
            yield db_session
            db_session.commit()
        except Exception:
            db_session.rollback()
            raise
        finally:
            db_session.close()

    def create_message(self, user_id: int, username: str, subject: str, content: str, image_path: Optional[str] = None) -> int:
        with self.get_session() as s:
            message = Message(user_id=user_id, username=username, subject=subject, content=content, image_path=image_path)
            s.add(message)
            s.flush()
            return message.id

    def get_message_by_id(self, message_id: int) -> Optional[Message]:
        with self.get_session() as s:
            return s.get(Message, message_id)

    def get_all_messages(self, limit: int = 100) -> List[Message]:
        with self.get_session() as s:
            stmt = select(Message).order_by(Message.created_at.desc()).limit(limit)
            return list(s.execute(stmt).scalars().all())

    def get_user_messages(self, user_id: int, limit: int = 50) -> List[Message]:
        with self.get_session() as s:
            stmt = select(Message).where(Message.user_id == user_id).order_by(Message.created_at.desc()).limit(limit)
            return list(s.execute(stmt).scalars().all())

    def mark_message_read(self, message_id: int) -> bool:
        with self.get_session() as s:
            message = s.get(Message, message_id)
            if message:
                message.is_read = True
                return True
            return False

    def mark_message_responded(self, message_id: int) -> bool:
        with self.get_session() as s:
            message = s.get(Message, message_id)
            if message:
                message.is_responded = True
                message.status = "answered"
                return True
            return False

    def create_response(self, message_id: int, admin_id: int, admin_username: str, content: str, image_path: Optional[str] = None) -> int:
        with self.get_session() as s:
            response = MessageResponse(message_id=message_id, admin_id=admin_id, admin_username=admin_username, content=content, image_path=image_path)
            s.add(response)
            s.flush()
            return response.id

    def get_message_responses(self, message_id: int) -> List[MessageResponse]:
        with self.get_session() as s:
            stmt = select(MessageResponse).where(MessageResponse.message_id == message_id).order_by(MessageResponse.created_at.asc())
            return list(s.execute(stmt).scalars().all())

    def get_pending_messages(self) -> List[Message]:
        with self.get_session() as s:
            stmt = select(Message).where(Message.is_responded == False).order_by(Message.created_at.asc())
            return list(s.execute(stmt).scalars().all())

    def delete_message(self, message_id: int) -> bool:
        with self.get_session() as s:
            stmt = delete(Message).where(Message.id == message_id)
            result = s.execute(stmt)
            return result.rowcount > 0

    def get_unread_count(self, user_id: Optional[int] = None, admin: bool = False) -> int:
        with self.get_session() as s:
            if admin:
                stmt = select(Message).where(Message.is_read == False)
            else:
                stmt = select(Message).where(Message.user_id == user_id, Message.is_responded == False)
            return len(list(s.execute(stmt).scalars().all()))