# ============================================================
# api_routes.py — REST API PRO EDITOR_APP.PY
# Blueprint "api" — všechny trasy začínají /api/...
# Komunikace probíhá přes JSON (ne HTML stránky).
# Autentizace: Bearer token v hlavičce Authorization
# ============================================================

import os
import secrets        # pro generování tokenů
from datetime import datetime

import bleach         # knihovna pro sanitizaci HTML (odstraňuje nebezpečné tagy)
from flask import Blueprint, request, jsonify, current_app
# ↑ jsonify = převede Python slovník na JSON odpověď
# ↑ current_app = odkaz na běžící Flask aplikaci (přístup k app.root_path apod.)
from werkzeug.security import check_password_hash
from werkzeug.utils import secure_filename  # ošetří jméno souboru (odstraní nebezpečné znaky)

from models import db, User, Article, ApiToken, Category, ArticleView
# ↑ Importuje modely z models.py — zde se používají pro čtení/zápis do DB

api_bp = Blueprint("api", __name__)
# ↑ Registrace blueprintu pod názvem "api"
#   Registruje se v app.py přes app.register_blueprint(api_bp)


# ────────────────────────────────────────────────────────────
# AUTENTIZACE POMOCÍ TOKENU
# ────────────────────────────────────────────────────────────

def get_user_from_token(req):
    """
    Přečte Bearer token z HTTP hlavičky Authorization a vrátí příslušného uživatele.
    Hlavička musí mít formát: Authorization: Bearer <token>
    Pokud token neexistuje nebo je neplatný, vrátí None.

    Token je uložen v tabulce "api_tokens" v DB (model ApiToken z models.py).
    Vytváří se při /api/login a předává se editor_app.py.
    """
    auth = req.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None   # hlavička chybí nebo má špatný formát
    token_value = auth.split(" ", 1)[1].strip()
    # ↑ Rozdělí "Bearer abc123" na ["Bearer", "abc123"] a vezme druhý prvek
    if not token_value:
        return None
    t = ApiToken.query.filter_by(token=token_value).first()
    # ↑ Hledá token v tabulce "api_tokens"; .first() = záznam nebo None
    return t.user if t else None
    # ↑ ApiToken.user je relationship definovaný v models.py → vrátí User objekt


def require_editor_role(user):
    """
    Vrátí True, pokud má uživatel roli 'admin' nebo 'editor'.
    Používá se jako kontrola oprávnění před API operacemi s články.
    """
    return user and user.role in ("admin", "editor")


# ────────────────────────────────────────────────────────────
# SANITIZACE HTML
# Bleach odstraní z HTML všechny tagy/atributy, které nejsou v whitelistu.
# Zabraňuje XSS útokům (vložení škodlivého JavaScriptu přes obsah článku).
# ────────────────────────────────────────────────────────────

ALLOWED_TAGS = [
    "b", "strong",   # tučné písmo
    "i", "em",       # kurzíva
    "u",             # podtržení
    "mark",          # zvýraznění
    "br", "p",       # zalomení řádku, odstavec
    "ul", "ol", "li", # seznamy
    "span",          # inline formátování
    "a",             # odkaz
    "img",           # obrázek
]
ALLOWED_ATTRS = {
    "a":    ["href", "target", "rel", "title"],    # povolené atributy pro odkaz
    "img":  ["src", "alt", "style", "title"],      # povolené atributy pro obrázek
    "span": ["style"],                             # jen styl pro span
}
ALLOWED_PROTOCOLS = ["http", "https"]
# ↑ Zabrání href="javascript:..." a podobným útokům přes protokol

def sanitize_html(html: str) -> str:
    """
    Vyčistí HTML od nebezpečných tagů a atributů.
    Volá se před uložením obsahu článku do databáze.
    """
    return bleach.clean(
        html or "",
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRS,
        protocols=ALLOWED_PROTOCOLS,
        strip=True   # odstraní zakázané tagy (místo jejich escapování)
    )


# ────────────────────────────────────────────────────────────
# NASTAVENÍ UPLOADU OBRÁZKŮ
# ────────────────────────────────────────────────────────────

ALLOWED_ARTICLE_EXT = {"png", "jpg", "jpeg", "webp", "gif"}
# ↑ ⚠️  Stejná konstanta je definována i v main_routes.py — duplikace kódu.
#   Lepší by bylo mít ji na jednom místě (např. v samostatném config.py).

