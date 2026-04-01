# ============================================================
# admin_routes.py — ADMINISTRÁTORSKÉ ROZHRANÍ (správa uživatelů a kategorií)
# Blueprint "admin" — všechny trasy jsou pod prefixem /admin/
#   /admin/login, /admin/users, /admin/categories, atd.
# Tento blueprint se registruje v admin_app.py (ne v app.py!)
# Přihlašovací stránka: http://127.0.0.1:5001/admin/login
# ============================================================

from flask import Blueprint, render_template, request, redirect, url_for, session
from werkzeug.security import check_password_hash
from functools import wraps

import re
from models import db, User, Category
# ↑ db a modely jsou ze souboru models.py — sdílená databáze s hlavní app.py

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")
# ↑ url_prefix="/admin" = všechny trasy tohoto blueprintu automaticky začínají /admin
#   Registruje se v admin_app.py přes app.register_blueprint(admin_bp)


# ────────────────────────────────────────────────────────────
# DECORATOR: kontrola admin přihlášení
# ────────────────────────────────────────────────────────────
def admin_login_required(view):
    """
    Obalí view funkci — zkontroluje, zda je admin přihlášen.
    Admin má vlastní session klíč "admin_logged_in" (odděleno od hlavní session).
    ⚠️  Pozor: admin_app.py běží na jiném portu (5001) a má vlastní SECRET_KEY
    shodný s app.py — session cookie tedy platí jen pro příslušný port.
    """
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("admin_logged_in"):
            return redirect(url_for("admin.login"))
            # ↑ url_for("admin.login") = URL trasy login() v tomto blueprintu → /admin/login
        return view(*args, **kwargs)
    return wrapped


# ────────────────────────────────────────────────────────────
# ADMIN PŘIHLÁŠENÍ
# ────────────────────────────────────────────────────────────
@admin_bp.route("/login", methods=["GET", "POST"])
def login():
    """
    Přihlásí uživatele do admin rozhraní.
    Projde jen účty s rolí 'admin'.
    GET:  zobrazí formulář (templates/admin/login.html)
    POST: ověří přihlašovací údaje
    """
    error = None

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        user = User.query.filter_by(username=username).first()
        # ↑ Hledá uživatele v tabulce "users" (sdílená DB s hlavní aplikací)

        if user and user.role == "admin" and check_password_hash(user.password, password):
            # ↑ Trojitá podmínka: uživatel existuje + má roli admin + heslo sedí
            session.clear()
            session["admin_logged_in"] = True
            # ↑ Nastaví admin session klíč (odlišný od "username" v hlavní aplikaci)
            session["admin_username"] = user.username
            # ↑ Uloží jméno admina — používá se v change_role() k zabránění změny vlastní role
            return redirect(url_for("admin.users"))
            # ↑ Po přihlášení přejde na seznam uživatelů
        else:
            error = "Neplatné admin přihlášení."

    return render_template("admin/login.html", error=error)
    # ↑ Šablona je v templates/admin/login.html (podsložka admin/)


@admin_bp.route("/logout")
def logout():
    """Odhlásí admina — smaže celou session."""
    session.clear()
    return redirect(url_for("admin.login"))


# ────────────────────────────────────────────────────────────
# SPRÁVA UŽIVATELŮ
# ────────────────────────────────────────────────────────────
@admin_bp.route("/users")
@admin_login_required  # ← nejprve zkontroluje přihlášení, pak spustí funkci
def users():
    """Zobrazí seznam všech uživatelů seřazených podle ID."""
    users = User.query.order_by(User.id.asc()).all()
    # ↑ Načte všechny uživatele z tabulky "users", seřazené od nejstaršího
    return render_template("admin/users.html", users=users)
    # ↑ Předá seznam uživatelů do šablony templates/admin/users.html


# ────────────────────────────────────────────────────────────
# RESET HESLA UŽIVATELE
# ────────────────────────────────────────────────────────────
@admin_bp.route("/reset-password/<int:user_id>", methods=["POST"])
@admin_login_required
def reset_password(user_id):
    """
    Resetuje heslo uživatele na náhodné dočasné.
    user_id = ID uživatele z URL (např. /admin/reset-password/5 → user_id=5)
    Vrátí stránku s dočasným heslem, které admin předá uživateli.
    """
    target = User.query.get_or_404(user_id)
    # ↑ Hledá uživatele podle ID; 404 pokud neexistuje

    # volitelně: zákaz resetu adminů (aktuálně zakomentováno)
    # if target.role == "admin":
    #     return redirect(url_for("admin.users"))

    temp_password = target.admin_reset_password()
    # ↑ admin_reset_password() je metoda User modelu (models.py):
    #   - vygeneruje náhodné heslo
    #   - zahashuje ho a uloží
    #   - nastaví force_password_change = True
    #   - zaznamená temp_password_issued_at = teď
    #   - vrátí plaintext dočasné heslo
    db.session.commit()  # uloží změny do DB

    return render_template(
        "admin/reset_done.html",
        username=target.username,
        temp=temp_password  # předá plaintext heslo do šablony pro zobrazení adminovi
    )
    # ↑ Šablona templates/admin/reset_done.html zobrazí dočasné heslo
    # ↑ ⚠️  Bezpečnostní poznámka: heslo se zobrazuje přímo v prohlížeči —
    #   admin si ho musí opsat a předat uživateli jiným kanálem (telefon, email)


