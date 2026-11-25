# ADR 002: Jobs em background com ThreadPoolExecutor e agendador in-process

## Status
Aprovado

## Contexto
As rotinas de atualização de cotações, fundamentos e Screener (até ~90 tickers da B3) realizam dezenas de chamadas HTTP externas. Executá-las de forma síncrona na requisição HTTP travava a interface por dezenas de segundos e expunha o navegador a timeouts.

Por outro lado, o Midas roda em uso pessoal com `replicas: 1` (SQLite local em um nó ARM64). Introduzir Redis + Celery aumentaria o consumo de memória e a complexidade operacional sem ganho real.

## Decisão
- **Registro de jobs em memória (`app/services/jobs.py`):** executa cada rotina em thread daemon com sessão própria do SQLModel, impede disparos concorrentes do mesmo job e expõe progresso ao vivo via `GET /jobs/{nome}` (polling HTMX a cada 2s).
- **Paralelismo controlado (`ThreadPoolExecutor`):** coleta de rede em até 3 workers com timeout global de lote (`90s`) e `shutdown(wait=False, cancel_futures=True)` para nunca travar em sockets pendurados; a escrita no SQLite permanece sequencial no final para evitar lock de escrita.
- **Agendador in-process (`app/services/scheduler.py`):** loop `asyncio` iniciado no `lifespan` do FastAPI (desativado em `TESTING=1`), disparando cotações a cada 15 min no pregão (10h–18h30 BRT) e fundamentos/Screener 1× por dia após as 19h.

## Consequências
- **Positivas:** zero infraestrutura extra, resposta imediata na UI (`< 50ms`), uso mínimo de RAM em `arm64`.
- **Negativas:** o estado de progresso de um job em andamento não sobrevive a um restart do container (aceitável, pois o job é idempotente e pode ser reexecutado).
