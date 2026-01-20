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


class Article(db.Model):
    __tablename__ = 'articles'
    id = db.Column(db.Integer, primary_key=True)

    title = db.Column(db.String(200), nullable=False)
    perex = db.Column(db.String(500), nullable=True)
    content = db.Column(db.Text, nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    author_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    author = db.relationship('User', backref='articles')

    def like_count(self) -> int:
        return db.session.query(func.count(ArticleLike.id))\
            .filter(ArticleLike.article_id == self.id)\
            .scalar() or 0

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