# ────────────────────────────────────────────────────────────
# SPRÁVA KATEGORIÍ — pomocná funkce
# ────────────────────────────────────────────────────────────
def slugify(text: str) -> str:
    """
    Převede název kategorie na URL-friendly slug.
    Příklady: "Zahraniční zprávy" → "zahranicni-zpravy"
              "Věda & Technika"   → "veda-technika"
    """
    import unicodedata
    text = unicodedata.normalize('NFKD', text)
    # ↑ NFKD normalizace rozdělí znaky s diakritikou: "č" → "c" + kombinační háček
    text = text.encode('ascii', 'ignore').decode('ascii')
    # ↑ encode('ascii', 'ignore') zahodí vše co není ASCII (kombinační znaky) → zbyde "c"
    text = text.lower().strip()                    # malá písmena, oříznutí mezer
    text = re.sub(r'[^\w\s-]', '', text)           # odstraní vše kromě písmen, číslic, mezer, pomlčky
    text = re.sub(r'[\s_-]+', '-', text)           # mezery a podtržítka → pomlčka
    text = re.sub(r'^-+|-+$', '', text)            # odstraní pomlčky na začátku a konci
    return text


# ────────────────────────────────────────────────────────────
# SPRÁVA KATEGORIÍ — trasy
# ────────────────────────────────────────────────────────────
@admin_bp.route("/categories")
@admin_login_required
def categories():
    """Zobrazí seznam všech kategorií."""
    cats = Category.query.order_by(Category.name.asc()).all()
    return render_template("admin/categories.html", categories=cats)


@admin_bp.route("/categories/create", methods=["POST"])
@admin_login_required
def create_category():
    """
    Vytvoří novou kategorii z formuláře.
    Automaticky vygeneruje slug z názvu pomocí slugify().
    Při duplicitním slugu tiše přesměruje (bez chybové hlášky — mohlo by být lepší).
    """
    name        = (request.form.get("name")        or "").strip()
    description = (request.form.get("description") or "").strip()

    if not name:
        return redirect(url_for("admin.categories"))

    slug = slugify(name)
    # ↑ Převede název na URL-friendly slug (definováno výše v tomto souboru)

    # Ošetření duplicit — dvě kategorie nemohou mít stejný slug
    if Category.query.filter_by(slug=slug).first():
        return redirect(url_for("admin.categories"))
        # ↑ ⚠️  Tiché přesměrování bez vysvětlení — uživatel neví proč se kategorie nevytvořila

    db.session.add(Category(name=name, slug=slug, description=description or None))
    db.session.commit()
    return redirect(url_for("admin.categories"))


@admin_bp.route("/categories/delete/<int:cat_id>", methods=["POST"])
@admin_login_required
def delete_category(cat_id):
    """Smaže kategorii. Díky ondelete='CASCADE' v models.py se smažou i vazby v article_categories."""
    cat = Category.query.get_or_404(cat_id)
    db.session.delete(cat)
    db.session.commit()
    return redirect(url_for("admin.categories"))


@admin_bp.route("/categories/edit/<int:cat_id>", methods=["POST"])
@admin_login_required
def edit_category(cat_id):
    """Upraví název a popis kategorie. Přegeneruje slug z nového názvu."""
    cat         = Category.query.get_or_404(cat_id)
    name        = (request.form.get("name")        or "").strip()
    description = (request.form.get("description") or "").strip()

    if not name:
        return redirect(url_for("admin.categories"))

    new_slug = slugify(name)

    # Kontrola duplicity slugu — ignorujeme aktuální kategorii (ta může mít stejný slug)
    existing = Category.query.filter_by(slug=new_slug).first()
    if existing and existing.id != cat_id:
        return redirect(url_for("admin.categories"))
        # ↑ ⚠️  Opět tiché přesměrování bez chybové hlášky

    cat.name        = name
    cat.slug        = new_slug
    cat.description = description or None
    db.session.commit()
    return redirect(url_for("admin.categories"))


# ────────────────────────────────────────────────────────────
# ZMĚNA ROLE UŽIVATELE
# ────────────────────────────────────────────────────────────
ALLOWED_ROLES = {'user', 'editor', 'moderator', 'admin'}
# ↑ Whitelist povolených rolí — zabraňuje nastavení neplatné role

@admin_bp.route("/change-role/<int:user_id>", methods=["POST"])
@admin_login_required
def change_role(user_id):
    """
    Změní roli uživatele.
    Admin nemůže měnit svou vlastní roli (aby se nepřipravil o admin přístup).
    """
    target = User.query.get_or_404(user_id)

    # Zákaz změny vlastní role
    if target.username == session.get("admin_username"):
        # ↑ session["admin_username"] se nastaví při admin přihlášení (viz login() výše)
        return redirect(url_for("admin.users"))

    new_role = request.form.get("role", "").strip()
    if new_role not in ALLOWED_ROLES:
        return redirect(url_for("admin.users"))
        # ↑ Pokud by někdo odeslal podvrženou hodnotu role, tato kontrola ho zastaví

    target.role = new_role
    db.session.commit()

    return redirect(url_for("admin.users"))