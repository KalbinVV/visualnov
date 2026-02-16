# -*- coding: utf-8 -*-
"""
Логика авторизации и регистрации
Любовный симулятор — без models.py
"""

from datetime import datetime, timedelta
from typing import Optional, Tuple, Dict, Any
import hashlib
import secrets

from database import Database, User, UserSession  # Убедитесь, что методы возвращают dict, а не объекты


def hash_password(password: str, salt: Optional[str] = None) -> Tuple[str, str]:
    """Хеширование пароля SHA-256 + соль"""
    if salt is None:
        salt = secrets.token_hex(16)
    pwd_hash = hashlib.sha256((password + salt).encode('utf-8')).hexdigest()
    return pwd_hash, salt


def verify_password(password: str, pwd_hash: str, salt: str) -> bool:
    """Проверка пароля"""
    new_hash, _ = hash_password(password, salt)
    return new_hash == pwd_hash


def generate_session_token(length: int = 64) -> str:
    """Генерация токена сессии (URL-safe)"""
    return secrets.token_urlsafe(length)


class AuthService:
    def __init__(self, db: Database):
        self.db = db

    def register_user(
            self,
            username: str,
            email: str,
            password: str,
            display_name: Optional[str] = None
    ) -> Tuple[bool, str, Optional[User]]:
        username = (username or "").strip()
        email = (email or "").strip().lower()
        password = (password or "").strip()

        if len(username) < 3:
            return False, "Имя пользователя: минимум 3 символа", None
        if len(email) < 5 or "@" not in email or "." not in email.split("@")[-1]:
            return False, "Неверный email", None
        if len(password) < 6:
            return False, "Пароль: минимум 6 символов", None

        if self.db.get_user_by_username(username):
            return False, "Имя пользователя занято", None
        if self.db.get_user_by_email(email):
            return False, "Email уже зарегистрирован", None

        pwd_hash, salt = hash_password(password)
        user_id = self.db.create_user(
            username=username,
            email=email,
            password_hash=pwd_hash,
            password_salt=salt,
            display_name=display_name or username,
            diamonds=100,
            is_leader=False
        )

        if not user_id:
            return False, "Ошибка создания (дубликат или БД)", None

        user_data = self.db.get_user_by_id(user_id)
        return True, "Регистрация успешна", user_data

    def login_user(
            self,
            identifier: str,
            password: str,
            ip_address: Optional[str] = None,
            user_agent: Optional[str] = None
    ) -> Tuple[bool, str, Optional[User], Optional[str]]:
        identifier = (identifier or "").strip()
        password = (password or "").strip()

        user_data = self.db.get_user_by_username(identifier)

        if not user_data:
            user_data = self.db.get_user_by_email(identifier)

        if not user_data:
            return False, "Неверный логин или пароль", None, None

        user_id = user_data.id
        pwd_hash = user_data.password_hash
        salt = user_data.password_salt
        failed_attempts = user_data.failed_login_attempts
        locked_until_str = user_data.locked_until

        if locked_until_str:
            try:
                lock_time = datetime.fromisoformat(locked_until_str.replace('Z', '+00:00'))  # UTC fix
                if datetime.now() < lock_time:
                    remaining_min = max(1, int((lock_time - datetime.now()).total_seconds() / 60))
                    return False, f"Заблокировано на {remaining_min} мин", None, None
            except (ValueError, TypeError):
                pass

        if not verify_password(password, pwd_hash, salt):
            new_attempts = failed_attempts + 1
            updates: Dict[str, Any] = {"failed_login_attempts": new_attempts}

            if new_attempts >= 5:
                lock_until = datetime.now() + timedelta(minutes=15)
                updates["locked_until"] = lock_until.isoformat()
                msg = "Блокировка на 15 мин (5+ попыток)"
            else:
                msg = "Неверный логин или пароль"

            self.db.update_user(user_id, **updates)
            return False, msg, None, None

        self.db.update_user(
            user_id,
            failed_login_attempts=0,
            locked_until=None,
            last_login=datetime.now().isoformat()
        )

        session_token = generate_session_token()
        expires_at = (datetime.now() + timedelta(days=30))

        self.db.create_session(
            user_id=user_id,
            session_token=session_token,
            expires_at=expires_at,
            ip_address=ip_address,
            user_agent=user_agent
        )

        fresh_data = self.db.get_user_by_id(user_id)
        return True, "Вход успешен", fresh_data, session_token

    def logout_user(self, session_token: str) -> bool:
        return self.db.delete_session(session_token)

    def validate_session_token(self, session_token: str) -> Tuple[bool, Optional[Dict[str, Any]]]:
        session_data = self.db.validate_session(session_token)
        if not session_data:
            return False, None

        return True, {
            "id": session_data.get("user_id"),
            "username": session_data.get("username"),
            "email": session_data.get("email"),
            "display_name": session_data.get("display_name", session_data.get("username")),
            "avatar_url": session_data.get("avatar_url"),
            "diamonds": session_data.get("diamonds", 0),
            "theme": session_data.get("theme", "orange"),
            "is_admin": session_data.get("is_admin", False)
        }

    def change_password(
            self,
            user_id: int,
            old_password: str,
            new_password: str
    ) -> Tuple[bool, str]:
        user_data = self.db.get_user_by_id(user_id)
        if not user_data:
            return False, "Пользователь не найден"

        if not verify_password(old_password, user_data["password_hash"], user_data["password_salt"]):
            return False, "Неверный старый пароль"

        new_pwd = (new_password or "").strip()
        if len(new_pwd) < 6:
            return False, "Новый пароль: минимум 6 символов"

        new_hash, new_salt = hash_password(new_pwd)

        self.db.update_user(
            user_id,
            password_hash=new_hash,
            password_salt=new_salt
        )

        return (True, "Пароль изменён")


if __name__ == "__main__":
    db = Database()
    auth = AuthService(db)