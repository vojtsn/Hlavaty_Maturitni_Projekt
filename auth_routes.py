# ============================================================
# auth_routes.py — PŘIHLÁŠENÍ, REGISTRACE, ODHLÁŠENÍ, ZMĚNA HESLA
# Blueprint "auth" — všechny trasy jsou dostupné bez prefixu:
#   /login, /register, /logout, /change-password
# ============================================================

from flask import Blueprint, render_template, request, redirect, url_for, session
# ↑ session = Flask session slovník (uložen v cookie podepsaném SECRET_KEY z app.py)
from werkzeug.security import generate_password_hash
from datetime import datetime, timedelta
import re          # regulární výrazy pro ověření hesla
from functools import wraps  # pro správné zachování metadat obalených funkcí
from models import db, User  # db = SQLAlchemy instance, User = model tabulky "users"

auth_bp = Blueprint("auth", __name__)
# ↑ Registrace blueprintu pod názvem "auth"
#   Tento název se používá při odkazování: url_for("auth.login"), url_for("auth.logout"), atd.
#   Blueprint se pak registruje v app.py přes app.register_blueprint(auth_bp)


# ── DECORATOR: kontrola povinné změny hesla ───────────────────────────
def require_password_change_check(view):
    """
    Decorator — obalí view funkci a před jejím spuštěním zkontroluje,
    zda přihlášený uživatel nemá nařízenou změnu hesla (force_password_change = True).

    Pokud ano, přesměruje na stránku změny hesla místo zobrazení požadované stránky.
    Pokud dočasné heslo vypršelo (starší než 24h), uživatele odhlásí.

    Používá se jako @require_password_change_check před route funkcemi v main_routes.py.
    """
    @wraps(view)  # zachová jméno a dokumentaci původní funkce
    def wrapped(*args, **kwargs):
        username = session.get("username")
        # ↑ session["username"] se nastavuje při přihlášení (viz login() níže)
        if username:
            user = User.query.filter_by(username=username).first()
            if user and user.force_password_change:
                # zkontroluj vypršení dočasného hesla (24 hodin)
                if user.temp_password_issued_at:
                    expiry = user.temp_password_issued_at + timedelta(hours=24)
                    if datetime.utcnow() > expiry:
                        # heslo vypršelo — odhlásit a informovat
                        session.clear()  # smaže všechna data v session (odhlásí uživatele)
                        return render_template("login.html",
                            error="Platnost dočasného hesla vypršela. Kontaktuj administrátora.")
                return redirect(url_for("auth.change_password"))
                # ↑ url_for("auth.change_password") = URL trasy change_password() v tomto blueprintu
        return view(*args, **kwargs)  # pokud vše ok, spustí původní view funkci
    return wrapped


# ── PŘIHLÁŠENÍ ────────────────────────────────────────────────────────
@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """
    GET:  zobrazí přihlašovací formulář (templates/login.html)
    POST: zpracuje odeslaný formulář, ověří heslo, nastaví session
    """
    error = None
    if request.method == 'POST':
        username = request.form['username'].strip()
        # ↑ request.form['username'] = hodnota pole <input name="username"> z HTML formuláře
        password = request.form['password']

        user = User.query.filter_by(username=username).first()
        # ↑ Hledá uživatele v tabulce "users" podle jména; .first() = první výsledek nebo None

        if user and user.check_password(password):
            # ↑ user.check_password() je definována v models.py — porovná hash s plaintextem

            # zkontroluj vypršení dočasného hesla před přihlášením
            if user.force_password_change and user.temp_password_issued_at:
                expiry = user.temp_password_issued_at + timedelta(hours=24)
                if datetime.utcnow() > expiry:
                    error = "Platnost dočasného hesla vypršela. Kontaktuj administrátora."
                    return render_template('login.html', error=error)

            session['username'] = user.username
            # ↑ Uloží jméno do session — ostatní části kódu (main_routes.py, atd.)
            #   čtou session.get("username") pro zjištění, kdo je přihlášen
            session['role'] = user.role
            # ↑ Uloží roli do session — používá se pro rychlou kontrolu oprávnění
            #   bez dotazu do DB (např. session.get("role") == "admin")

            if user.force_password_change:
                return redirect(url_for('auth.change_password'))
                # ↑ Okamžité přesměrování na změnu hesla (admin resetoval heslo)

            return redirect(url_for('main.index'))
            # ↑ url_for('main.index') = URL hlavní stránky definované v main_routes.py
        else:
            error = "Špatné jméno nebo heslo."
    return render_template('login.html', error=error)
    # ↑ Předá proměnnou error do šablony templates/login.html
    #   V šabloně ji použiješ jako: {% if error %} {{ error }} {% endif %}


