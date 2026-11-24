# Midas — Copiloto Pessoal de Carteira

Ferramenta web de uso pessoal para acompanhar a carteira de investimentos e apoiar decisões de aporte com regras explícitas, metas por classe/segmento e análise baseada em dados.

## Stack

- **Backend:** Python 3.11+, FastAPI, Jinja2, SQLModel, Alembic
- **Frontend:** HTMX (vendored em `app/web/static/js/htmx.min.js`) + Tailwind CSS
- **Banco de dados:** SQLite por padrão (`data/midas.db`), configurável via `DATABASE_URL`
- **Qualidade & CI:** Ruff, Mypy, Pytest, pre-commit, GitHub Actions (CI, GHCR e Release Please)

## Como executar

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"

# Carrega data/carteira.csv (ou data/carteira_exemplo.csv se não existir)
.venv/bin/python -m app.cli seed

# Sobe a aplicação em http://127.0.0.1:8000
.venv/bin/uvicorn app.main:app --reload
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
├── api/          # Rotas web (HTML + fragmentos HTMX)
├── core/         # Configurações (.env)
├── database/     # Modelos SQLModel e sessão/migrações
├── services/     # Motor de aporte, importador CSV, cotações, agregações
├── web/          # Templates Jinja2 e estáticos (HTMX)
├── cli.py        # Comandos CLI (seed)
└── main.py       # Entrypoint FastAPI
alembic/          # Migrações de banco
data/             # Carteira local (ignorado no git, exceto carteira_exemplo.csv)
docs/             # ADRs e documentação técnica
tests/            # Testes unitários e de integração
```

## Roadmap

- **Fase 1 (atual):** Carteira, importação CSV, metas com banda de tolerância, edição inline (segmento, peso, preço teto, status *Em revisão*), simulador de aporte com justificativa e atualização de cotações.
- **Fase 2:** Preço teto multi-método (Graham, Bazin, Lynch, Buffett/DDM, FIIs vs NTN-B) e screener com dados oficiais da CVM.
- **Fase 3:** Monitor de fatos relevantes (CVM IPE) com resumo via LLM e alertas.
- **Fase 4:** Estatística e risco (volatilidade, drawdown, cenários, event study e backtest).
