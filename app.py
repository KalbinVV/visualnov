#!/usr/bin/env python3
# -*- coding: utf-8 -*-


from flask import Flask, request, jsonify, session, render_template, redirect, url_for, make_response
from functools import wraps
import sys

from sqlalchemy import update
from sqlalchemy.orm import Session

from config import config
from database import Database, User, Choice, Scene, Story, GameSave, DiamondCode, DiamondCodesHistory, TeamCode, \
    ChoiceHistory, MoveCode
from auth import AuthService
from game import GameService

app = Flask(__name__,
            template_folder='templates',
            static_folder='static')

app.config.from_object(config['development'])

db = Database("postgresql+psycopg2://postgres:y82AtQ8aM8=m@84.21.191.37:5432/postgres")
auth_service = AuthService(db)
game_service = GameService(db)

from werkzeug.utils import secure_filename
import os

app.config['UPLOAD_FOLDER'] = 'static/images'
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'webp', 'avif'}

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login_page'))
        return f(*args, **kwargs)

    return decorated_function


def api_login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Необходима авторизация'}), 401
        return f(*args, **kwargs)

    return decorated_function


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login_page'))

        user = db.get_user_by_id(session['user_id'])
        if not user or not user.is_admin:
            return render_template('error.html',
                                   message='Доступ запрещен',
                                   code=403), 403

        return f(*args, **kwargs)

    return decorated_function


@app.route('/api/register', methods=['POST'])
def api_register():
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

        session['user_id'] = user_data.id
        session['username'] = user_data.username

        return jsonify({
            'success': True,
            'message': message,
            'user': {
                'id': user_data.id,
                'username': user_data.username,
                'email': user_data.email,
                'display_name': user_data.display_name,
                'diamonds': user_data.diamonds,
                'theme': user_data.theme
            }
        }), 201

    except Exception as e:
        return jsonify({'error': f'Ошибка регистрации: {str(e)}'}), 500


@app.route('/api/login', methods=['POST'])
def api_login():
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

        session['user_id'] = user_data.id
        session['username'] = user_data.username

        return jsonify({
            'success': True,
            'message': message,
            'user': {
                'id': user_data.id,
                'username': user_data.username,
                'email': user_data.email,
                'display_name': user_data.display_name,
                'avatar_url': user_data.avatar_url,
                'diamonds': user_data.diamonds,
                'theme': user_data.theme,
                'is_admin': user_data.is_admin
            },
            'session_token': session_token
        }), 200

    except Exception as e:
        return jsonify({'error': f'Ошибка авторизации: {str(e)}'}), 500


