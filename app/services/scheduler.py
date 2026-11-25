"""Agendador leve em segundo plano para cotações (15 min no pregão) e rotina diária."""

import asyncio
import logging
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlmodel import Session

from app.services import fundamentals, jobs, quotes, screener

logger = logging.getLogger(__name__)

BRT = ZoneInfo("America/Sao_Paulo")
QUOTES_INTERVAL_MINUTES = 15


def is_b3_trading_hours(now: datetime) -> bool:
    """Retorna True durante o pregão da B3 (seg-sex, 10:00 às 18:30 BRT)."""
    local = now.astimezone(BRT)
    if local.weekday() >= 5:
        return False
    minutes = local.hour * 60 + local.minute
    return (10 * 60) <= minutes <= (18 * 60 + 30)


def run_quotes_job(session: Session, on_progress: jobs.ProgressCallback) -> str:
    """Executa a atualização de cotações da carteira."""
    updated, failed = quotes.update_quotes(session)
    on_progress(updated, updated + len(failed))
    msg = f"{updated} cotações atualizadas."
    return f"{msg} Falharam: {len(failed)}" if failed else msg


def run_fundamentals_job(session: Session, on_progress: jobs.ProgressCallback) -> str:
    """Executa a coleta paralela de fundamentos e dividendos da carteira."""
    updated, failed = fundamentals.update_fundamentals(session, on_progress=on_progress)
    msg = f"{updated} fundamentos atualizados."
    return f"{msg} Falharam: {len(failed)}" if failed else msg


def run_screener_job(session: Session, on_progress: jobs.ProgressCallback) -> str:
    """Sincroniza ativos líquidos da B3 e avalia o universo do Screener em paralelo."""
    added = screener.sync_b3_universe(session)
    updated, failed = screener.update_screener_data(session, on_progress=on_progress)
    msg = f"{updated} ativos avaliados"
    if added:
        msg += f" (+{added} novos da B3)"
    return f"{msg}. Falharam: {len(failed)}" if failed else f"{msg}."


async def scheduler_loop() -> None:
    """Loop periódico iniciado no lifespan do FastAPI."""
    last_quotes_slot: tuple[date, int] | None = None
    last_daily_fundamentals: date | None = None
    last_daily_screener: date | None = None

    logger.info("Agendador automático do Midas iniciado (cotações a cada 15 min no pregão).")
    # Aguarda 2 min após o startup para não disparar coletas pesadas em restarts rápidos
    await asyncio.sleep(120)
    while True:
        try:
            now = datetime.now(BRT)
            today = now.date()

            if is_b3_trading_hours(now):
                slot = (today, (now.hour * 60 + now.minute) // QUOTES_INTERVAL_MINUTES)
                if slot != last_quotes_slot:
                    last_quotes_slot = slot
                    jobs.trigger("quotes", run_quotes_job, "Atualização automática de cotações...")

            if now.weekday() < 5 and now.hour >= 19:
                if last_daily_fundamentals != today:
                    last_daily_fundamentals = today
                    jobs.trigger(
                        "fundamentals",
                        run_fundamentals_job,
                        "Atualização diária de fundamentos...",
                    )
                if now.minute >= 15 and last_daily_screener != today:
                    last_daily_screener = today
                    jobs.trigger(
                        "screener",
                        run_screener_job,
                        "Atualização diária do Screener B3...",
                    )
        except Exception:
            logger.exception("Erro no ciclo do agendador automático")

        await asyncio.sleep(60)
