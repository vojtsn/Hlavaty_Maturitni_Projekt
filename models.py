from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import secrets
import string
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import func
db = SQLAlchemy()

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)

    username = db.Column(db.String(50), unique=True, nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)

    # v DB je password = hash
    password = db.Column(db.String(200), nullable=False)

    role = db.Column(db.String(20), nullable=False, default='user')

    # PROFIL
    display_name = db.Column(db.String(100))
    bio = db.Column(db.Text)
    birth_date = db.Column(db.Date)
    gender = db.Column(db.String(10))  # v DB je enum; ve Flasku může být String
    avatar = db.Column(db.String(255))

    # admin reset workflow (musí existovat i v DB — viz ALTER TABLE výše)
    force_password_change = db.Column(db.Boolean, default=False, nullable=False)
    temp_password_issued_at = db.Column(db.DateTime, nullable=True)

    def set_password(self, plain: str):
        self.password = generate_password_hash(plain)

    def check_password(self, plain: str) -> bool:
        return check_password_hash(self.password, plain)

    def is_admin_user(self) -> bool:
        return self.role == "admin"

    @staticmethod
    def generate_temporary_password(length: int = 12) -> str:
        alphabet = string.ascii_letters + string.digits
        return "".join(secrets.choice(alphabet) for _ in range(length))

    def admin_reset_password(self) -> str:
        temp = self.generate_temporary_password()
        self.set_password(temp)
        self.force_password_change = True
        self.temp_password_issued_at = datetime.utcnow()
        return temp

    theme = db.Column(db.String(10), nullable=False, default='light')

    def followers_count(self) -> int:
        return UserFollow.query.filter_by(followed_id=self.id).count()

    def following_count(self) -> int:
        return UserFollow.query.filter_by(follower_id=self.id).count()

    def is_following(self, other_user) -> bool:
        if not other_user:
            return False
        return UserFollow.query.filter_by(
            follower_id=self.id,
            followed_id=other_user.id
        ).first() is not None


