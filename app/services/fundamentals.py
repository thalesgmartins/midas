"""Coleta paralela de indicadores fundamentalistas e histórico de proventos via yfinance."""

import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from concurrent.futures import TimeoutError as FuturesTimeoutError
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlmodel import Session, select

from app.database.models import Asset, AssetFundamentals

logger = logging.getLogger(__name__)

MAX_WORKERS = 3
BATCH_TIMEOUT_SECONDS = 90


@dataclass
class TickerSnapshot:
    """Dados coletados de um ticker fora da sessão do banco."""

    ticker: str
    price: float | None
    lpa: float | None
    vpa: float | None
    pl: float | None
    pvp: float | None
    roe: float | None
    payout: float | None
    div_12m: float | None
    div_avg_5y: float | None
    profit_margin: float | None = None
    debt_to_equity: float | None = None
    drawdown_52w: float | None = None


def _to_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        num = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return num if num == num else None  # descarta NaN


def _dividend_metrics(dividends: object) -> tuple[float | None, float | None]:
    """Calcula proventos dos últimos 12 meses e média anual (até 5 anos)."""
    if dividends is None or getattr(dividends, "empty", True):
        return None, None
    now = datetime.now(UTC)
    cutoff_12m = now - timedelta(days=365)
    cutoff_5y = now - timedelta(days=365 * 5)

    total_12m = 0.0
    by_year: dict[int, float] = {}
    for ts, amount in dividends.items():  # type: ignore[attr-defined]
        dt = ts.to_pydatetime()
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        val = _to_float(amount)
        if val is None or val <= 0:
            continue
        if dt >= cutoff_12m:
            total_12m += val
        if dt >= cutoff_5y:
            by_year[dt.year] = by_year.get(dt.year, 0.0) + val

    div_12m = round(total_12m, 4) if total_12m > 0 else None
    div_avg_5y = round(sum(by_year.values()) / len(by_year), 4) if by_year else None
    return div_12m, div_avg_5y


def fetch_ticker_snapshot(ticker: str) -> TickerSnapshot:
    """Busca preço, indicadores e dividendos de um único ticker na B3."""
    import yfinance as yf

    ticker_obj = yf.Ticker(f"{ticker}.SA")
    info = ticker_obj.info or {}
    div_12m, div_avg_5y = _dividend_metrics(ticker_obj.dividends)
    price = _to_float(info.get("currentPrice") or info.get("regularMarketPrice"))
    high_52w = _to_float(info.get("fiftyTwoWeekHigh"))
    drawdown_52w = (
        round((price / high_52w - 1.0) * 100.0, 1)
        if price is not None and high_52w is not None and high_52w > 0
        else None
    )
    return TickerSnapshot(
        ticker=ticker,
        price=round(price, 2) if price is not None and price > 0 else None,
        lpa=_to_float(info.get("trailingEps")),
        vpa=_to_float(info.get("bookValue")),
        pl=_to_float(info.get("trailingPE")),
        pvp=_to_float(info.get("priceToBook")),
        roe=_to_float(info.get("returnOnEquity")),
        payout=_to_float(info.get("payoutRatio")),
        div_12m=div_12m,
        div_avg_5y=div_avg_5y,
        profit_margin=_to_float(info.get("profitMargins")),
        debt_to_equity=_to_float(info.get("debtToEquity")),
        drawdown_52w=drawdown_52w,
    )


def fetch_many_snapshots(
    tickers: list[str],
    on_progress: Callable[[int, int], None] | None = None,
    max_workers: int = MAX_WORKERS,
) -> tuple[dict[str, TickerSnapshot], list[str]]:
    """Coleta snapshots de múltiplos tickers em paralelo.

    Args:
        tickers: Lista de tickers (sem sufixo ``.SA``).
        on_progress: Callback opcional ``(concluidos, total)``.
        max_workers: Número máximo de threads concorrentes.

    Returns:
        Dicionário ``ticker -> TickerSnapshot`` e lista de tickers que falharam.
    """
    total = len(tickers)
    if total == 0:
        return {}, []

    results: dict[str, TickerSnapshot] = {}
    failed: list[str] = []
    done = 0

    pool = ThreadPoolExecutor(max_workers=min(max_workers, total))
    futures = {pool.submit(fetch_ticker_snapshot, t): t for t in tickers}
    try:
        for future in as_completed(futures, timeout=BATCH_TIMEOUT_SECONDS):
            ticker = futures[future]
            try:
                results[ticker] = future.result(timeout=1)
            except Exception:
                logger.warning("Falha ao coletar fundamentos de %s", ticker)
                failed.append(ticker)
            done += 1
            if on_progress is not None:
                on_progress(done, total)
    except FuturesTimeoutError:
        for future, ticker in futures.items():
            if not future.done():
                failed.append(ticker)
                done += 1
        logger.warning(
            "Timeout após %ds; %d tickers não responderam.", BATCH_TIMEOUT_SECONDS, len(failed)
        )
        if on_progress is not None:
            on_progress(total, total)
    finally:
        pool.shutdown(wait=False, cancel_futures=True)

    return results, failed


def update_fundamentals(
    session: Session,
    on_progress: Callable[[int, int], None] | None = None,
) -> tuple[int, list[str]]:
    """Coleta fundamentos e dividendos dos ativos da carteira em paralelo.

    Args:
        session: Sessão do banco.
        on_progress: Callback opcional ``(concluidos, total)``.

    Returns:
        Quantidade de ativos atualizados e lista de tickers com falha.
    """
    assets = [a for a in session.exec(select(Asset)).all() if not a.divisible]
    if not assets:
        return 0, []

    snapshots, failed = fetch_many_snapshots([a.ticker for a in assets], on_progress=on_progress)
    now = datetime.now(UTC)
    updated = 0

    for asset in assets:
        snap = snapshots.get(asset.ticker)
        if snap is None or asset.id is None:
            continue
        fund = session.exec(
            select(AssetFundamentals).where(AssetFundamentals.asset_id == asset.id)
        ).first()
        if fund is None:
            fund = AssetFundamentals(asset_id=asset.id)

        fund.lpa = snap.lpa
        fund.vpa = snap.vpa
        fund.pl = snap.pl
        fund.pvp = snap.pvp
        fund.roe = snap.roe
        fund.payout = snap.payout
        fund.div_12m = snap.div_12m
        fund.div_avg_5y = snap.div_avg_5y
        fund.updated_at = now
        session.add(fund)

        if snap.price is not None:
            asset.current_price = snap.price
            asset.price_updated_at = now
            session.add(asset)
        updated += 1

    session.commit()
    return updated, failed
