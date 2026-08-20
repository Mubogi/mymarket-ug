import os
import secrets as _secrets


class Config:
    # If SECRET_KEY is unset, generate a random one per boot (safe, but logs everyone
    # out on restart — set SECRET_KEY in production for stable sessions).
    SECRET_KEY = os.environ.get("SECRET_KEY") or _secrets.token_hex(32)

    # Session hardening
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    # Secure cookies in prod; off automatically for local http dev (FLASK_DEBUG=1)
    SESSION_COOKIE_SECURE = os.environ.get(
        "SESSION_COOKIE_SECURE", "0" if os.environ.get("FLASK_DEBUG") == "1" else "1"
    ) == "1"
    PERMANENT_SESSION_LIFETIME = 60 * 60 * 24 * 30  # 30 days
    WTF_CSRF_TIME_LIMIT = None  # CSRF tokens tied to session, not a clock

    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "sqlite:///mymarket.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    if SQLALCHEMY_DATABASE_URI.startswith("postgres://"):
        # Render.com provides postgres:// URLs; SQLAlchemy needs postgresql://
        SQLALCHEMY_DATABASE_URI = SQLALCHEMY_DATABASE_URI.replace(
            "postgres://", "postgresql://", 1
        )
    # On Render, set UPLOAD_FOLDER to a mounted disk path (e.g. /var/data/uploads)
    # so uploaded images survive redeploys/static restarts.
    UPLOAD_FOLDER = os.environ.get(
        "UPLOAD_FOLDER",
        os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "app", "static", "uploads"
        ),
    )
    MAX_CONTENT_LENGTH = 4 * 1024 * 1024  # 4MB uploads — hard cap against DoS
    CRON_SECRET = os.environ.get("CRON_SECRET") or _secrets.token_hex(16)
    BASE_DOMAIN = os.environ.get("BASE_DOMAIN", "mymarket.ug")
    VAPID_PUBLIC_KEY = os.environ.get("VAPID_PUBLIC_KEY", "")
    VAPID_PRIVATE_KEY = os.environ.get("VAPID_PRIVATE_KEY", "")
    VAPID_CLAIMS_EMAIL = os.environ.get("VAPID_CLAIMS_EMAIL", "admin@mymarket.ug")

    # Flutterwave (MTN MoMo / Airtel Money). Leave blank to use simulated payments.
    FLW_SECRET_KEY = os.environ.get("FLW_SECRET_KEY", "")
    FLW_PUBLIC_KEY = os.environ.get("FLW_PUBLIC_KEY", "")
    FLW_WEBHOOK_HASH = os.environ.get("FLW_WEBHOOK_HASH", "")

    # Africa's Talking SMS. Leave blank to disable.
    AT_USERNAME = os.environ.get("AT_USERNAME", "")
    AT_API_KEY = os.environ.get("AT_API_KEY", "")

    SEND_FILE_MAX_AGE_DEFAULT = 60 * 60 * 24 * 30  # 30-day static cache

    # Pricing (UGX)
    SETUP_FEE = 10_000
    SUBSCRIPTION_FEE = 5_000
    PRO_UPLOAD_FEE = 5_000
    BOOST_FEE = 5_000
    FREE_PRODUCT_LIMIT = 10
