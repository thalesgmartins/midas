"""Ponto de entrada da aplicação FastAPI."""

import asyncio
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from app.api.auth import router as auth_router
from app.api.web import router as web_router
from app.core import auth, config
from app.database.session import create_all, run_migrations
from app.services.scheduler import scheduler_loop

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

PUBLIC_PREFIXES = ("/login", "/auth/", "/logout", "/static/")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Prepara o banco e inicia o agendador automático ao subir."""
    task: asyncio.Task[None] | None = None
    if config.TESTING:
        create_all()
    else:
        run_migrations()
        task = asyncio.create_task(scheduler_loop())
    try:
        yield
    finally:
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task


app = FastAPI(title="Midas", lifespan=lifespan)


@app.middleware("http")
async def require_google_session(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Protege todas as rotas com sessão Google OAuth quando configurada."""
    path = request.url.path
    if not config.is_auth_enabled() or path.startswith(PUBLIC_PREFIXES):
        return await call_next(request)

    user = auth.verify_session_token(request.cookies.get(auth.SESSION_COOKIE_NAME))
    if user is None:
        if request.headers.get("HX-Request") == "true":
            return Response(status_code=401, headers={"HX-Redirect": "/login"})
        return RedirectResponse("/login", status_code=303)

    request.state.user = user
    return await call_next(request)


app.mount(
    "/static",
    StaticFiles(directory=config.BASE_DIR / "app" / "web" / "static"),
    name="static",
)
app.include_router(auth_router)
app.include_router(web_router)
