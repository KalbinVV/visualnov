# -*- coding: utf-8 -*-
"""
Конфигурация приложения
Любовный симулятор
"""

import os
import secrets
from datetime import timedelta


class Config:
    """Базовая конфигурация"""

    # Секретный ключ
    SECRET_KEY = os.environ.get('SECRET_KEY', secrets.token_hex(32))

    # База данных
    DATABASE_PATH = 'love_simulator.db'
    DATABASE_URI = f'sqlite:///{DATABASE_PATH}'

    # Сессии
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = timedelta(days=30)

    # Безопасность
    MAX_LOGIN_ATTEMPTS = 5
    LOCKOUT_TIME = timedelta(minutes=15)

    # Пути
    TEMPLATES_FOLDER = 'templates'
    STATIC_FOLDER = 'static'

    # Игровые настройки
    STARTING_DIAMONDS = 100
    PREMIUM_DIAMONDS_COST = 50

    # CORS (если понадобится)
    CORS_HEADERS = 'Content-Type'


class DevelopmentConfig(Config):
    """Конфигурация для разработки"""
    DEBUG = True
    TESTING = False


class ProductionConfig(Config):
    """Конфигурация для продакшена"""
    DEBUG = False
    TESTING = False

    # В продакшене секретный ключ должен быть в переменных окружения
    SECRET_KEY = os.environ.get('SECRET_KEY')

    # Более строгие настройки безопасности
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True


class TestingConfig(Config):
    """Конфигурация для тестирования"""
    TESTING = True
    DEBUG = True
    DATABASE_PATH = ':memory:'  # In-memory база для тестов


# Выбор конфигурации
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}