def allowed_article_file(filename):
    """Vrátí True, pokud má soubor povolenou příponu."""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_ARTICLE_EXT
    # ↑ rsplit(".", 1)[1] = vezme část za poslední tečkou (přípona souboru)


# ────────────────────────────────────────────────────────────
# API ROUTE: Přihlášení (získání tokenu)
# ────────────────────────────────────────────────────────────

@api_bp.route("/api/login", methods=["POST"])
def api_login():
    """
    Přijme JSON s username a password, ověří přihlašovací údaje.
    Při úspěchu vygeneruje nový API token a vrátí ho v JSON odpovědi.
    Token se pak posílá v hlavičce Authorization: Bearer <token> ke všem dalším requestům.

    Vstup (JSON body):  { "username": "...", "password": "..." }
    Výstup (JSON):      { "ok": true, "token": "...", "role": "...", "username": "...", "user_id": ... }
    """
    data = request.get_json(force=True)
    # ↑ force=True = parsuje JSON i bez Content-Type: application/json hlavičky
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""

    user = User.query.filter_by(username=username).first()
    if not user or not check_password_hash(user.password, password):
        return jsonify({"ok": False, "error": "Špatné jméno nebo heslo."}), 401
        # ↑ HTTP 401 = Unauthorized

    token_value = secrets.token_hex(24)
    # ↑ Vygeneruje 48-znakový náhodný hexadecimální řetězec (24 bytů = 48 hex znaků)
    db.session.add(ApiToken(token=token_value, user_id=user.id))
    # ↑ Uloží token do tabulky "api_tokens" — propojí ho s uživatelem
    db.session.commit()

    return jsonify({"ok": True, "token": token_value, "role": user.role, "username": user.username, "user_id": user.id}), 200


# ────────────────────────────────────────────────────────────
# API ROUTE: Vytvoření článku
# ────────────────────────────────────────────────────────────

@api_bp.route("/api/articles", methods=["POST"])
def api_create_article():
    """
    Vytvoří nový článek. Vyžaduje token s rolí editor nebo admin.

    Vstup (JSON body):
      { "title": "...", "perex": "...", "content": "...", "category_ids": [1, 2] }
    Výstup:
      { "ok": true, "id": <nové id článku> }
    """
    user = get_user_from_token(request)  # ověří token z Authorization hlavičky
    if not user:
        return jsonify({"ok": False, "error": "Neplatný token."}), 401

    if not require_editor_role(user):
        return jsonify({"ok": False, "error": "Nemáš oprávnění přidávat články."}), 403
        # ↑ HTTP 403 = Forbidden (přihlášen, ale nemá práva)

    data = request.get_json(force=True)
    title   = (data.get("title")   or "").strip()
    perex   = (data.get("perex")   or "").strip()
    content = (data.get("content") or "").strip()

    if not title or not content:
        return jsonify({"ok": False, "error": "title a content jsou povinné."}), 400
        # ↑ HTTP 400 = Bad Request

    # Sanitizace HTML před uložením
    perex_clean   = sanitize_html(perex)
    content_clean = sanitize_html(content)

    a = Article(title=title, perex=perex_clean, content=content_clean, author_id=user.id)
    # ↑ author_id=user.id = cizí klíč do tabulky "users" — zaznamená autora článku
    db.session.add(a)
    db.session.flush()
    # ↑ flush() zapíše do DB, ale zatím necommituje — důvod: potřebujeme a.id
    #   pro přiřazení kategorií (M:N vztah přes article_categories)

    # Přiřazení kategorií (M:N vztah)
    category_ids = data.get("category_ids") or []
    if category_ids:
        cats = Category.query.filter(Category.id.in_(category_ids)).all()
        # ↑ Načte Category objekty pro zadaná ID; .in_() = SQL IN (...)
        a.categories = cats
        # ↑ SQLAlchemy automaticky zapíše záznamy do vazební tabulky "article_categories"

    db.session.commit()  # teprve teď se vše uloží permanentně

    return jsonify({"ok": True, "id": a.id}), 200


# ────────────────────────────────────────────────────────────
# API ROUTE: Upload obrázku pro článek
# ────────────────────────────────────────────────────────────

