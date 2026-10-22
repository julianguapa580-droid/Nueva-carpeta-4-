import os
from flask import Flask, render_template
from config import Config
from .extensions import db, login_manager, csrf, limiter


def create_app(config_class=Config):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_class)
    os.makedirs(app.instance_path, exist_ok=True)

    db.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Inicia sesión para continuar."
    login_manager.login_message_category = "warning"
    login_manager.session_protection = "strong"

    from .blueprints.auth import bp as auth_bp
    from .blueprints.main import bp as main_bp
    from .blueprints.activities import bp as act_bp
    from .blueprints.admin import bp as admin_bp
    from .blueprints.reports import bp as reports_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(act_bp, url_prefix="/actividades")
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(reports_bp, url_prefix="/reportes")

    from . import cli
    cli.register(app)

    @app.errorhandler(403)
    def e403(e):
        return render_template("errors/error.html", code=403,
                               message="No tienes permisos para esta sección."), 403

    @app.errorhandler(404)
    def e404(e):
        return render_template("errors/error.html", code=404,
                               message="La página solicitada no existe."), 404

    @app.errorhandler(429)
    def e429(e):
        return render_template("errors/error.html", code=429,
                               message="Demasiados intentos. Espera un momento."), 429

    with app.app_context():
        from . import models  # noqa: F401
        db.create_all()

    return app