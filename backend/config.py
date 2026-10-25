"""Application settings, read once from the environment (and backend/.env)."""
import os
import secrets
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _load_secret_key() -> str:
    """Use SECRET_KEY if set, otherwise create and reuse a local key file."""
    key = os.getenv("SECRET_KEY")
    if key:
        return key
    path = BASE_DIR / ".secret_key"
    if path.exists():
        return path.read_text().strip()
    key = secrets.token_urlsafe(48)
    path.write_text(key)
    try:
        path.chmod(0o600)
    except OSError:  # e.g. Windows
        pass
    return key


def _database_url() -> str:
    """SQLite by default. Accepts postgres:// and postgresql:// and maps them to the psycopg 3 driver."""
    url = os.getenv("DATABASE_URL") or f"sqlite:///{BASE_DIR / 'acehill.db'}"
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


DATABASE_URL = _database_url()
SECRET_KEY = _load_secret_key()
TOKEN_TTL_MINUTES = int(os.getenv("TOKEN_TTL_MINUTES", "720"))  # 12 hours
SETUP_KEY = os.getenv("SETUP_KEY", "")
SHOP_TIMEZONE = os.getenv("SHOP_TIMEZONE", "Africa/Nairobi")
ALLOWED_ORIGINS = [
    o.strip()
    for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
    if o.strip()
]

AT_USERNAME = os.getenv("AT_USERNAME", "sandbox")
AT_API_KEY = os.getenv("AT_API_KEY", "")
AT_SENDER_ID = os.getenv("AT_SENDER_ID") or None
