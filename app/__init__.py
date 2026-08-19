from flask import Flask, redirect, request

from config import Config

from .extensions import db, login_manager
from .models import User


def create_app(config_object=Config):
    app = Flask(__name__)
    app.config.from_object(config_object)

    db.init_app(app)
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    from .routes import main, vendor, admin, cron

    app.register_blueprint(main.bp)
    app.register_blueprint(vendor.bp)
    app.register_blueprint(admin.bp)
    app.register_blueprint(cron.bp)

    from .utils import ugx

    app.jinja_env.filters["ugx"] = ugx

    @app.template_global()
    def app_name():
        return "MyMarket.ug"

    with app.app_context():
        db.create_all()
        _ensure_admin()

    return app


def _ensure_admin():
    """Create the default admin user once (change password after first login!)."""
    import os

    email = os.environ.get("ADMIN_EMAIL", "admin@mymarket.ug").lower()
    password = os.environ.get("ADMIN_PASSWORD", "admin123")
    if not User.query.filter_by(email=email).first():
        u = User(name="Admin", phone="0700000000", email=email, role="admin")
        u.set_password(password)
        db.session.add(u)
        db.session.commit()
