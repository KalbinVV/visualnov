# -*- coding: utf-8 -*-

import os
import json
import uuid
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple
from functools import wraps

from flask import (
    Flask, request, jsonify, render_template,
    session, redirect, url_for, send_from_directory
)
from werkzeug.utils import secure_filename

from database import Database


app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['UPLOAD_FOLDER'] = 'uploads/support'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

DATABASE_URL = os.environ.get('DATABASE_URL', 'postgresql+psycopg2://postgres:y82AtQ8aM8=m@185.172.131.57:5432/postgres')
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
            return redirect(url_for('login'))
        return f(*args, **kwargs)

    return decorated_function


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or not session.get('is_admin'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)

    return decorated_function


def get_support_key(user_id: int) -> str:
    return f"support_{user_id}"


def get_support_messages(user_id: int) -> List[Dict[str, Any]]:
    user_data = db.get_user_by_id(user_id)
    if not user_data:
        return []

    settings = json.loads(user_data.settings or '{}')
    support_key = get_support_key(user_id)
    return settings.get('support_messages', [])


def save_support_messages(user_id: int, messages: List[Dict[str, Any]]):
    user_data = db.get_user_by_id(user_id)
    if not user_data:
        return

    settings = json.loads(user_data.settings or '{}')
    settings['support_messages'] = messages
    db.update_user(user_id, settings=json.dumps(settings, ensure_ascii=False))


def add_support_message(user_id: int, sender_id: int, message_text: str,
                        image_path: Optional[str] = None) -> Dict[str, Any]:
    messages = get_support_messages(user_id)

    message = {
        'id': str(uuid.uuid4()),
        'sender_id': sender_id,
        'message_text': message_text,
        'image_path': image_path,
        'is_read': False,
        'is_from_admin': sender_id != user_id,
        'created_at': datetime.now().isoformat()
    }

    messages.append(message)
    save_support_messages(user_id, messages)

    return message


def mark_support_read(user_id: int, reader_is_admin: bool):
    messages = get_support_messages(user_id)

    for msg in messages:
        if reader_is_admin:
            if not msg['is_from_admin']:
                msg['is_read'] = True
        else:
            if msg['is_from_admin']:
                msg['is_read'] = True

    save_support_messages(user_id, messages)


def get_user_unread(user_id: int) -> int:
    messages = get_support_messages(user_id)
    return sum(1 for msg in messages if msg['is_from_admin'] and not msg['is_read'])


def get_all_support_tickets() -> List[Dict[str, Any]]:
    with db.get_session() as s:
        from database import User
        from sqlalchemy import select

        users = s.execute(
            select(User).where(User.is_admin == False, User.is_active == True)
        ).scalars().all()

        tickets = []
        for user in users:
            messages = get_support_messages(user.id)
            if messages:  # Только если есть сообщения
                unread = sum(1 for msg in messages if not msg['is_read'] and not msg['is_from_admin'])
                last_message = messages[-1] if messages else None

                tickets.append({
                    'user_id': user.id,
                    'username': user.username,
                    'display_name': user.display_name or user.username,
                    'avatar_url': user.avatar_url,
                    'last_login': user.last_login.isoformat() if user.last_login else None,
                    'message_count': len(messages),
                    'unread_count': unread,
                    'last_message_at': last_message['created_at'] if last_message else None,
                    'last_message_text': last_message['message_text'] if last_message else None,
                    'last_message_from_admin': last_message['is_from_admin'] if last_message else False
                })

        tickets.sort(key=lambda x: (x['unread_count'] == 0, x['last_message_at'] or ''), reverse=True)
        return tickets


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        identifier = request.form.get('identifier', '').strip()
        password = request.form.get('password', '').strip()

        if not identifier or not password:
            return render_template('support.html', error='Введите логин и пароль', page='login')

        user_data = db.get_user_by_username(identifier)
        if not user_data:
            user_data = db.get_user_by_email(identifier)

        if not user_data:
            return render_template('support.html', error='Пользователь не найден', page='login')

        if not verify_password(password, user_data.password_hash, user_data.password_salt):
            return render_template('support.html', error='Неверный пароль', page='login')

        if user_data.locked_until:
            try:
                lock_time = datetime.fromisoformat(user_data.locked_until.replace('Z', '+00:00'))
                if datetime.now() < lock_time:
                    remaining = int((lock_time - datetime.now()).total_seconds() / 60)
                    return render_template('support.html',
                                           error=f'Аккаунт заблокирован на {remaining} мин',
                                           page='login')
            except:
                pass

        session_token = generate_session_token()
        expires_at = datetime.now() + timedelta(days=30)

        db.create_session(
            user_id=user_data.id,
            session_token=session_token,
            expires_at=expires_at,
            ip_address=request.remote_addr,
            user_agent=request.headers.get('User-Agent')
        )

        db.update_user(
            user_data.id,
            last_login=datetime.now().isoformat(),
            failed_login_attempts=0,
            locked_until=None
        )

        session['user_id'] = user_data.id
        session['username'] = user_data.username
        session['is_admin'] = user_data.is_admin
        session['display_name'] = user_data.display_name or user_data.username
        session['session_token'] = session_token

        if user_data.is_admin:
            return redirect(url_for('admin_dashboard'))
        else:
            return redirect(url_for('user_support'))

    return render_template('support.html', page='login')


