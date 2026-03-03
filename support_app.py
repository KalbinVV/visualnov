# -*- coding: utf-8 -*-

import os
import sys
import json
import uuid
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple
from functools import wraps

from flask import (
    Flask, request, jsonify, render_template,
    session, redirect, url_for, send_from_directory, flash
)
from werkzeug.utils import secure_filename

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import Database, User

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'super-secret-key-2024')
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(__file__), 'uploads', 'support')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

DATABASE_URL = os.environ.get('DATABASE_URL', 'sqlite:///romance.db')
db = Database(DATABASE_URL)


def hash_password(password: str, salt: Optional[str] = None) -> Tuple[str, str]:
    if salt is None:
        salt = secrets.token_hex(16)
    pwd_hash = hashlib.sha256((password + salt).encode('utf-8')).hexdigest()
    return pwd_hash, salt


def verify_password(password: str, pwd_hash: str, salt: str) -> bool:
    new_hash, _ = hash_password(password, salt)
    return new_hash == pwd_hash


def generate_session_token(length: int = 64) -> str:
    return secrets.token_urlsafe(length)


def allowed_file(filename: str) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Требуется авторизация', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)

    return decorated_function


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        if not session.get('is_admin', False):
            flash('Доступ только для администраторов', 'error')
            return redirect(url_for('user_support'))
        return f(*args, **kwargs)

    return decorated_function


def get_user_data(user_id: int) -> Optional[Dict[str, Any]]:
    try:
        user = db.get_user_by_id(user_id)
        if not user:
            return None

        if hasattr(user, '__tablename__'):
            return {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'display_name': user.display_name or user.username,
                'avatar_url': user.avatar_url,
                'is_admin': user.is_admin,
                'is_active': user.is_active,
                'settings': user.settings or '{}',
                'locked_until': user.locked_until,
                'failed_login_attempts': user.failed_login_attempts,
                'password_hash': user.password_hash,
                'password_salt': user.password_salt,
                'last_login': user.last_login,
                'diamonds': user.diamonds,
                'theme': user.theme
            }
        return user
    except Exception as e:
        print(f"Error getting user {user_id}: {e}")
        return None


def update_user_settings(user_id: int, settings: dict) -> bool:
    try:
        with db.get_session() as s:
            user = s.get(User, user_id)
            if not user:
                return False
            user.settings = json.dumps(settings, ensure_ascii=False)
            s.commit()
        return True
    except Exception as e:
        print(f"Error updating settings for user {user_id}: {e}")
        return False


def get_support_messages(user_id: int) -> List[Dict[str, Any]]:
    user_data = get_user_data(user_id)
    if not user_data:
        return []

    try:
        settings = json.loads(user_data.get('settings', '{}'))
        return settings.get('support_messages', [])
    except:
        return []


def save_support_messages(user_id: int, messages: List[Dict[str, Any]]) -> bool:
    user_data = get_user_data(user_id)
    if not user_data:
        return False

    try:
        settings = json.loads(user_data.get('settings', '{}'))
        settings['support_messages'] = messages
        return update_user_settings(user_id, settings)
    except Exception as e:
        print(f"Error saving messages: {e}")
        return False


