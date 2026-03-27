

import pytest
import sys
import os
import re as _re

sys.path.insert(0, os.path.dirname(__file__))

from admin_routes import slugify
from api_routes import sanitize_html


def highlight(text, query):
    """Stejná logika jako highlight_filter v app.py."""
    if not text or not query:
        return text
    escaped = _re.escape(query)
    return _re.sub(f'({escaped})', r'<mark>\1</mark>', str(text), flags=_re.IGNORECASE)


# fixtures

@pytest.fixture
def app():
    """TOHLE NEZASAHUJE DO PRODUKCNI DB"""
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
    """HHTP testovaci klient"""
    return app.test_client()


@pytest.fixture
def user(app):
    """VYTVORI TEST. UZIVATELE V TEST. DATABAZI"""
    from models import db, User
    with app.app_context():
        u = User(username="vojta", email="vojta@test.com", password="x", role="user")
        u.set_password("HesloTest1")
        db.session.add(u)
        db.session.commit()
    return {"username": "vojta", "password": "HesloTest1"}

# testy

def test_slugify_základní():
    """prevod textu s diakritikou na slug"""
    assert slugify("Sport a zdraví") == "sport-a-zdravi"

def test_sanitize_odstraní_script():
    """kontrola ze kod neobsahuje script tag"""
    result = sanitize_html("<script>alert('xss')</script>text")
    assert "<script>" not in result
    assert "text" in result

def test_highlight_case_insensitive():
    """vyhledavani nerozlisuje velka mala pismena"""
    assert "<mark>" in highlight("Sport je zdraví", "sport")

def test_heslo_hashování(app):
    """heslo se neklada jako plain text"""
    from models import User
    with app.app_context():
        u = User(username="u1", email="u1@test.com", password="x", role="user")
        u.set_password("HesloTest1")
        assert u.password != "HesloTest1"
        assert u.check_password("HesloTest1") is True

def test_přihlášení_správné(client, user):
    """pri spravnem prihlaseni je uizvatel presmerovan"""
    r = client.post("/login", data=user, follow_redirects=False)
    assert r.status_code == 302