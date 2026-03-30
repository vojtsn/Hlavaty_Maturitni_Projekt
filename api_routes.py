import os
import secrets
from datetime import datetime

import bleach
from flask import Blueprint, request, jsonify, current_app
from werkzeug.security import check_password_hash
from werkzeug.utils import secure_filename

from models import db, User, Article, ApiToken, Category, ArticleView

api_bp = Blueprint("api", __name__)

# ---------------------------
# Token auth
# ---------------------------
def get_user_from_token(req):
    auth = req.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    token_value = auth.split(" ", 1)[1].strip()
    if not token_value:
        return None
    t = ApiToken.query.filter_by(token=token_value).first()
    return t.user if t else None

def require_editor_role(user):
    return user and user.role in ("admin", "editor")

# ---------------------------
# HTML sanitization (safe formatting)
# ---------------------------
ALLOWED_TAGS = [
    "b", "strong",
    "i", "em",
    "u",
    "mark",
    "br", "p",
    "ul", "ol", "li",
    "span",
    "a",
    "img",
]
ALLOWED_ATTRS = {
    "a": ["href", "target", "rel", "title"],
    "img": ["src", "alt", "style", "title"],
    "span": ["style"],
}
ALLOWED_PROTOCOLS = ["http", "https"]

def sanitize_html(html: str) -> str:
    return bleach.clean(
        html or "",
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRS,
        protocols=ALLOWED_PROTOCOLS,
        strip=True
    )

# ---------------------------
# Upload settings
# ---------------------------
ALLOWED_ARTICLE_EXT = {"png", "jpg", "jpeg", "webp", "gif"}

def allowed_article_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_ARTICLE_EXT

# ---------------------------
# Routes
# ---------------------------

@api_bp.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json(force=True)
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""

    user = User.query.filter_by(username=username).first()
    if not user or not check_password_hash(user.password, password):
        return jsonify({"ok": False, "error": "Špatné jméno nebo heslo."}), 401

    token_value = secrets.token_hex(24)
    db.session.add(ApiToken(token=token_value, user_id=user.id))
    db.session.commit()

    return jsonify({"ok": True, "token": token_value, "role": user.role, "username": user.username, "user_id": user.id}), 200


@api_bp.route("/api/articles", methods=["POST"])
def api_create_article():
    user = get_user_from_token(request)
    if not user:
        return jsonify({"ok": False, "error": "Neplatný token."}), 401

    if not require_editor_role(user):
        return jsonify({"ok": False, "error": "Nemáš oprávnění přidávat články."}), 403

    data = request.get_json(force=True)
    title = (data.get("title") or "").strip()
    perex = (data.get("perex") or "").strip()
    content = (data.get("content") or "").strip()

    if not title or not content:
        return jsonify({"ok": False, "error": "title a content jsou povinné."}), 400

    # ✅ bezpečné HTML
    perex_clean = sanitize_html(perex)
    content_clean = sanitize_html(content)

    a = Article(title=title, perex=perex_clean, content=content_clean, author_id=user.id)
    db.session.add(a)
    db.session.flush()  # získáme a.id před commitem

    # přiřazení kategorií
    category_ids = data.get("category_ids") or []
    if category_ids:
        cats = Category.query.filter(Category.id.in_(category_ids)).all()
        a.categories = cats

    db.session.commit()

    return jsonify({"ok": True, "id": a.id}), 200


@api_bp.route("/api/upload", methods=["POST"])
def upload_article_image():
    user = get_user_from_token(request)
    if not user:
        return jsonify({"ok": False, "error": "Neplatný token."}), 401

    if not require_editor_role(user):
        return jsonify({"ok": False, "error": "Nemáš oprávnění nahrávat obrázky."}), 403

    file = request.files.get("file")
    if not file or not file.filename:
        return jsonify({"ok": False, "error": "Chybí soubor."}), 400

    if not allowed_article_file(file.filename):
        return jsonify({"ok": False, "error": "Nepovolený typ souboru."}), 400

    safe_name = secure_filename(file.filename)
    upload_dir = os.path.join(current_app.root_path, "static", "article_uploads")
    os.makedirs(upload_dir, exist_ok=True)

    filename = f"{int(datetime.utcnow().timestamp())}_{safe_name}"
    file_path = os.path.join(upload_dir, filename)
    file.save(file_path)

    return jsonify({"ok": True, "url": f"/static/article_uploads/{filename}"}), 200

