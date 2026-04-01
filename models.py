# ============================================================
# models.py — DEFINICE DATABÁZOVÝCH TABULEK (ORM modely)
# Tento soubor popisuje strukturu databáze pomocí Python tříd.
# SQLAlchemy pak automaticky mapuje třídy na SQL tabulky.
# ============================================================

from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import secrets   # pro generování bezpečných náhodných řetězců
import string    # pro seznam písmen a číslic
from werkzeug.security import generate_password_hash, check_password_hash
# ↑ werkzeug je součástí Flasku — tyto funkce hashují hesla (bcrypt/scrypt)
from sqlalchemy import func
# ↑ func umožňuje použít SQL agregační funkce jako COUNT(), SUM() atd.

db = SQLAlchemy()
# ↑ Vytvoří SQLAlchemy instanci BEZ napojení na konkrétní aplikaci.
#   Napojení proběhne v app.py přes db.init_app(app).
#   Všechny modely níže z ní dědí (db.Model) a sdílejí toto připojení.


# ────────────────────────────────────────────────────────────
# MODEL: User — tabulka "users"
# ────────────────────────────────────────────────────────────
class User(db.Model):
    __tablename__ = 'users'   # ← přesný název tabulky v MySQL
    id = db.Column(db.Integer, primary_key=True)  # automaticky rostoucí ID

    username = db.Column(db.String(50), unique=True, nullable=False)
    # ↑ unikátní, max 50 znaků, nesmí být prázdné
    email = db.Column(db.String(100), unique=True, nullable=False)

    # v DB je password = hash (nikdy plaintext)
    password = db.Column(db.String(200), nullable=False)
    # ↑ hash hesla, generovaný přes generate_password_hash() níže

    role = db.Column(db.String(20), nullable=False, default='user')
    # ↑ Možné hodnoty: 'user', 'editor', 'moderator', 'admin'
    #   Výchozí hodnota při registraci je 'user'.

    # PROFIL — nepovinné profilové údaje
    display_name = db.Column(db.String(100))
    bio = db.Column(db.Text)
    birth_date = db.Column(db.Date)
    gender = db.Column(db.String(10))  # v DB je enum; ve Flasku může být String
    avatar = db.Column(db.String(255))
    # ↑ avatar = jméno souboru uloženého ve složce static/profilovky/
    #   Celá cesta k souboru se skládá v šablonách: /static/profilovky/{{ user.avatar }}

    # admin reset workflow (musí existovat i v DB — viz ALTER TABLE výše)
    force_password_change = db.Column(db.Boolean, default=False, nullable=False)
    # ↑ True = uživatel musí po přihlášení hned změnit heslo (po resetu adminem)
    temp_password_issued_at = db.Column(db.DateTime, nullable=True)
    # ↑ Čas vydání dočasného hesla — používá se ke kontrole vypršení (24 hodin) v auth_routes.py

    def set_password(self, plain: str):
        """Zahashuje plaintext heslo a uloží do self.password."""
        self.password = generate_password_hash(plain)

    def check_password(self, plain: str) -> bool:
        """Ověří, zda zadané plaintext heslo odpovídá uloženému hashi."""
        return check_password_hash(self.password, plain)

    def is_admin_user(self) -> bool:
        """Vrátí True, pokud má uživatel roli 'admin'."""
        return self.role == "admin"

    @staticmethod
    def generate_temporary_password(length: int = 12) -> str:
        """Vygeneruje náhodné dočasné heslo (písmena + číslice, délka 12)."""
        alphabet = string.ascii_letters + string.digits
        return "".join(secrets.choice(alphabet) for _ in range(length))
        # ↑ secrets.choice je bezpečnější než random.choice (kryptograficky bezpečný RNG)

    def admin_reset_password(self) -> str:
        """
        Resetuje heslo uživatele na dočasné.
        Nastaví force_password_change = True a zaznamená čas vydání.
        Vrátí dočasné heslo v plaintextu (admin ho musí předat uživateli).
        Volá se z admin_routes.py → reset_password().
        """
        temp = self.generate_temporary_password()
        self.set_password(temp)                        # zahashuje a uloží
        self.force_password_change = True              # přinutí ke změně po přihlášení
        self.temp_password_issued_at = datetime.utcnow()  # zaznamená čas pro kontrolu expirace
        return temp                                    # vrátí plaintext pro zobrazení adminovi

    theme = db.Column(db.String(10), nullable=False, default='light')
    # ↑ Preferované téma uživatele ('light' nebo 'dark'), výchozí je 'light'

    def followers_count(self) -> int:
        """Počet uživatelů, kteří sledují tohoto uživatele."""
        return UserFollow.query.filter_by(followed_id=self.id).count()
        # ↑ Hledá záznamy v tabulce "user_follows", kde followed_id = toto uživatelovo id

    def following_count(self) -> int:
        """Počet uživatelů, které tento uživatel sleduje."""
        return UserFollow.query.filter_by(follower_id=self.id).count()

    def is_following(self, other_user) -> bool:
        """Vrátí True, pokud tento uživatel sleduje other_user."""
        if not other_user:
            return False
        return UserFollow.query.filter_by(
            follower_id=self.id,
            followed_id=other_user.id
        ).first() is not None
        # ↑ .first() vrátí první nalezený záznam nebo None; is not None = True/False


