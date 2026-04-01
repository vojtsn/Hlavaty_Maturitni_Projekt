import os
from datetime import datetime, date  # datetime = datum + čas, date = jen datum (bez času)

from flask import (
    Blueprint, render_template, session,       # Blueprint = skupina routes, session = data přihlášeného uživatele
    redirect, url_for, request, current_app, jsonify  # redirect = přesměrování, request = data příchozího requestu
)
from werkzeug.utils import secure_filename
# secure_filename odstraní nebezpečné znaky z názvů souborů (např. "../hesla.txt" → "hesla.txt")

from auth_routes import require_password_change_check
# tento decorator zkontroluje při každém requestu jestli admin nenařídil uživateli změnu hesla
# pokud ano, přesměruje ho na stránku pro změnu hesla místo toho co chtěl

from models import db, User, Article, ArticleLike, Comment, CommentLike, CommentReplyLike, CommentReply, UserFollow, Category, UserFavoriteCategory, ArticleView
# importujeme všechny databázové modely — každý odpovídá jedné tabulce v databázi

main_bp = Blueprint("main", __name__)
# Blueprint je způsob jak rozdělit routes do více souborů
# název "main" se pak používá v url_for(), např. url_for("main.index") pro hlavní stránku

# cesta ke složce pro ukládání profilových fotek (relativní od app.py)
UPLOAD_FOLDER = 'static/profilovky'

# povolené formáty pro profilové fotky
ALLOWED_EXT = {'png', 'jpg', 'jpeg'}

# povolené formáty pro obrázky v článcích (navíc webp a gif)
# pozor: stejná konstanta existuje i v api_routes.py — pokud změníš zde, změň i tam
ALLOWED_ARTICLE_EXT = {"png", "jpg", "jpeg", "webp", "gif"}

def allowed_file(filename):
    # zkontroluje jestli má soubor povolenou příponu pro profilové fotky
    # rsplit('.', 1) rozdělí jméno souboru na část před a za poslední tečkou
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXT

def allowed_article_file(filename):
    # totéž ale pro obrázky v článcích (povoluje navíc webp a gif)
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_ARTICLE_EXT


# --- hlavní stránka ---

@main_bp.route('/')
@require_password_change_check  # zkontroluje potřebu změny hesla před zobrazením stránky
def index():
    # načte všechny články seřazené od nejnovějšího
    articles = Article.query.order_by(Article.created_at.desc()).all()
    categories = Category.query.order_by(Category.name.asc()).all()

    # zjistí kdo je přihlášen z cookies session
    # session["username"] se nastavuje v auth_routes.py při přihlášení
    username = session.get("username")
    user = User.query.filter_by(username=username).first() if username else None

    followed_users = []
    personal_articles = []
    fav_category_ids = set()

    if user:
        # uživatelé které tento user sleduje — max 5 pro sidebar
        followed_users = (User.query
                          .join(UserFollow, User.id == UserFollow.followed_id)
                          .filter(UserFollow.follower_id == user.id)
                          .order_by(User.display_name.asc(), User.username.asc())
                          .limit(5)
                          .all())

        # oblíbené kategorie uživatele uložené v tabulce user_favorite_categories
        fav_cats = UserFavoriteCategory.query.filter_by(user_id=user.id).all()
        fav_category_ids = {fc.category_id for fc in fav_cats}  # převede na set ID pro rychlé hledání

        if fav_category_ids:
            from datetime import timedelta
            cutoff = datetime.utcnow() - timedelta(days=30)  # datum před 30 dny
            # načte nejnovější články z oblíbených kategorií za posledních 30 dní
            # distinct() zajistí že se článek nezobrazí vícekrát pokud patří do více oblíbených kategorií
            personal_articles = (Article.query
                                 .join(Article.categories)
                                 .filter(Category.id.in_(fav_category_ids))
                                 .filter(Article.created_at >= cutoff)
                                 .order_by(Article.created_at.desc())
                                 .distinct()
                                 .limit(10)
                                 .all())

    # předá všechna data do HTML šablony index.html
    return render_template(
        "index.html",
        articles=articles,
        categories=categories,
        current_user=user,
        username=username,
        followed_users=followed_users,
        personal_articles=personal_articles,
        fav_category_ids=fav_category_ids,
    )


