"""Ponto de entrada da aplicação FastAPI."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.web import router
from app.core.config import BASE_DIR, TESTING
from app.database.session import create_all, run_migrations

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Prepara o banco ao iniciar."""
    if TESTING:
        create_all()
    else:
        run_migrations()
    yield


app = FastAPI(title="Midas", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=BASE_DIR / "app" / "web" / "static"), name="static")
app.include_router(router)