@api_bp.route("/api/upload", methods=["POST"])
def upload_article_image():
    """
    Nahraje obrázek na server. Vrátí URL, kterou lze vložit do obsahu článku.
    Obrázky se ukládají do: static/article_uploads/<timestamp>_<filename>
    """
    user = get_user_from_token(request)
    if not user:
        return jsonify({"ok": False, "error": "Neplatný token."}), 401

    if not require_editor_role(user):
        return jsonify({"ok": False, "error": "Nemáš oprávnění nahrávat obrázky."}), 403

    file = request.files.get("file")
    # ↑ request.files = multipart formulářové soubory; "file" = název pole v HTTP requestu
    if not file or not file.filename:
        return jsonify({"ok": False, "error": "Chybí soubor."}), 400

    if not allowed_article_file(file.filename):
        return jsonify({"ok": False, "error": "Nepovolený typ souboru."}), 400

    safe_name = secure_filename(file.filename)
    # ↑ secure_filename odstraní nebezpečné znaky (např. "../../../etc/passwd" → "etc_passwd")

    upload_dir = os.path.join(current_app.root_path, "static", "article_uploads")
    # ↑ current_app.root_path = absolutní cesta ke složce kde je app.py
    #   Výsledek: /absolutní/cesta/k/projektu/static/article_uploads
    os.makedirs(upload_dir, exist_ok=True)
    # ↑ Vytvoří složku pokud neexistuje; exist_ok=True = nespadne pokud už existuje

    filename = f"{int(datetime.utcnow().timestamp())}_{safe_name}"
    # ↑ Přidá timestamp jako prefix (např. 1711900000_foto.jpg) — zabrání přepisování souborů se stejným jménem
    file_path = os.path.join(upload_dir, filename)
    file.save(file_path)  # uloží soubor na disk

    return jsonify({"ok": True, "url": f"/static/article_uploads/{filename}"}), 200
    # ↑ Vrátí relativní URL — editor_app.py ji pak vloží do HTML obsahu článku jako <img src="...">


# ────────────────────────────────────────────────────────────
# API ROUTE: Seznam článků
# ────────────────────────────────────────────────────────────

@api_bp.route("/api/articles", methods=["GET"])
def api_list_articles():
    """Vrátí posledních 50 článků jako JSON seznam."""
    user = get_user_from_token(request)
    if not user:
        return jsonify({"ok": False, "error": "Neplatný token."}), 401
    if not require_editor_role(user):
        return jsonify({"ok": False, "error": "Nemáš oprávnění."}), 403

    articles = (Article.query
                .order_by(Article.created_at.desc())
                .limit(50)   # ← lze změnit pokud potřebuješ víc
                .all())

    out = []
    for a in articles:
        out.append({
            "id": a.id,
            "title": a.title,
            "created_at": a.created_at.isoformat() if a.created_at else None,
            # ↑ .isoformat() = formát "2024-03-30T20:27:00" (JSON-friendly)
            "author_id": a.author_id,
            "author": a.author.username if a.author else None,
            # ↑ a.author = User objekt díky relationship v Article modelu (models.py)
        })
    return jsonify({"ok": True, "articles": out}), 200


# ────────────────────────────────────────────────────────────
# API ROUTE: Detail článku
# ────────────────────────────────────────────────────────────

@api_bp.route("/api/articles/<int:article_id>", methods=["GET"])
def api_get_article(article_id):
    """
    Vrátí kompletní data jednoho článku včetně obsahu a kategorií.
    article_id je číslo z URL (např. /api/articles/42 → article_id=42).
    """
    user = get_user_from_token(request)
    if not user:
        return jsonify({"ok": False, "error": "Neplatný token."}), 401
    if not require_editor_role(user):
        return jsonify({"ok": False, "error": "Nemáš oprávnění."}), 403

    a = Article.query.get_or_404(article_id)
    # ↑ get_or_404 = hledá podle primárního klíče; pokud nenajde, vrátí HTTP 404
    return jsonify({
        "ok": True,
        "article": {
            "id": a.id,
            "title": a.title,
            "perex": a.perex or "",
            "content": a.content or "",
            "author_id": a.author_id,
            "created_at": a.created_at.isoformat() if a.created_at else None,
            "category_ids": [c.id for c in a.categories]
            # ↑ a.categories je M:N relationship z models.py → seznam Category objektů
            #   list comprehension vytvoří seznam jejich ID: [1, 3, 5]
        }
    }), 200


# ────────────────────────────────────────────────────────────
# API ROUTE: Úprava článku
# ────────────────────────────────────────────────────────────

