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

    from .routes import chat as chat_routes

    app.register_blueprint(chat_routes.bp)

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
    """Add newly introduced columns to existing databases (SQLite + Postgres)."""
    from sqlalchemy import inspect, text

    dialect = db.engine.dialect.name
    with db.engine.connect() as conn:
        for table, column, ddl, pddl in [
            ("payments", "tx_ref", "VARCHAR(120)", "VARCHAR(120)"),
            ("vendors", "location_area", "VARCHAR(120)", "VARCHAR(120)"),
            ("vendors", "shop_no", "VARCHAR(40)", "VARCHAR(40)"),
            ("vendors", "phone", "VARCHAR(30)", "VARCHAR(30)"),
            ("vendors", "whatsapp", "VARCHAR(30)", "VARCHAR(30)"),
            ("vendors", "email", "VARCHAR(120)", "VARCHAR(120)"),
            ("vendors", "opening_hours", "VARCHAR(160)", "VARCHAR(160)"),
            ("vendors", "referred_by", "INTEGER", "INTEGER"),
            ("vendors", "credit", "INTEGER DEFAULT 0", "INTEGER DEFAULT 0"),
            ("products", "stock", "INTEGER", "INTEGER"),
            ("products", "discount", "INTEGER DEFAULT 0", "INTEGER DEFAULT 0"),
            ("products", "is_hidden", "BOOLEAN DEFAULT 0", "BOOLEAN DEFAULT false"),
            ("reviews", "reply", "TEXT", "TEXT"),
            ("reviews", "replied_at", "DATETIME", "TIMESTAMP"),
            ("payments", "merchant_notify", "BOOLEAN DEFAULT 0", "BOOLEAN DEFAULT false"),
            ("vendors", "flw_subaccount_id", "VARCHAR(80)", "VARCHAR(80)"),
            ("vendors", "facebook", "VARCHAR(255)", "VARCHAR(255)"),
            ("vendors", "instagram", "VARCHAR(255)", "VARCHAR(255)"),
            ("vendors", "tiktok", "VARCHAR(255)", "VARCHAR(255)"),
            ("vendors", "twitter", "VARCHAR(255)", "VARCHAR(255)"),
            ("vendors", "website", "VARCHAR(255)", "VARCHAR(255)"),
            ("orders", "qty", "INTEGER DEFAULT 1", "INTEGER DEFAULT 1"),
            ("orders", "delivery_fee", "INTEGER DEFAULT 0", "INTEGER DEFAULT 0"),
            ("orders", "customer_name", "VARCHAR(120)", "VARCHAR(120)"),
            ("orders", "customer_phone", "VARCHAR(30)", "VARCHAR(30)"),
            ("orders", "customer_email", "VARCHAR(120)", "VARCHAR(120)"),
            ("orders", "customer_address", "VARCHAR(255)", "VARCHAR(255)"),
            ("orders", "status", "VARCHAR(20) DEFAULT 'pending'", "VARCHAR(20) DEFAULT 'pending'"),
            ("orders", "tx_ref", "VARCHAR(120)", "VARCHAR(120)"),
            ("orders", "merchant_notify", "BOOLEAN DEFAULT 0", "BOOLEAN DEFAULT false"),
            ("orders", "buyer_notify", "BOOLEAN DEFAULT 0", "BOOLEAN DEFAULT false"),
            ("orders", "payment_method", "VARCHAR(20) DEFAULT 'flutterwave'", "VARCHAR(20) DEFAULT 'flutterwave'"),
            ("orders", "created_at", "DATETIME", "TIMESTAMP"),
            ("orders", "paid_at", "DATETIME", "TIMESTAMP"),
        ]:
            cols = [c["name"] for c in inspect(db.engine).get_columns(table)]
            if column not in cols:
                sql = f"ALTER TABLE {table} ADD COLUMN {column} {(pddl if dialect == 'postgresql' else ddl)}"
                conn.execute(text(sql))
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
