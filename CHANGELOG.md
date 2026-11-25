# Changelog

Todas as mudanças relevantes deste projeto são documentadas neste arquivo.

## [0.5.0](https://github.com/thalesgmartins/midas/compare/v0.4.0...v0.5.0) (2026-11-25)


### Features

* **analytics:** implementar risco, correlacao, cenarios bootstrap e metas ([e9d66ab](https://github.com/thalesgmartins/midas/commit/e9d66abe0ebb2b7f4be5e4302b59c8391604fe38))
* **db:** adicionar tabela marketevent e configuracoes opcionais de alertas/IA ([f141687](https://github.com/thalesgmartins/midas/commit/f14168753f0d842ddb9dbe94a47c756ac2f7c386))
* **db:** adicionar tabela pricepoint para historico de fechamentos ([914c779](https://github.com/thalesgmartins/midas/commit/914c7793efd239b64661ccbe172e6c4605779cd9))
* **events:** implementar monitor CVM (IPE), Fundos.NET (FIIs), Telegram e Gemini opcional ([c472a92](https://github.com/thalesgmartins/midas/commit/c472a9234dc679f3d88a1d073ca687c4372055a7))
* **ui:** adicionar tela de Eventos CVM & FIIs com filtros HTMX ([c2122cd](https://github.com/thalesgmartins/midas/commit/c2122cd2e82e4253b2187282242676627254482c))
* **ui:** adicionar tela de Risco & Cenarios com projecao interativa de metas ([7285f38](https://github.com/thalesgmartins/midas/commit/7285f38af02392961099dfac943a4f92402f4b26))


### Documentation

* atualizar README e adicionar ADR 002 sobre jobs e agendador ([baa0225](https://github.com/thalesgmartins/midas/commit/baa0225060b3ce005de20a7d08a6a304b08758da))
* atualizar README para todas as 4 fases e adicionar ADR 003 ([b4fcf79](https://github.com/thalesgmartins/midas/commit/b4fcf799fc8363b3603968bbea8d5aa81050d9eb))

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
