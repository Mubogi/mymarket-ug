import os


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key")
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "sqlite:///mymarket.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    if SQLALCHEMY_DATABASE_URI.startswith("postgres://"):
        # Render.com provides postgres:// URLs; SQLAlchemy needs postgresql://
        SQLALCHEMY_DATABASE_URI = SQLALCHEMY_DATABASE_URI.replace(
            "postgres://", "postgresql://", 1
        )
    UPLOAD_FOLDER = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "app", "static", "uploads"
    )
    MAX_CONTENT_LENGTH = 4 * 1024 * 1024  # 4MB uploads
    CRON_SECRET = os.environ.get("CRON_SECRET", "cron-secret")
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