@api_bp.route("/api/articles", methods=["GET"])
def api_list_articles():
    user = get_user_from_token(request)
    if not user:
        return jsonify({"ok": False, "error": "Neplatný token."}), 401
    if not require_editor_role(user):
        return jsonify({"ok": False, "error": "Nemáš oprávnění."}), 403

    # posledních 50 článků (můžeš změnit limit)
    articles = (Article.query
                .order_by(Article.created_at.desc())
                .limit(50)
                .all())

    out = []
    for a in articles:
        out.append({
            "id": a.id,
            "title": a.title,
            "created_at": a.created_at.isoformat() if a.created_at else None,
            "author_id": a.author_id,
            "author": a.author.username if a.author else None,
        })
    return jsonify({"ok": True, "articles": out}), 200


@api_bp.route("/api/articles/<int:article_id>", methods=["GET"])
def api_get_article(article_id):
    user = get_user_from_token(request)
    if not user:
        return jsonify({"ok": False, "error": "Neplatný token."}), 401
    if not require_editor_role(user):
        return jsonify({"ok": False, "error": "Nemáš oprávnění."}), 403

    a = Article.query.get_or_404(article_id)
    return jsonify({
        "ok": True,
        "article": {
            "id": a.id,
            "title": a.title,
            "perex": a.perex or "",
            "content": a.content or "",
            "author_id": a.author_id,
            "created_at": a.created_at.isoformat() if a.created_at else None,
            "category_ids": [c.id for c in a.categories]
        }
    }), 200


@api_bp.route("/api/articles/<int:article_id>", methods=["PUT"])
def api_update_article(article_id):
    user = get_user_from_token(request)
    if not user:
        return jsonify({"ok": False, "error": "Neplatný token."}), 401
    if not require_editor_role(user):
        return jsonify({"ok": False, "error": "Nemáš oprávnění."}), 403

    a = Article.query.get_or_404(article_id)

    # pravidla: admin/moderator může cokoliv, editor jen svoje
    if user.role not in ("admin", "moderator") and a.author_id != user.id:
        return jsonify({"ok": False, "error": "Můžeš upravovat jen své články."}), 403

    data = request.get_json(force=True)
    title = (data.get("title") or "").strip()
    perex = (data.get("perex") or "").strip()
    content = (data.get("content") or "").strip()

    if not title or not content:
        return jsonify({"ok": False, "error": "title a content jsou povinné."}), 400

    a.title = title
    a.perex = sanitize_html(perex)
    a.content = sanitize_html(content)

    # aktualizace kategorií (pokud jsou v requestu)
    if "category_ids" in data:
        cats = Category.query.filter(Category.id.in_(data["category_ids"] or [])).all()
        a.categories = cats

    db.session.commit()

    return jsonify({"ok": True, "id": a.id}), 200


@api_bp.route("/api/articles/<int:article_id>", methods=["DELETE"])
def api_delete_article(article_id):
    user = get_user_from_token(request)
    if not user:
        return jsonify({"ok": False, "error": "Neplatný token."}), 401
    if not require_editor_role(user):
        return jsonify({"ok": False, "error": "Nemáš oprávnění."}), 403

    a = Article.query.get_or_404(article_id)

    if user.role not in ("admin", "moderator") and a.author_id != user.id:
        return jsonify({"ok": False, "error": "Můžeš mazat jen své články."}), 403

    db.session.delete(a)
    db.session.commit()

    return jsonify({"ok": True}), 200


@api_bp.route("/api/categories", methods=["GET"])
def api_list_categories():
    """Vrátí seznam všech kategorií (nevyžaduje token — veřejné)."""
    cats = Category.query.order_by(Category.name.asc()).all()
    return jsonify({
        "ok": True,
        "categories": [{"id": c.id, "name": c.name, "slug": c.slug} for c in cats]
    }), 200


@api_bp.route("/api/articles/<int:article_id>/stats", methods=["GET"])
def api_article_stats(article_id):
    user = get_user_from_token(request)
    if not user:
        return jsonify({"ok": False, "error": "Neplatný token."}), 401
    if not require_editor_role(user):
        return jsonify({"ok": False, "error": "Nemáš oprávnění."}), 403

    a = Article.query.get_or_404(article_id)
    return jsonify({
        "ok": True,
        "stats": {
            "views":        a.views or 0,
            "unique_views": ArticleView.unique_count(article_id),
            "likes":        a.like_count(),
            "comments":     len(a.comments),
        }
    }), 200