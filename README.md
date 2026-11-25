# Midas — Copiloto Pessoal de Carteira

Ferramenta web de uso pessoal para acompanhar a carteira de investimentos, avaliar ativos por múltiplos métodos, filtrar oportunidades da B3 e apoiar decisões de aporte com regras explícitas.

## Funcionalidades

- **Dashboard Operacional (`/`):** central de decisão com faixa de sinais do dia (renda mensal, eventos CVM não lidos, patrimônio/equilíbrio), simulador rápido de aporte com atalhos (`R$ 200`, `400`, `800`, `1500`), 3 cards de prioridade dinâmicos (HTMX OOB), lista de execução com barras de progresso e botão **Registrar compras na carteira** (atualiza quantidades e preço médio automaticamente).
- **Segurança (`/login`):** autenticação exclusiva via **Google OAuth 2.0** com allowlist de e-mail (`ALLOWED_EMAILS`), cookie assinado `HttpOnly` e proteção CSRF (`state`), ativada automaticamente ao configurar `GOOGLE_CLIENT_ID` e `GOOGLE_CLIENT_SECRET` no `.env`.
- **Estatísticas (`/estatisticas`):** 4 KPIs (patrimônio total, custo vs. mercado, aderência às metas e ativos monitorados), mapa de alocação vs. meta/banda, diversificação por segmento e tabela completa com edição inline (segmento, peso, preço teto manual e status *Em revisão*).
- **Risco & Cenários (`/risco`):** volatilidade anualizada + ganho de diversificação, drawdown máximo histórico (2 anos), VaR 30 dias (95%), Beta vs. Ibovespa, cone de cenários (bootstrap 30d/90d/12m), matriz de correlação (pares colados vs. melhores diversificadores) e projeção interativa de metas de patrimônio.
- **Valuation & Proventos (`/valuation`):** preço teto multi-método (**Graham**, **Bazin/Barsi 6%**, **Peter Lynch / PEG** para ações; **P/VP = 1** e **Yield alvo 11%** para FIIs), preço teto consenso (mediana) integrado automaticamente ao motor de aporte, DY, Yield on Cost e renda mensal estimada.
- **Screener & Watchlist (`/screener`):** catálogo líquido da B3 (`brapi.dev` + universo curado BESST), pontuação objetiva (`0–100`), **filtros anti-armadilha de valor** (queda forte em 52 semanas, alavancagem alta, margem líquida baixa e distorções de P/L ou DY), cobertura de setores perenes (BESST) e Watchlist pessoal.
- **Eventos CVM & FIIs (`/eventos`):** monitor oficial da **CVM (IPE)** para ações e do **Fundos.NET (B3)** para FIIs (Fatos Relevantes, Relatórios Gerenciais, Avisos aos Acionistas, Rendimentos e Comunicados), com links diretos para os PDFs oficiais, controle de lidos, alertas opcionais via Telegram e resumo opcional por IA (Gemini).
- **Metas (`/metas`):** metas por classe com banda configurável entre **Fixa (`± p.p.`)** e **Metade / Dobro (`½×` a `2×`)**.
- **Atualizações assíncronas e agendadas:** coleta paralela em background com progresso em tempo real via polling HTMX (`GET /jobs/{nome}`) e agendador automático no startup (cotações a cada 15 min no pregão da B3; fundamentos e Screener 1× por dia após o fechamento).

## Stack

- **Backend:** Python 3.11+, FastAPI, Jinja2, SQLModel, Alembic
- **Frontend:** Dark Mode 100% local (sem CDNs) — Tailwind CSS compilado, Material Design Icons e HTMX
- **Dados:** `yfinance` (cotações, histórico 2a, fundamentos e dividendos), `brapi.dev` (catálogo líquido B3), **CVM Dados Abertos (IPE)** e **B3 Fundos.NET**
- **Banco de dados:** SQLite (`data/midas.db`), configurável via `DATABASE_URL`
- **Qualidade & CI:** Ruff, Mypy, Pytest, pre-commit, GitHub Actions (CI, GHCR multi-arch `amd64/arm64` e Release Please)

## Como executar

### Local (Python)
```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"

# Carrega data/carteira.csv (ou data/carteira_exemplo.csv se não existir)
.venv/bin/python -m app.cli seed

# Sobe a aplicação em http://127.0.0.1:8000
.venv/bin/uvicorn app.main:app --reload
```

### Docker Compose (desenvolvimento local com hot-reload)
```bash
cp .env.example .env
cp docker-compose.yml.example docker-compose.yml
cp docker-compose.override.yml.example docker-compose.override.yml
docker compose up --build
```

### Qualidade e testes
```bash
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/mypy app
.venv/bin/pytest -q
```

## Estrutura do repositório

```text
app/
├── api/          # Rotas web (HTML, fragmentos HTMX e polling de jobs)
├── core/         # Configurações (.env)
├── database/     # Modelos SQLModel e sessão/migrações
├── services/     # Rebalanceamento, valuation, screener, catálogo B3, jobs e agendador
├── web/          # Templates Jinja2 e estáticos locais (Tailwind, MDI, HTMX)
├── cli.py        # Comandos CLI (seed)
└── main.py       # Entrypoint FastAPI + lifespan do agendador
alembic/          # Migrações de banco (0001 a 0007)
data/             # Carteira local (ignorado no git, exceto carteira_exemplo.csv)
docs/             # ADRs e documentação técnica
tests/            # Testes unitários e de integração
```

## Roadmap

- **Fase 1 (concluída):** Carteira, importação CSV, metas com banda (`± p.p.` e `metade/dobro`), edição inline, simulador de aporte, cotações e interface Dark Mode local.
- **Fase 2 (concluída):** Valuation multi-método (Graham, Bazin, Lynch/PEG, FIIs), dividendos/YoC, Screener B3 com filtros anti-value-trap, Watchlist, jobs em background e agendador automático.
- **Fase 3 (concluída):** Monitor de fatos relevantes (CVM IPE para ações + B3 Fundos.NET para FIIs) com links oficiais, controle de lidos, alertas opcionais no Telegram e resumo opcional por IA (Gemini).
- **Fase 4 (concluída):** Estatística e risco (volatilidade, drawdown, VaR, Beta vs. IBOV, matriz de correlação, cone de cenários bootstrap e projeção de metas).
