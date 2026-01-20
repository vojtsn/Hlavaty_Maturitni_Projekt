from flask import Blueprint, request, jsonify
from werkzeug.security import check_password_hash
import secrets

from models import db, User, Article, ApiToken

api_bp = Blueprint("api", __name__)

def get_user_from_token(req):
    auth = req.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    token_value = auth.split(" ", 1)[1].strip()
    t = ApiToken.query.filter_by(token=token_value).first()
    return t.user if t else None

@api_bp.route('/api/login', methods=['POST'])
def api_login():
    data = request.get_json(force=True)
    username = (data.get('username') or "").strip()
    password = data.get('password') or ""

    user = User.query.filter_by(username=username).first()
    if not user or not check_password_hash(user.password, password):
        return jsonify({"ok": False, "error": "Špatné jméno nebo heslo."}), 401

    token_value = secrets.token_hex(24)
    db.session.add(ApiToken(token=token_value, user_id=user.id))
    db.session.commit()

    return jsonify({"ok": True, "token": token_value, "role": user.role, "username": user.username})

@api_bp.route('/api/articles', methods=['POST'])
def api_create_article():
    user = get_user_from_token(request)
    if not user:
        return jsonify({"ok": False, "error": "Neplatný token."}), 401

    if user.role not in ("admin", "editor", "moderator"):
        return jsonify({"ok": False, "error": "Nemáš oprávnění přidávat články."}), 403

    data = request.get_json(force=True)
    title = (data.get("title") or "").strip()
    perex = (data.get("perex") or "").strip()
    content = (data.get("content") or "").strip()

    if not title or not content:
        return jsonify({"ok": False, "error": "title a content jsou povinné."}), 400

    a = Article(title=title, perex=perex, content=content, author_id=user.id)
    db.session.add(a)
    db.session.commit()

    return jsonify({"ok": True, "id": a.id})
