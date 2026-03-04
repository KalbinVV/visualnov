# -*- coding: utf-8 -*-
"""
Система сообщений — одностраничное приложение (SPA)
PostgreSQL (существующая БД) + SQLite (сообщения)
"""

import os
import uuid
import hashlib
import secrets
from datetime import datetime
from pathlib import Path

from flask import Flask, request, jsonify, session, redirect, url_for, render_template, send_from_directory
from werkzeug.utils import secure_filename

from messages_db import MessagesDatabase

BASE_DIR = Path(__file__).parent
UPLOAD_FOLDER = BASE_DIR / "uploads" / "messages"

POSTGRES_URL = os.getenv("POSTGRES_URL", "postgresql+psycopg2://postgres:y82AtQ8aM8=m@185.172.131.57:5432/postgres")

MESSAGES_DB_URL = os.getenv("MESSAGES_DB_URL", f"sqlite:///{BASE_DIR / 'messages.db'}")

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
MAX_FILE_SIZE = 5 * 1024 * 1024

app = Flask(__name__, template_folder="templates")
app.secret_key = os.getenv("SECRET_KEY", secrets.token_hex(32))
app.config["UPLOAD_FOLDER"] = str(UPLOAD_FOLDER)
app.config["MAX_CONTENT_LENGTH"] = MAX_FILE_SIZE

UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)

messages_db = MessagesDatabase(MESSAGES_DB_URL)

from sqlalchemy import create_engine, select, Table, MetaData, text
from sqlalchemy.pool import NullPool

postgres_engine = create_engine(
    POSTGRES_URL,
    echo=False,
    poolclass=NullPool,
    connect_args={"sslmode": "prefer"}
)

def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def save_uploaded_file(file) -> str:
    if file and file.filename and allowed_file(file.filename):
        UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
        filename = f"{uuid.uuid4().hex}_{secure_filename(file.filename)}"
        filepath = UPLOAD_FOLDER / filename
        file.save(filepath)
        return f"/uploads/messages/{filename}"
    return ""


