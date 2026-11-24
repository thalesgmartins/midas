"""Engine, sessões e migrações do banco de dados."""

from collections.abc import Iterator

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.core.config import BASE_DIR, DATA_DIR, DATABASE_URL


def _build_engine():
    if DATABASE_URL.startswith("sqlite"):
        if ":memory:" in DATABASE_URL:
            return create_engine(
                DATABASE_URL,
                connect_args={"check_same_thread": False},
                poolclass=StaticPool,
            )
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        return create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
    return create_engine(DATABASE_URL)


engine = _build_engine()


def create_all() -> None:
    """Cria as tabelas direto pelos modelos (usado nos testes)."""
    from app.database import models  # noqa: F401

    SQLModel.metadata.create_all(engine)


def run_migrations() -> None:
    """Aplica as migrações pendentes do Alembic (``alembic upgrade head``)."""
    from alembic import command
    from alembic.config import Config

    command.upgrade(Config(str(BASE_DIR / "alembic.ini")), "head")


def get_session() -> Iterator[Session]:
    """Dependência do FastAPI que fornece uma sessão por requisição."""
    with Session(engine) as session:
        yield session