class Article(db.Model):
    __tablename__ = 'articles'
    id = db.Column(db.Integer, primary_key=True)

    title = db.Column(db.String(200), nullable=False)
    perex = db.Column(db.String(500), nullable=True)
    content = db.Column(db.Text, nullable=False)
    views = db.Column(db.Integer, default=0, nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    author_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    author = db.relationship('User', backref='articles')

    def like_count(self) -> int:
        return db.session.query(func.count(ArticleLike.id))\
            .filter(ArticleLike.article_id == self.id)\
            .scalar() or 0

    def is_liked_by(self, user) -> bool:
        if not user:
            return False
        from models import ArticleLike
        return ArticleLike.query.filter_by(
            article_id=self.id,
            user_id=user.id
        ).first() is not None


class ApiToken(db.Model):
    __tablename__ = 'api_tokens'
    id = db.Column(db.Integer, primary_key=True)

    token = db.Column(db.String(64), unique=True, nullable=False)

    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    user = db.relationship('User')

class ArticleLike(db.Model):
    __tablename__ = 'article_likes'
    id = db.Column(db.Integer, primary_key=True)

    article_id = db.Column(db.Integer, db.ForeignKey('articles.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    user = db.relationship('User', backref='article_likes')
    article = db.relationship('Article', backref='likes')

class Comment(db.Model):
    __tablename__ = 'comments'
    id = db.Column(db.Integer, primary_key=True)

    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    article_id = db.Column(db.Integer, db.ForeignKey('articles.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    article = db.relationship('Article', backref='comments')
    user = db.relationship('User', backref='comments')
    replies = db.relationship('CommentReply', backref='parent_comment', cascade='all, delete-orphan')

    def like_count(self) -> int:
        return db.session.query(func.count(CommentLike.id)) \
            .filter(CommentLike.comment_id == self.id) \
            .scalar() or 0

    def is_liked_by(self, user) -> bool:
        if not user:
            return False
        return CommentLike.query.filter_by(
            comment_id=self.id,
            user_id=user.id
        ).first() is not None

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
    )
class CommentReply(db.Model):
    __tablename__ = 'comment_replies'
    id = db.Column(db.Integer, primary_key=True)

    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    comment_id = db.Column(db.Integer, db.ForeignKey('comments.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    comment = db.relationship('Comment', foreign_keys=[comment_id])
    user = db.relationship('User', backref='comment_replies')

    def like_count(self) -> int:
        from models import CommentReplyLike
        return db.session.query(func.count(CommentReplyLike.id))\
            .filter(CommentReplyLike.reply_id == self.id)\
            .scalar() or 0

    def is_liked_by(self, user) -> bool:
        if not user:
            return False
        from models import CommentReplyLike
        return CommentReplyLike.query.filter_by(
            reply_id=self.id,
            user_id=user.id
        ).first() is not None


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
    )

# Vazební tabulka pro M:N vztah Article <-> Category
article_categories = db.Table(
    'article_categories',
    db.Column('article_id', db.Integer, db.ForeignKey('articles.id', ondelete='CASCADE'), primary_key=True),
    db.Column('category_id', db.Integer, db.ForeignKey('categories.id', ondelete='CASCADE'), primary_key=True)
)


class Category(db.Model):
    """Kategorie článků. Vytváří admin, přiřazují editoři/admini."""
    __tablename__ = 'categories'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    slug = db.Column(db.String(100), unique=True, nullable=False)  # URL-friendly název, např. "sport"
    description = db.Column(db.String(300), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    articles = db.relationship('Article', secondary=article_categories, backref='categories', lazy='dynamic')

    def article_count(self) -> int:
        return self.articles.count()


class UserFavoriteCategory(db.Model):
    """Oblíbené kategorie uživatele."""
    __tablename__ = 'user_favorite_categories'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id', ondelete='CASCADE'), nullable=False)

    user = db.relationship('User', backref='favorite_categories')
    category = db.relationship('Category', backref='favorited_by')

    __table_args__ = (
        db.UniqueConstraint('user_id', 'category_id', name='uq_user_fav_category'),
    )


class ArticleView(db.Model):
    """Zaznamenává unikátní zobrazení článku per uživatel nebo IP."""
    __tablename__ = 'article_views'

    id = db.Column(db.Integer, primary_key=True)
    article_id = db.Column(db.Integer, db.ForeignKey('articles.id', ondelete='CASCADE'), nullable=False)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id',    ondelete='SET NULL'), nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)   # IPv4 i IPv6
    viewed_at  = db.Column(db.Date, nullable=False)         # jen datum — unikátnost per den

    article = db.relationship('Article', backref=db.backref('article_views', cascade='all, delete-orphan', passive_deletes=True))
    user    = db.relationship('User',    backref='article_views')

    __table_args__ = (
        # jeden záznam per (článek, uživatel, den) nebo (článek, IP, den)
        db.UniqueConstraint('article_id', 'user_id',    'viewed_at', name='uq_view_user'),
        db.UniqueConstraint('article_id', 'ip_address', 'viewed_at', name='uq_view_ip'),
    )

    @staticmethod
    def unique_count(article_id: int) -> int:
        """Celkový počet unikátních návštěvníků (přihlášení + anonymní)."""
        logged_in = (
            db.session.query(func.count(func.distinct(ArticleView.user_id)))
            .filter(ArticleView.article_id == article_id, ArticleView.user_id.isnot(None))
            .scalar() or 0
        )
        anonymous = (
            db.session.query(func.count(func.distinct(ArticleView.ip_address)))
            .filter(ArticleView.article_id == article_id, ArticleView.user_id.is_(None))
            .scalar() or 0
        )
        return logged_in + anonymous


class UserFollow(db.Model):
    __tablename__ = "user_follows"
    id = db.Column(db.Integer, primary_key=True)

    follower_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    followed_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    follower = db.relationship("User", foreign_keys=[follower_id], backref="following_links")
    followed = db.relationship("User", foreign_keys=[followed_id], backref="follower_links")

    __table_args__ = (
        db.UniqueConstraint("follower_id", "followed_id", name="uq_user_follow"),
    )