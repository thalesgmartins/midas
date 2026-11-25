"""Autenticação de sessão assinada (HMAC-SHA256) e fluxo Google OAuth 2.0."""

import base64
import hashlib
import hmac
import json
import logging
import secrets
import time
from dataclasses import dataclass
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.core import config

logger = logging.getLogger(__name__)

SESSION_COOKIE_NAME = "midas_session"
OAUTH_STATE_COOKIE = "midas_oauth_state"

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"


@dataclass
class SessionUser:
    """Usuário autenticado extraído do cookie de sessão."""

    email: str
    name: str
    picture: str = ""


def _sign(payload_b64: str) -> str:
    digest = hmac.new(
        config.SECRET_KEY.encode("utf-8"),
        payload_b64.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def create_session_token(user: SessionUser) -> str:
    """Cria token assinado contendo e-mail, nome e expiração."""
    payload = {
        "email": user.email.lower(),
        "name": user.name,
        "picture": user.picture,
        "exp": int(time.time()) + config.SESSION_MAX_AGE_SECONDS,
    }
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    b64 = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    return f"{b64}.{_sign(b64)}"


def verify_session_token(token: str | None) -> SessionUser | None:
    """Valida assinatura, expiração e allowlist de e-mail do token de sessão."""
    if not token or "." not in token:
        return None
    b64, sig = token.split(".", 1)
    if not hmac.compare_digest(_sign(b64), sig):
        return None
    try:
        padded = b64 + "=" * (-len(b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
    except (ValueError, KeyError):
        return None

    exp = int(payload.get("exp") or 0)
    if exp < int(time.time()):
        return None

    email = str(payload.get("email") or "").strip().lower()
    if not email or email not in config.ALLOWED_EMAILS:
        return None

    return SessionUser(
        email=email,
        name=str(payload.get("name") or email.split("@")[0]),
        picture=str(payload.get("picture") or ""),
    )


def build_google_login_url() -> tuple[str, str]:
    """Gera a URL de redirecionamento do Google OAuth 2.0 e o token CSRF ``state``."""
    state = secrets.token_urlsafe(24)
    params = urlencode(
        {
            "client_id": config.GOOGLE_CLIENT_ID,
            "redirect_uri": config.GOOGLE_REDIRECT_URI,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "prompt": "select_account",
        }
    )
    return f"{GOOGLE_AUTH_URL}?{params}", state


def exchange_google_code(code: str) -> SessionUser | None:
    """Troca o ``code`` do Google por ``access_token`` e valida o perfil autorizado."""
    body = urlencode(
        {
            "code": code,
            "client_id": config.GOOGLE_CLIENT_ID,
            "client_secret": config.GOOGLE_CLIENT_SECRET,
            "redirect_uri": config.GOOGLE_REDIRECT_URI,
            "grant_type": "authorization_code",
        }
    ).encode("utf-8")
    token_req = Request(
        GOOGLE_TOKEN_URL,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urlopen(token_req, timeout=15) as resp:  # noqa: S310
            token_data = json.loads(resp.read().decode("utf-8"))
        access_token = token_data.get("access_token")
        if not access_token:
            return None

        user_req = Request(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        with urlopen(user_req, timeout=15) as resp:  # noqa: S310
            profile = json.loads(resp.read().decode("utf-8"))
    except (URLError, TimeoutError, ValueError, OSError):
        logger.error("Falha na troca de token com o Google OAuth.")
        return None

    email = str(profile.get("email") or "").strip().lower()
    verified = bool(profile.get("email_verified"))
    if not verified or email not in config.ALLOWED_EMAILS:
        logger.warning("Tentativa de acesso bloqueada para e-mail não autorizado.")
        return None

    return SessionUser(
        email=email,
        name=str(profile.get("name") or email.split("@")[0]),
        picture=str(profile.get("picture") or ""),
    )