# --- profil přihlášeného uživatele ---

@main_bp.route('/profile')
@require_password_change_check
def profile():
    # pokud uživatel není přihlášen, pošleme ho na přihlášení
    if 'username' not in session:
        return redirect(url_for('auth.login'))

    user = User.query.filter_by(username=session['username']).first()
    if not user:
        # uživatel existuje v session ale ne v databázi — smažeme session a pošleme na login
        session.clear()
        return redirect(url_for('auth.login'))

    # komentáře uživatele od nejnovějšího
    comments = (Comment.query
                .filter_by(user_id=user.id)
                .order_by(Comment.created_at.desc())
                .all())

    # odpovědi uživatele na cizí komentáře
    replies = (CommentReply.query
               .filter_by(user_id=user.id)
               .order_by(CommentReply.created_at.desc())
               .all())

    # uživatelé které tento user sleduje
    following = (User.query
                 .join(UserFollow, User.id == UserFollow.followed_id)
                 .filter(UserFollow.follower_id == user.id)
                 .order_by(User.display_name.asc(), User.username.asc())
                 .all())

    # uživatelé kteří sledují tohoto usera
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
        followers=followers,
        # kategorie se předávají pro výběr oblíbených přímo na stránce profilu
        categories=Category.query.order_by(Category.name.asc()).all()
    )


# --- info stránka pro editory ---

@main_bp.route('/editor')
@require_password_change_check
def editor_info():
    # zobrazí stránku jen pro privilegované role — ostatní přesměrujeme na hlavní stránku
    if session.get('role') not in ('admin', 'editor', 'moderator'):
        return redirect(url_for('main.index'))
    return render_template('editor.html')


# --- detail článku ---

@main_bp.route('/clanek/<int:article_id>')
def clanek_detail(article_id):
    # article_id přijde z URL (např. /clanek/42) — Flask ho automaticky převede na číslo
    # get_or_404 vrátí článek nebo automaticky zobrazí chybu 404 pokud článek neexistuje
    article = Article.query.get_or_404(article_id)

    # celkový počet zobrazení se zvýší vždy — i opakovaná návštěva se počítá
    article.views = (article.views or 0) + 1

    username = session.get("username")
    user = User.query.filter_by(username=username).first() if username else None
    today = date.today()  # dnešní datum pro deduplikaci unikátních zobrazení

    if user:
        # pro přihlášené uživatele: jedno unikátní zobrazení per uživatel per den
        exists = ArticleView.query.filter_by(
            article_id=article_id,
            user_id=user.id,
            viewed_at=today
        ).first()
        if not exists:
            # pokud dnes ještě článek nečetl, zapíšeme nové unikátní zobrazení
            db.session.add(ArticleView(
                article_id=article_id,
                user_id=user.id,
                viewed_at=today
            ))
    else:
        # pro nepřihlášené: jedno unikátní zobrazení per IP adresa per den
        ip = request.remote_addr
        exists = ArticleView.query.filter_by(
            article_id=article_id,
            ip_address=ip,
            viewed_at=today
        ).filter(ArticleView.user_id.is_(None)).first()  # is_(None) = jen záznamy bez uživatele
        if not exists:
            db.session.add(ArticleView(
                article_id=article_id,
                ip_address=ip,
                viewed_at=today
            ))

    db.session.commit()  # uloží do databáze zvýšený počet zobrazení i případný nový záznam

    # komentáře od nejstaršího — chronologické pořadí je přirozenější pro čtení
    comments = (Comment.query
                .filter_by(article_id=article.id)
                .order_by(Comment.created_at.asc())
                .all())

    return render_template(
        'clanek_detail.html',
        article=article,
        comments=comments,
        current_user=user
    )


# --- editace profilu ---

