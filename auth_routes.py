from flask import Blueprint, render_template, request, redirect, url_for, session
from werkzeug.security import generate_password_hash, check_password_hash
import re

from models import db, User

auth_bp = Blueprint("auth", __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            session['username'] = user.username
            session['role'] = user.role
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
            new_user = User(username=username, email=email, password=hashed_password, role='user')
            db.session.add(new_user)
            db.session.commit()
            session['username'] = username
            return redirect(url_for('main.index'))

    return render_template('register.html', error=error)

@auth_bp.route('/logout')
def logout():
    session.pop('username', None)
    session.clear()
    return redirect(url_for('main.index'))