# ────────────────────────────────────────────────────────────
# MODEL: Article — tabulka "articles"
# ────────────────────────────────────────────────────────────
class Article(db.Model):
    __tablename__ = 'articles'
    id = db.Column(db.Integer, primary_key=True)

    title = db.Column(db.String(200), nullable=False)
    perex = db.Column(db.String(500), nullable=True)    # krátký úvodní text, nepovinný
    content = db.Column(db.Text, nullable=False)         # hlavní obsah článku (HTML/Markdown)
    views = db.Column(db.Integer, default=0, nullable=False)
    # ↑ Celkový počet zobrazení (přičítá se při každém načtení stránky článku)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    # ↑ Automaticky se nastaví na aktuální UTC čas při vytvoření záznamu

    author_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    # ↑ Cizí klíč — odkazuje na sloupec 'id' v tabulce 'users'
    author = db.relationship('User', backref='articles')
    # ↑ relationship = ORM zkratka: article.author → vrátí User objekt autora
    #   backref='articles' = opačný směr: user.articles → vrátí seznam článků daného uživatele

    def like_count(self) -> int:
        """Vrátí celkový počet lajků tohoto článku."""
        return db.session.query(func.count(ArticleLike.id))\
            .filter(ArticleLike.article_id == self.id)\
            .scalar() or 0
        # ↑ SQL ekvivalent: SELECT COUNT(id) FROM article_likes WHERE article_id = self.id
        # ↑ .scalar() vrátí jedno číslo, or 0 ošetří případ kdy je výsledek None

    def is_liked_by(self, user) -> bool:
        """Vrátí True, pokud daný uživatel lajkoval tento článek."""
        if not user:
            return False
        from models import ArticleLike  # lokální import aby se předešlo cyklickým závislostem
        return ArticleLike.query.filter_by(
            article_id=self.id,
            user_id=user.id
        ).first() is not None


# ────────────────────────────────────────────────────────────
# MODEL: ApiToken — tabulka "api_tokens"
# Tokeny se používají pro autentizaci v API (editor_app.py komunikuje přes API)
# ────────────────────────────────────────────────────────────
class ApiToken(db.Model):
    __tablename__ = 'api_tokens'
    id = db.Column(db.Integer, primary_key=True)

    token = db.Column(db.String(64), unique=True, nullable=False)
    # ↑ Náhodný hex řetězec (48 znaků) generovaný v api_routes.py přes secrets.token_hex(24)

    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    # ↑ Cizí klíč — každý token patří jednomu uživateli
    user = db.relationship('User')
    # ↑ api_token.user → vrátí User objekt vlastníka tokenu (používá se v api_routes.py)


