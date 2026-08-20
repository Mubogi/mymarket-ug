from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect

db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = "vendor.login"
login_manager.login_message = "Please log in to continue."
csrf = CSRFProtect()
limiter = Limiter(key_func=get_remote_address)