# ── REGISTRACE ────────────────────────────────────────────────────────
@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    """
    GET:  zobrazí registrační formulář (templates/register.html)
    POST: ověří vstup, vytvoří nového uživatele, přihlásí ho
    """
    error = None
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']

        # Kontrola duplicit v databázi
        if User.query.filter_by(username=username).first():
            error = "Uživatelské jméno je již obsazeno."
        elif User.query.filter_by(email=email).first():
            error = "Email je již použit."
        # Kontrola síly hesla pomocí regulárních výrazů
        elif not re.search(r'[A-Z]', password):
            error = "Heslo musí obsahovat alespoň 1 velké písmeno."
        elif not re.search(r'\d', password):
            error = "Heslo musí obsahovat alespoň 1 číslo."
        else:
            hashed_password = generate_password_hash(password)
            # ↑ Zahashuje heslo — do DB se NIKDY neukládá plaintext
            new_user = User(username=username, email=email,
                            password=hashed_password, role='user')
            # ↑ Vytvoří nový User objekt; role='user' = výchozí role při registraci
            db.session.add(new_user)   # přidá do session (zatím neuloženo)
            db.session.commit()        # uloží do databáze

            # Automatické přihlášení po registraci
            session['username'] = username
            session['role'] = 'user'
            return redirect(url_for('main.index'))

    return render_template('register.html', error=error)


# ── ODHLÁŠENÍ ────────────────────────────────────────────────────────
@auth_bp.route('/logout')
def logout():
    """Smaže session a přesměruje na hlavní stránku."""
    session.clear()  # odstraní username, role a vše ostatní ze session
    return redirect(url_for('main.index'))


# ── ZMĚNA HESLA ───────────────────────────────────────────────────────
@auth_bp.route("/change-password", methods=["GET", "POST"])
def change_password():
    """
    Povinná změna hesla po admin resetu (force_password_change = True).
    Také dostupná dobrovolně z profilu.
    GET:  zobrazí formulář (templates/change_password.html)
    POST: validuje a uloží nové heslo
    """
    username = session.get("username")
    if not username:
        return redirect(url_for("auth.login"))
        # ↑ Nepřihlášený uživatel nemůže měnit heslo

    user = User.query.filter_by(username=username).first()
    if not user:
        session.clear()
        return redirect(url_for("auth.login"))
        # ↑ Pokud uživatel neexistuje v DB (smazán), odhlásí a přesměruje

    error = None

    if request.method == "POST":
        p1 = request.form.get("password", "")   # nové heslo
        p2 = request.form.get("password2", "")  # potvrzení nového hesla

        # Validace nového hesla
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
            # ↑ user.set_password() je definována v models.py — zahashuje a uloží
            user.force_password_change = False
            # ↑ Zruší příznak povinné změny (uživatel se pak dostane normálně dál)
            user.temp_password_issued_at = None
            # ↑ Vymaže čas vydání dočasného hesla (už není relevantní)
            db.session.commit()
            return redirect(url_for("main.index"))

    return render_template("change_password.html", error=error,
                           force=user.force_password_change)
    # ↑ force=True → šablona může zobrazit jiné sdělení (povinná změna vs. dobrovolná)


# ── DECORATOR: kontrola admin role ────────────────────────────────────
def admin_required(view):
    """
    Decorator pro ochranu routes — povolí přístup jen uživatelům s rolí 'admin'.
    Definován tady, ale NENÍ používán v tomto souboru — importují ho jiné moduly.
    ⚠️  Poznámka: admin_app.py používá vlastní decorator admin_login_required,
    který kontroluje session["admin_logged_in"] místo session["role"].
    """
    @wraps(view)
    def wrapped(*args, **kwargs):
        if session.get("role") != "admin":
            return redirect(url_for("main.index"))
            # ↑ Neprivilegovaný uživatel je přesměrován na hlavní stránku (bez chybové hlášky)
        return view(*args, **kwargs)
    return wrapped