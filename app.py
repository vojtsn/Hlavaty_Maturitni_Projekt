from flask import Flask, render_template, request, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import re
app = Flask(__name__)
app.config['SECRET_KEY'] = 'tajny_klic'

app.config['SQLALCHEMY_DATABASE_URI'] = "mysql+pymysql://student11:spsnet@dbs.spskladno.cz:3306/vyuka11"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)

# --- Domovská stránka ---
@app.route('/')
def index():
    username = session.get('username')
    return render_template('index.html', username=username)

# --- Přihlášení ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            session['username'] = user.username
            return redirect(url_for('index'))
        else:
            error = "Špatné jméno nebo heslo."
    return render_template('login.html', error=error)

# --- Registrace ---
@app.route('/register', methods=['GET', 'POST'])
def register():
    error = None
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']

        # Kontrola unikátnosti
        if User.query.filter_by(username=username).first():
            error = "Uživatelské jméno je již obsazeno."
        elif User.query.filter_by(email=email).first():
            error = "Email je již použit."
        # Kontrola hesla: alespoň 1 velké písmeno a 1 číslo
        elif not re.search(r'[A-Z]', password):
            error = "Heslo musí obsahovat alespoň 1 velké písmeno."
        elif not re.search(r'\d', password):
            error = "Heslo musí obsahovat alespoň 1 číslo."
        else:
            hashed_password = generate_password_hash(password)
            new_user = User(username=username, email=email, password=hashed_password)
            db.session.add(new_user)
            db.session.commit()
            session['username'] = username
            return redirect(url_for('index'))

    return render_template('register.html', error=error)


# --- Odhlášení ---
@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)

