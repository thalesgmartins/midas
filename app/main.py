"""Ponto de entrada da aplicação FastAPI."""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.web import router
from app.core.config import BASE_DIR, TESTING
from app.database.session import create_all, run_migrations
from app.services.scheduler import scheduler_loop

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Prepara o banco e inicia o agendador automático ao subir."""
    task: asyncio.Task[None] | None = None
    if TESTING:
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
app.mount("/static", StaticFiles(directory=BASE_DIR / "app" / "web" / "static"), name="static")
app.include_router(router)
