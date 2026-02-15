#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Любовный симулятор - Веб приложение
Автор: V.V. Kalbin
"""

from flask import Flask, request, jsonify, session, render_template, redirect, url_for, make_response
from functools import wraps
from datetime import datetime
import os

from config import config
from database import Database
from auth import AuthService
from game import GameService

# Инициализация приложения
app = Flask(__name__,
            template_folder='templates',
            static_folder='static')

# Загрузка конфигурации
app.config.from_object(config['development'])

# Инициализация базы данных и сервисов
db = Database(app.config['DATABASE_PATH'])
auth_service = AuthService(db)
game_service = GameService(db)

from werkzeug.utils import secure_filename
import os

app.config['UPLOAD_FOLDER'] = 'static/images'
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'webp', 'avif'}

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']


# ========== Декораторы ==========

def login_required(f):
    """Декоратор проверки авторизации"""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)

    return decorated_function


def api_login_required(f):
    """Декоратор проверки авторизации для API"""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Необходима авторизация'}), 401
        return f(*args, **kwargs)

    return decorated_function


def admin_required(f):
    """Декоратор проверки прав администратора"""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login_page'))

        user = db.get_user_by_id(session['user_id'])
        if not user or not user.get('is_admin'):
            return render_template('error.html',
                                   message='Доступ запрещен',
                                   code=403), 403

        return f(*args, **kwargs)

    return decorated_function


# ========== API Роуты ==========

# ----- Авторизация -----

@app.route('/api/register', methods=['POST'])
def api_register():
    """API регистрации нового пользователя"""
    try:
        data = request.get_json()

        if not data:
            return jsonify({'error': 'Нет данных'}), 400

        username = data.get('username', '').strip()
        email = data.get('email', '').strip()
        password = data.get('password', '')
        display_name = data.get('display_name', '').strip() or None

        success, message, user_data = auth_service.register_user(
            username=username,
            email=email,
            password=password,
            display_name=display_name
        )

        if not success:
            return jsonify({'error': message}), 400

        # Создание сессии
        session['user_id'] = user_data['id']
        session['username'] = user_data['username']

        return jsonify({
            'success': True,
            'message': message,
            'user': {
                'id': user_data['id'],
                'username': user_data['username'],
                'email': user_data['email'],
                'display_name': user_data['display_name'],
                'diamonds': user_data['diamonds'],
                'theme': user_data['theme']
            }
        }), 201

    except Exception as e:
        return jsonify({'error': f'Ошибка регистрации: {str(e)}'}), 500


@app.route('/api/login', methods=['POST'])
def api_login():
    """API авторизации"""
    try:
        data = request.get_json()

        if not data:
            return jsonify({'error': 'Нет данных'}), 400

        identifier = data.get('identifier', '').strip()
        password = data.get('password', '')

        success, message, user_data, session_token = auth_service.login_user(
            identifier=identifier,
            password=password,
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent')
        )

        if not success:
            return jsonify({'error': message}), 401

        # Создание сессии
        session['user_id'] = user_data['id']
        session['username'] = user_data['username']

        return jsonify({
            'success': True,
            'message': message,
            'user': {
                'id': user_data['id'],
                'username': user_data['username'],
                'email': user_data['email'],
                'display_name': user_data['display_name'],
                'avatar_url': user_data['avatar_url'],
                'diamonds': user_data['diamonds'],
                'theme': user_data['theme'],
                'is_admin': user_data['is_admin']
            },
            'session_token': session_token
        }), 200

    except Exception as e:
        return jsonify({'error': f'Ошибка авторизации: {str(e)}'}), 500


@app.route('/api/logout', methods=['POST'])
@api_login_required
def api_logout():
    """API выхода из системы"""
    try:
        session_token = request.headers.get('Authorization', '').replace('Bearer ', '')

        if session_token:
            auth_service.logout_user(session_token)

        session.clear()

        return jsonify({'success': True, 'message': 'Выход выполнен'}), 200

    except Exception as e:
        return jsonify({'error': f'Ошибка выхода: {str(e)}'}), 500


@app.route('/api/profile', methods=['GET'])
@api_login_required
def api_get_profile():
    """API получения профиля"""
    try:
        user = db.get_user_by_id(session['user_id'])

        if not user:
            session.clear()
            return jsonify({'error': 'Пользователь не найден'}), 404

        # Получение статистики
        stats = db.get_user_stats(session['user_id'])
        achievements = db.get_user_achievements(session['user_id'])

        return jsonify({
            'success': True,
            'user': {
                'id': user['id'],
                'username': user['username'],
                'email': user['email'],
                'display_name': user['display_name'],
                'avatar_url': user['avatar_url'],
                'diamonds': user['diamonds'],
                'theme': user['theme'],
                'created_at': user['created_at'],
                'last_login': user['last_login'],
                'is_admin': user['is_admin']
            },
            'stats': stats,
            'achievements': achievements
        }), 200

    except Exception as e:
        return jsonify({'error': f'Ошибка получения профиля: {str(e)}'}), 500


@app.route('/api/profile', methods=['PUT'])
@api_login_required
def api_update_profile():
    """API обновления профиля"""
    try:
        data = request.get_json()

        if not data:
            return jsonify({'error': 'Нет данных'}), 400

        update_data = {}

        if 'display_name' in data:
            display_name = data['display_name'].strip()
            if display_name and len(display_name) >= 2:
                update_data['display_name'] = display_name

        if 'theme' in data:
            theme = data['theme']
            if theme in ['orange', 'purple', 'dark-green']:
                update_data['theme'] = theme

        if 'avatar_url' in data:
            update_data['avatar_url'] = data['avatar_url'].strip()

        if update_data:
            success = db.update_user(session['user_id'], **update_data)

            if not success:
                return jsonify({'error': 'Ошибка обновления профиля'}), 500

        # Получение обновленных данных
        updated_user = db.get_user_by_id(session['user_id'])

        return jsonify({
            'success': True,
            'message': 'Профиль обновлен',
            'user': {
                'id': updated_user['id'],
                'username': updated_user['username'],
                'display_name': updated_user['display_name'],
                'avatar_url': updated_user['avatar_url'],
                'diamonds': updated_user['diamonds'],
                'theme': updated_user['theme']
            }
        }), 200

    except Exception as e:
        return jsonify({'error': f'Ошибка обновления профиля: {str(e)}'}), 500


# ----- Игры -----

@app.route('/api/games', methods=['GET'])
@api_login_required
def api_get_games():
    """API получения списка игр"""
    try:
        games = game_service.get_available_games(session['user_id'])

        return jsonify({
            'success': True,
            'games': games
        }), 200

    except Exception as e:
        return jsonify({'error': f'Ошибка получения списка игр: {str(e)}'}), 500


@app.route('/api/games/<game_key>/access', methods=['GET'])
@api_login_required
def api_check_game_access(game_key):
    """API проверки доступа к игре"""
    try:
        accessible, message = game_service.can_access_game(session['user_id'], game_key)

        return jsonify({
            'accessible': accessible,
            'message': message
        }), 200

    except Exception as e:
        return jsonify({'error': f'Ошибка проверки доступа: {str(e)}'}), 500


@app.route('/api/games/<game_key>/purchase', methods=['POST'])
@api_login_required
def api_purchase_game(game_key):
    """API покупки игры"""
    try:
        success, message = game_service.purchase_game(session['user_id'], game_key)

        if not success:
            return jsonify({'error': message}), 400

        # Обновление данных пользователя
        user = db.get_user_by_id(session['user_id'])

        return jsonify({
            'success': True,
            'message': message,
            'user': {
                'diamonds': user['diamonds']
            }
        }), 200

    except Exception as e:
        return jsonify({'error': f'Ошибка покупки: {str(e)}'}), 500


@app.route('/api/games/<game_key>/load', methods=['GET'])
@api_login_required
def api_load_game(game_key):
    """API загрузки игры"""
    try:
        save_slot = request.args.get('slot', 1, type=int)

        game_state = game_service.load_game_state(session['user_id'], game_key, save_slot)

        if not game_state:
            return jsonify({'error': 'Игра не найдена'}), 404

        # Получение текущей сцены
        chapter = game_state.get('chapter', 1)
        scene = game_state.get('scene', 1)

        story_data = game_service.get_game_story(game_key, chapter, scene)

        return jsonify({
            'success': True,
            'game_state': game_state,
            'story': story_data
        }), 200

    except Exception as e:
        return jsonify({'error': f'Ошибка загрузки игры: {str(e)}'}), 500


@app.route('/api/games/<game_key>/save', methods=['POST'])
@api_login_required
def api_save_game(game_key):
    """API сохранения игры"""
    try:
        data = request.get_json()

        if not data:
            return jsonify({'error': 'Нет данных'}), 400

        game_state = data.get('game_state')
        save_slot = data.get('slot', 1)

        if not game_state:
            return jsonify({'error': 'Нет данных для сохранения'}), 400

        success = game_service.save_game_state(
            session['user_id'],
            game_key,
            game_state,
            save_slot
        )

        if not success:
            return jsonify({'error': 'Ошибка сохранения'}), 500

        return jsonify({
            'success': True,
            'message': 'Игра сохранена'
        }), 200

    except Exception as e:
        return jsonify({'error': f'Ошибка сохранения игры: {str(e)}'}), 500


@app.route('/api/games/<game_key>/choice', methods=['POST'])
@api_login_required
def api_make_choice(game_key):
    """API совершения выбора в игре"""
    try:
        data = request.get_json()

        if not data:
            return jsonify({'error': 'Нет данных'}), 400

        choice_id = data.get('choice_id')
        save_slot = data.get('slot', 1)

        if not choice_id:
            return jsonify({'error': 'Не указан выбор'}), 400

        success, message, game_state = game_service.make_choice(
            session['user_id'],
            game_key,
            choice_id,
            save_slot
        )

        if not success:
            return jsonify({'error': message}), 400

        # Получение следующей сцены

        choice = db.get_choice_by_id(choice_id)

        if choice['next_scene_id']:
            scene = int(choice['next_scene_id'])
        else:
            scene = game_state.get('scene', 1) + 1

        if choice['next_chapter_id']:
            chapter = int(choice['next_chapter_id'])
        else:
            chapter = game_state.get('chapter', 1)

        game_state['scene'] = scene
        game_state['chapter'] = chapter

        game_service.save_game_state(session['user_id'], game_key, game_state, save_slot)

        story_data = game_service.get_game_story(game_key, chapter, scene)

        game_service.update_game_stats(session['user_id'], game_key, choices_made=1)

        return jsonify({
            'success': True,
            'message': message,
            'game_state': game_state,
            'story': story_data
        }), 200

    except Exception as e:
        return jsonify({'error': f'Ошибка выбора: {str(e)}'}), 500


@app.route('/api/progress', methods=['GET'])
@api_login_required
def api_get_progress():
    """API получения прогресса пользователя"""
    try:
        progress = game_service.get_user_progress(session['user_id'])

        return jsonify({
            'success': True,
            'progress': progress
        }), 200

    except Exception as e:
        return jsonify({'error': f'Ошибка получения прогресса: {str(e)}'}), 500


# ========== Web Роуты ==========

@app.route('/')
def index():
    """Главная страница"""
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login_page'))


@app.route('/login')
def login_page():
    """Страница авторизации"""
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('login.html')


@app.route('/register')
def register_page():
    """Страница регистрации"""
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('register.html')


@app.route('/dashboard')
@login_required
def dashboard():
    """Дашборд пользователя"""
    user = db.get_user_by_id(session['user_id'])

    if not user:
        session.clear()
        return redirect(url_for('login_page'))

    # Получение списка игр
    games = game_service.get_available_games(session['user_id'])

    # Получение прогресса
    progress = game_service.get_user_progress(session['user_id'])

    return render_template(
        'dashboard.html',
        user=user,
        games=games,
        progress=progress
    )


@app.route('/game/<game_key>')
@login_required
def game_page(game_key):
    """Страница игры"""
    user = db.get_user_by_id(session['user_id'])

    if not user:
        session.clear()
        return redirect(url_for('login_page'))

    # Проверка доступа к игре
    accessible, message = game_service.can_access_game(session['user_id'], game_key)

    if not accessible:
        return render_template('error.html', message=message, code=403), 403

    # Получение информации об игре
    game_info = game_service.get_game_info(game_key)

    if not game_info:
        return render_template('error.html', message='Игра не найдена', code=404), 404

    # Загрузка состояния игры
    game_state = game_service.load_game_state(session['user_id'], game_key)

    # Получение текущей сцены
    chapter = game_state.get('chapter', 1)
    scene = game_state.get('scene', 1)
    story_data = game_service.get_game_story(game_key, chapter, scene)

    if not story_data:
        # Если сцена не найдена, попробуем загрузить первую сцену
        game_state['chapter'] = 1
        game_state['scene'] = 1
        story_data = game_service.get_game_story(game_key, 1, 1)

        if not story_data:
            return render_template('error.html', message='Сцена не найдена', code=404), 404

    return render_template(
        'game_2.html',
        user=user,
        game_key=game_key,
        game_info=game_info,
        game_state=game_state,
        story=story_data
    )


@app.route('/profile')
@login_required
def profile_page():
    """Страница профиля"""
    user = db.get_user_by_id(session['user_id'])

    if not user:
        session.clear()
        return redirect(url_for('login_page'))

    stats = db.get_user_stats(session['user_id'])
    achievements = db.get_user_achievements(session['user_id'])

    return render_template(
        'profile.html',
        user=user,
        stats=stats,
        achievements=achievements
    )


@app.route('/admin')
@admin_required
def admin_page():
    """Административная панель"""
    user = db.get_user_by_id(session['user_id'])

    # Статистика базы данных
    with db.get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute('SELECT COUNT(*) as count FROM users')
        total_users = cursor.fetchone()['count']

        cursor.execute('SELECT COUNT(*) as count FROM game_stats')
        total_games_played = cursor.fetchone()['count']

        cursor.execute('SELECT SUM(play_time) as total FROM game_stats')
        total_play_time = cursor.fetchone()['total'] or 0

        cursor.execute('SELECT * FROM users ORDER BY created_at DESC LIMIT 10')
        recent_users = [dict(row) for row in cursor.fetchall()]

    return render_template(
        'admin.html',
        user=user,
        total_users=total_users,
        total_games_played=total_games_played,
        total_play_time=total_play_time,
        recent_users=recent_users
    )


@app.route('/error')
def error_page():
    """Страница ошибки"""
    code = request.args.get('code', 404, type=int)
    message = request.args.get('message', 'Страница не найдена')

    return render_template('error.html', message=message, code=code), code


from story import StoryService

# Инициализация сервиса сюжетов
story_service = StoryService(db)


# ========== API для редактора сюжетов ==========

# ----- Истории -----

@app.route('/api/stories', methods=['GET'])
@admin_required
def api_get_stories():
    """API получения всех историй"""
    try:
        published_only = request.args.get('published', 'false').lower() == 'true'
        stories = story_service.get_all_stories(published_only)

        return jsonify({
            'success': True,
            'stories': stories
        }), 200

    except Exception as e:
        return jsonify({'error': f'Ошибка получения историй: {str(e)}'}), 500


@app.route('/api/stories', methods=['POST'])
@admin_required
def api_create_story():
    """API создания новой истории"""
    try:
        data = request.get_json()

        if not data:
            return jsonify({'error': 'Нет данных'}), 400

        story_id = story_service.create_story(
            story_key=data['story_key'],
            title=data['title'],
            description=data.get('description'),
            cover_image=data.get('cover_image'),
            background_image=data.get('background_image'),
            premium=data.get('premium', False),
            diamonds_cost=data.get('diamonds_cost', 0),
            author_id=session['user_id']
        )

        if not story_id:
            return jsonify({'error': 'Ошибка создания истории'}), 500

        story = story_service.get_story_by_id(story_id)

        return jsonify({
            'success': True,
            'message': 'История создана',
            'story': story
        }), 201

    except Exception as e:
        return jsonify({'error': f'Ошибка создания истории: {str(e)}'}), 500


@app.route('/api/stories/<int:story_id>', methods=['GET'])
@admin_required
def api_get_story(story_id):
    """API получения истории по ID"""
    try:
        story = story_service.get_story_by_id(story_id)

        if not story:
            return jsonify({'error': 'История не найдена'}), 404

        # Получить главы
        chapters = story_service.get_chapters_by_story(story_id)

        # Получить персонажей
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT c.* FROM characters c
                JOIN story_characters sc ON c.id = sc.character_id
                WHERE sc.story_id = ?
            ''', (story_id,))
            characters = [dict(row) for row in cursor.fetchall()]

        return jsonify({
            'success': True,
            'story': story,
            'chapters': chapters,
            'characters': characters
        }), 200

    except Exception as e:
        return jsonify({'error': f'Ошибка получения истории: {str(e)}'}), 500


@app.route('/api/stories/<int:story_id>', methods=['PUT'])
@admin_required
def api_update_story(story_id):
    """API обновления истории"""
    try:
        data = request.get_json()

        if not data:
            return jsonify({'error': 'Нет данных'}), 400

        success = story_service.update_story(story_id, **data)

        if not success:
            return jsonify({'error': 'Ошибка обновления истории'}), 500

        story = story_service.get_story_by_id(story_id)

        return jsonify({
            'success': True,
            'message': 'История обновлена',
            'story': story
        }), 200

    except Exception as e:
        return jsonify({'error': f'Ошибка обновления истории: {str(e)}'}), 500


@app.route('/api/stories/<int:story_id>', methods=['DELETE'])
@admin_required
def api_delete_story(story_id):
    """API удаления истории"""
    try:
        success = story_service.delete_story(story_id)

        if not success:
            return jsonify({'error': 'Ошибка удаления истории'}), 500

        return jsonify({
            'success': True,
            'message': 'История удалена'
        }), 200

    except Exception as e:
        return jsonify({'error': f'Ошибка удаления истории: {str(e)}'}), 500


@app.route('/api/stories/<int:story_id>/export', methods=['GET'])
@admin_required
def api_export_story(story_id):
    """API экспорта истории"""
    try:
        story_data = story_service.export_story(story_id)

        if not story_data:
            return jsonify({'error': 'История не найдена'}), 404

        return jsonify({
            'success': True,
            'story': story_data
        }), 200

    except Exception as e:
        return jsonify({'error': f'Ошибка экспорта истории: {str(e)}'}), 500


@app.route('/api/stories/import', methods=['POST'])
@admin_required
def api_import_story():
    """API импорта истории"""
    try:
        data = request.get_json()

        if not data:
            return jsonify({'error': 'Нет данных'}), 400

        story_id = story_service.import_story(data, session['user_id'])

        if not story_id:
            return jsonify({'error': 'Ошибка импорта истории'}), 500

        return jsonify({
            'success': True,
            'message': 'История импортирована',
            'story_id': story_id
        }), 201

    except Exception as e:
        return jsonify({'error': f'Ошибка импорта истории: {str(e)}'}), 500


# ----- Главы -----

@app.route('/api/stories/<int:story_id>/chapters', methods=['GET'])
@admin_required
def api_get_chapters(story_id):
    """API получения глав истории"""
    try:
        chapters = story_service.get_chapters_by_story(story_id)

        # Добавить сцены для каждой главы
        for chapter in chapters:
            chapter_id = chapter['id']
            scenes = story_service.get_scenes_by_chapter(chapter_id)
            chapter['scenes'] = scenes

        return jsonify({
            'success': True,
            'chapters': chapters
        }), 200

    except Exception as e:
        return jsonify({'error': f'Ошибка получения глав: {str(e)}'}), 500


@app.route('/api/chapters', methods=['POST'])
@admin_required
def api_create_chapter():
    """API создания главы"""
    try:
        data = request.get_json()

        if not data:
            return jsonify({'error': 'Нет данных'}), 400

        chapter_id = story_service.create_chapter(
            story_id=data['story_id'],
            chapter_number=data['chapter_number'],
            title=data.get('title'),
            description=data.get('description'),
            background_image=data.get('background_image')
        )

        if not chapter_id:
            return jsonify({'error': 'Ошибка создания главы'}), 500

        chapter = story_service.get_chapter_by_id(chapter_id)

        return jsonify({
            'success': True,
            'message': 'Глава создана',
            'chapter': chapter
        }), 201

    except Exception as e:
        return jsonify({'error': f'Ошибка создания главы: {str(e)}'}), 500


@app.route('/api/chapters/<int:chapter_id>', methods=['PUT'])
@admin_required
def api_update_chapter(chapter_id):
    """API обновления главы"""
    try:
        data = request.get_json()

        if not data:
            return jsonify({'error': 'Нет данных'}), 400

        success = story_service.update_chapter(chapter_id, **data)

        if not success:
            return jsonify({'error': 'Ошибка обновления главы'}), 500

        chapter = story_service.get_chapter_by_id(chapter_id)

        return jsonify({
            'success': True,
            'message': 'Глава обновлена',
            'chapter': chapter
        }), 200

    except Exception as e:
        return jsonify({'error': f'Ошибка обновления главы: {str(e)}'}), 500


@app.route('/api/chapters/<int:chapter_id>', methods=['DELETE'])
@admin_required
def api_delete_chapter(chapter_id):
    """API удаления главы"""
    try:
        success = story_service.delete_chapter(chapter_id)

        if not success:
            return jsonify({'error': 'Ошибка удаления главы'}), 500

        return jsonify({
            'success': True,
            'message': 'Глава удалена'
        }), 200

    except Exception as e:
        return jsonify({'error': f'Ошибка удаления главы: {str(e)}'}), 500


# ----- Сцены -----

@app.route('/api/chapters/<int:chapter_id>/scenes', methods=['GET'])
@admin_required
def api_get_scenes(chapter_id):
    """API получения сцен главы"""
    try:
        scenes = story_service.get_scenes_by_chapter(chapter_id)

        # Добавить варианты выбора для каждой сцены
        for scene in scenes:
            scene_id = scene['id']
            choices = story_service.get_choices_by_scene(scene_id)
            scene['choices'] = choices

        return jsonify({
            'success': True,
            'scenes': scenes
        }), 200

    except Exception as e:
        return jsonify({'error': f'Ошибка получения сцен: {str(e)}'}), 500


@app.route('/api/scenes', methods=['POST'])
@admin_required
def api_create_scene():
    """API создания сцены"""
    try:
        data = request.get_json()

        if not data:
            return jsonify({'error': 'Нет данных'}), 400

        scene_id = story_service.create_scene(
            chapter_id=data['chapter_id'],
            scene_number=data['scene_number'],
            character_name=data['character_name'],
            dialogue_text=data['dialogue_text'],
            character_image=data.get('character_image'),
            background_image=data.get('background_image'),
            music_track=data.get('music_track'),
            position_x=data.get('position_x', 0),
            position_y=data.get('position_y', 0),
            scale=data.get('scale', 1.0)
        )

        if not scene_id:
            return jsonify({'error': 'Ошибка создания сцены'}), 500

        scene = story_service.get_scene_by_id(scene_id)

        return jsonify({
            'success': True,
            'message': 'Сцена создана',
            'scene': scene
        }), 201

    except Exception as e:
        return jsonify({'error': f'Ошибка создания сцены: {str(e)}'}), 500


@app.route('/api/scenes/<int:scene_id>', methods=['PUT'])
@admin_required
def api_update_scene(scene_id):
    """API обновления сцены"""
    try:
        data = request.get_json()

        if not data:
            return jsonify({'error': 'Нет данных'}), 400

        success = story_service.update_scene(scene_id, **data)

        if not success:
            return jsonify({'error': 'Ошибка обновления сцены'}), 500

        scene = story_service.get_scene_by_id(scene_id)

        return jsonify({
            'success': True,
            'message': 'Сцена обновлена',
            'scene': scene
        }), 200

    except Exception as e:
        return jsonify({'error': f'Ошибка обновления сцены: {str(e)}'}), 500


@app.route('/api/scenes/<int:scene_id>', methods=['DELETE'])
@admin_required
def api_delete_scene(scene_id):
    """API удаления сцены"""
    try:
        success = story_service.delete_scene(scene_id)

        if not success:
            return jsonify({'error': 'Ошибка удаления сцены'}), 500

        return jsonify({
            'success': True,
            'message': 'Сцена удалена'
        }), 200

    except Exception as e:
        return jsonify({'error': f'Ошибка удаления сцены: {str(e)}'}), 500


# ----- Варианты выбора -----

@app.route('/api/scenes/<int:scene_id>/choices', methods=['GET'])
@admin_required
def api_get_choices(scene_id):
    """API получения вариантов выбора сцены"""
    try:
        choices = story_service.get_choices_by_scene(scene_id)

        return jsonify({
            'success': True,
            'choices': choices
        }), 200

    except Exception as e:
        return jsonify({'error': f'Ошибка получения вариантов: {str(e)}'}), 500


@app.route('/api/choices', methods=['POST'])
@admin_required
def api_create_choice():
    """API создания варианта выбора"""
    try:
        data = request.get_json()

        if not data:
            return jsonify({'error': 'Нет данных'}), 400

        choice_id = story_service.create_choice(
            scene_id=data['scene_id'],
            choice_number=data['choice_number'],
            choice_text=data['choice_text'],
            next_scene_id=data.get('next_scene_id'),
            next_chapter_id=data.get('next_chapter_id'),
            effect_type=data.get('effect_type'),
            effect_data=data.get('effect_data'),
            premium=data.get('premium', False),
            diamonds_cost=data.get('diamonds_cost', 0),
            affection_change=data.get('affection_change', 0),
            trust_change=data.get('trust_change', 0),
            passion_change=data.get('passion_change', 0),
            unlock_condition=data.get('unlock_condition')
        )

        if not choice_id:
            return jsonify({'error': 'Ошибка создания варианта'}), 500

        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM choices WHERE id = ?', (choice_id,))
            choice = dict(cursor.fetchone())

        return jsonify({
            'success': True,
            'message': 'Вариант создан',
            'choice': choice
        }), 201

    except Exception as e:
        return jsonify({'error': f'Ошибка создания варианта: {str(e)}'}), 500


@app.route('/api/choices/<int:choice_id>', methods=['PUT'])
@admin_required
def api_update_choice(choice_id):
    """API обновления варианта выбора"""
    try:
        data = request.get_json()

        if not data:
            return jsonify({'error': 'Нет данных'}), 400

        success = story_service.update_choice(choice_id, **data)

        if not success:
            return jsonify({'error': 'Ошибка обновления варианта'}), 500

        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM choices WHERE id = ?', (choice_id,))
            choice = dict(cursor.fetchone())

        return jsonify({
            'success': True,
            'message': 'Вариант обновлен',
            'choice': choice
        }), 200

    except Exception as e:
        return jsonify({'error': f'Ошибка обновления варианта: {str(e)}'}), 500


@app.route('/api/choices/<int:choice_id>', methods=['DELETE'])
@admin_required
def api_delete_choice(choice_id):
    """API удаления варианта выбора"""
    try:
        success = story_service.delete_choice(choice_id)

        if not success:
            return jsonify({'error': 'Ошибка удаления варианта'}), 500

        return jsonify({
            'success': True,
            'message': 'Вариант удален'
        }), 200

    except Exception as e:
        return jsonify({'error': f'Ошибка удаления варианта: {str(e)}'}), 500


@app.route('/admin/stories')
@admin_required
def admin_stories_page():
    """Страница управления историями"""
    user = db.get_user_by_id(session['user_id'])
    return render_template('admin/stories.html', user=user)


@app.route('/admin/stories/editor/<int:story_id>')
@admin_required
def admin_story_editor_page(story_id):
    """Страница редактора истории"""
    user = db.get_user_by_id(session['user_id'])
    story = story_service.get_story_by_id(story_id)

    if not story:
        return redirect(url_for('admin_stories_page'))

    return render_template('admin/story_editor.html', user=user, story=story)


@app.route('/admin/stories/create')
@admin_required
def admin_story_create_page():
    """Страница создания новой истории"""
    user = db.get_user_by_id(session['user_id'])
    return render_template('admin/story_create.html', user=user)


@app.route('/api/choices/<int:choice_id>', methods=['GET'])
@admin_required
def api_get_choice(choice_id):
    """API получения варианта выбора по ID"""
    try:
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM choices WHERE id = ?', (choice_id,))
            choice = cursor.fetchone()

            if not choice:
                return jsonify({'error': 'Вариант не найден'}), 404

            return jsonify({
                'success': True,
                'choice': dict(choice)
            }), 200

    except Exception as e:
        return jsonify({'error': f'Ошибка получения варианта: {str(e)}'}), 500


@app.route('/api/upload/image', methods=['POST'])
@admin_required
def upload_image():
    """Загрузка изображений в редакторе"""
    if 'image' not in request.files:
        return jsonify({'error': 'Нет файла изображения'}), 400

    file = request.files['image']
    if file.filename == '':
        return jsonify({'error': 'Файл не выбран'}), 400

    if file and allowed_file(file.filename):
        # Создаем директорию, если не существует
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

        # Генерируем безопасное имя файла
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)

        # Возвращаем URL изображения
        return jsonify({
            'success': True,
            'url': f'/static/images/{filename}'
        }), 200

    return jsonify({'error': 'Недопустимый формат файла'}), 400


@app.route('/admin/users')
@admin_required
def admin_users_page():
    """Страница управления пользователями"""
    user = db.get_user_by_id(session['user_id'])

    # Получаем всех пользователей
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM users 
            ORDER BY created_at DESC
        ''')
        users = [dict(row) for row in cursor.fetchall()]

    return render_template('admin/users.html', user=user, users=users)


@app.route('/api/admin/users/<int:user_id>/reset-progress', methods=['POST'])
@admin_required
def reset_user_progress(user_id):
    """Сброс прогресса пользователя (для тестирования)"""
    try:
        # Удаляем все сохранения
        db.delete_user_saves(user_id)

        # Удаляем статистику игр
        db.delete_user_game_stats(user_id)

        # Удаляем достижения
        db.delete_user_achievements(user_id)

        return jsonify({
            'success': True,
            'message': 'Прогресс пользователя успешно сброшен'
        }), 200
    except Exception as e:
        return jsonify({'error': f'Ошибка сброса прогресса: {str(e)}'}), 500


# ========== Обработчики ошибок ==========

@app.errorhandler(404)
def not_found_error(error):
    return render_template('error.html', message='Страница не найдена', code=404), 404


@app.errorhandler(500)
def internal_error(error):
    return render_template('error.html', message='Внутренняя ошибка сервера', code=500), 500


# ========== Запуск приложения ==========

if __name__ == '__main__':
    print("=" * 60)
    print("🎮 Любовный симулятор - Веб приложение")
    print("=" * 60)
    print(f"✓ База данных: {app.config['DATABASE_PATH']}")
    print(f"✓ Тестовый админ: admin / admin")
    print(f"✓ Сервер запущен на: http://localhost:5000")
    print(f"✓ Режим отладки: {app.debug}")
    print("=" * 60)

    app.run(debug=True, host='0.0.0.0', port=5000)