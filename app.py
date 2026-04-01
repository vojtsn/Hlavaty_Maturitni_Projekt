# ============================================================
# app.py — HLAVNÍ VSTUPNÍ BOD WEBOVÉ APLIKACE
# Spouští se příkazem: python app.py
# Běží na adrese: http://127.0.0.1:5000
# ============================================================

from flask import Flask
from models import db, Category
# ↑ db je SQLAlchemy instance definovaná v models.py (db = SQLAlchemy())
# ↑ Category je třída/model tabulky "categories" z models.py

from main_routes import main_bp
from auth_routes import auth_bp
from api_routes import api_bp
# ↑ Importujeme tzv. "Blueprinty" — každý Blueprint je samostatná skupina URL tras
#   main_bp   → hlavní stránky (index, profil, články, komentáře...)  — soubor main_routes.py
#   auth_bp   → přihlášení, registrace, odhlášení                     — soubor auth_routes.py
#   api_bp    → REST API pro editor_app.py (komunikace přes JSON)     — soubor api_routes.py


def create_app():
    """Tovární funkce — vytvoří a nakonfiguruje Flask aplikaci."""

    app = Flask(__name__)
    # ↑ __name__ říká Flasku, kde hledat složky templates/ a static/
    #   (hledá je ve stejné složce jako tento soubor)

    # ── Bezpečnostní klíč ──────────────────────────────────────────────
    app.config['SECRET_KEY'] = 'tajny_klic'

    # ── Připojení k databázi ───────────────────────────────────────────
    app.config['SQLALCHEMY_DATABASE_URI'] = "mysql+pymysql://student11:spsnet@dbs.spskladno.cz:3306/vyuka11"

    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    # ↑ Vypíná sledování změn objektů (šetří paměť, Flask-SQLAlchemy to doporučuje)

    db.init_app(app)
    # ↑ Propojí SQLAlchemy instanci (z models.py) s touto Flask aplikací.
    #   db sama o sobě nezná žádnou aplikaci — teprve tady se "aktivuje".

    # ── Registrace Blueprintů ──────────────────────────────────────────
    app.register_blueprint(main_bp)   # trasy z main_routes.py (/, /profile, /clanek/..., atd.)
    app.register_blueprint(auth_bp)   # trasy z auth_routes.py (/login, /register, /logout, atd.)
    app.register_blueprint(api_bp)    # trasy z api_routes.py (/api/login, /api/articles, atd.)

    # ── Context processor: proměnné dostupné ve VŠECH šablonách ───────
    @app.context_processor
    def inject_categories():
        """
        Tato funkce se spustí před vykreslením KAŽDÉ šablony.
        Vrátí slovník, jehož klíče jsou pak přímo dostupné v šablonách jako proměnné.
        Díky tomu nemusíme kategorie předávat ručně v každé route.
        """
        from datetime import datetime as _dt
        try:
            cats = Category.query.order_by(Category.name.asc()).all()
            # ↑ Načte všechny kategorie z tabulky "categories", seřazené A→Z podle jména
        except Exception:
            cats = []
            # ↑ Pokud databáze nereaguje, vrátí prázdný seznam (aplikace nespadne)
        return dict(categories=cats, now=_dt.utcnow)
        # ↑ V šablonách je pak dostupné:
        #   {{ categories }} → seznam všech kategorií (pro navigaci)
        #   {{ now() }}      → aktuální čas (UTC) — lze použít v šablonách

    # ── Jinja2 filtr: zvýraznění hledaného výrazu ─────────────────────
    import re as _re
    def highlight_filter(text, query):
        """
        Vlastní filtr pro šablony. Použití v šabloně: {{ článek.title | highlight(q) }}
        Zabalí nalezený výraz do <mark>...</mark> (žluté zvýraznění v HTML).
        """
        if not text or not query:
            return text
        escaped = _re.escape(query)
        # ↑ escape() zajistí, že speciální znaky v query (např. +, *, [) se hledají doslova
        return _re.sub(f'({escaped})', r'<mark>\1</mark>', str(text), flags=_re.IGNORECASE)
        # ↑ IGNORECASE = hledání nerozlišuje velká/malá písmena

    app.jinja_env.filters['highlight'] = highlight_filter
    # ↑ Zaregistruje filtr pod názvem "highlight" — šablony ho pak mohou používat

    # ── Jinja2 filtr: Markdown → HTML ─────────────────────────────────
    import markdown as _md
    def markdown_filter(text):
        """
        Převede Markdown text na HTML. Použití v šabloně: {{ článek.content | markdown | safe }}
        Rozšíření:
          nl2br       = zalomí řádky (Enter → <br>)
          tables      = umožňuje Markdown tabulky
          fenced_code = blokový kód ohraničený ```
        """
        if not text:
            return ''
        return _md.markdown(text, extensions=['nl2br', 'tables', 'fenced_code'])

    app.jinja_env.filters['markdown'] = markdown_filter
    # ↑ Zaregistruje filtr pod názvem "markdown" — šablony ho pak mohou používat

    return app


# ── Spuštění aplikace ──────────────────────────────────────────────────
app = create_app()
# ↑ Vytvoří instanci aplikace — tuto proměnnou pouziva flask ke spusteni

if __name__ == '__main__':
    app.run(debug=True)
    # ↑ Spustí vestavěný vývojový server na http://127.0.0.1:5000
    # ↑ debug=True = automatický restart při změně kódu + podrobné chybové stránky