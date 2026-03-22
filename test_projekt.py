"""
Testy pro maturitní projekt InfoBox.
Spuštění: python -m pytest test_projekt.py -v
"""

import pytest
import sys
import os
import re as _re
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(__file__))

from admin_routes import slugify
from api_routes import sanitize_html


def highlight(text, query):
    """Stejná logika jako highlight_filter v app.py."""
    if not text or not query:
        return text
    escaped = _re.escape(query)
    return _re.sub(f'({escaped})', r'<mark>\1</mark>', str(text), flags=_re.IGNORECASE)


# ══════════════════════════════════════════════════════════════════════
# FIXTURES
# ══════════════════════════════════════════════════════════════════════

@pytest.fixture
def app():
    """Izolovaná testovací Flask app s SQLite v paměti — nedotýká se produkční DB."""
    from flask import Flask
    from models import db as _db
    from main_routes import main_bp
    from auth_routes import auth_bp

    test_app = Flask(__name__)
    test_app.config.update({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "SECRET_KEY": "test-key",
        "SQLALCHEMY_TRACK_MODIFICATIONS": False,
    })
    _db.init_app(test_app)
    test_app.register_blueprint(main_bp)
    test_app.register_blueprint(auth_bp)

    with test_app.app_context():
        _db.create_all()
        yield test_app
        _db.session.remove()
        _db.drop_all()


@pytest.fixture
def client(app):
    """HTTP testovací klient."""
    return app.test_client()


@pytest.fixture
def user(app):
    """Vytvoří testovacího uživatele v izolované DB."""
    from models import db, User
    with app.app_context():
        u = User(username="vojta", email="vojta@test.com", password="x", role="user")
        u.set_password("HesloTest1")
        db.session.add(u)
        db.session.commit()
    return {"username": "vojta", "password": "HesloTest1"}


# ══════════════════════════════════════════════════════════════════════
# TESTY — pomocné funkce (nevyžadují DB ani Flask)
# ══════════════════════════════════════════════════════════════════════

def test_slugify_základní():
    """Převod textu s diakritikou na slug."""
    assert slugify("Sport a zdraví") == "sport-a-zdravi"

def test_slugify_speciální_znaky():
    """Speciální znaky se odstraní."""
    assert slugify("Věda & technika!") == "veda-technika"

def test_slugify_prázdný_string():
    """Prázdný string vrátí prázdný string."""
    assert slugify("") == ""

def test_sanitize_odstraní_script():
    """Script tag je odstraněn — ochrana před XSS."""
    result = sanitize_html("<script>alert('xss')</script>text")
    assert "<script>" not in result
    assert "</script>" not in result
    assert "text" in result

def test_sanitize_povolí_tučné():
    """Bezpečné tagy jako <b> jsou povoleny."""
    assert "<b>text</b>" in sanitize_html("<b>text</b>")

def test_sanitize_none():
    """None vstup vrátí prázdný string."""
    assert sanitize_html(None) == ""

def test_highlight_základní():
    """Nalezený výraz je obalen <mark> tagem."""
    assert "<mark>sport</mark>" in highlight("Mám rád sport", "sport")

def test_highlight_case_insensitive():
    """Vyhledávání nerozlišuje velká a malá písmena."""
    assert "<mark>" in highlight("Sport je zdraví", "sport")

def test_highlight_prázdný_dotaz():
    """Prázdný dotaz vrátí původní text beze změny."""
    assert highlight("text", "") == "text"


# ══════════════════════════════════════════════════════════════════════
# TESTY — modely
# ══════════════════════════════════════════════════════════════════════

def test_heslo_hashování(app):
    """Heslo se neukládá jako plaintext a správně se ověřuje."""
    from models import User
    with app.app_context():
        u = User(username="u1", email="u1@test.com", password="x", role="user")
        u.set_password("HesloTest1")
        assert u.password != "HesloTest1"
        assert u.check_password("HesloTest1") is True

def test_špatné_heslo(app):
    """Nesprávné heslo vrátí False."""
    from models import User
    with app.app_context():
        u = User(username="u2", email="u2@test.com", password="x", role="user")
        u.set_password("HesloTest1")
        assert u.check_password("SpatneHeslo1") is False

def test_admin_reset(app):
    """Reset hesla nastaví force_password_change a vygeneruje dočasné heslo."""
    from models import db, User
    with app.app_context():
        u = User(username="u3", email="u3@test.com", password="x", role="user")
        u.set_password("HesloTest1")
        db.session.add(u)
        db.session.commit()
        temp = u.admin_reset_password()
        assert u.force_password_change is True
        assert u.check_password(temp) is True


# ══════════════════════════════════════════════════════════════════════
# TESTY — Flask routes
# ══════════════════════════════════════════════════════════════════════

def test_přihlášení_správné(client, user):
    """Správné přihlášení přesměruje uživatele."""
    r = client.post("/login", data=user, follow_redirects=False)
    assert r.status_code == 302

def test_přihlášení_špatné_heslo(client, user):
    """Špatné heslo zobrazí chybovou hlášku."""
    r = client.post("/login", data={"username": "vojta", "password": "SpatneHeslo9"})
    assert "Špatné jméno nebo heslo" in r.data.decode("utf-8")

def test_registrace_slabé_heslo(client):
    """Heslo bez čísla je odmítnuto."""
    r = client.post("/register", data={
        "username": "novy", "email": "novy@test.com", "password": "BezCisla"
    })
    assert "číslo" in r.data.decode("utf-8")

def test_profil_bez_přihlášení(client):
    """Nepřihlášený uživatel je přesměrován z profilu na login."""
    r = client.get("/profile")
    assert r.status_code == 302

def test_neexistující_článek_404(client):
    """Neexistující článek vrátí 404."""
    r = client.get("/clanek/99999")
    assert r.status_code == 404

def test_vypršelé_dočasné_heslo(client, app):
    """Dočasné heslo starší než 24h je odmítnuto."""
    from models import db, User
    with app.app_context():
        u = User(username="expired", email="exp@test.com", password="x", role="user")
        u.set_password("HesloTest1")
        db.session.add(u)
        db.session.commit()
        temp = u.admin_reset_password()
        u.temp_password_issued_at = datetime.utcnow() - timedelta(hours=25)
        db.session.commit()
    r = client.post("/login", data={"username": "expired", "password": temp})
    assert "vypršela" in r.data.decode("utf-8")