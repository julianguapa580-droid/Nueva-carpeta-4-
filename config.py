import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
INSTANCE_DIR = os.path.join(BASE_DIR, "instance")
os.makedirs(INSTANCE_DIR, exist_ok=True)


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-insecure-change-me")

    _db_url = os.getenv("DATABASE_URL", "sqlite:///" + os.path.join(INSTANCE_DIR, "practicas.db"))
    # Render entrega URLs "postgres://", SQLAlchemy necesita "postgresql://"
    if _db_url.startswith("postgres://"):
        _db_url = _db_url.replace("postgres://", "postgresql://", 1)
    SQLALCHEMY_DATABASE_URI = _db_url
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}

    # --- Sesión / cookies ---
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.getenv("COOKIE_SECURE", "0") == "1"
    REMEMBER_COOKIE_HTTPONLY = True
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)

    # --- CSRF / subidas ---
    WTF_CSRF_TIME_LIMIT = None
    MAX_CONTENT_LENGTH = 8 * 1024 * 1024

    # --- Reglas de negocio ---
    LOGIN_MAX_ATTEMPTS = 5
    LOGIN_LOCK_MINUTES = 15
    PASSWORD_MIN_LENGTH = 10
    ITEMS_PER_PAGE = 15
    DEFAULT_TARGET_HOURS = 400