@api_bp.route("/api/articles/<int:article_id>", methods=["PUT"])
def api_update_article(article_id):
    """
    Aktualizuje existující článek.
    Editor může měnit jen své články; admin/moderátor může cokoliv.
    """
    user = get_user_from_token(request)
    if not user:
        return jsonify({"ok": False, "error": "Neplatný token."}), 401
    if not require_editor_role(user):
        return jsonify({"ok": False, "error": "Nemáš oprávnění."}), 403

    a = Article.query.get_or_404(article_id)

    # Pravidla: admin/moderátor může editovat cokoliv, editor jen vlastní články
    if user.role not in ("admin", "moderator") and a.author_id != user.id:
        return jsonify({"ok": False, "error": "Můžeš upravovat jen své články."}), 403

    data = request.get_json(force=True)
    title   = (data.get("title")   or "").strip()
    perex   = (data.get("perex")   or "").strip()
    content = (data.get("content") or "").strip()

    if not title or not content:
        return jsonify({"ok": False, "error": "title a content jsou povinné."}), 400

    a.title   = title
    a.perex   = sanitize_html(perex)    # sanitizace před uložením
    a.content = sanitize_html(content)  # sanitizace před uložením

    # Aktualizace kategorií (pouze pokud jsou v requestu)
    if "category_ids" in data:
        cats = Category.query.filter(Category.id.in_(data["category_ids"] or [])).all()
        a.categories = cats
        # ↑ SQLAlchemy automaticky aktualizuje záznamy v "article_categories"

    db.session.commit()
    return jsonify({"ok": True, "id": a.id}), 200


# ────────────────────────────────────────────────────────────
# API ROUTE: Smazání článku
# ────────────────────────────────────────────────────────────

@api_bp.route("/api/articles/<int:article_id>", methods=["DELETE"])
def api_delete_article(article_id):
    """Smaže článek. Editor může mazat jen své, admin/moderátor cokoliv."""
    user = get_user_from_token(request)
    if not user:
        return jsonify({"ok": False, "error": "Neplatný token."}), 401
    if not require_editor_role(user):
        return jsonify({"ok": False, "error": "Nemáš oprávnění."}), 403

    a = Article.query.get_or_404(article_id)

    if user.role not in ("admin", "moderator") and a.author_id != user.id:
        return jsonify({"ok": False, "error": "Můžeš mazat jen své články."}), 403

    db.session.delete(a)   # označí k smazání
    db.session.commit()    # provede DELETE v DB

    return jsonify({"ok": True}), 200


# ────────────────────────────────────────────────────────────
# API ROUTE: Seznam kategorií (veřejné, bez tokenu)
# ────────────────────────────────────────────────────────────

@api_bp.route("/api/categories", methods=["GET"])
def api_list_categories():
    """Vrátí seznam všech kategorií. Nevyžaduje token — veřejná route."""
    cats = Category.query.order_by(Category.name.asc()).all()
    return jsonify({
        "ok": True,
        "categories": [{"id": c.id, "name": c.name, "slug": c.slug} for c in cats]
        # ↑ Vrátí jen základní info o kategorii (id, název, slug)
    }), 200


# ────────────────────────────────────────────────────────────
# API ROUTE: Statistiky článku
# ────────────────────────────────────────────────────────────

@api_bp.route("/api/articles/<int:article_id>/stats", methods=["GET"])
def api_article_stats(article_id):
    """
    Vrátí statistiky článku: celkové zobrazení, unikátní zobrazení, lajky, komentáře.
    ArticleView.unique_count() je statická metoda definovaná v models.py.
    """
    user = get_user_from_token(request)
    if not user:
        return jsonify({"ok": False, "error": "Neplatný token."}), 401
    if not require_editor_role(user):
        return jsonify({"ok": False, "error": "Nemáš oprávnění."}), 403

    a = Article.query.get_or_404(article_id)
    return jsonify({
        "ok": True,
        "stats": {
            "views":        a.views or 0,
            # ↑ a.views = celkový počet zobrazení (přičítá se v main_routes.py → clanek_detail())
            "unique_views": ArticleView.unique_count(article_id),
            # ↑ ArticleView.unique_count() = statická metoda v models.py; počítá unikátní návštěvníky
            "likes":        a.like_count(),
            # ↑ a.like_count() = metoda Article modelu v models.py; COUNT z article_likes
            "comments":     len(a.comments),
            # ↑ a.comments = backref relationship z Comment modelu v models.py
        }
    }), 200