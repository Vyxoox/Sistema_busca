from flask import Flask
from .extensions import db, login_manager, csrf

def create_app():
    app = Flask(__name__)
    #app.config.from_object(Config)

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)

    from routes.planilha import planilha_bp
    app.register_blueprint(planilha_bp)

    return app
