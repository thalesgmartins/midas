# Changelog

Todas as mudanças relevantes deste projeto são documentadas neste arquivo.

## [0.4.0](https://github.com/thalesgmartins/midas/compare/v0.3.0...v0.4.0) (2026-11-25)


### Features

* **db:** adicionar tabela watchlistasset com metricas de qualidade ([5b10ef7](https://github.com/thalesgmartins/midas/commit/5b10ef74fa674b700d19e54b0bc3bb38a9218595))
* **jobs:** paralelizar coleta, jobs em background e agendador automatico ([c099299](https://github.com/thalesgmartins/midas/commit/c099299d247ba0889af5918d9e60f45ae560b661))
* **screener:** implementar screener B3 com filtros anti-value-trap e watchlist ([2043317](https://github.com/thalesgmartins/midas/commit/2043317a056398b9ccf5f53a79c7649bddd9177c))
* **ui:** adicionar tela de Screener, progresso HTMX e horario em BRT ([cd42ac4](https://github.com/thalesgmartins/midas/commit/cd42ac4b38aceaa876f28d9c891f458409e237af))

## [0.3.0](https://github.com/thalesgmartins/midas/compare/v0.2.0...v0.3.0) (2026-11-24)


### Features

* **db:** adicionar tabela assetfundamentals e migracao 0003 ([8e21ddc](https://github.com/thalesgmartins/midas/commit/8e21ddc12b325d742828cf34d8d9a23677545e84))
* **ui:** adicionar tela de Valuation & Proventos ([6d02aa6](https://github.com/thalesgmartins/midas/commit/6d02aa6f219a7b5c408672cb5a06e438bf5b5501))
* **ui:** tornar prioridades dinamicas via HTMX OOB e melhorar leitura do plano de aporte ([685943e](https://github.com/thalesgmartins/midas/commit/685943e5d7ff48635f2df755165ec159e7439d89))
* **valuation:** implementar motor multi-metodo, coleta de fundamentos e integracao no aporte ([0361c2b](https://github.com/thalesgmartins/midas/commit/0361c2bafbdddcfc168993a9ef7ea5de691d3f81))


### Bug Fixes

* **db:** persistir valores do enum band_mode e preservar logs do uvicorn ([01dd316](https://github.com/thalesgmartins/midas/commit/01dd3169b53a08ac5998578be84f2e209e9888f6))

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
