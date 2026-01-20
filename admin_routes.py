from flask import Blueprint, render_template, request, redirect, url_for, session
from werkzeug.security import check_password_hash
from functools import wraps

from models import db, User

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
