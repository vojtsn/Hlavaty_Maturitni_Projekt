import os
from datetime import datetime

from flask import (
    Blueprint, render_template, session,
    redirect, url_for, request, current_app, jsonify
)
from werkzeug.utils import secure_filename

from models import db, User, Article, ArticleLike, Comment, CommentLike, CommentReplyLike, CommentReply, UserFollow

main_bp = Blueprint("main", __name__)

UPLOAD_FOLDER = 'static/profilovky'
ALLOWED_EXT = {'png', 'jpg', 'jpeg'}
ALLOWED_ARTICLE_EXT = {"png", "jpg", "jpeg", "webp", "gif"}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXT

def allowed_article_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_ARTICLE_EXT

@main_bp.route('/')
def index():
    articles = Article.query.order_by(Article.created_at.desc()).all()

    username = session.get("username")
    user = User.query.filter_by(username=username).first() if username else None

    followed_users = []
    if user:
        followed_users = (User.query
                          .join(UserFollow, User.id == UserFollow.followed_id)
                          .filter(UserFollow.follower_id == user.id)
                          .order_by(User.display_name.asc(), User.username.asc())
                          .limit(5)
                          .all())

    return render_template(
        "index.html",
        articles=articles,
        current_user=user,
        username=username,
        followed_users=followed_users
    )

@main_bp.route('/profile')
def profile():
    if 'username' not in session:
        return redirect(url_for('auth.login'))

    user = User.query.filter_by(username=session['username']).first()
    if not user:
        session.clear()
        return redirect(url_for('auth.login'))

    # komentáře
    comments = (Comment.query
                .filter_by(user_id=user.id)
                .order_by(Comment.created_at.desc())
                .all())

    # odpovědi
    replies = (CommentReply.query
               .filter_by(user_id=user.id)
               .order_by(CommentReply.created_at.desc())
               .all())

    # FOLLOWING (koho sleduje)
    following = (User.query
                 .join(UserFollow, User.id == UserFollow.followed_id)
                 .filter(UserFollow.follower_id == user.id)
                 .order_by(User.display_name.asc(), User.username.asc())
                 .all())

    # FOLLOWERS (kdo sleduje jeho)
    followers = (User.query
                 .join(UserFollow, User.id == UserFollow.follower_id)
                 .filter(UserFollow.followed_id == user.id)
                 .order_by(User.display_name.asc(), User.username.asc())
                 .all())

    return render_template(
        'profile.html',
        user=user,
        comments=comments,
        replies=replies,
        following=following,
        followers=followers
    )


@main_bp.route('/editor')
def editor_info():
    if session.get('role') not in ('admin', 'editor', 'moderator'):
        return redirect(url_for('main.index'))
    return render_template('editor.html')


@main_bp.route('/clanek/<int:article_id>')
def clanek_detail(article_id):
    article = Article.query.get_or_404(article_id)

    comments = (Comment.query
                .filter_by(article_id=article.id)
                .order_by(Comment.created_at.asc())
                .all())

    username = session.get("username")
    user = User.query.filter_by(username=username).first() if username else None

    return render_template(
        'clanek_detail.html',
        article=article,
        comments=comments,
        current_user=user
    )



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
        user.display_name = (request.form.get("display_name") or "").strip() or None
        user.bio = (request.form.get("bio") or "").strip() or None

        # birth_date: čeká input type="date" => YYYY-MM-DD
        bd_raw = (request.form.get("birth_date") or "").strip()
        if bd_raw:
            try:
                user.birth_date = datetime.strptime(bd_raw, "%Y-%m-%d").date()
            except ValueError:
                user.birth_date = None
        else:
            user.birth_date = None

        # gender: text/select
        gender = (request.form.get("gender") or "").strip()
        user.gender = gender or None

        db.session.commit()
        return redirect(url_for("main.profile"))

    return render_template("edit_profile.html", user=user)



@main_bp.route('/profile/avatar', methods=['POST'])
def upload_avatar():
    if 'username' not in session:
        return redirect(url_for('auth.login'))

    file = request.files.get('avatar')
    if not file or not allowed_file(file.filename):
        return redirect(url_for('main.profile'))

    safe_name = secure_filename(file.filename)
    filename = f"{session['username']}_{safe_name}"

    upload_dir = os.path.join(current_app.root_path, 'static', 'profilovky')
    os.makedirs(upload_dir, exist_ok=True)

    file_path = os.path.join(upload_dir, filename)
    file.save(file_path)

    user = User.query.filter_by(username=session['username']).first()
    user.avatar = filename
    db.session.commit()

    return redirect(url_for('main.profile'))


