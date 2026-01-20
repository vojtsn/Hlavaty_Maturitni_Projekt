from flask import Blueprint, render_template, session, redirect, url_for, abort
from models import User, Article


main_bp = Blueprint("main", __name__)

@main_bp.route('/')
def index():
    username = session.get('username')
    articles = Article.query.order_by(Article.created_at.desc()).all()
    return render_template('index.html', username=username, articles=articles)

@main_bp.route('/profile')
def profile():
    username = session.get('username')
    if not username:
        return redirect(url_for('auth.login'))

    user = User.query.filter_by(username=username).first()
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

