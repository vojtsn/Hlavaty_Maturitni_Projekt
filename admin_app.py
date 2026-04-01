# ============================================================
# Běží na adrese: http://127.0.0.1:5001
# Přihlašovací stránka: http://127.0.0.1:5001/admin/login
# (URL musí být zadána ručně — není odkazována z hlavní aplikace)
# ============================================================

from flask import Flask
from models import db
# ↑ db je SQLAlchemy instance z models.py — sdílí se s app.py přes stejnou databázi

from admin_routes import admin_bp
# ↑ admin_bp je Blueprint ze souboru admin_routes.py
#   Obsahuje všechny /admin/* trasy (přihlášení, uživatelé, kategorie, role)


def create_admin_app():
    """Tovární funkce — vytvoří a nakonfiguruje Flask admin aplikaci."""
    app = Flask(__name__)

    # 🔑 STEJNÝ SECRET KEY jako v app.py — NUTNÉ aby session fungovala správně
    app.config['SECRET_KEY'] = 'tajny_klic'
    # ↑ ⚠️  PROBLÉM: natvrdo v kódu — stejný problém jako v app.py
    #   Navíc: oba soubory musí mít IDENTICKÝ klíč — pokud ho změníš v jednom,
    #   musíš ho změnit i ve druhém, jinak se session cookies nebudou číst správně.

    # 🛢 STEJNÁ DB jako hlavní aplikace
    app.config['SQLALCHEMY_DATABASE_URI'] = (
        "mysql+pymysql://student11:spsnet@dbs.spskladno.cz:3306/vyuka11"
    )
    # ↑ ⚠️  KRITICKÝ PROBLÉM: přihlašovací údaje natvrdo — viz komentář v app.py
    #   Admin aplikace přistupuje do STEJNÉ databáze jako hlavní aplikace.
    #   Na jiném počítači NEBUDE fungovat bez přístupu na dbs.spskladno.cz
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    db.init_app(app)
    # ↑ Propojí SQLAlchemy instanci (z models.py) s touto admin aplikací

    app.register_blueprint(admin_bp)
    # ↑ Zaregistruje admin Blueprint — přidá všechny /admin/* trasy z admin_routes.py

    return app


# ── Spuštění admin aplikace ────────────────────────────────────────────
app = create_admin_app()

if __name__ == '__main__':
    # admin app běží separátně na jiném portu než hlavní aplikace
    app.run(host='127.0.0.1', port=5001, debug=True)