@app.route('/api/logout', methods=['POST'])
@api_login_required
def api_logout():
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
    try:
        with Session(db.engine) as s:
            user = s.query(User).filter_by(id=session['user_id']).first()

            if not user:
                session.clear()
                return jsonify({'error': 'Пользователь не найден'}), 404

            stats = db.get_user_stats(session['user_id'])
            achievements = db.get_user_achievements(session['user_id'])

            return jsonify({
                'success': True,
                'user': {
                    'id': user.id,
                    'username': user.username,
                    'email': user.email,
                    'display_name': user.display_name,
                    'avatar_url': user.avatar_url,
                    'diamonds': user.diamonds,
                    'theme': user.theme,
                    'created_at': user.created_at,
                    'last_login': user.last_login,
                    'is_admin': user.is_admin,
                    'team': {
                        'name': user.team.name
                    } if user.team else None
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


@app.route('/api/games', methods=['GET'])
@api_login_required
def api_get_games():
    try:
        games = game_service.get_available_games(session['user_id'])

        return jsonify({
            'success': True,
            'games': games
        }), 200

    except Exception as e:
        return jsonify({'error': f'Ошибка получения списка игр: {str(e)}'}), 500


@app.route('/api/games/<game_id>/access', methods=['GET'])
@api_login_required
def api_check_game_access(game_id: int):
    try:
        accessible, message = game_service.can_access_game(session['user_id'], game_id)

        return jsonify({
            'accessible': accessible,
            'message': message
        }), 200

    except Exception as e:
        return jsonify({'error': f'Ошибка проверки доступа: {str(e)}'}), 500


@app.route('/api/games/<story_id>/choice', methods=['POST'])
@api_login_required
def api_make_choice(story_id: int):
    try:
        data = request.get_json()

        accessible, message = game_service.can_access_game(session['user_id'], story_id)

        if not accessible:
            return render_template('error.html', message=message, code=403), 403

        choice_id = data.get('choice_id')

        status, msg, scene_id, chapter_id = game_service.make_choice(session['user_id'], story_id,
                                                                     int(choice_id))

        if status:
            with Session(db.engine) as s:
                next_scene = s.get(Scene, scene_id)
                user = s.get(User, session['user_id'])

                return jsonify({
                    'success': status,
                    'message': msg,
                    'scene_id': scene_id,
                    'chapter_id': chapter_id,
                    'next_scene': {
                        'scene_id': next_scene.id,
                        'character_image': next_scene.character_image,
                        'character_name': next_scene.character_name.replace('{name}', user.display_name),
                        'background': next_scene.background_image,
                        'dialogue': next_scene.dialogue_text.replace('{name}', user.display_name),
                        'choices': [{'data': Choice.as_dict(choice),
                                     'is_available': game_service.is_choice_available(user.id, choice_id)[0]}
                                    for choice in next_scene.choices] if next_scene.scene_type != "input" else [],
                        'current_user_diamonds': user.diamonds,
                        'scene_type': next_scene.scene_type,
                        'scene_effect': next_scene.scene_effect
                    }
                }), 200
        else:
            return jsonify({'success': status, 'message': msg})

    except Exception as e:
        print(e)
        return jsonify({'error': f'Ошибка выбора: {str(e)}'}), 500


@app.route('/api/games/<story_id>/choice_input', methods=['POST'])
@api_login_required
def api_make_input_choice(story_id: int):
    try:
        data = request.get_json()

        scene_id = int(data.get('scene_id'))
        choice_value = data.get('value')

        status, msg, scene_id, chapter_id = game_service.make_input_choice(session['user_id'], story_id, scene_id, choice_value)

        if status:
            with Session(db.engine) as s:
                next_scene = s.get(Scene, scene_id)
                user = s.get(User, session['user_id'])

                return jsonify({
                    'success': status,
                    'message': msg,
                    'scene_id': scene_id,
                    'chapter_id': chapter_id,
                    'next_scene': {
                        'character_image': next_scene.character_image,
                        'character_name': next_scene.character_name.replace('{name}', user.display_name),
                        'background': next_scene.background_image,
                        'dialogue': next_scene.dialogue_text.replace('{name}', user.display_name),
                        'choices': [{'data': Choice.as_dict(choice),
                                     'is_available': game_service.is_choice_available(user.id, choice.id)[0]}
                                    for choice in next_scene.choices] if next_scene.scene_type != "input" else [],
                        'current_user_diamonds': user.diamonds,
                        'scene_type': next_scene.scene_type
                    }
                }), 200
        else:
            return jsonify({'success': status, 'message': msg})

    except Exception as e:
        print(e)
        return jsonify({'error': f'Ошибка выбора: {str(e)}'}), 500


@app.route('/api/games/<story_id>/to_next_scene', methods=['POST'])
@api_login_required
def to_next_scene(story_id: int):
    with (Session(db.engine) as s):
        accessible, message = game_service.can_access_game(session['user_id'], story_id)

        if not accessible:
            return render_template('error.html', message=message, code=403), 403

        user = s.get(User, session['user_id'])

        user_save = db.load_game_raw(user.id, story_id)
        scene = s.query(Scene).filter(Scene.id > user_save.scene_id,
                                      Scene.chapter_id == user_save.chapter_id
                                      ).order_by(Scene.id).first()

        if not scene:
            return jsonify({
                'success': False,
                'message': 'Конец!',
                'is_ending': True
            })

        db.save_game(user.id, story_id, scene.id, scene.chapter_id, 0, 0, 0)

        return jsonify({
            'success': True,
            'message': '',
            'scene_id': scene.id,
            'chapter_id': scene.chapter_id,
            'next_scene': {
                'character_image': scene.character_image,
                'character_name': scene.character_name.replace("{name}", user.display_name),
                'background': scene.background_image,
                'dialogue': scene.dialogue_text.replace("{name}", user.display_name),
                'choices': [{'data': Choice.as_dict(choice),
                             'is_available': game_service.is_choice_available(user.id, choice.id)[0]}
                            for choice in scene.choices
                            if game_service.is_choice_visible_for_user(user.id, choice.id)],
                'current_user_diamonds': user.diamonds,
                'scene_type': scene.scene_type,
                'scene_effect': scene.scene_effect
            }
        }), 200


@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login_page'))


@app.route('/login')
def login_page():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('login.html')


@app.route('/register')
def register_page():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('register.html')


@app.route('/dashboard')
@login_required
def dashboard():
    user = db.get_user_by_id(session['user_id'])

    if not user:
        session.clear()
        return redirect(url_for('login_page'))

    games = game_service.get_available_games(session['user_id'])

    return render_template(
        'dashboard.html',
        user=user,
        games=games
    )


@app.route('/game/<story_id>')
@login_required
def game_page(story_id: int):
    user = db.get_user_by_id(session['user_id'])

    if not user:
        session.clear()
        return redirect(url_for('login_page'))

    accessible, message = game_service.can_access_game(session['user_id'], story_id)

    if not accessible:
        return render_template('error.html', message=message, code=403), 403

    game_info = game_service.get_game_info(story_id)

    if not game_info:
        return render_template('error.html', message='Игра не найдена', code=404), 404

    scene_data = game_service.get_current_user_scene_data(db, user.id, story_id)

    if not scene_data:
        return render_template('error.html', message='Сцена не найдена', code=404), 404

    return render_template(
        'game_2.html',
        user=user,
        story_id=story_id,
        scene_data=scene_data,
        game_info=game_info,
    )


@app.route('/profile')
@login_required
def profile_page():
    with Session(db.engine) as s:
        user = s.query(User).filter_by(id=session['user_id']).first()

        if not user:
            session.clear()
            return redirect(url_for('login_page'))

        stats = db.get_user_stats(session['user_id'])
        achievements = db.get_user_achievements(session['user_id'])

        return render_template(
            'profile.html',
            user=user,
            team_info=user.team,
            is_team_leader=user.is_leader,
            stats=stats,
            achievements=achievements
        )


@app.route('/admin')
@admin_required
def admin_page():
    user = db.get_user_by_id(session['user_id'])

    with db.get_connection() as conn:
        cursor = conn.connection.cursor()

        cursor.execute('SELECT COUNT(*) as count FROM users')
        total_users = cursor.fetchone()[0]

        cursor.execute('SELECT COUNT(*) as count FROM game_stats')

        total_games_played = cursor.fetchone()[0]

        cursor.execute('SELECT SUM(play_time) as total FROM game_stats')
        total_play_time = cursor.fetchone()[0] or 0

        with Session(db.engine) as s:
            users = s.query(User).all()

    return render_template(
        'admin.html',
        user=user,
        total_users=total_users,
        total_games_played=total_games_played,
        total_play_time=total_play_time,
        recent_users=users
    )


@app.route('/ending/<story_id>/')
@login_required
def ending_page(story_id: int):
    with Session(db.engine) as s:
        story = s.get(Story, story_id)

        if not story:
            return render_template('error.html', message='История не найдена!', code=404), 404


        return render_template(
            'ending.html',
            legend_choices=game_service.get_player_legend_choices(session['user_id'], story_id),
            story_title=story.title,
            story_id=story.id
        )


@app.route('/error')
def error_page():
    code = request.args.get('code', 404, type=int)
    message = request.args.get('message', 'Страница не найдена')

    return render_template('error.html', message=message, code=code), code


from story import StoryService

story_service = StoryService(db)



@app.route('/api/stories', methods=['GET'])
@admin_required
def api_get_stories():
    try:
        published_only = request.args.get('published', 'false').lower() == 'true'
        stories = story_service.get_all_stories(published_only)

        return jsonify({
            'success': True,
            'stories': [{'title': story.title,
                         'description': story.description,
                         'chapters_count': story.chapters_count,
                         'scenes_count': story.scenes_count,
                         'id': story.id} for story in stories]
        }), 200

    except Exception as e:
        return jsonify({'error': f'Ошибка получения историй: {str(e)}'}), 500


@app.route('/api/stories', methods=['POST'])
@admin_required
def api_create_story():
    try:
        data = request.get_json()

        if not data:
            return jsonify({'error': 'Нет данных'}), 400

        story_service.create_story(
            story_key=data['story_key'],
            title=data['title'],
            description=data.get('description'),
            cover_image=data.get('cover_image'),
            background_image=data.get('background_image'),
            premium=data.get('premium', False),
            diamonds_cost=data.get('diamonds_cost', 0),
            author_id=session['user_id']
        )

        return jsonify({
            'success': True,
            'message': 'История создана'
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

        story_service.update_story(story_id, **data)

        return jsonify({
            'success': True,
            'message': 'История обновлена'
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
    try:
        chapters = story_service.get_chapters_by_story(story_id)

        return jsonify({
            'success': True,
            'chapters': [{'id': chapter.id,
                          'title': chapter.title,
                          'chapter_number': chapter.chapter_number} for chapter in chapters]
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

        return jsonify({
            'success': True,
            'message': 'Глава создана'
        }), 201

    except Exception as e:
        return jsonify({'error': f'Ошибка создания главы: {str(e)}'}), 500


@app.route('/api/chapters/<int:chapter_id>', methods=['PUT'])
@admin_required
def api_update_chapter(chapter_id):
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


@app.route('/api/chapters/<int:chapter_id>/scenes', methods=['GET'])
@admin_required
def api_get_scenes(chapter_id):
    try:
        scenes = story_service.get_scenes_by_chapter(chapter_id)

        return jsonify({
            'success': True,
            'scenes': [{'id': scene.id,
                        'scene_number': scene.scene_number,
                        'character_name': scene.character_name,
                        'dialogue_text': scene.dialogue_text,
                        'character_image': scene.character_image,
                        'background_image': scene.background_image,
                        'chapter_id': scene.chapter_id,
                        'scene_type': scene.scene_type,
                        'scene_effect': scene.scene_effect
                        } for scene in scenes]
        }), 200

    except Exception as e:
        return jsonify({'error': f'Ошибка получения сцен: {str(e)}'}), 500


@app.route('/api/scenes', methods=['POST'])
@admin_required
def api_create_scene():
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
            scale=data.get('scale', 1.0),
            scene_type=data.get('scene_type', 'simple'),
            scene_effect=data.get('scene_effect', None)
        )

        if not scene_id:
            return jsonify({'error': 'Ошибка создания сцены'}), 500

        return jsonify({
            'success': True,
            'message': 'Сцена создана'
        }), 201

    except Exception as e:
        return jsonify({'error': f'Ошибка создания сцены: {str(e)}'}), 500


@app.route('/api/scenes/<int:scene_id>', methods=['PUT'])
@admin_required
def api_update_scene(scene_id):
    try:
        data = request.get_json()

        if not data:
            return jsonify({'error': 'Нет данных'}), 400

        story_service.update_scene(scene_id, **data)

        return jsonify({
            'success': True,
            'message': 'Сцена обновлена'
        }), 200

    except Exception as e:
        return jsonify({'error': f'Ошибка обновления сцены: {str(e)}'}), 500


@app.route('/api/scenes/<int:scene_id>', methods=['DELETE'])
@admin_required
def api_delete_scene(scene_id):
    try:
        success = story_service.delete_scene(scene_id)

        if not success:
            return jsonify({'error': 'Ошибка удаления сцены'}), 500

        return jsonify({
            'success': True,
            'message': 'Сцена удалена'
        }), 200

    except Exception as e:
        return jsonify({'success': False, 'msg': f'Ошибка удаления сцены: {str(e)}'}), 500

@app.route('/api/scenes/<int:scene_id>/choices', methods=['GET'])
@admin_required
def api_get_choices(scene_id):
    try:
        choices = story_service.get_choices_by_scene(scene_id)

        return jsonify({
            'success': True,
            'choices': [{'length': 999,
                         'choice_number': choice.choice_number,
                         'id': choice.id,
                         'friendship_change': choice.friendship_change,
                         'teasing_change': choice.teasing_change,
                         'passion_change': choice.passion_change,
                         'premium': choice.premium,
                         'choice_text': choice.choice_text,
                         'required_passion_level': choice.required_passion_level,
                         'required_friendship_level': choice.required_friendship_level,
                         'required_teasing_level': choice.required_teasing_level,
                         'is_legend_choice': choice.is_legend_choice,
                         'legend_title': choice.legend_title,
                         'legend_icon': choice.legend_icon,
                         'visible_only_for_team': choice.visible_only_for_team,
                         'move_to_url': choice.move_to_url} for choice in choices]
        }), 200

    except Exception as e:
        return jsonify({'error': f'Ошибка получения вариантов: {str(e)}'}), 500


@app.route('/api/choices', methods=['POST'])
@admin_required
def api_create_choice():
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
            premium=data.get('premium', False),
            diamonds_cost=data.get('diamonds_cost', 0),
            teasing_change=data.get('teasing_change', 0),
            friendship_change=data.get('friendship_change', 0),
            passion_change=data.get('passion_change', 0),
            required_passion_level=data.get('required_passion_level'),
            required_friendship_level=data.get('required_friendship_level'),
            required_teasing_level=data.get('required_teasing_level'),
            is_legend_choice=data.get('isLegendChoice'),
            legend_title=data.get('legendTitle'),
            legend_icon=data.get('legend_icon'),
            visible_only_for_team=data.get('visible_only_for_team')
        )

        if not choice_id:
            return jsonify({'error': 'Ошибка создания варианта'}), 500

        return jsonify({
            'success': True,
            'message': 'Вариант создан'
        }), 201

    except Exception as e:
        return jsonify({'error': f'Ошибка создания варианта: {str(e)}'}), 500


@app.route('/api/choices/<int:choice_id>', methods=['PUT'])
@admin_required
def api_update_choice(choice_id):
    try:
        data = request.get_json()

        if not data:
            return jsonify({'error': 'Нет данных'}), 400

        success = story_service.update_choice(choice_id, **data)

        if not success:
            return jsonify({'error': 'Ошибка обновления варианта'}), 500

        return jsonify({
            'success': True,
            'message': 'Вариант обновлен'
        }), 200

    except Exception as e:
        return jsonify({'error': f'Ошибка обновления варианта: {str(e)}'}), 500


@app.route('/api/choices/<int:choice_id>', methods=['DELETE'])
@admin_required
def api_delete_choice(choice_id):
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
    user = db.get_user_by_id(session['user_id'])
    return render_template('admin/stories.html', user=user)


@app.route('/admin/stories/editor/<int:story_id>')
@admin_required
def admin_story_editor_page(story_id):
    user = db.get_user_by_id(session['user_id'])
    story = story_service.get_story_by_id(story_id)

    if not story:
        return redirect(url_for('admin_stories_page'))

    return render_template('admin/story_editor.html', user=user, story=story)


@app.route('/admin/stories/create')
@admin_required
def admin_story_create_page():
    user = db.get_user_by_id(session['user_id'])
    return render_template('admin/story_create.html', user=user)


@app.route('/api/choices/<int:choice_id>', methods=['GET'])
@admin_required
def api_get_choice(choice_id):
    try:
        with Session(db.engine) as s:
            choice = s.query(Choice).filter_by(id=choice_id).first()

            return jsonify({
                'success': True,
                'choice': Choice.as_dict(choice)
            }), 200

    except Exception as e:
        return jsonify({'error': f'Ошибка получения варианта: {str(e)}'}), 500


@app.route('/api/upload/image', methods=['POST'])
@admin_required
def upload_image():
    if 'image' not in request.files:
        return jsonify({'error': 'Нет файла изображения'}), 400

    file = request.files['image']
    if file.filename == '':
        return jsonify({'error': 'Файл не выбран'}), 400

    if file and allowed_file(file.filename):
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)

        return jsonify({
            'success': True,
            'url': f'/static/images/{filename}'
        }), 200

    return jsonify({'error': 'Недопустимый формат файла'}), 400


@app.route('/admin/codes/diamond/generate/<amount>/<value>')
@admin_required
def generate_diamond_code(amount: int, value: int) -> str:
    with Session(db.engine) as s:
        diamond_code = db.generate_diamond_code(amount, value)

        return str(diamond_code.code)


@app.route('/admin/codes/teams/generate/<team_id>')
@admin_required
def generate_team_code(team_id: int) -> str:
    with Session(db.engine) as s:
        team_code = TeamCode(team_id=team_id)

        s.add(team_code)
        s.commit()

        return str(team_code.code)


@app.route('/codes/teams/<uuid>')
@login_required
def activate_team_code(uuid: str):
    with Session(db.engine) as s:
        team_code = s.get(TeamCode, uuid)

        if not team_code:
            return render_template('error.html', message='Код не найден!', code=404), 404

        s.query(User).filter_by(team_id=team_code.team_id).update({"is_leader": False})
        s.commit()

        current_user = s.get(User, session['user_id'])
        current_user.is_leader = True

        s.commit()

        return redirect('/profile')


@app.route('/codes/diamond/<uuid>')
@login_required
def activate_diamond_code(uuid: str):
    with Session(db.engine) as s:
        diamond_code = s.get(DiamondCode, uuid)

        if not diamond_code or diamond_code.amount <= 0:
            return render_template('error.html', message='Код не найден!', code=404), 404

        user = s.get(User, session['user_id'])

        user.diamonds += diamond_code.value
        diamond_code.amount -= 1

        diamond_code_history = DiamondCodesHistory(user_id=user.id,
                                                   diamond_code_uuid=diamond_code.code)
        s.add(diamond_code_history)

        s.commit()

        return redirect('/dashboard')


@app.route('/api/stories/<int:story_id>/start_again', methods=['POST'])
@login_required
def start_story_again(story_id: int):
    with Session(db.engine) as s:
        user_id = session['user_id']

        s.query(GameSave).filter_by(user_id=user_id, story_id=story_id).delete()

        stmt = (update(ChoiceHistory)
                .where(ChoiceHistory.user_id == user_id,
                       ChoiceHistory.story_id == story_id).
                values(is_active=False))

        s.execute(stmt)

        s.commit()

        return {'success': True}


@app.route('/api/admin/users/<int:user_id>/reset-progress', methods=['POST'])
@admin_required
def reset_user_progress(user_id):
    try:
        with Session(db.engine) as s:
            s.query(GameSave).filter_by(user_id=user_id).delete()

            stmt = (update(ChoiceHistory)
                    .where(ChoiceHistory.user_id == user_id).
                    values(is_active=False))

            s.execute(stmt)

            s.commit()

        return jsonify({
            'success': True,
            'message': 'Прогресс пользователя успешно сброшен'
        }), 200
    except Exception as e:
        return jsonify({'error': f'Ошибка сброса прогресса: {str(e)}'}), 500


@app.route('/api/stories/int:story_id/lock_status_toggle')
@admin_required
def change_lock_status_of_story(story_id: int):
    with Session(db.engine) as s:
        story = s.get(Story, story_id)

        if not story:
            return jsonify({
                'status': False,
                'message': 'Неправильный ID!'
            }, 404)

        story.is_unlocked = not story.is_unlocked
        s.commit()

        return jsonify({
            'status': True,
            'is_unlocked': story.is_unlocked
        }, 200)


@app.route('/codes/move/<str:uuid>')
@login_required
def code_move_to(uuid: str):
    with Session(db.engine) as s:
        user = s.get(User, session['user_id'])
        code = s.get(MoveCode, uuid)

        if not code:
            return render_template('error.html', message='Код не найден', code=404), 404

        current_save = s.query(GameSave).filter_by(user_id=user.id,
                                                   story_id=code.story_id).first()

        if not current_save:
            return render_template('error.html',
                                   message='Сначала инициализируйтесь в игре перед тем как использовать коды!',
                                   code=403), 403

        current_save.scene_id = code.scene_id

        s.commit()

        return redirect(f'/game/{code.story_id}')


@app.route('/admin/codes/move/<int:story_id>/<int:scene_id>')
@admin_required
def generate_move_code(story_id: int, scene_id: int):
    with Session(db.engine) as s:
        move_code = MoveCode(story_id=story_id,
                        scene_id=scene_id)

        s.add(move_code)
        s.commit()

        return f'/codes/move/{move_code.code}'


@app.errorhandler(404)
def not_found_error(error):
    return render_template('error.html', message='Страница не найдена', code=404), 404


@app.errorhandler(500)
def internal_error(error):
    return render_template('error.html', message='Внутренняя ошибка сервера', code=500), 500


if __name__ == '__main__':
    port = int(sys.argv[1]) if sys.argv[1] else 5000

    print("=" * 60)
    print("🎮 Любовный симулятор - Веб приложение")
    print("=" * 60)
    print(f"✓ База данных: {app.config['DATABASE_PATH']}")
    print(f"✓ Сервер запущен на: http://localhost:{port}")
    print(f"✓ Режим отладки: {app.debug}")
    print("=" * 60)

    app.run(debug=True, host='0.0.0.0', port=port)