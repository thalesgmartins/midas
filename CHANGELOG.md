# Changelog

Todas as mudanças relevantes deste projeto são documentadas neste arquivo.

## [0.1.0] - 2026-11-24

### Added
- Estrutura inicial FastAPI + Jinja2 + HTMX + Tailwind + SQLite (SQLModel + Alembic).
- Importação de carteira via CSV (`;`, formato pt-BR) e CLI (`python -m app.cli seed`).
- Dashboard por classe, metas com banda de tolerância e diversificação por segmento.
- Motor de aporte com preço teto manual, peso por ativo e status "Em revisão".
- Atualização de cotações via yfinance.
- Workflows de CI (Ruff + Mypy + Pytest), Docker (GHCR) e Release Please.
