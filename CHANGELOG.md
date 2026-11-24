# Changelog

Todas as mudanças relevantes deste projeto são documentadas neste arquivo.

## [0.2.0](https://github.com/thalesgmartins/midas/compare/v0.1.0...v0.2.0) (2026-11-24)


### Features

* **rebalance:** adicionar modo de banda metade/dobro por classe ([fc8d60f](https://github.com/thalesgmartins/midas/commit/fc8d60feb6c13f725f1f41c798b82ab7d4ab1096))
* **ui:** redesenhar interface em Dark Mode com sidebar e visao analitica ([d8a9294](https://github.com/thalesgmartins/midas/commit/d8a9294bbba8d5eb447cba863daa1ca2675a76b6))


### Bug Fixes

* **quotes:** usar datetime com timezone UTC ao salvar cotacoes ([cd91ccf](https://github.com/thalesgmartins/midas/commit/cd91ccf6e43880f9947d9d4730af41f1aeecc752))

## 0.1.0 (2026-11-24)


### Features

* estrutura inicial do Midas (Fase 1) ([7b11f67](https://github.com/thalesgmartins/midas/commit/7b11f67a3e55b5de8f043aed3fa82b4eb47f5b89))

## [0.1.0] - 2026-11-24

### Added
- Estrutura inicial FastAPI + Jinja2 + HTMX + Tailwind + SQLite (SQLModel + Alembic).
- Importação de carteira via CSV (`;`, formato pt-BR) e CLI (`python -m app.cli seed`).
- Dashboard por classe, metas com banda de tolerância e diversificação por segmento.
- Motor de aporte com preço teto manual, peso por ativo e status "Em revisão".
- Atualização de cotações via yfinance.
- Workflows de CI (Ruff + Mypy + Pytest), Docker (GHCR) e Release Please.