def get_user_from_postgres(identifier: str, password: str = None):
    """Получение пользователя из PostgreSQL (только чтение)"""
    try:
        with postgres_engine.connect() as conn:
            # Проверяем существование таблицы users
            result = conn.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name = 'users'
                )
            """)).scalar()

            if not result:
                return None

            # Поиск по username или email
            stmt = text("""
                SELECT id, username, email, password_hash, password_salt, 
                       display_name, avatar_url, is_admin, diamonds, theme
                FROM users 
                WHERE username = :identifier OR email = :identifier
                LIMIT 1
            """)
            result = conn.execute(stmt, {"identifier": identifier}).fetchone()

            if not result:
                return None

            user = {
                "id": result.id,
                "username": result.username,
                "email": result.email,
                "password_hash": result.password_hash,
                "password_salt": result.password_salt,
                "display_name": result.display_name or result.username,
                "avatar_url": result.avatar_url,
                "is_admin": bool(result.is_admin) if result.is_admin is not None else False,
                "diamonds": result.diamonds if result.diamonds is not None else 0,
                "theme": result.theme or "orange",
            }

            if password:
                pwd_hash = hashlib.sha256(
                    (password + user["password_salt"]).encode("utf-8")
                ).hexdigest()
                if pwd_hash != user["password_hash"]:
                    return None

            return user
    except Exception as e:
        print(f"Ошибка подключения к PostgreSQL: {e}")
        return None


@app.route("/")
def index():
    user = None
    if "user_id" in session:
        user = {
            "id": session["user_id"],
            "username": session["username"],
            "display_name": session["display_name"],
            "is_admin": session.get("is_admin", False),
            "theme": session.get("theme", "orange"),
            "avatar_url": session.get("avatar_url"),
        }
    return render_template("support.html", user=user)


@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json()
    identifier = data.get("identifier", "").strip()
    password = data.get("password", "").strip()

    if not identifier or not password:
        return jsonify({"success": False, "error": "Введите логин и пароль"}), 400

    user = get_user_from_postgres(identifier, password)

    if not user:
        return jsonify({"success": False, "error": "Неверный логин или пароль"}), 401

    session["user_id"] = user["id"]
    session["username"] = user["username"]
    session["display_name"] = user["display_name"]
    session["is_admin"] = user["is_admin"]
    session["theme"] = user["theme"]
    session["avatar_url"] = user["avatar_url"]

    return jsonify({
        "success": True,
        "user": {
            "id": user["id"],
            "username": user["username"],
            "display_name": user["display_name"],
            "is_admin": user["is_admin"],
            "theme": user["theme"]
        }
    })


@app.route("/api/logout", methods=["POST"])
def api_logout():
    session.clear()
    return jsonify({"success": True})


@app.route("/api/user")
def api_user():
    if "user_id" not in session:
        return jsonify({"success": False}), 401
    return jsonify({
        "success": True,
        "user": {
            "id": session["user_id"],
            "username": session["username"],
            "display_name": session["display_name"],
            "is_admin": session.get("is_admin", False),
            "theme": session.get("theme", "orange")
        }
    })


@app.route("/api/messages")
def api_get_messages():
    if "user_id" not in session:
        return jsonify({"success": False}), 401

    user_id = session["user_id"]
    is_admin = session.get("is_admin", False)

    if is_admin:
        messages = messages_db.get_all_messages()
    else:
        messages = messages_db.get_user_messages(user_id)

    return jsonify({
        "success": True,
        "messages": [{
            "id": m.id,
            "subject": m.subject,
            "username": m.username,
            "created_at": m.created_at.isoformat(),
            "is_read": m.is_read,
            "is_responded": m.is_responded,
            "status": m.status
        } for m in messages]
    })


@app.route("/api/messages/<int:message_id>")
def api_get_message(message_id):
    if "user_id" not in session:
        return jsonify({"success": False}), 401

    message = messages_db.get_message_by_id(message_id)

    if not message:
        return jsonify({"success": False, "error": "Не найдено"}), 404

    if message.user_id != session["user_id"] and not session.get("is_admin"):
        return jsonify({"success": False, "error": "Нет доступа"}), 403

    messages_db.mark_message_read(message_id)
    responses = messages_db.get_message_responses(message_id)

    return jsonify({
        "success": True,
        "message": {
            "id": message.id,
            "subject": message.subject,
            "username": message.username,
            "content": message.content,
            "image_path": message.image_path,
            "created_at": message.created_at.isoformat(),
            "is_responded": message.is_responded
        },
        "responses": [{
            "id": r.id,
            "admin_username": r.admin_username,
            "content": r.content,
            "image_path": r.image_path,
            "created_at": r.created_at.isoformat()
        } for r in responses]
    })


@app.route("/api/messages", methods=["POST"])
def api_create_message():
    if "user_id" not in session:
        return jsonify({"success": False}), 401

    subject = request.form.get("subject", "").strip()
    content = request.form.get("content", "").strip()

    if not subject or not content:
        return jsonify({"success": False, "error": "Заполните тему и сообщение"}), 400

    image = request.files.get("image")
    image_path = save_uploaded_file(image)

    message_id = messages_db.create_message(
        user_id=session["user_id"],
        username=session["username"],
        subject=subject,
        content=content,
        image_path=image_path
    )

    return jsonify({"success": True, "message_id": message_id})


@app.route("/api/messages/<int:message_id>/respond", methods=["POST"])
def api_respond_message(message_id):
    if "user_id" not in session or not session.get("is_admin"):
        return jsonify({"success": False}), 403

    message = messages_db.get_message_by_id(message_id)

    if not message:
        return jsonify({"success": False, "error": "Не найдено"}), 404

    content = request.form.get("content", "").strip()

    if not content:
        return jsonify({"success": False, "error": "Введите текст ответа"}), 400

    image = request.files.get("image")
    image_path = save_uploaded_file(image)

    messages_db.create_response(
        message_id=message_id,
        admin_id=session["user_id"],
        admin_username=session["username"],
        content=content,
        image_path=image_path
    )

    messages_db.mark_message_responded(message_id)

    return jsonify({"success": True})


@app.route("/api/messages/pending")
def api_pending_messages():
    if "user_id" not in session or not session.get("is_admin"):
        return jsonify({"success": False}), 403

    messages = messages_db.get_pending_messages()

    return jsonify({
        "success": True,
        "messages": [{
            "id": m.id,
            "subject": m.subject,
            "username": m.username,
            "created_at": m.created_at.isoformat()
        } for m in messages]
    })


@app.route("/api/messages/count")
def api_unread_count():
    if "user_id" not in session:
        return jsonify({"success": False}), 401

    count = messages_db.get_unread_count(
        session["user_id"],
        admin=session.get("is_admin", False)
    )

    return jsonify({"success": True, "count": count})


@app.route("/uploads/messages/<filename>")
def serve_upload(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5001)