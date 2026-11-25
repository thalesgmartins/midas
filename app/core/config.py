"""Configurações centrais da aplicação."""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = Path(os.getenv("DATA_DIR", str(BASE_DIR / "data")))
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR / 'midas.db'}")
TESTING = os.getenv("TESTING") == "1"

# Autenticação Google OAuth 2.0 (acesso exclusivo por allowlist de e-mail)
SECRET_KEY = os.getenv("SECRET_KEY", "midas-dev-secret-change-in-production")
SESSION_MAX_AGE_SECONDS = int(os.getenv("SESSION_MAX_AGE_SECONDS", str(60 * 60 * 24 * 7)))
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI = os.getenv(
    "GOOGLE_REDIRECT_URI",
    "http://localhost:8001/auth/google/callback",
)
ALLOWED_EMAILS: set[str] = {
    email.strip().lower()
    for email in os.getenv("ALLOWED_EMAILS", "thalesdiniz30@gmail.com").split(",")
    if email.strip()
}

# Integrações opcionais da Fase 3 (Monitor CVM)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")


def is_auth_enabled() -> bool:
    """Ativa a exigência de login quando as credenciais Google OAuth estão configuradas."""
    return bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET) and not TESTING
