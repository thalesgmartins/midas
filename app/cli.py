"""Linha de comando do Midas.

Uso:
    python -m app.cli seed [arquivo.csv]
"""

import argparse
import logging
from pathlib import Path

from sqlmodel import Session

from app.core.config import DATA_DIR
from app.database.session import engine, run_migrations
from app.services.importer import import_portfolio_csv

logger = logging.getLogger(__name__)


def seed(csv_path: Path) -> int:
    """Aplica as migrações e importa a carteira a partir de um CSV.

    Args:
        csv_path: Caminho do CSV no formato da planilha.

    Returns:
        Número de ativos importados.

    Raises:
        FileNotFoundError: Se o arquivo não existir.
    """
    run_migrations()
    with Session(engine) as session:
        return import_portfolio_csv(session, csv_path.read_text(encoding="utf-8"))


def main() -> None:
    """Interpreta os argumentos e executa o comando."""
    parser = argparse.ArgumentParser(prog="midas")
    commands = parser.add_subparsers(dest="command", required=True)
    seed_cmd = commands.add_parser("seed", help="importa a carteira de um CSV")
    seed_cmd.add_argument("arquivo", nargs="?", type=Path)
    args = parser.parse_args()

    if args.command == "seed":
        default = DATA_DIR / "carteira.csv"
        path = args.arquivo or (default if default.exists() else DATA_DIR / "carteira_exemplo.csv")
        logging.basicConfig(level=logging.INFO)
        logger.info("%d ativos importados de %s", seed(path), path)


if __name__ == "__main__":
    main()
