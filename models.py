# -*- coding: utf-8 -*-
"""
Модели данных
Любовный симулятор
"""

import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional, Dict, Any


class User:
    """Модель пользователя"""

    def __init__(self, user_id: int, username: str, email: str,
                 password_hash: str, password_salt: str,
                 display_name: str = None, avatar_url: str = None,
                 created_at: str = None, last_login: str = None,
                 is_active: bool = True, is_admin: bool = False,
                 failed_login_attempts: int = 0, locked_until: str = None,
                 diamonds: int = 0, theme: str = 'orange',
                 settings: str = None):
        """
        Инициализация пользователя

        Args:
            user_id: ID пользователя
            username: Имя пользователя
            email: Email
            password_hash: Хеш пароля
            password_salt: Соль пароля
            display_name: Отображаемое имя
            avatar_url: URL аватара
            created_at: Время создания
            last_login: Время последнего входа
            is_active: Активен ли пользователь
            is_admin: Является ли администратором
            failed_login_attempts: Количество неудачных попыток входа
            locked_until: Время разблокировки
            diamonds: Количество алмазов
            theme: Тема интерфейса
            settings: Дополнительные настройки
        """
        self.id = user_id
        self.username = username
        self.email = email
        self.password_hash = password_hash
        self.password_salt = password_salt
        self.display_name = display_name or username
        self.avatar_url = avatar_url
        self.created_at = created_at
        self.last_login = last_login
        self.is_active = is_active
        self.is_admin = is_admin
        self.failed_login_attempts = failed_login_attempts
        self.locked_until = locked_until
        self.diamonds = diamonds
        self.theme = theme
        self.settings = settings or '{}'

    @staticmethod
    def hash_password(password: str, salt: str = None) -> tuple[str, str]:
        """
        Хеширование пароля

        Args:
            password: Пароль
            salt: Соль (если None, генерируется новая)

        Returns:
            Кортеж (хеш, соль)
        """
        if salt is None:
            salt = secrets.token_hex(16)
        pwd_hash = hashlib.sha256((password + salt).encode()).hexdigest()
        return pwd_hash, salt

    @staticmethod
    def verify_password(password: str, pwd_hash: str, salt: str) -> bool:
        """
        Проверка пароля

        Args:
            password: Пароль для проверки
            pwd_hash: Хеш пароля
            salt: Соль пароля

        Returns:
            True если пароль верный
        """
        new_hash, _ = User.hash_password(password, salt)
        return new_hash == pwd_hash

    @staticmethod
    def create_admin(username: str, email: str, password: str,
                     display_name: str = None) -> 'User':
        """
        Создание администратора

        Args:
            username: Имя пользователя
            email: Email
            password: Пароль
            display_name: Отображаемое имя

        Returns:
            Объект User
        """
        pwd_hash, salt = User.hash_password(password)
        return User(
            user_id=0,  # Будет установлен при сохранении в БД
            username=username,
            email=email,
            password_hash=pwd_hash,
            password_salt=salt,
            display_name=display_name or username,
            is_admin=True,
            diamonds=9999
        )

    def to_dict(self) -> Dict[str, Any]:
        """
        Преобразование в словарь

        Returns:
            Словарь с данными пользователя
        """
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'display_name': self.display_name,
            'avatar_url': self.avatar_url,
            'created_at': self.created_at,
            'last_login': self.last_login,
            'is_active': self.is_active,
            'is_admin': self.is_admin,
            'diamonds': self.diamonds,
            'theme': self.theme
        }

    def is_locked(self) -> bool:
        """
        Проверка, заблокирован ли пользователь

        Returns:
            True если заблокирован
        """
        if not self.locked_until:
            return False

        lockout_time = datetime.fromisoformat(self.locked_until)
        return datetime.now() < lockout_time

    def get_lockout_remaining_minutes(self) -> int:
        """
        Получить оставшееся время блокировки в минутах

        Returns:
            Количество минут или 0
        """
        if not self.locked_until:
            return 0

        lockout_time = datetime.fromisoformat(self.locked_until)
        if datetime.now() >= lockout_time:
            return 0

        return (lockout_time - datetime.now()).seconds // 60


class Session:
    """Модель сессии"""

    def __init__(self, session_id: int, user_id: int, session_token: str,
                 created_at: str, expires_at: str, ip_address: str = None,
                 user_agent: str = None):
        """
        Инициализация сессии

        Args:
            session_id: ID сессии
            user_id: ID пользователя
            session_token: Токен сессии
            created_at: Время создания
            expires_at: Время истечения
            ip_address: IP адрес
            user_agent: User agent
        """
        self.id = session_id
        self.user_id = user_id
        self.session_token = session_token
        self.created_at = created_at
        self.expires_at = expires_at
        self.ip_address = ip_address
        self.user_agent = user_agent

    @staticmethod
    def generate_token() -> str:
        """
        Генерация токена сессии

        Returns:
            Токен сессии
        """
        return secrets.token_hex(32)

    def is_expired(self) -> bool:
        """
        Проверка, истекла ли сессия

        Returns:
            True если истекла
        """
        expires_time = datetime.fromisoformat(self.expires_at)
        return datetime.now() > expires_time


class GameSave:
    """Модель сохранения игры"""

    def __init__(self, save_id: int, user_id: int, game_name: str,
                 save_slot: int, save_data: Dict[str, Any],
                 created_at: str, updated_at: str):
        """
        Инициализация сохранения

        Args:
            save_id: ID сохранения
            user_id: ID пользователя
            game_name: Название игры
            save_slot: Слот сохранения
            save_data: Данные сохранения
            created_at: Время создания
            updated_at: Время обновления
        """
        self.id = save_id
        self.user_id = user_id
        self.game_name = game_name
        self.save_slot = save_slot
        self.save_data = save_data
        self.created_at = created_at
        self.updated_at = updated_at


class GameStats:
    """Модель статистики игры"""

    def __init__(self, stat_id: int, user_id: int, game_name: str,
                 play_time: int = 0, completed: bool = False,
                 rating: int = None, choices_made: int = 0,
                 created_at: str = None):
        """
        Инициализация статистики

        Args:
            stat_id: ID записи
            user_id: ID пользователя
            game_name: Название игры
            play_time: Время игры в секундах
            completed: Завершена ли игра
            rating: Рейтинг
            choices_made: Количество сделанных выборов
            created_at: Время создания
        """
        self.id = stat_id
        self.user_id = user_id
        self.game_name = game_name
        self.play_time = play_time
        self.completed = completed
        self.rating = rating
        self.choices_made = choices_made
        self.created_at = created_at


class Achievement:
    """Модель достижения"""

    def __init__(self, achievement_id: int, user_id: int,
                 achievement_name: str, description: str = None,
                 unlocked_at: str = None):
        """
        Инициализация достижения

        Args:
            achievement_id: ID достижения
            user_id: ID пользователя
            achievement_name: Название достижения
            description: Описание
            unlocked_at: Время разблокировки
        """
        self.id = achievement_id
        self.user_id = user_id
        self.achievement_name = achievement_name
        self.description = description
        self.unlocked_at = unlocked_at