@main_bp.route('/u/<string:username>')
def public_profile(username):
    user = User.query.filter_by(username=username).first_or_404()

    current_username = session.get("username")
    current_user = User.query.filter_by(username=current_username).first() if current_username else None

    comments = (Comment.query
                .filter_by(user_id=user.id)
                .order_by(Comment.created_at.desc())
                .all())

    replies = (CommentReply.query
               .filter_by(user_id=user.id)
               .order_by(CommentReply.created_at.desc())
               .all())

    followers = (User.query
                 .join(UserFollow, User.id == UserFollow.follower_id)
                 .filter(UserFollow.followed_id == user.id)
                 .order_by(User.display_name.asc(), User.username.asc())
                 .all())

    following = (User.query
                 .join(UserFollow, User.id == UserFollow.followed_id)
                 .filter(UserFollow.follower_id == user.id)
                 .order_by(User.display_name.asc(), User.username.asc())
                 .all())

    return render_template(
        'public_profile.html',
        user=user,
        current_user=current_user,
        comments=comments,
        replies=replies,
        followers=followers,
        following=following
    )


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
    else:
        db.session.add(ArticleLike(article_id=article_id, user_id=user.id))

    db.session.commit()

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


# ✅ PŘIDAT KOMENTÁŘ (přihlášený)
@main_bp.route("/articles/<int:article_id>/comment", methods=["POST"])
def add_comment(article_id):
    username = session.get("username")
    if not username:
        return redirect(url_for("auth.login"))

    user = User.query.filter_by(username=username).first()
    if not user:
        session.clear()
        return redirect(url_for("auth.login"))

    article = Article.query.get_or_404(article_id)

    content = (request.form.get("content") or "").strip()
    if not content:
        return redirect(url_for("main.clanek_detail", article_id=article.id))

    if len(content) > 2000:
        content = content[:2000]

    db.session.add(Comment(content=content, article_id=article.id, user_id=user.id))
    db.session.commit()

    return redirect(url_for("main.clanek_detail", article_id=article.id))

@main_bp.route("/comments/<int:comment_id>/like", methods=["POST"])
def like_comment(comment_id):
    username = session.get("username")
    if not username:
        return redirect(url_for("auth.login"))

    user = User.query.filter_by(username=username).first()
    if not user:
        session.clear()
        return redirect(url_for("auth.login"))

    comment = Comment.query.get_or_404(comment_id)

    existing = CommentLike.query.filter_by(comment_id=comment.id, user_id=user.id).first()
    if existing:
        db.session.delete(existing)
    else:
        db.session.add(CommentLike(comment_id=comment.id, user_id=user.id))

    db.session.commit()

    return redirect(
        (request.referrer or url_for("main.clanek_detail", article_id=comment.article_id))
        + f"#comment-{comment.id}"
    )

@main_bp.route("/comments/<int:comment_id>/reply", methods=["POST"])
def add_reply(comment_id):
    username = session.get("username")
    if not username:
        return redirect(url_for("auth.login"))

    user = User.query.filter_by(username=username).first()
    if not user:
        session.clear()
        return redirect(url_for("auth.login"))

    comment = Comment.query.get_or_404(comment_id)

    content = (request.form.get("content") or "").strip()
    if not content:
        return redirect(url_for("main.clanek_detail", article_id=comment.article_id) + f"#comment-{comment.id}")

    if len(content) > 2000:
        content = content[:2000]

    db.session.add(CommentReply(content=content, comment_id=comment.id, user_id=user.id))
    db.session.commit()

    # zůstaneš u komentáře, ne nahoře
    return redirect(url_for("main.clanek_detail", article_id=comment.article_id) + f"#comment-{comment.id}")

@main_bp.route("/replies/<int:reply_id>/like", methods=["POST"])
def like_reply(reply_id):
    username = session.get("username")
    if not username:
        return redirect(url_for("auth.login"))

    user = User.query.filter_by(username=username).first()
    if not user:
        session.clear()
        return redirect(url_for("auth.login"))

    reply = CommentReply.query.get_or_404(reply_id)
    comment = Comment.query.get_or_404(reply.comment_id)

    existing = CommentReplyLike.query.filter_by(reply_id=reply.id, user_id=user.id).first()
    if existing:
        db.session.delete(existing)
    else:
        db.session.add(CommentReplyLike(reply_id=reply.id, user_id=user.id))

    db.session.commit()

    return redirect(url_for("main.clanek_detail", article_id=comment.article_id) + f"#comment-{comment.id}")

@main_bp.route("/u/<string:username>/follow", methods=["POST"])
def toggle_follow(username):
    current_username = session.get("username")
    if not current_username:
        return redirect(url_for("auth.login"))

    me = User.query.filter_by(username=current_username).first()
    if not me:
        session.clear()
        return redirect(url_for("auth.login"))

    target = User.query.filter_by(username=username).first_or_404()

    # zakázat follow sebe
    if target.id == me.id:
        return redirect(request.referrer or url_for("main.public_profile", username=target.username))

    existing = UserFollow.query.filter_by(follower_id=me.id, followed_id=target.id).first()
    if existing:
        db.session.delete(existing)
    else:
        db.session.add(UserFollow(follower_id=me.id, followed_id=target.id))

    db.session.commit()

    return redirect(request.referrer or url_for("main.public_profile", username=target.username))