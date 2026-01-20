from flask import Flask
from models import db

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

    return app

app = create_app()

if __name__ == '__main__':
    app.run(debug=True)