def add_support_message(user_id: int, sender_id: int, message_text: str,
                        image_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    try:
        messages = get_support_messages(user_id)

        sender_data = get_user_data(sender_id)
        sender_name = sender_data['display_name'] if sender_data else 'Unknown'

        message = {
            'id': str(uuid.uuid4()),
            'sender_id': sender_id,
            'sender_name': sender_name,
            'message_text': message_text if message_text else None,
            'image_path': image_path,
            'is_read': False,
            'is_from_admin': sender_id != user_id,
            'created_at': datetime.now().isoformat()
        }

        messages.append(message)
        save_support_messages(user_id, messages)

        return message
    except Exception as e:
        print(f"Error adding message: {e}")
        return None


def mark_support_read(user_id: int, reader_is_admin: bool) -> bool:
    try:
        messages = get_support_messages(user_id)

        for msg in messages:
            if reader_is_admin:
                if not msg.get('is_from_admin', False):
                    msg['is_read'] = True
            else:
                if msg.get('is_from_admin', False):
                    msg['is_read'] = True

        return save_support_messages(user_id, messages)
    except Exception as e:
        print(f"Error marking read: {e}")
        return False


def get_user_unread(user_id: int) -> int:
    messages = get_support_messages(user_id)
    return sum(1 for msg in messages if msg.get('is_from_admin', False) and not msg.get('is_read', True))


def get_all_tickets() -> List[Dict[str, Any]]:
    try:
        with db.get_session() as s:
            users = s.query(User).filter(
                User.is_admin == False,
                User.is_active == True
            ).order_by(User.username).all()

            tickets = []
            for user in users:
                messages = get_support_messages(user.id)
                if messages:
                    unread = sum(
                        1 for msg in messages if not msg.get('is_read', True) and not msg.get('is_from_admin', False))
                    last_msg = messages[-1] if messages else None

                    tickets.append({
                        'user_id': user.id,
                        'username': user.username,
                        'display_name': user.display_name or user.username,
                        'avatar_url': user.avatar_url,
                        'message_count': len(messages),
                        'unread_count': unread,
                        'last_message_at': last_msg['created_at'] if last_msg else None,
                        'last_message_text': last_msg['message_text'] if last_msg and last_msg.get(
                            'message_text') else None,
                        'last_message_from_admin': last_msg.get('is_from_admin', False) if last_msg else False
                    })

            tickets.sort(key=lambda x: (x['unread_count'] == 0, x['last_message_at'] or ''), reverse=True)
            return tickets
    except Exception as e:
        print(f"Error getting tickets: {e}")
        return []


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        identifier = request.form.get('identifier', '').strip()
        password = request.form.get('password', '').strip()

        if not identifier or not password:
            return render_template('support.html',
                                   page='login',
                                   error='Введите логин и пароль')

        user = db.get_user_by_username(identifier)
        if not user:
            user = db.get_user_by_email(identifier)

        if not user:
            return render_template('support.html',
                                   page='login',
                                   error='Пользователь не найден')

        if hasattr(user, '__tablename__'):
            user_data = {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'display_name': user.display_name or user.username,
                'is_admin': user.is_admin,
                'is_active': user.is_active,
                'password_hash': user.password_hash,
                'password_salt': user.password_salt,
                'locked_until': user.locked_until,
                'failed_login_attempts': user.failed_login_attempts
            }
        else:
            user_data = user

        if user_data.get('locked_until'):
            try:
                lock_str = str(user_data['locked_until'])
                if 'Z' in lock_str:
                    lock_str = lock_str.replace('Z', '+00:00')
                lock_time = datetime.fromisoformat(lock_str)
                if datetime.now() < (lock_time.replace(tzinfo=None) if lock_time.tzinfo else lock_time):
                    remaining = int((lock_time.replace(
                        tzinfo=None) if lock_time.tzinfo else lock_time).timestamp() - datetime.now().timestamp()) // 60
                    return render_template('support.html',
                                           page='login',
                                           error=f'Аккаунт заблокирован на {max(1, remaining)} мин')
            except Exception as e:
                print(f"Lock check error: {e}")

        if not verify_password(password, user_data['password_hash'], user_data['password_salt']):
            new_attempts = (user_data.get('failed_login_attempts', 0) or 0) + 1
            updates = {'failed_login_attempts': new_attempts}

            if new_attempts >= 5:
                updates['locked_until'] = (datetime.now() + timedelta(minutes=15)).isoformat()
                return render_template('support.html',
                                       page='login',
                                       error='Слишком много попыток. Блокировка на 15 мин')

            db.update_user(user_data['id'], **updates)
            return render_template('support.html',
                                   page='login',
                                   error='Неверный пароль')

        session_token = generate_session_token()
        expires_at = datetime.now() + timedelta(days=30)

        try:
            db.create_session(
                user_id=user_data['id'],
                session_token=session_token,
                expires_at=expires_at,
                ip_address=request.remote_addr,
                user_agent=request.headers.get('User-Agent')
            )
        except Exception as e:
            print(f"Session creation error: {e}")

        db.update_user(
            user_data['id'],
            last_login=datetime.now().isoformat(),
            failed_login_attempts=0,
            locked_until=None
        )

        session['user_id'] = user_data['id']
        session['username'] = user_data['username']
        session['is_admin'] = user_data.get('is_admin', False)
        session['display_name'] = user_data.get('display_name', user_data['username'])
        session['session_token'] = session_token

        if user_data.get('is_admin', False):
            return redirect(url_for('admin_dashboard'))
        else:
            return redirect(url_for('user_support'))

    return render_template('support.html', page='login')


@app.route('/logout')
@login_required
def logout():
    session_token = session.get('session_token')
    if session_token:
        try:
            db.delete_session(session_token)
        except:
            pass
    session.clear()
    flash('Вы вышли из системы', 'success')
    return redirect(url_for('login'))


@app.route('/support')
@login_required
def user_support():
    if session.get('is_admin', False):
        return redirect(url_for('admin_dashboard'))

    user_id = session['user_id']
    messages = get_support_messages(user_id)
    mark_support_read(user_id, reader_is_admin=False)
    unread = get_user_unread(user_id)

    return render_template('support.html',
                           page='user',
                           messages=messages,
                           unread=unread,
                           display_name=session.get('display_name', 'Пользователь'))


@app.route('/api/user/send', methods=['POST'])
@login_required
def user_send_message():
    if session.get('is_admin', False):
        return jsonify({'success': False, 'error': 'Доступ запрещён'}), 403

    message_text = request.form.get('message', '').strip()
    has_image = 'image' in request.files

    if not message_text and not has_image:
        return jsonify({'success': False, 'error': 'Пустое сообщение'}), 400

    image_path = None
    if has_image:
        file = request.files['image']
        if file and file.filename and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            unique_filename = f"{uuid.uuid4().hex}_{filename}"

            upload_dir = app.config['UPLOAD_FOLDER']
            os.makedirs(upload_dir, exist_ok=True)

            file_path = os.path.join(upload_dir, unique_filename)
            file.save(file_path)
            image_path = f"/support_uploads/{unique_filename}"

    message = add_support_message(
        user_id=session['user_id'],
        sender_id=session['user_id'],
        message_text=message_text,
        image_path=image_path
    )

    if message:
        return jsonify({
            'success': True,
            'message': {
                'id': message['id'],
                'message_text': message['message_text'],
                'image_path': message['image_path'],
                'created_at': message['created_at'],
                'is_from_admin': False,
                'sender_name': message.get('sender_name', 'Вы')
            }
        })
    else:
        return jsonify({'success': False, 'error': 'Ошибка сохранения'}), 500


@app.route('/api/user/messages')
@login_required
def user_get_messages():
    if session.get('is_admin', False):
        return jsonify({'success': False, 'error': 'Доступ запрещён'}), 403

    messages = get_support_messages(session['user_id'])
    mark_support_read(session['user_id'], reader_is_admin=False)

    return jsonify({
        'success': True,
        'messages': [{
            'id': msg['id'],
            'message_text': msg.get('message_text'),
            'image_path': msg.get('image_path'),
            'is_read': msg.get('is_read', False),
            'created_at': msg.get('created_at'),
            'is_from_admin': msg.get('is_from_admin', False),
            'sender_name': msg.get('sender_name', 'Админ' if msg.get('is_from_admin') else 'Вы')
        } for msg in messages]
    })


@app.route('/api/user/unread')
@login_required
def user_get_unread():
    if session.get('is_admin', False):
        return jsonify({'success': False, 'error': 'Доступ запрещён'}), 403

    return jsonify({
        'success': True,
        'unread': get_user_unread(session['user_id'])
    })


@app.route('/admin')
@admin_required
def admin_dashboard():
    tickets = get_all_tickets()
    return render_template('support.html',
                           page='admin',
                           tickets=tickets,
                           display_name=session.get('display_name', 'Админ'))


@app.route('/api/admin/tickets')
@admin_required
def admin_get_tickets():
    tickets = get_all_tickets()
    return jsonify({
        'success': True,
        'tickets': tickets
    })


@app.route('/api/admin/messages/<int:user_id>')
@admin_required
def admin_get_messages(user_id: int):
    messages = get_support_messages(user_id)
    mark_support_read(user_id, reader_is_admin=True)

    return jsonify({
        'success': True,
        'messages': [{
            'id': msg['id'],
            'sender_id': msg.get('sender_id'),
            'sender_name': msg.get('sender_name'),
            'message_text': msg.get('message_text'),
            'image_path': msg.get('image_path'),
            'is_read': msg.get('is_read', False),
            'created_at': msg.get('created_at'),
            'is_from_admin': msg.get('is_from_admin', False)
        } for msg in messages]
    })


@app.route('/api/admin/send', methods=['POST'])
@admin_required
def admin_send_message():
    user_id = request.form.get('user_id', type=int)
    message_text = request.form.get('message', '').strip()

    if not user_id:
        return jsonify({'success': False, 'error': 'Не указан пользователь'}), 400

    if not message_text and 'image' not in request.files:
        return jsonify({'success': False, 'error': 'Пустое сообщение'}), 400

    target_user = db.get_user_by_id(user_id)
    if not target_user:
        return jsonify({'success': False, 'error': 'Пользователь не найден'}), 404

    image_path = None
    if 'image' in request.files:
        file = request.files['image']
        if file and file.filename and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            unique_filename = f"{uuid.uuid4().hex}_{filename}"

            upload_dir = app.config['UPLOAD_FOLDER']
            os.makedirs(upload_dir, exist_ok=True)

            file_path = os.path.join(upload_dir, unique_filename)
            file.save(file_path)
            image_path = f"/support_uploads/{unique_filename}"

    message = add_support_message(
        user_id=user_id,
        sender_id=session['user_id'],
        message_text=message_text,
        image_path=image_path
    )

    if message:
        return jsonify({
            'success': True,
            'message': {
                'id': message['id'],
                'message_text': message['message_text'],
                'image_path': message['image_path'],
                'created_at': message['created_at'],
                'is_from_admin': True,
                'sender_name': message.get('sender_name', 'Админ')
            }
        })
    else:
        return jsonify({'success': False, 'error': 'Ошибка сохранения'}), 500


@app.route('/api/admin/unread-total')
@admin_required
def admin_get_unread_total():
    tickets = get_all_tickets()
    total = sum(t.get('unread_count', 0) for t in tickets)
    return jsonify({
        'success': True,
        'total': total
    })


@app.route('/support_uploads/<filename>')
@login_required
def serve_upload(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


@app.route('/')
def index():
    if 'user_id' in session:
        if session.get('is_admin', False):
            return redirect(url_for('admin_dashboard'))
        else:
            return redirect(url_for('user_support'))
    return redirect(url_for('login'))


if __name__ == '__main__':
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    print("=" * 50)
    print("Чат поддержки - Любовный симулятор")
    print("=" * 50)
    print(f"База данных: {DATABASE_URL}")
    print(f"Загрузки: {app.config['UPLOAD_FOLDER']}")
    print("=" * 50)
    print("Запуск сервера на http://0.0.0.0:5001")
    print("=" * 50)
    
    app.run(debug=True, port=5001, host='0.0.0.0')