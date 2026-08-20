from flask import Flask, redirect, render_template, request
from werkzeug.middleware.proxy_fix import ProxyFix

from config import Config

from .extensions import csrf, db, limiter, login_manager
from .models import User


def create_app(config_object=Config):
    app = Flask(__name__)
    app.config.from_object(config_object)
    # Trust Render's proxy so rate limiting and is_secure see the real client
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    from .routes import main, vendor, admin, cron, payments

    app.register_blueprint(main.bp)
    app.register_blueprint(vendor.bp)
    app.register_blueprint(admin.bp)
    app.register_blueprint(cron.bp)
    app.register_blueprint(payments.bp)

    # Machine-to-machine endpoints verified by secrets, not cookies: no CSRF needed
    csrf.exempt(cron.bp)
    csrf.exempt(payments.bp)

    from .utils import ugx

    app.jinja_env.filters["ugx"] = ugx

    @app.template_global()
    def app_name():
        return "MyMarket.ug"

    @app.after_request
    def security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Permissions-Policy", "camera=(), microphone=(), geolocation=()"
        )
        if request.is_secure:
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.tailwindcss.com; "
            "img-src 'self' data: https:; "
            "font-src 'self' data:; "
            "connect-src 'self'; "
            "form-action 'self' https://checkout.flutterwave.com; "
            "frame-ancestors 'self'; base-uri 'self'",
        )
        return response

    @app.errorhandler(403)
    def forbidden(_):
        return render_template("error.html", code=403, message="You don't have access to this page."), 403

    @app.errorhandler(404)
    def not_found(_):
        return render_template("error.html", code=404, message="Page not found."), 404

    @app.errorhandler(429)
    def too_many(_):
        return render_template("error.html", code=429, message="Too many attempts. Please wait a moment and try again."), 429

    @app.errorhandler(500)
    def server_error(_):
        return render_template("error.html", code=500, message="Something went wrong on our side. Please try again."), 500

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