# ────────────────────────────────────────────────────────────
# MODEL: ArticleLike — tabulka "article_likes"
# Každý řádek = jeden lajk (jeden uživatel lajkoval jeden článek)
# ────────────────────────────────────────────────────────────
class ArticleLike(db.Model):
    __tablename__ = 'article_likes'
    id = db.Column(db.Integer, primary_key=True)

    article_id = db.Column(db.Integer, db.ForeignKey('articles.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    user = db.relationship('User', backref='article_likes')
    # ↑ like.user → vrátí uživatele, který lajkoval; user.article_likes → všechny lajky uživatele
    article = db.relationship('Article', backref='likes')
    # ↑ like.article → vrátí článek; article.likes → seznam všech lajků článku


# ────────────────────────────────────────────────────────────
# MODEL: Comment — tabulka "comments"
# ────────────────────────────────────────────────────────────
class Comment(db.Model):
    __tablename__ = 'comments'
    id = db.Column(db.Integer, primary_key=True)

    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    article_id = db.Column(db.Integer, db.ForeignKey('articles.id'), nullable=False)
    # ↑ Pod kterým článkem komentář je
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    # ↑ Kdo komentář napsal

    article = db.relationship('Article', backref='comments')
    # ↑ comment.article → článek; article.comments → všechny komentáře článku
    user = db.relationship('User', backref='comments')
    # ↑ comment.user → uživatel; user.comments → všechny komentáře uživatele
    replies = db.relationship('CommentReply', backref='parent_comment', cascade='all, delete-orphan')
    # ↑ comment.replies → seznam odpovědí na tento komentář
    #   cascade='all, delete-orphan' = když smažeš komentář, smažou se i všechny jeho odpovědi

    def like_count(self) -> int:
        """Počet lajků tohoto komentáře."""
        return db.session.query(func.count(CommentLike.id)) \
            .filter(CommentLike.comment_id == self.id) \
            .scalar() or 0

    def is_liked_by(self, user) -> bool:
        """Vrátí True, pokud daný uživatel lajkoval tento komentář."""
        if not user:
            return False
        return CommentLike.query.filter_by(
            comment_id=self.id,
            user_id=user.id
        ).first() is not None


# ────────────────────────────────────────────────────────────
# MODEL: CommentLike — tabulka "comment_likes"
# ────────────────────────────────────────────────────────────
class CommentLike(db.Model):
    __tablename__ = 'comment_likes'
    id = db.Column(db.Integer, primary_key=True)

    comment_id = db.Column(db.Integer, db.ForeignKey('comments.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    user = db.relationship('User', backref='comment_likes')
    comment = db.relationship('Comment', backref='likes')

    __table_args__ = (
        db.UniqueConstraint('comment_id', 'user_id', name='uq_comment_like'),
        # ↑ Databázová úroveň ochrany: jeden uživatel nemůže lajknout stejný komentář dvakrát
    )


# ────────────────────────────────────────────────────────────
# MODEL: CommentReply — tabulka "comment_replies"
# Odpovědi na komentáře (jedna úroveň zanoření)
# ────────────────────────────────────────────────────────────
class CommentReply(db.Model):
    __tablename__ = 'comment_replies'
    id = db.Column(db.Integer, primary_key=True)

    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    comment_id = db.Column(db.Integer, db.ForeignKey('comments.id'), nullable=False)
    # ↑ Na který komentář odpověď reaguje
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    comment = db.relationship('Comment', foreign_keys=[comment_id])
    # ↑ foreign_keys=[comment_id] = explicitně říká, který sloupec je cizí klíč
    #   (nutné protože Comment má na CommentReply i relationship přes replies výše)
    user = db.relationship('User', backref='comment_replies')

    def like_count(self) -> int:
        """Počet lajků této odpovědi."""
        from models import CommentReplyLike  # lokální import — vyhýbá se cyklickému importu
        return db.session.query(func.count(CommentReplyLike.id))\
            .filter(CommentReplyLike.reply_id == self.id)\
            .scalar() or 0

    def is_liked_by(self, user) -> bool:
        """Vrátí True, pokud daný uživatel lajkoval tuto odpověď."""
        if not user:
            return False
        from models import CommentReplyLike
        return CommentReplyLike.query.filter_by(
            reply_id=self.id,
            user_id=user.id
        ).first() is not None


# ────────────────────────────────────────────────────────────
# MODEL: CommentReplyLike — tabulka "comment_reply_likes"
# ────────────────────────────────────────────────────────────
class CommentReplyLike(db.Model):
    __tablename__ = 'comment_reply_likes'
    id = db.Column(db.Integer, primary_key=True)

    reply_id = db.Column(db.Integer, db.ForeignKey('comment_replies.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    reply = db.relationship('CommentReply', backref='likes')
    user = db.relationship('User', backref='comment_reply_likes')

    __table_args__ = (
        db.UniqueConstraint('reply_id', 'user_id', name='uq_reply_like'),
        # ↑ Jeden uživatel nemůže lajknout stejnou odpověď dvakrát
    )


# ────────────────────────────────────────────────────────────
# VAZEBNÍ TABULKA: article_categories
# Propojuje articles a categories (vztah M:N — jeden článek může mít více kategorií
# a jedna kategorie může mít více článků)
# ────────────────────────────────────────────────────────────
article_categories = db.Table(
    'article_categories',
    db.Column('article_id', db.Integer, db.ForeignKey('articles.id', ondelete='CASCADE'), primary_key=True),
    # ↑ ondelete='CASCADE' = když smažeš článek, smažou se i jeho záznamy v této tabulce
    db.Column('category_id', db.Integer, db.ForeignKey('categories.id', ondelete='CASCADE'), primary_key=True),
    # ↑ Oba sloupce dohromady tvoří primární klíč (dvojice musí být unikátní)
)


# ────────────────────────────────────────────────────────────
# MODEL: Category — tabulka "categories"
# Kategorie vytváří admin přes admin_app.py
# ────────────────────────────────────────────────────────────
class Category(db.Model):
    """Kategorie článků. Vytváří admin, přiřazují editoři/admini."""
    __tablename__ = 'categories'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    slug = db.Column(db.String(100), unique=True, nullable=False)
    # ↑ URL-friendly název, např. "sport", "zahranicni-zpravy"
    #   Generuje se automaticky v admin_routes.py funkcí slugify()
    description = db.Column(db.String(300), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    articles = db.relationship('Article', secondary=article_categories, backref='categories', lazy='dynamic')
    # ↑ secondary=article_categories = vazební tabulka pro M:N vztah (definovaná výše)
    #   backref='categories' = article.categories → seznam kategorií článku
    #   lazy='dynamic' = nevytáhne hned všechny články, vrátí query objekt (lze filtrovat dál)

    def article_count(self) -> int:
        """Počet článků v této kategorii."""
        return self.articles.count()
        # ↑ .count() funguje kvůli lazy='dynamic' — vrátí SQL COUNT bez načítání objektů


# ────────────────────────────────────────────────────────────
# MODEL: UserFavoriteCategory — tabulka "user_favorite_categories"
# Oblíbené kategorie uživatele (pro personalizaci úvodní stránky)
# ────────────────────────────────────────────────────────────
class UserFavoriteCategory(db.Model):
    """Oblíbené kategorie uživatele."""
    __tablename__ = 'user_favorite_categories'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id', ondelete='CASCADE'), nullable=False)

    user = db.relationship('User', backref='favorite_categories')
    # ↑ user.favorite_categories → seznam oblíbených kategorií uživatele
    category = db.relationship('Category', backref='favorited_by')

    __table_args__ = (
        db.UniqueConstraint('user_id', 'category_id', name='uq_user_fav_category'),
        # ↑ Jeden uživatel nemůže mít stejnou kategorii jako oblíbenou dvakrát
    )


# ────────────────────────────────────────────────────────────
# MODEL: ArticleView — tabulka "article_views"
# Sleduje UNIKÁTNÍ zobrazení článku (per uživatel nebo IP adresa, per den)
# ────────────────────────────────────────────────────────────
class ArticleView(db.Model):
    """Zaznamenává unikátní zobrazení článku per uživatel nebo IP."""
    __tablename__ = 'article_views'

    id = db.Column(db.Integer, primary_key=True)
    article_id = db.Column(db.Integer, db.ForeignKey('articles.id', ondelete='CASCADE'), nullable=False)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id',    ondelete='SET NULL'), nullable=True)
    # ↑ nullable=True = pro nepřihlášené uživatele (anonymní návštěvníci)
    #   ondelete='SET NULL' = když se smaže uživatel, záznamy zůstanou ale user_id bude NULL
    ip_address = db.Column(db.String(45), nullable=True)   # IPv4 i IPv6 (max 45 znaků)
    viewed_at  = db.Column(db.Date, nullable=False)
    # ↑ Jen datum (ne čas) — unikátnost se počítá per den, ne per hodinu

    article = db.relationship('Article', backref=db.backref('article_views', cascade='all, delete-orphan', passive_deletes=True))
    user    = db.relationship('User',    backref='article_views')

    __table_args__ = (
        # Databáze zaručí, že přihlášený uživatel se započítá max. jednou denně
        db.UniqueConstraint('article_id', 'user_id',    'viewed_at', name='uq_view_user'),
        # Anonymní návštěvník (stejná IP) se započítá max. jednou denně
        db.UniqueConstraint('article_id', 'ip_address', 'viewed_at', name='uq_view_ip'),
    )

    @staticmethod
    def unique_count(article_id: int) -> int:
        """
        Vrátí celkový počet unikátních návštěvníků článku.
        Přihlášení se počítají podle user_id, anonymní podle IP adresy.
        Volá se z api_routes.py → api_article_stats().
        """
        logged_in = (
            db.session.query(func.count(func.distinct(ArticleView.user_id)))
            # ↑ SQL: SELECT COUNT(DISTINCT user_id) FROM article_views WHERE ...
            .filter(ArticleView.article_id == article_id, ArticleView.user_id.isnot(None))
            .scalar() or 0
        )
        anonymous = (
            db.session.query(func.count(func.distinct(ArticleView.ip_address)))
            .filter(ArticleView.article_id == article_id, ArticleView.user_id.is_(None))
            # ↑ is_(None) = SQL IS NULL — hledá záznamy bez přihlášeného uživatele
            .scalar() or 0
        )
        return logged_in + anonymous


# ────────────────────────────────────────────────────────────
# MODEL: UserFollow — tabulka "user_follows"
# Sledování uživatelů (follower sleduje followed)
# ────────────────────────────────────────────────────────────
class UserFollow(db.Model):
    __tablename__ = "user_follows"
    id = db.Column(db.Integer, primary_key=True)

    follower_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    # ↑ ID uživatele, který sleduje (ten, kdo kliknul "Sledovat")
    followed_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    # ↑ ID uživatele, který je sledován

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    follower = db.relationship("User", foreign_keys=[follower_id], backref="following_links")
    # ↑ foreign_keys=[follower_id] = nutné protože obě FK odkazují na stejnou tabulku (User)
    #   backref="following_links" = user.following_links → záznamy sledování (koho uživatel sleduje)
    followed = db.relationship("User", foreign_keys=[followed_id], backref="follower_links")
    # ↑ backref="follower_links" = user.follower_links → záznamy sledování (kdo sleduje uživatele)

    __table_args__ = (
        db.UniqueConstraint("follower_id", "followed_id", name="uq_user_follow"),
        # ↑ Jeden uživatel nemůže sledovat stejného uživatele dvakrát
    )