@main_bp.route("/edit-profile", methods=["GET", "POST"])
@require_password_change_check
def edit_profile():
    username = session.get("username")
    if not username:
        return redirect(url_for("auth.login"))

    user = User.query.filter_by(username=username).first()
    if not user:
        session.clear()
        return redirect(url_for("auth.login"))

    error = None

    if request.method == "POST":
        # GET zobrazí formulář, POST zpracuje odeslaná data
        new_username = (request.form.get("username") or "").strip()
        # prázdný řetězec ukládáme jako None (NULL v databázi) — šetří místo a jde snáz testovat
        user.display_name = (request.form.get("display_name") or "").strip() or None
        user.bio = (request.form.get("bio") or "").strip() or None

        bd_raw = (request.form.get("birth_date") or "").strip()
        if bd_raw:
            try:
                # datum přijde z HTML inputu jako "2000-01-31" — strptime ho naparsuje na objekt date
                user.birth_date = datetime.strptime(bd_raw, "%Y-%m-%d").date()
            except ValueError:
                # pokud formát nesedí (uživatel ho nějak upravil), prostě datum nenastavíme
                user.birth_date = None
        else:
            user.birth_date = None

        gender = (request.form.get("gender") or "").strip()
        user.gender = gender or None  # prázdný řetězec → None

        username_changed = False
        if new_username and new_username != user.username:
            # uživatel chce změnit jméno — ověříme že nové jméno není obsazené
            if User.query.filter_by(username=new_username).first():
                error = "Toto uživatelské jméno je již obsazeno."
            elif len(new_username) < 3:
                error = "Uživatelské jméno musí mít alespoň 3 znaky."
            else:
                user.username = new_username
                username_changed = True

        if not error:
            db.session.commit()
            if username_changed:
                # po změně jména musíme uživatele odhlásit — v session je uloženo staré jméno
                # a to by způsobilo problémy při dalším načítání dat
                session.clear()
                return redirect(url_for("auth.login"))
            return redirect(url_for("main.profile"))

    # GET request nebo POST s chybou — zobrazí formulář (s případnou chybovou hláškou)
    return render_template("edit_profile.html", user=user, error=error)


# --- nahrání profilové fotky ---

@main_bp.route('/profile/avatar', methods=['POST'])
@require_password_change_check
def upload_avatar():
    if 'username' not in session:
        return redirect(url_for('auth.login'))

    # request.files obsahuje soubory nahrané přes HTML formulář (multipart/form-data)
    file = request.files.get('avatar')
    if not file or not allowed_file(file.filename):
        # žádný soubor nebyl vybrán nebo má špatnou příponu — tiše přesměrujeme zpět
        return redirect(url_for('main.profile'))

    # secure_filename odstraní z názvu souboru nebezpečné znaky jako "../" nebo absolutní cesty
    safe_name = secure_filename(file.filename)
    # přidáme username jako prefix aby se fotky různých uživatelů nepřepisovaly
    filename = f"{session['username']}_{safe_name}"

    # current_app.root_path = absolutní cesta ke složce kde leží app.py
    upload_dir = os.path.join(current_app.root_path, 'static', 'profilovky')
    os.makedirs(upload_dir, exist_ok=True)  # vytvoří složku pokud neexistuje, nespadne pokud existuje

    file_path = os.path.join(upload_dir, filename)
    file.save(file_path)  # uloží soubor na disk

    user = User.query.filter_by(username=session['username']).first()
    # uložíme jen název souboru, ne celou cestu
    # celá URL se skládá v šabloně jako: /static/profilovky/{{ user.avatar }}
    user.avatar = filename
    db.session.commit()

    return redirect(url_for('main.profile'))


# --- veřejný profil libovolného uživatele ---

