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

    from .routes import main, vendor, admin, cron, payments

    app.register_blueprint(main.bp)
    app.register_blueprint(vendor.bp)
    app.register_blueprint(admin.bp)
    app.register_blueprint(cron.bp)
    app.register_blueprint(payments.bp)

    from .utils import ugx

    app.jinja_env.filters["ugx"] = ugx

    @app.template_global()
    def app_name():
        return "MyMarket.ug"

    with app.app_context():
        db.create_all()
        _auto_migrate(app)
        _ensure_admin()

    return app


def _auto_migrate(app):
    """Add newly introduced columns to existing SQLite databases."""
    from sqlalchemy import inspect, text

    with db.engine.connect() as conn:
        for table, column, ddl in [
            ("payments", "tx_ref", "VARCHAR(120)"),
            ("vendors", "location_area", "VARCHAR(120)"),
            ("vendors", "shop_no", "VARCHAR(40)"),
        ]:
            if column not in [c["name"] for c in inspect(db.engine).get_columns(table)]:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
                conn.commit()


def _ensure_admin():
    """Create the admin user once; keeps the password synced with ADMIN_PASSWORD env
    so you can always log in by setting/resetting that variable and redeploying."""
    import os

    email = os.environ.get("ADMIN_EMAIL", "admin@mymarket.ug").lower()
    password = os.environ.get("ADMIN_PASSWORD", "admin123")
    admin = User.query.filter_by(email=email).first()
    if not admin:
        admin = User(name="Admin", phone="0700000000", email=email, role="admin")
        db.session.add(admin)
    if not admin.password_hash or not admin.check_password(password):
        admin.set_password(password)
    db.session.commit()
