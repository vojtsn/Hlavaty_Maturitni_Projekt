from flask import Flask
from models import db, Category

from main_routes import main_bp
from auth_routes import auth_bp
from api_routes import api_bp

def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'tajny_klic'

    app.config['SQLALCHEMY_DATABASE_URI'] = "mysql+pymysql://student11:spsnet@dbs.spskladno.cz:3306/vyuka11"
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    db.init_app(app)

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(api_bp)

    @app.context_processor
    def inject_categories():
        from datetime import datetime as _dt
        try:
            cats = Category.query.order_by(Category.name.asc()).all()
        except Exception:
            cats = []
        return dict(categories=cats, now=_dt.utcnow)

    import re as _re
    def highlight_filter(text, query):
        if not text or not query:
            return text
        escaped = _re.escape(query)
        return _re.sub(f'({escaped})', r'<mark>\1</mark>', str(text), flags=_re.IGNORECASE)

    app.jinja_env.filters['highlight'] = highlight_filter

    import markdown as _md
    def markdown_filter(text):
        if not text:
            return ''
        return _md.markdown(text, extensions=['nl2br', 'tables', 'fenced_code'])

    app.jinja_env.filters['markdown'] = markdown_filter

    return app

app = create_app()

if __name__ == '__main__':
    app.run(debug=True)