@app.route('/logout')
@login_required
def logout():
    session_token = session.get('session_token')
    if session_token:
        db.delete_session(session_token)
    session.clear()
    return redirect(url_for('login'))


@app.route('/support')
@login_required
def user_support():
    if session.get('is_admin'):
        return redirect(url_for('admin_dashboard'))

    user_id = session['user_id']
    messages = get_support_messages(user_id)
    mark_support_read(user_id, reader_is_admin=False)
    unread = get_user_unread(user_id)

    return render_template('support.html',
                           page='user',
                           messages=messages,
                           unread=unread)


@app.route('/api/user/send', methods=['POST'])
@login_required
def user_send_message():
    if session.get('is_admin'):
        return jsonify({'error': 'Доступ запрещён'}), 403

    message_text = request.form.get('message', '').strip()

    if not message_text and 'image' not in request.files:
        return jsonify({'error': 'Пустое сообщение'}), 400

    image_path = None
    if 'image' in request.files:
        file = request.files['image']
        if file and file.filename and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            unique_filename = f"{uuid.uuid4().hex}_{filename}"
            upload_dir = app.config['UPLOAD_FOLDER']
            os.makedirs(upload_dir, exist_ok=True)
            file.save(os.path.join(upload_dir, unique_filename))
            image_path = f"/support_uploads/{unique_filename}"

    message = add_support_message(
        user_id=session['user_id'],
        sender_id=session['user_id'],
        message_text=message_text,
        image_path=image_path
    )

    return jsonify({
        'id': message['id'],
        'message_text': message['message_text'],
        'image_path': message['image_path'],
        'created_at': message['created_at'],
        'is_from_admin': False
    })


@app.route('/api/user/messages')
@login_required
def user_get_messages():
    if session.get('is_admin'):
        return jsonify({'error': 'Доступ запрещён'}), 403

    messages = get_support_messages(session['user_id'])
    mark_support_read(session['user_id'], reader_is_admin=False)

    return jsonify([{
        'id': msg['id'],
        'message_text': msg['message_text'],
        'image_path': msg['image_path'],
        'is_read': msg['is_read'],
        'created_at': msg['created_at'],
        'is_from_admin': msg['is_from_admin']
    } for msg in messages])


@app.route('/api/user/unread')
@login_required
def user_get_unread():
    if session.get('is_admin'):
        return jsonify({'error': 'Доступ запрещён'}), 403

    return jsonify({'unread': get_user_unread(session['user_id'])})


@app.route('/admin')
@admin_required
def admin_dashboard():
    tickets = get_all_support_tickets()
    return render_template('support.html', page='admin', tickets=tickets)


@app.route('/api/admin/tickets')
@admin_required
def admin_get_tickets():
    tickets = get_all_support_tickets()
    return jsonify(tickets)


@app.route('/api/admin/messages/<int:user_id>')
@admin_required
def admin_get_messages(user_id: int):
    messages = get_support_messages(user_id)
    mark_support_read(user_id, reader_is_admin=True)

    return jsonify([{
        'id': msg['id'],
        'sender_id': msg['sender_id'],
        'message_text': msg['message_text'],
        'image_path': msg['image_path'],
        'is_read': msg['is_read'],
        'created_at': msg['created_at'],
        'is_from_admin': msg['is_from_admin']
    } for msg in messages])


@app.route('/api/admin/send', methods=['POST'])
@admin_required
def admin_send_message():
    user_id = request.form.get('user_id', type=int)
    message_text = request.form.get('message', '').strip()

    if not user_id:
        return jsonify({'error': 'Не указан пользователь'}), 400

    if not message_text and 'image' not in request.files:
        return jsonify({'error': 'Пустое сообщение'}), 400

    image_path = None
    if 'image' in request.files:
        file = request.files['image']
        if file and file.filename and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            unique_filename = f"{uuid.uuid4().hex}_{filename}"
            upload_dir = app.config['UPLOAD_FOLDER']
            os.makedirs(upload_dir, exist_ok=True)
            file.save(os.path.join(upload_dir, unique_filename))
            image_path = f"/support_uploads/{unique_filename}"

    message = add_support_message(
        user_id=user_id,
        sender_id=session['user_id'],
        message_text=message_text,
        image_path=image_path
    )

    return jsonify({
        'id': message['id'],
        'message_text': message['message_text'],
        'image_path': message['image_path'],
        'created_at': message['created_at'],
        'is_from_admin': True
    })


@app.route('/api/admin/unread-total')
@admin_required
def admin_get_unread_total():
    tickets = get_all_support_tickets()
    total = sum(t['unread_count'] for t in tickets)
    return jsonify({'total': total})


@app.route('/support_uploads/<filename>')
@login_required
def serve_upload(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


if __name__ == '__main__':
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    app.run(debug=True, port=5001, host='0.0.0.0')