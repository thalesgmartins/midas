"""Configuração global dos testes (SQLite em memória)."""

import os

os.environ["TESTING"] = "1"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from collections.abc import Generator

import pytest
from sqlmodel import Session, SQLModel

from app.database.session import create_all, engine

create_all()


@pytest.fixture(autouse=True)
def clean_database() -> Generator[None, None, None]:
    """Limpa todas as tabelas após cada teste para manter isolamento."""
    yield
    with Session(engine) as session:
        for table in reversed(SQLModel.metadata.sorted_tables):
            session.exec(table.delete())  # type: ignore[call-overload]
        session.commit()
