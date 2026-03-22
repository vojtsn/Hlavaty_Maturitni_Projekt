from flask import Blueprint, render_template, request, redirect, url_for, session
from werkzeug.security import generate_password_hash
from datetime import datetime, timedelta
import re
from functools import wraps
from models import db, User

auth_bp = Blueprint("auth", __name__)

# ── Decorator: přesměruje na změnu hesla pokud je vyžadována ──────────
def require_password_change_check(view):
    """Přesměruje přihlášeného uživatele na změnu hesla pokud je vyžadována."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        username = session.get("username")
        if username:
            user = User.query.filter_by(username=username).first()
            if user and user.force_password_change:
                # zkontroluj vypršení dočasného hesla (24 hodin)
                if user.temp_password_issued_at:
                    expiry = user.temp_password_issued_at + timedelta(hours=24)
                    if datetime.utcnow() > expiry:
                        # heslo vypršelo — odhlásit a informovat
                        session.clear()
                        return render_template("login.html",
                            error="Platnost dočasného hesla vypršela. Kontaktuj administrátora.")
                return redirect(url_for("auth.change_password"))
        return view(*args, **kwargs)
    return wrapped


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password']

        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):

            # zkontroluj vypršení dočasného hesla před přihlášením
            if user.force_password_change and user.temp_password_issued_at:
                expiry = user.temp_password_issued_at + timedelta(hours=24)
                if datetime.utcnow() > expiry:
                    error = "Platnost dočasného hesla vypršela. Kontaktuj administrátora."
                    return render_template('login.html', error=error)

            session['username'] = user.username
            session['role'] = user.role

            if user.force_password_change:
                return redirect(url_for('auth.change_password'))

            return redirect(url_for('main.index'))
        else:
            error = "Špatné jméno nebo heslo."
    return render_template('login.html', error=error)


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    error = None
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']

        if User.query.filter_by(username=username).first():
            error = "Uživatelské jméno je již obsazeno."
        elif User.query.filter_by(email=email).first():
            error = "Email je již použit."
        elif not re.search(r'[A-Z]', password):
            error = "Heslo musí obsahovat alespoň 1 velké písmeno."
        elif not re.search(r'\d', password):
            error = "Heslo musí obsahovat alespoň 1 číslo."
        else:
            hashed_password = generate_password_hash(password)
            new_user = User(username=username, email=email,
                            password=hashed_password, role='user')
            db.session.add(new_user)
            db.session.commit()
            session['username'] = username
            session['role'] = 'user'
            return redirect(url_for('main.index'))

    return render_template('register.html', error=error)


@auth_bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('main.index'))


@auth_bp.route("/change-password", methods=["GET", "POST"])
def change_password():
    username = session.get("username")
    if not username:
        return redirect(url_for("auth.login"))

    user = User.query.filter_by(username=username).first()
    if not user:
        session.clear()
        return redirect(url_for("auth.login"))

    error = None

    if request.method == "POST":
        p1 = request.form.get("password", "")
        p2 = request.form.get("password2", "")

        if len(p1) < 8:
            error = "Heslo musí mít alespoň 8 znaků."
        elif p1 != p2:
            error = "Hesla se neshodují."
        elif not re.search(r'[A-Z]', p1):
            error = "Heslo musí obsahovat alespoň 1 velké písmeno."
        elif not re.search(r'\d', p1):
            error = "Heslo musí obsahovat alespoň 1 číslo."
        else:
            user.set_password(p1)
            user.force_password_change = False
            user.temp_password_issued_at = None
            db.session.commit()
            return redirect(url_for("main.index"))

    return render_template("change_password.html", error=error,
                           force=user.force_password_change)


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if session.get("role") != "admin":
            return redirect(url_for("main.index"))
        return view(*args, **kwargs)
    return wrapped