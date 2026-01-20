from flask import Flask
from models import db

from admin_routes import admin_bp

def create_admin_app():
    app = Flask(__name__)

    # 🔑 STEJNÝ SECRET KEY jako v app.py
    app.config['SECRET_KEY'] = 'tajny_klic'

    # 🛢 STEJNÁ DB jako hlavní aplikace
    app.config['SQLALCHEMY_DATABASE_URI'] = (
        "mysql+pymysql://student11:spsnet@dbs.spskladno.cz:3306/vyuka11"
    )
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    db.init_app(app)

    app.register_blueprint(admin_bp)

    return app


app = create_admin_app()

if __name__ == '__main__':
    # admin app běží separátně
    app.run(host='127.0.0.1', port=5001, debug=True)