@main_bp.route('/u/<string:username>')
def public_profile(username):
    # tato stránka je dostupná i bez přihlášení
    # first_or_404 vrátí uživatele nebo automaticky zobrazí chybu 404
    user = User.query.filter_by(username=username).first_or_404()

    current_username = session.get("username")
    current_user = User.query.filter_by(username=current_username).first() if current_username else None

    # komentáře daného uživatele — od nejnovějšího
    comments = (Comment.query
                .filter_by(user_id=user.id)
                .order_by(Comment.created_at.desc())
                .all())

    # odpovědi daného uživatele na komentáře
    replies = (CommentReply.query
               .filter_by(user_id=user.id)
               .order_by(CommentReply.created_at.desc())
               .all())

    # kdo sleduje tohoto uživatele
    followers = (User.query
                 .join(UserFollow, User.id == UserFollow.follower_id)
                 .filter(UserFollow.followed_id == user.id)
                 .order_by(User.display_name.asc(), User.username.asc())
                 .all())

    # koho tento uživatel sleduje
    following = (User.query
                 .join(UserFollow, User.id == UserFollow.followed_id)
                 .filter(UserFollow.follower_id == user.id)
                 .order_by(User.display_name.asc(), User.username.asc())
                 .all())

    # články se zobrazují jen u editorů a adminů — běžní uživatelé články nepíší
    articles = []
    if user.role in ('editor', 'admin', 'moderator'):
        articles = (Article.query
                    .filter_by(author_id=user.id)
                    .order_by(Article.created_at.desc())
                    .all())

    return render_template(
        'public_profile.html',
        user=user,
        current_user=current_user,
        comments=comments,
        replies=replies,
        followers=followers,
        following=following,
        articles=articles,
        article_count=len(articles),
    )


# --- lajkování článku ---

@main_bp.route("/articles/<int:article_id>/like", methods=["POST"])
def like_article(article_id):
    username = session.get("username")
    if not username:
        return redirect(url_for("auth.login"))

    user = User.query.filter_by(username=username).first()
    if not user:
        session.clear()
        return redirect(url_for("auth.login"))

    # toggle: pokud lajk existuje, smaže ho — pokud ne, přidá ho
    existing = ArticleLike.query.filter_by(article_id=article_id, user_id=user.id).first()
    if existing:
        db.session.delete(existing)  # druhý klik na lajk ho odebere
    else:
        db.session.add(ArticleLike(article_id=article_id, user_id=user.id))

    db.session.commit()

    # přesměruje zpět na stránku odkud request přišel (request.referrer = adresa předchozí stránky)
    return redirect(request.referrer or url_for("main.clanek_detail", article_id=article_id))


# --- stránka se seznamem kdo lajkoval článek ---

@main_bp.route("/articles/<int:article_id>/likes")
def article_likes(article_id):
    article = Article.query.get_or_404(article_id)

    # načte lajky spojené s uživatelskými daty přes JOIN — aby bylo vidět kdo lajkoval
    likes = (ArticleLike.query
             .filter_by(article_id=article.id)
             .join(User, User.id == ArticleLike.user_id)
             .order_by(ArticleLike.created_at.desc())
             .all())

    return render_template("article_likes.html", article=article, likes=likes)


# --- přidání komentáře ---

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
        # prázdný komentář ignorujeme — přesměrujeme zpět bez uložení
        return redirect(url_for("main.clanek_detail", article_id=article.id))

    # ořežeme komentář na 2000 znaků pokud je delší — ochrana před spamem
    if len(content) > 2000:
        content = content[:2000]

    db.session.add(Comment(content=content, article_id=article.id, user_id=user.id))
    db.session.commit()

    return redirect(url_for("main.clanek_detail", article_id=article.id))


# --- lajkování komentáře ---

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

    # toggle — stejná logika jako u lajku článku
    existing = CommentLike.query.filter_by(comment_id=comment.id, user_id=user.id).first()
    if existing:
        db.session.delete(existing)
    else:
        db.session.add(CommentLike(comment_id=comment.id, user_id=user.id))

    db.session.commit()

    # přesměruje zpět a scrolluje přímo na komentář pomocí #comment-{id} v URL
    return redirect(
        (request.referrer or url_for("main.clanek_detail", article_id=comment.article_id))
        + f"#comment-{comment.id}"
    )


# --- přidání odpovědi na komentář ---

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
        # prázdná odpověď — přesměrujeme zpět na rodičovský komentář
        return redirect(url_for("main.clanek_detail", article_id=comment.article_id) + f"#comment-{comment.id}")

    if len(content) > 2000:
        content = content[:2000]  # stejný limit jako u komentářů

    db.session.add(CommentReply(content=content, comment_id=comment.id, user_id=user.id))
    db.session.commit()

    # scrolluje na rodičovský komentář, ne na začátek stránky
    return redirect(url_for("main.clanek_detail", article_id=comment.article_id) + f"#comment-{comment.id}")


