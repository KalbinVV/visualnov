# -*- coding: utf-8 -*-

import os
import json
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any
from functools import wraps

from flask import (
    Flask, request, jsonify, render_template,
    session, redirect, url_for, send_from_directory
)
from sqlalchemy import create_engine, String, Boolean, DateTime, func, select, update
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, Session, sessionmaker
from werkzeug.utils import secure_filename


app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
app.config['UPLOAD_FOLDER'] = 'uploads/chat'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.config['ALLOWED_EXTENSIONS'] = {'png', 'jpg', 'jpeg', 'gif', 'webp'}

DATABASE_URL = os.environ.get('DATABASE_URL', 'sqlite:///romance.db')


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    password_salt: Mapped[str] = mapped_column(String(128), nullable=False)
    display_name: Mapped[Optional[str]] = mapped_column(String(100))
    avatar_url: Mapped[Optional[str]] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    diamonds: Mapped[int] = mapped_column(default=0)
    is_leader: Mapped[bool] = mapped_column(Boolean, default=False)
    theme: Mapped[str] = mapped_column(String(50), default="orange")
    settings: Mapped[str] = mapped_column(String, default="{}")
    team_id: Mapped[Optional[int]] = mapped_column()


engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)


def get_db_session():
    return SessionLocal()


def get_messages_key(admin_id: int, user_id: int) -> str:
    return f"chat_{min(admin_id, user_id)}_{max(admin_id, user_id)}"


def get_chat_messages(admin_id: int, user_id: int) -> List[Dict[str, Any]]:
    with get_db_session() as s:
        user = s.get(User, user_id)
        if not user:
            return []

        settings = json.loads(user.settings or '{}')
        messages_key = get_messages_key(admin_id, user_id)
        return settings.get('messages', {}).get(messages_key, [])


def save_chat_messages(admin_id: int, user_id: int, messages: List[Dict[str, Any]]):
    with get_db_session() as s:
        admin = s.get(User, admin_id)
        user = s.get(User, user_id)

        messages_key = get_messages_key(admin_id, user_id)

        for u in [admin, user]:
            settings = json.loads(u.settings or '{}')
            if 'messages' not in settings:
                settings['messages'] = {}
            settings['messages'][messages_key] = messages
            u.settings = json.dumps(settings, ensure_ascii=False)

        s.commit()


def add_message(admin_id: int, user_id: int, sender_id: int,
                message_text: str, image_path: Optional[str] = None) -> Dict[str, Any]:
    messages = get_chat_messages(admin_id, user_id)

    message = {
        'id': str(uuid.uuid4()),
        'sender_id': sender_id,
        'message_text': message_text,
        'image_path': image_path,
        'is_read': False,
        'created_at': datetime.now().isoformat()
    }

    messages.append(message)
    save_chat_messages(admin_id, user_id, messages)

    return message


def mark_messages_read(admin_id: int, user_id: int, reader_id: int):
    messages = get_chat_messages(admin_id, user_id)

    for msg in messages:
        if msg['sender_id'] != reader_id:
            msg['is_read'] = True

    save_chat_messages(admin_id, user_id, messages)


def get_unread_count(admin_id: int, user_id: int) -> int:
    messages = get_chat_messages(admin_id, user_id)
    return sum(1 for msg in messages if msg['sender_id'] == user_id and not msg['is_read'])


def get_total_unread(admin_id: int) -> int:
    with get_db_session() as s:
        users = s.execute(
            select(User).where(User.is_admin == False, User.is_active == True)
        ).scalars().all()

        total = 0
        for user in users:
            total += get_unread_count(admin_id, user.id)
        return total


def allowed_file(filename: str) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or not session.get('is_admin'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)

    return decorated_function


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')

        with get_db_session() as s:
            user = s.scalar(select(User).where(User.username == username))

            if user and user.is_admin:
                if password == 'admin' or password == username:
                    session['user_id'] = user.id
                    session['username'] = user.username
                    session['is_admin'] = True
                    session['display_name'] = user.display_name or user.username

                    user.last_login = datetime.now()
                    s.commit()

                    return redirect(url_for('chat_index'))

        return render_template('chat.html', error='Неверный логин или пароль', page='login')

    return render_template('chat.html', page='login')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route('/')
@login_required
def chat_index():
    unread_total = get_total_unread(session['user_id'])

    return render_template('support_chat.html', page='chat', unread_total=unread_total)


@app.route('/api/users')
@login_required
def get_users():
    with get_db_session() as s:
        users = s.execute(
            select(User)
            .where(User.is_admin == False, User.is_active == True)
            .order_by(User.username)
        ).scalars().all()

        result = []
        for user in users:
            unread = get_unread_count(session['user_id'], user.id)
            result.append({
                'id': user.id,
                'username': user.username,
                'display_name': user.display_name or user.username,
                'avatar_url': user.avatar_url,
                'last_login': user.last_login.isoformat() if user.last_login else None,
                'unread_count': unread
            })

        return jsonify(result)


@app.route('/api/messages/<int:user_id>')
@login_required
def get_messages(user_id: int):
    messages = get_chat_messages(session['user_id'], user_id)
    mark_messages_read(session['user_id'], user_id, session['user_id'])

    result = []
    for msg in messages:
        result.append({
            'id': msg['id'],
            'sender_id': msg['sender_id'],
            'message_text': msg['message_text'],
            'image_path': msg['image_path'],
            'is_read': msg['is_read'],
            'created_at': msg['created_at'],
            'is_mine': msg['sender_id'] == session['user_id']
        })

    return jsonify(result)


@app.route('/api/send', methods=['POST'])
@login_required
def send_message():
    receiver_id = request.form.get('receiver_id', type=int)
    message_text = request.form.get('message', '').strip()

    if not receiver_id:
        return jsonify({'error': 'Не указан получатель'}), 400

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

            file_path = os.path.join(upload_dir, unique_filename)
            file.save(file_path)
            image_path = f"/chat_uploads/{unique_filename}"

    message = add_message(
        session['user_id'], receiver_id,
        session['user_id'], message_text, image_path
    )

    return jsonify({
        'id': message['id'],
        'sender_id': message['sender_id'],
        'message_text': message['message_text'],
        'image_path': message['image_path'],
        'created_at': message['created_at'],
        'is_mine': True
    })


@app.route('/chat_uploads/<filename>')
@login_required
def serve_upload(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


@app.route('/api/unread')
@login_required
def get_unread():
    total = get_total_unread(session['user_id'])
    return jsonify({'total': total})



if __name__ == '__main__':
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    app.run(debug=True, port=5001)