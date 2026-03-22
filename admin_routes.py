from flask import Blueprint, render_template, request, redirect, url_for, session
from werkzeug.security import check_password_hash
from functools import wraps

import re
from models import db, User, Category

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


# ───────────────
# AUTH DECORATOR
# ───────────────
def admin_login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("admin_logged_in"):
            return redirect(url_for("admin.login"))
        return view(*args, **kwargs)
    return wrapped


# ───────────────
# ADMIN LOGIN
# ───────────────
@admin_bp.route("/login", methods=["GET", "POST"])
def login():
    error = None

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        user = User.query.filter_by(username=username).first()

        if user and user.role == "admin" and check_password_hash(user.password, password):
            session.clear()
            session["admin_logged_in"] = True
            session["admin_username"] = user.username
            return redirect(url_for("admin.users"))
        else:
            error = "Neplatné admin přihlášení."

    return render_template("admin/login.html", error=error)


@admin_bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("admin.login"))


# ───────────────
# USERS LIST
# ───────────────
@admin_bp.route("/users")
@admin_login_required
def users():
    users = User.query.order_by(User.id.asc()).all()
    return render_template("admin/users.html", users=users)


# ───────────────
# RESET PASSWORD
# ───────────────
@admin_bp.route("/reset-password/<int:user_id>", methods=["POST"])
@admin_login_required
def reset_password(user_id):
    target = User.query.get_or_404(user_id)

    # volitelně: zákaz resetu adminů
    # if target.role == "admin":
    #     return redirect(url_for("admin.users"))

    temp_password = target.admin_reset_password()
    db.session.commit()

    return render_template(
        "admin/reset_done.html",
        username=target.username,
        temp=temp_password
    )


# ───────────────
# CATEGORIES
# ───────────────
def slugify(text: str) -> str:
    """Převede název kategorie na URL-friendly slug."""
    import unicodedata
    # odstraní diakritiku (á→a, č→c, ž→z atd.)
    text = unicodedata.normalize('NFKD', text)
    text = text.encode('ascii', 'ignore').decode('ascii')
    text = text.lower().strip()
    text = re.sub(r'[^\w\s-]', '', text)
    text = re.sub(r'[\s_-]+', '-', text)
    text = re.sub(r'^-+|-+$', '', text)
    return text


@admin_bp.route("/categories")
@admin_login_required
def categories():
    cats = Category.query.order_by(Category.name.asc()).all()
    return render_template("admin/categories.html", categories=cats)


@admin_bp.route("/categories/create", methods=["POST"])
@admin_login_required
def create_category():
    name = (request.form.get("name") or "").strip()
    description = (request.form.get("description") or "").strip()

    if not name:
        return redirect(url_for("admin.categories"))

    slug = slugify(name)

    # Ošetření duplicit
    if Category.query.filter_by(slug=slug).first():
        return redirect(url_for("admin.categories"))

    db.session.add(Category(name=name, slug=slug, description=description or None))
    db.session.commit()
    return redirect(url_for("admin.categories"))


@admin_bp.route("/categories/delete/<int:cat_id>", methods=["POST"])
@admin_login_required
def delete_category(cat_id):
    cat = Category.query.get_or_404(cat_id)
    db.session.delete(cat)
    db.session.commit()
    return redirect(url_for("admin.categories"))


# ───────────────
# CHANGE ROLE
# ───────────────
ALLOWED_ROLES = {'user', 'editor', 'moderator', 'admin'}

@admin_bp.route("/change-role/<int:user_id>", methods=["POST"])
@admin_login_required
def change_role(user_id):
    target = User.query.get_or_404(user_id)

    # nelze měnit vlastní roli
    if target.username == session.get("admin_username"):
        return redirect(url_for("admin.users"))

    new_role = request.form.get("role", "").strip()
    if new_role not in ALLOWED_ROLES:
        return redirect(url_for("admin.users"))

    target.role = new_role
    db.session.commit()

    return redirect(url_for("admin.users"))