# --- lajkování odpovědi na komentář ---

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
    # comment potřebujeme jen kvůli article_id pro přesměrování na konci

    # toggle lajku na odpověď
    existing = CommentReplyLike.query.filter_by(reply_id=reply.id, user_id=user.id).first()
    if existing:
        db.session.delete(existing)
    else:
        db.session.add(CommentReplyLike(reply_id=reply.id, user_id=user.id))

    db.session.commit()

    return redirect(url_for("main.clanek_detail", article_id=comment.article_id) + f"#comment-{comment.id}")


# --- sledování / odsledování uživatele ---

@main_bp.route("/u/<string:username>/follow", methods=["POST"])
def toggle_follow(username):
    current_username = session.get("username")
    if not current_username:
        return redirect(url_for("auth.login"))

    me = User.query.filter_by(username=current_username).first()
    if not me:
        session.clear()
        return redirect(url_for("auth.login"))

    # target = uživatel kterého chceme sledovat/odsledovat
    target = User.query.filter_by(username=username).first_or_404()

    # nejde sledovat sám sebe — to by nedávalo smysl
    if target.id == me.id:
        return redirect(request.referrer or url_for("main.public_profile", username=target.username))

    # toggle sledování — pokud záznam existuje, smažeme ho; pokud ne, přidáme
    existing = UserFollow.query.filter_by(follower_id=me.id, followed_id=target.id).first()
    if existing:
        db.session.delete(existing)
    else:
        db.session.add(UserFollow(follower_id=me.id, followed_id=target.id))

    db.session.commit()

    return redirect(request.referrer or url_for("main.public_profile", username=target.username))


# --- detail kategorie ---

@main_bp.route('/kategorie/<string:slug>')
def category_detail(slug):
    # slug je URL-přátelský název kategorie, např. "zahranicni-zpravy"
    # vytváří ho slugify() v admin_routes.py při zakládání kategorie
    cat = Category.query.filter_by(slug=slug).first_or_404()

    username = session.get("username")
    user = User.query.filter_by(username=username).first() if username else None

    # cat.articles je lazy='dynamic' query objekt (definováno v models.py)
    # proto musíme přidat .order_by().all() pro skutečné načtení dat
    articles = (cat.articles
                .order_by(Article.created_at.desc())
                .all())

    categories = Category.query.order_by(Category.name.asc()).all()

    return render_template(
        'category_detail.html',
        category=cat,
        articles=articles,
        categories=categories,
        current_user=user,
        username=username
    )


# --- uložení oblíbených kategorií uživatele ---

@main_bp.route('/favorite-categories', methods=['POST'])
def save_favorite_categories():
    username = session.get('username')
    if not username:
        return redirect(url_for('auth.login'))

    user = User.query.filter_by(username=username).first()
    if not user:
        session.clear()
        return redirect(url_for('auth.login'))

    # nejjednodušší přístup: smažeme všechny stávající oblíbené a uložíme nové od nuly
    # alternativou by bylo porovnávat co přibylo a co ubylo — zbytečně složité
    UserFavoriteCategory.query.filter_by(user_id=user.id).delete()

    # getlist vrátí seznam všech hodnot se stejným názvem z formuláře
    # funguje pro HTML checkboxy: <input type="checkbox" name="category_ids" value="3">
    selected_ids = request.form.getlist('category_ids')
    for cat_id in selected_ids:
        try:
            db.session.add(UserFavoriteCategory(user_id=user.id, category_id=int(cat_id)))
        except Exception:
            pass  # ignorujeme neplatná ID (např. pokud někdo upravil formulář v prohlížeči)

    db.session.commit()
    return redirect(url_for('main.profile'))


# --- smazání komentáře ---

@main_bp.route('/comments/<int:comment_id>/delete', methods=['POST'])
def delete_comment(comment_id):
    username = session.get('username')
    if not username:
        return redirect(url_for('auth.login'))

    user = User.query.filter_by(username=username).first()
    if not user:
        session.clear()
        return redirect(url_for('auth.login'))

    comment = Comment.query.get_or_404(comment_id)
    article_id = comment.article_id  # uložíme si pro přesměrování po smazání

    # mazat může jen autor komentáře, admin nebo moderátor — nikdo jiný
    if comment.user_id != user.id and user.role not in ('admin', 'moderator'):
        return redirect(url_for('main.clanek_detail', article_id=article_id))

    db.session.delete(comment)
    db.session.commit()

    return redirect(url_for('main.clanek_detail', article_id=article_id))


