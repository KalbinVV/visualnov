# -*- coding: utf-8 -*-
"""
Логика авторизации и регистрации
Любовный симулятор
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from models import User, Session
from database import Database


class AuthService:
    """Сервис авторизации"""

    def __init__(self, db: Database):
        """
        Инициализация сервиса

        Args:
            db: Объект базы данных
        """
        self.db = db

    def register_user(self, username: str, email: str, password: str,
                      display_name: str = None) -> tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        Регистрация нового пользователя

        Args:
            username: Имя пользователя
            email: Email
            password: Пароль
            display_name: Отображаемое имя

        Returns:
            Кортеж (успешно, сообщение, данные пользователя)
        """
        # Валидация данных
        if len(username) < 3:
            return False, 'Имя пользователя должно содержать минимум 3 символа', None

        if '@' not in email:
            return False, 'Неверный формат email', None

        if len(password) < 6:
            return False, 'Пароль должен содержать минимум 6 символов', None

        # Проверка существования пользователя
        if self.db.get_user_by_username(username):
            return False, 'Пользователь с таким именем уже существует', None

        if self.db.get_user_by_email(email):
            return False, 'Пользователь с таким email уже существует', None

        # Хеширование пароля
        pwd_hash, salt = User.hash_password(password)

        # Создание пользователя
        user_id = self.db.create_user(
            username=username,
            email=email,
            password_hash=pwd_hash,
            password_salt=salt,
            display_name=display_name,
            diamonds=100  # Начальные алмазы
        )

        if not user_id:
            return False, 'Ошибка создания пользователя', None

        # Получение данных пользователя
        user_data = self.db.get_user_by_id(user_id)

        return True, 'Регистрация успешна', user_data

    def login_user(self, identifier: str, password: str,
                   ip_address: str = None, user_agent: str = None) -> tuple[
        bool, str, Optional[Dict[str, Any]], Optional[str]]:
        """
        Авторизация пользователя

        Args:
            identifier: Имя пользователя или email
            password: Пароль
            ip_address: IP адрес
            user_agent: User agent

        Returns:
            Кортеж (успешно, сообщение, данные пользователя, токен сессии)
        """
        # Поиск пользователя
        user_data = self.db.get_user_by_username(identifier)
        if not user_data:
            user_data = self.db.get_user_by_email(identifier)

        if not user_data:
            return False, 'Неверный логин или пароль', None, None

        # Создание объекта пользователя
        user = User(
            user_id=user_data['id'],
            username=user_data['username'],
            email=user_data['email'],
            password_hash=user_data['password_hash'],
            password_salt=user_data['password_salt'],
            display_name=user_data['display_name'],
            avatar_url=user_data['avatar_url'],
            created_at=user_data['created_at'],
            last_login=user_data['last_login'],
            is_active=user_data['is_active'],
            is_admin=user_data['is_admin'],
            failed_login_attempts=user_data['failed_login_attempts'],
            locked_until=user_data['locked_until'],
            diamonds=user_data['diamonds'],
            theme=user_data['theme']
        )

        # Проверка блокировки
        if user.is_locked():
            remaining = user.get_lockout_remaining_minutes()
            return False, f'Аккаунт заблокирован. Попробуйте через {remaining} минут', None, None

        # Проверка пароля
        if not User.verify_password(password, user.password_hash, user.password_salt):
            # Увеличение счетчика неудачных попыток
            new_attempts = user.failed_login_attempts + 1
            self.db.update_user(user.id, failed_login_attempts=new_attempts)

            # Блокировка при превышении лимита
            if new_attempts >= 5:
                lockout_until = datetime.now() + timedelta(minutes=15)
                self.db.update_user(user.id, locked_until=lockout_until.isoformat())
                return False, 'Слишком много неудачных попыток. Аккаунт заблокирован на 15 минут', None, None

            return False, 'Неверный логин или пароль', None, None

        # Сброс счетчика неудачных попыток
        self.db.update_user(
            user.id,
            failed_login_attempts=0,
            locked_until=None,
            last_login=datetime.now().isoformat()
        )

        # Создание сессии
        session_token = Session.generate_token()
        expires_at = datetime.now() + timedelta(days=30)

        self.db.create_session(
            user_id=user.id,
            session_token=session_token,
            expires_at=expires_at,
            ip_address=ip_address,
            user_agent=user_agent
        )

        # Обновление данных пользователя
        user_data = self.db.get_user_by_id(user.id)

        return True, 'Авторизация успешна', user_data, session_token

    def logout_user(self, session_token: str) -> bool:
        """
        Выход из системы

        Args:
            session_token: Токен сессии

        Returns:
            True если успешно
        """
        return self.db.delete_session(session_token)

    def validate_session_token(self, session_token: str) -> tuple[bool, Optional[Dict[str, Any]]]:
        """
        Проверка токена сессии

        Args:
            session_token: Токен сессии

        Returns:
            Кортеж (валиден, данные пользователя)
        """
        session_data = self.db.validate_session(session_token)

        if not session_data:
            return False, None

        # Извлечение данных пользователя из сессии
        user_data = {
            'id': session_data['user_id'],
            'username': session_data['username'],
            'email': session_data['email'],
            'display_name': session_data['display_name'],
            'avatar_url': session_data['avatar_url'],
            'diamonds': session_data['diamonds'],
            'theme': session_data['theme'],
            'is_admin': session_data['is_admin']
        }

        return True, user_data

    def change_password(self, user_id: int, old_password: str,
                        new_password: str) -> tuple[bool, str]:
        """
        Изменение пароля

        Args:
            user_id: ID пользователя
            old_password: Старый пароль
            new_password: Новый пароль

        Returns:
            Кортеж (успешно, сообщение)
        """
        user_data = self.db.get_user_by_id(user_id)

        if not user_data:
            return False, 'Пользователь не найден'

        # Проверка старого пароля
        if not User.verify_password(old_password, user_data['password_hash'],
                                    user_data['password_salt']):
            return False, 'Неверный старый пароль'

        # Хеширование нового пароля
        pwd_hash, salt = User.hash_password(new_password)

        # Обновление пароля
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE users 
                SET password_hash = ?, password_salt = ?
                WHERE id = ?
            ''', (pwd_hash, salt, user_id))

        return True, 'Пароль успешно изменен'