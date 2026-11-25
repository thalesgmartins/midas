"""Rotas de autenticação Google OAuth 2.0 (acesso exclusivo)."""

import hmac

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.core import auth, config

router = APIRouter()
templates = Jinja2Templates(directory=config.BASE_DIR / "app" / "web" / "templates")

_ERROR_MESSAGES: dict[str, str] = {
    "acesso_negado": "Esta conta Google não tem permissão para acessar este cofre.",
    "estado_invalido": "Sessão de login expirada ou inválida. Tente novamente.",
    "oauth_nao_configurado": "Configure GOOGLE_CLIENT_ID e GOOGLE_CLIENT_SECRET no .env.",
    "falha_google": "Não foi possível validar sua conta com o Google. Tente novamente.",
}


def _use_secure_cookie() -> bool:
    return config.GOOGLE_REDIRECT_URI.startswith("https://")


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request, erro: str = "") -> HTMLResponse:
    """Tela de login split-screen em Dark Mode."""
    context = {
        "error_message": _ERROR_MESSAGES.get(erro, ""),
        "oauth_configured": bool(config.GOOGLE_CLIENT_ID and config.GOOGLE_CLIENT_SECRET),
    }
    return templates.TemplateResponse(request, "login.html", context)


@router.get("/auth/google")
def auth_google_start() -> RedirectResponse:
    """Redireciona o navegador para o consentimento do Google OAuth 2.0."""
    if not (config.GOOGLE_CLIENT_ID and config.GOOGLE_CLIENT_SECRET):
        return RedirectResponse("/login?erro=oauth_nao_configurado", status_code=303)

    url, state = auth.build_google_login_url()
    response = RedirectResponse(url, status_code=303)
    response.set_cookie(
        key=auth.OAUTH_STATE_COOKIE,
        value=state,
        max_age=300,
        httponly=True,
        samesite="lax",
        secure=_use_secure_cookie(),
    )
    return response


@router.get("/auth/google/callback")
def auth_google_callback(request: Request, code: str = "", state: str = "") -> RedirectResponse:
    """Valida CSRF state, troca o código no Google e libera apenas o e-mail autorizado."""
    expected_state = request.cookies.get(auth.OAUTH_STATE_COOKIE, "")
    if (
        not code
        or not state
        or not expected_state
        or not hmac.compare_digest(expected_state, state)
    ):
        resp = RedirectResponse("/login?erro=estado_invalido", status_code=303)
        resp.delete_cookie(auth.OAUTH_STATE_COOKIE)
        return resp

    user = auth.exchange_google_code(code)
    if user is None:
        resp = RedirectResponse("/login?erro=acesso_negado", status_code=303)
        resp.delete_cookie(auth.OAUTH_STATE_COOKIE)
        resp.delete_cookie(auth.SESSION_COOKIE_NAME)
        return resp

    token = auth.create_session_token(user)
    resp = RedirectResponse("/", status_code=303)
    resp.delete_cookie(auth.OAUTH_STATE_COOKIE)
    resp.set_cookie(
        key=auth.SESSION_COOKIE_NAME,
        value=token,
        max_age=config.SESSION_MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
        secure=_use_secure_cookie(),
    )
    return resp


@router.get("/logout")
@router.post("/logout")
def logout() -> RedirectResponse:
    """Encerra a sessão removendo o cookie assinado."""
    resp = RedirectResponse("/login", status_code=303)
    resp.delete_cookie(auth.SESSION_COOKIE_NAME)
    return resp