# --- smazání odpovědi na komentář ---

@main_bp.route('/replies/<int:reply_id>/delete', methods=['POST'])
def delete_reply(reply_id):
    username = session.get('username')
    if not username:
        return redirect(url_for('auth.login'))

    user = User.query.filter_by(username=username).first()
    if not user:
        session.clear()
        return redirect(url_for('auth.login'))

    reply = CommentReply.query.get_or_404(reply_id)
    # odpověď nemá article_id přímo — musíme ho dohledat přes rodičovský komentář
    article_id = db.session.get(Comment, reply.comment_id).article_id

    # mazat může jen autor odpovědi, admin nebo moderátor
    if reply.user_id != user.id and user.role not in ('admin', 'moderator'):
        return redirect(url_for('main.clanek_detail', article_id=article_id))

    db.session.delete(reply)
    db.session.commit()

    return redirect(url_for('main.clanek_detail', article_id=article_id))


# --- vyhledávání ---

@main_bp.route('/search')
def search():
    # q = hledaný výraz z URL, např. /search?q=python
    q = (request.args.get('q') or '').strip()

    articles = []
    users = []

    if q:
        # % jsou SQL wildcards pro LIKE — %python% najde "python" kdekoliv v textu
        pattern = f'%{q}%'

        # hledá ve třech polích článku: titulek, obsah i perex
        # ilike = case-insensitive LIKE (hledá bez ohledu na velikost písmen)
        articles = (Article.query
                    .filter(
                        db.or_(
                            Article.title.ilike(pattern),
                            Article.content.ilike(pattern),
                            Article.perex.ilike(pattern)
                        )
                    )
                    .order_by(Article.created_at.desc())
                    .limit(20)  # maximálně 20 výsledků aby se stránka nenačítala dlouho
                    .all())

        # hledá v username i zobrazovaném jménu uživatelů
        users = (User.query
                 .filter(
                     db.or_(
                         User.username.ilike(pattern),
                         User.display_name.ilike(pattern)
                     )
                 )
                 .order_by(User.username.asc())
                 .limit(10)
                 .all())

    username = session.get('username')
    current_user = User.query.filter_by(username=username).first() if username else None

    return render_template(
        'search.html',
        q=q,             # předáme zpět hledaný výraz aby byl vidět v poli vyhledávání
        articles=articles,
        users=users,
        current_user=current_user
    )


# --- smazání článku přes webové rozhraní (ne přes API) ---

@main_bp.route('/articles/<int:article_id>/delete', methods=['POST'])
def delete_article(article_id):
    username = session.get('username')
    if not username:
        return redirect(url_for('auth.login'))

    user = User.query.filter_by(username=username).first()
    if not user:
        session.clear()
        return redirect(url_for('auth.login'))

    # jen editor, moderátor nebo admin vůbec může mazat články
    if user.role not in ('admin', 'moderator', 'editor'):
        return redirect(url_for('main.clanek_detail', article_id=article_id))

    article = Article.query.get_or_404(article_id)

    # editor smí smazat jen vlastní články — ne cizí
    if user.role == 'editor' and article.author_id != user.id:
        return redirect(url_for('main.clanek_detail', article_id=article_id))

    # moderátor nesmí smazat článek od admina
    if user.role == 'moderator' and article.author.role == 'admin':
        return redirect(url_for('main.clanek_detail', article_id=article_id))

    # před smazáním je vyžadováno zadání hesla jako potvrzení — mazání je nevratné
    password = request.form.get('confirm_password', '')
    if not user.check_password(password):
        # špatné heslo — přesměrujeme zpět na článek, šablona ukáže chybovou hlášku
        return redirect(url_for('main.clanek_detail', article_id=article_id,
                                _anchor='delete-error'))

    db.session.delete(article)
    db.session.commit()

    return redirect(url_for('main.index'))  # po smazání pošleme uživatele na hlavní stránku