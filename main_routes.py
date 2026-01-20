import os
from datetime import datetime

from flask import (
    Blueprint, render_template, session,
    redirect, url_for, request, current_app, flash
)
from werkzeug.utils import secure_filename

from models import db, User, Article, ArticleLike

main_bp = Blueprint("main", __name__)

UPLOAD_FOLDER = 'static/profilovky'
ALLOWED_EXT = {'png', 'jpg', 'jpeg'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXT

main_bp = Blueprint("main", __name__)

@main_bp.route('/')
def index():
    username = session.get('username')
    articles = Article.query.order_by(Article.created_at.desc()).all()
    return render_template('index.html', username=username, articles=articles)

@main_bp.route('/profile')
def profile():
    if 'username' not in session:
        return redirect(url_for('auth.login'))

    user = User.query.filter_by(username=session['username']).first()
    return render_template('profile.html', user=user)

@main_bp.route('/editor')
def editor_info():
    if session.get('role') not in ('admin', 'editor', 'moderator'):
        return redirect(url_for('main.index'))
    return render_template('editor.html')

@main_bp.route('/clanek/<int:article_id>')
def clanek_detail(article_id):
    article = Article.query.get_or_404(article_id)
    return render_template('clanek_detail.html', article=article)

@main_bp.route("/edit-profile", methods=["GET", "POST"])
def edit_profile():
    username = session.get("username")
    if not username:
        return redirect(url_for("auth.login"))

    user = User.query.filter_by(username=username).first()
    if not user:
        session.clear()
        return redirect(url_for("auth.login"))

    if request.method == "POST":
        user.display_name = request.form.get("display_name")
        user.bio = request.form.get("bio")

        theme = request.form.get("theme", "light")
        if theme not in ("light", "dark"):
            theme = "light"

        user.theme = theme

        db.session.commit()

        session["theme"] = theme

        return redirect(url_for("main.profile"))

    return render_template("edit_profile.html", user=user)


@main_bp.route('/profile/avatar', methods=['POST'])
def upload_avatar():
    if 'username' not in session:
        return redirect(url_for('auth.login'))

    file = request.files.get('avatar')
    if not file or not allowed_file(file.filename):
        return redirect(url_for('main.profile'))

    # bezpečný název souboru
    safe_name = secure_filename(file.filename)
    filename = f"{session['username']}_{safe_name}"

    # absolutní cesta: projekt/static/profilovky
    upload_dir = os.path.join(current_app.root_path, 'static', 'profilovky')
    os.makedirs(upload_dir, exist_ok=True)

    file_path = os.path.join(upload_dir, filename)
    file.save(file_path)

    # uložíme jen název souboru do DB
    user = User.query.filter_by(username=session['username']).first()
    user.avatar = filename
    db.session.commit()

    return redirect(url_for('main.profile'))

@main_bp.route('/u/<string:username>')
def public_profile(username):
    user = User.query.filter_by(username=username).first_or_404()
    return render_template('public_profile.html', user=user)

@main_bp.route("/articles/<int:article_id>/like", methods=["POST"])
def like_article(article_id):
    username = session.get("username")
    if not username:
        return redirect(url_for("auth.login"))

    user = User.query.filter_by(username=username).first()
    if not user:
        session.clear()
        return redirect(url_for("auth.login"))

    existing = ArticleLike.query.filter_by(article_id=article_id, user_id=user.id).first()
    if existing:
        db.session.delete(existing)
        action = "UNLIKED"
    else:
        db.session.add(ArticleLike(article_id=article_id, user_id=user.id))
        action = "LIKED"

    db.session.commit()

    print(action, "article:", article_id, "by user:", user.id)  # ✅ TADY je to OK

    return redirect(request.referrer or url_for("main.clanek_detail", article_id=article_id))
@main_bp.route("/articles/<int:article_id>/likes")
def article_likes(article_id):
    article = Article.query.get_or_404(article_id)

    likes = (ArticleLike.query
             .filter_by(article_id=article.id)
             .join(User, User.id == ArticleLike.user_id)
             .order_by(ArticleLike.created_at.desc())
             .all())

    return render_template("article_likes.html", article=article, likes=likes)
