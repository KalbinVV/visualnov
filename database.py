# -*- coding: utf-8 -*-
"""
Модуль работы с базой данных
Любовный симулятор
"""

import sqlite3
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
from contextlib import contextmanager


class Database:
    """Класс для работы с SQLite базой данных"""

    def __init__(self, db_path: str = 'love_simulator.db'):
        """
        Инициализация базы данных

        Args:
            db_path: Путь к файлу базы данных
        """
        self.db_path = db_path
        self.init_database()

    @contextmanager
    def get_connection(self):
        """
        Контекстный менеджер для подключения к БД

        Yields:
            sqlite3.Connection: Подключение к базе данных
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init_database(self):
        """Инициализация базы данных (создание таблиц)"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Таблица пользователей
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    password_salt TEXT NOT NULL,
                    display_name TEXT,
                    avatar_url TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_login TIMESTAMP,
                    is_active BOOLEAN DEFAULT 1,
                    is_admin BOOLEAN DEFAULT 0,
                    failed_login_attempts INTEGER DEFAULT 0,
                    locked_until TIMESTAMP,
                    diamonds INTEGER DEFAULT 0,
                    theme TEXT DEFAULT 'orange',
                    settings TEXT DEFAULT '{}'
                )
            ''')

            # Таблица сессий
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    session_token TEXT UNIQUE NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP NOT NULL,
                    ip_address TEXT,
                    user_agent TEXT,
                    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
                )
            ''')

            # Таблица статистики игр
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS game_stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    game_name TEXT NOT NULL,
                    play_time INTEGER DEFAULT 0,
                    completed BOOLEAN DEFAULT 0,
                    rating INTEGER,
                    choices_made INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
                )
            ''')

            # Таблица сохранений игр
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS game_saves (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    game_name TEXT NOT NULL,
                    save_slot INTEGER NOT NULL,
                    save_data TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, game_name, save_slot),
                    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
                )
            ''')

            # Таблица достижений
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS achievements (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    achievement_name TEXT NOT NULL,
                    description TEXT,
                    unlocked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, achievement_name),
                    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
                )
            ''')

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS stories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    story_key TEXT UNIQUE NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT,
                    cover_image TEXT,
                    background_image TEXT,
                    premium BOOLEAN DEFAULT 0,
                    diamonds_cost INTEGER DEFAULT 0,
                    chapters_count INTEGER DEFAULT 1,
                    scenes_count INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_published BOOLEAN DEFAULT 0,
                    author_id INTEGER,
                    FOREIGN KEY (author_id) REFERENCES users (id)
                )
            ''')

            # Таблица глав
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS chapters (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    story_id INTEGER NOT NULL,
                    chapter_number INTEGER NOT NULL,
                    title TEXT,
                    description TEXT,
                    background_image TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (story_id) REFERENCES stories (id) ON DELETE CASCADE,
                    UNIQUE(story_id, chapter_number)
                )
            ''')

            # Таблица сцен
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS scenes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chapter_id INTEGER NOT NULL,
                    scene_number INTEGER NOT NULL,
                    character_name TEXT NOT NULL,
                    character_image TEXT,
                    dialogue_text TEXT NOT NULL,
                    background_image TEXT,
                    music_track TEXT,
                    effects TEXT,
                    position_x INTEGER DEFAULT 0,
                    position_y INTEGER DEFAULT 0,
                    scale REAL DEFAULT 1.0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (chapter_id) REFERENCES chapters (id) ON DELETE CASCADE,
                    UNIQUE(chapter_id, scene_number)
                )
            ''')

            # Таблица вариантов выбора
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS choices (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    scene_id INTEGER NOT NULL,
                    choice_number INTEGER NOT NULL,
                    choice_text TEXT NOT NULL,
                    next_scene_id INTEGER,
                    next_chapter_id INTEGER,
                    effect_type TEXT,
                    effect_data TEXT,
                    premium BOOLEAN DEFAULT 0,
                    diamonds_cost INTEGER DEFAULT 0,
                    affection_change INTEGER DEFAULT 0,
                    trust_change INTEGER DEFAULT 0,
                    passion_change INTEGER DEFAULT 0,
                    unlock_condition TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (scene_id) REFERENCES scenes (id) ON DELETE CASCADE,
                    FOREIGN KEY (next_scene_id) REFERENCES scenes (id),
                    FOREIGN KEY (next_chapter_id) REFERENCES chapters (id)
                )
            ''')

            # Таблица персонажей
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS characters (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    description TEXT,
                    avatar_image TEXT,
                    portrait_image TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Таблица связей историй и персонажей
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS story_characters (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    story_id INTEGER NOT NULL,
                    character_id INTEGER NOT NULL,
                    role TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (story_id) REFERENCES stories (id) ON DELETE CASCADE,
                    FOREIGN KEY (character_id) REFERENCES characters (id) ON DELETE CASCADE,
                    UNIQUE(story_id, character_id)
                )
            ''')

            print("✓ Таблицы сюжетов инициализированы")

            # Создание тестового администратора
            cursor.execute('SELECT * FROM users WHERE username = ?', ('admin',))
            admin_exists = cursor.fetchone()

            if not admin_exists:
                from models import User
                admin_user = User.create_admin(
                    username='admin',
                    email='admin@lovesim.com',
                    password='admin',
                    display_name='Администратор'
                )
                cursor.execute('''
                    INSERT INTO users (username, email, password_hash, password_salt, 
                                     display_name, is_admin, diamonds)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    admin_user.username,
                    admin_user.email,
                    admin_user.password_hash,
                    admin_user.password_salt,
                    admin_user.display_name,
                    admin_user.is_admin,
                    admin_user.diamonds
                ))
                print("✓ Создан тестовый администратор: admin / admin")

            print("✓ База данных инициализирована")

    # ========== Методы для пользователей ==========

    def get_user_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        """
        Получить пользователя по ID

        Args:
            user_id: ID пользователя

        Returns:
            Словарь с данными пользователя или None
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
            user = cursor.fetchone()
            return dict(user) if user else None

    def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """
        Получить пользователя по имени

        Args:
            username: Имя пользователя

        Returns:
            Словарь с данными пользователя или None
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM users WHERE username = ?', (username,))
            user = cursor.fetchone()
            return dict(user) if user else None

    def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """
        Получить пользователя по email

        Args:
            email: Email пользователя

        Returns:
            Словарь с данными пользователя или None
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM users WHERE email = ?', (email,))
            user = cursor.fetchone()
            return dict(user) if user else None

    def create_user(self, username: str, email: str, password_hash: str,
                    password_salt: str, display_name: str = None,
                    diamonds: int = 100) -> Optional[int]:
        """
        Создать нового пользователя

        Args:
            username: Имя пользователя
            email: Email
            password_hash: Хеш пароля
            password_salt: Соль пароля
            display_name: Отображаемое имя
            diamonds: Начальное количество алмазов

        Returns:
            ID созданного пользователя или None
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute('''
                    INSERT INTO users (username, email, password_hash, password_salt, 
                                     display_name, diamonds)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (username, email, password_hash, password_salt,
                      display_name or username, diamonds))
                return cursor.lastrowid
            except sqlite3.IntegrityError:
                return None

    def update_user(self, user_id: int, **kwargs) -> bool:
        """
        Обновить данные пользователя

        Args:
            user_id: ID пользователя
            **kwargs: Поля для обновления

        Returns:
            True если успешно, False в противном случае
        """
        allowed_fields = {
            'display_name', 'avatar_url', 'theme', 'diamonds',
            'failed_login_attempts', 'locked_until', 'last_login'
        }

        fields_to_update = {k: v for k, v in kwargs.items() if k in allowed_fields}

        if not fields_to_update:
            return False

        set_clause = ', '.join([f'{field} = ?' for field in fields_to_update.keys()])
        values = list(fields_to_update.values()) + [user_id]

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f'''
                UPDATE users 
                SET {set_clause}
                WHERE id = ?
            ''', values)
            return cursor.rowcount > 0

    def increment_diamonds(self, user_id: int, amount: int) -> bool:
        """
        Увеличить количество алмазов у пользователя

        Args:
            user_id: ID пользователя
            amount: Количество алмазов

        Returns:
            True если успешно
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE users 
                SET diamonds = diamonds + ?
                WHERE id = ?
            ''', (amount, user_id))
            return cursor.rowcount > 0

    def decrement_diamonds(self, user_id: int, amount: int) -> bool:
        """
        Уменьшить количество алмазов у пользователя

        Args:
            user_id: ID пользователя
            amount: Количество алмазов

        Returns:
            True если успешно, False если недостаточно алмазов
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE users 
                SET diamonds = diamonds - ?
                WHERE id = ? AND diamonds >= ?
            ''', (amount, user_id, amount))
            return cursor.rowcount > 0

    # ========== Методы для сессий ==========

    def create_session(self, user_id: int, session_token: str,
                       expires_at: datetime, ip_address: str = None,
                       user_agent: str = None) -> bool:
        """
        Создать новую сессию

        Args:
            user_id: ID пользователя
            session_token: Токен сессии
            expires_at: Время истечения
            ip_address: IP адрес
            user_agent: User agent

        Returns:
            True если успешно
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO sessions (user_id, session_token, expires_at, ip_address, user_agent)
                VALUES (?, ?, ?, ?, ?)
            ''', (user_id, session_token, expires_at.isoformat(), ip_address, user_agent))
            return True

    def validate_session(self, session_token: str) -> Optional[Dict[str, Any]]:
        """
        Проверить валидность сессии

        Args:
            session_token: Токен сессии

        Returns:
            Словарь с данными сессии и пользователя или None
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT s.*, u.id as user_id, u.username, u.email, u.display_name,
                       u.avatar_url, u.diamonds, u.theme, u.is_admin
                FROM sessions s
                JOIN users u ON s.user_id = u.id
                WHERE s.session_token = ? AND s.expires_at > ?
            ''', (session_token, datetime.now().isoformat()))
            result = cursor.fetchone()
            return dict(result) if result else None

    def delete_session(self, session_token: str) -> bool:
        """
        Удалить сессию

        Args:
            session_token: Токен сессии

        Returns:
            True если успешно
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM sessions WHERE session_token = ?', (session_token,))
            return cursor.rowcount > 0

    def delete_user_sessions(self, user_id: int) -> bool:
        """
        Удалить все сессии пользователя

        Args:
            user_id: ID пользователя

        Returns:
            True если успешно
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM sessions WHERE user_id = ?', (user_id,))
            return True

    # ========== Методы для сохранений игр ==========

    def save_game(self, user_id: int, game_name: str, save_slot: int,
                  save_data: Dict[str, Any]) -> bool:
        """
        Сохранить игру

        Args:
            user_id: ID пользователя
            game_name: Название игры
            save_slot: Слот сохранения
            save_data: Данные сохранения

        Returns:
            True если успешно
        """
        save_json = json.dumps(save_data, ensure_ascii=False)

        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute('''
                    INSERT INTO game_saves (user_id, game_name, save_slot, save_data)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(user_id, game_name, save_slot) 
                    DO UPDATE SET save_data = excluded.save_data, 
                                 updated_at = CURRENT_TIMESTAMP
                ''', (user_id, game_name, save_slot, save_json))
                return True
            except Exception:
                return False

    def load_game(self, user_id: int, game_name: str,
                  save_slot: int) -> Optional[Dict[str, Any]]:
        """
        Загрузить игру

        Args:
            user_id: ID пользователя
            game_name: Название игры
            save_slot: Слот сохранения

        Returns:
            Данные сохранения или None
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT save_data FROM game_saves
                WHERE user_id = ? AND game_name = ? AND save_slot = ?
            ''', (user_id, game_name, save_slot))
            result = cursor.fetchone()

            if result:
                return json.loads(result['save_data'])
            return None

    def get_user_saves(self, user_id: int, game_name: str) -> List[Dict[str, Any]]:
        """
        Получить все сохранения пользователя для игры

        Args:
            user_id: ID пользователя
            game_name: Название игры

        Returns:
            Список сохранений
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, save_slot, created_at, updated_at
                FROM game_saves
                WHERE user_id = ? AND game_name = ?
                ORDER BY save_slot
            ''', (user_id, game_name))
            return [dict(row) for row in cursor.fetchall()]

    # ========== Методы для статистики ==========

    def create_game_stat(self, user_id: int, game_name: str) -> Optional[int]:
        """
        Создать запись статистики игры

        Args:
            user_id: ID пользователя
            game_name: Название игры

        Returns:
            ID записи или None
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO game_stats (user_id, game_name)
                VALUES (?, ?)
            ''', (user_id, game_name))
            return cursor.lastrowid

    def update_game_stat(self, stat_id: int, **kwargs) -> bool:
        """
        Обновить статистику игры

        Args:
            stat_id: ID записи
            **kwargs: Поля для обновления

        Returns:
            True если успешно
        """
        allowed_fields = {'play_time', 'completed', 'rating', 'choices_made'}
        fields_to_update = {k: v for k, v in kwargs.items() if k in allowed_fields}

        if not fields_to_update:
            return False

        set_clause = ', '.join([f'{field} = ?' for field in fields_to_update.keys()])
        values = list(fields_to_update.values()) + [stat_id]

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f'''
                UPDATE game_stats 
                SET {set_clause}
                WHERE id = ?
            ''', values)
            return cursor.rowcount > 0

    def get_user_stats(self, user_id: int) -> List[Dict[str, Any]]:
        """
        Получить статистику пользователя

        Args:
            user_id: ID пользователя

        Returns:
            Список статистики
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT game_name, SUM(play_time) as total_time, 
                       COUNT(*) as games_played,
                       SUM(CASE WHEN completed THEN 1 ELSE 0 END) as completed_count
                FROM game_stats
                WHERE user_id = ?
                GROUP BY game_name
            ''', (user_id,))
            return [dict(row) for row in cursor.fetchall()]

    # ========== Методы для достижений ==========

    def unlock_achievement(self, user_id: int, achievement_name: str,
                           description: str = None) -> bool:
        """
        Разблокировать достижение

        Args:
            user_id: ID пользователя
            achievement_name: Название достижения
            description: Описание

        Returns:
            True если успешно
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute('''
                    INSERT INTO achievements (user_id, achievement_name, description)
                    VALUES (?, ?, ?)
                ''', (user_id, achievement_name, description))
                return True
            except sqlite3.IntegrityError:
                return False

    def get_user_achievements(self, user_id: int) -> List[Dict[str, Any]]:
        """
        Получить достижения пользователя

        Args:
            user_id: ID пользователя

        Returns:
            Список достижений
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT achievement_name, description, unlocked_at
                FROM achievements
                WHERE user_id = ?
                ORDER BY unlocked_at DESC
            ''', (user_id,))
            return [dict(row) for row in cursor.fetchall()]

    def get_choice_by_id(self, choice_id: int) -> Optional[Dict[str, Any]]:
        """
        Получить вариант выбора по ID

        Args:
            choice_id: ID варианта

        Returns:
            Словарь с данными варианта или None
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM choices WHERE id = ?', (choice_id,))
            choice = cursor.fetchone()
            return dict(choice) if choice else None

    def delete_user_saves(self, user_id):
        """Удалить все сохранения пользователя"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM game_saves WHERE user_id = ?', (user_id,))
            return cursor.rowcount > 0

    def delete_user_game_stats(self, user_id):
        """Удалить статистику игр пользователя"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM game_stats WHERE user_id = ?', (user_id,))
            return cursor.rowcount > 0

    def delete_user_achievements(self, user_id):
        """Удалить достижения пользователя"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM achievements WHERE user_id = ?', (user_id,))
            return cursor.rowcount > 0

    def get_scene_by_id(self, scene_id: int) -> Optional[Dict[str, Any]]:
        """
        Получить сцену по ID

        Args:
            scene_id: ID сцены

        Returns:
            Словарь с данными сцены или None
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM scenes WHERE id = ?', (scene_id,))
            scene = cursor.fetchone()
            return dict(scene) if scene else None

    def get_chapter_by_id(self, chapter_id: int) -> Optional[Dict[str, Any]]:
        """
        Получить главу по ID

        Args:
            chapter_id: ID главы

        Returns:
            Словарь с данными главы или None
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM chapters WHERE id = ?', (chapter_id,))
            chapter = cursor.fetchone()
            return dict(chapter) if chapter else None