"""Coleta de indicadores fundamentalistas e histórico de proventos via yfinance."""

import logging
from datetime import UTC, datetime, timedelta

from sqlmodel import Session, select

from app.database.models import Asset, AssetFundamentals

logger = logging.getLogger(__name__)


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


def update_fundamentals(session: Session) -> tuple[int, list[str]]:
    """Coleta fundamentos e dividendos dos ativos negociados em bolsa.

    Args:
        session: Sessão do banco.

    Returns:
        Quantidade de ativos atualizados e lista de tickers com falha.
    """
    import yfinance as yf

    assets = [a for a in session.exec(select(Asset)).all() if not a.divisible]
    if not assets:
        return 0, []

    updated, failed = 0, []
    now = datetime.now(UTC)

    for asset in assets:
        assert asset.id is not None
        try:
            ticker_obj = yf.Ticker(f"{asset.ticker}.SA")
            info = ticker_obj.info or {}
            div_12m, div_avg_5y = _dividend_metrics(ticker_obj.dividends)

            fund = session.exec(
                select(AssetFundamentals).where(AssetFundamentals.asset_id == asset.id)
            ).first()
            if fund is None:
                fund = AssetFundamentals(asset_id=asset.id)

            fund.lpa = _to_float(info.get("trailingEps"))
            fund.vpa = _to_float(info.get("bookValue"))
            fund.pl = _to_float(info.get("trailingPE"))
            fund.pvp = _to_float(info.get("priceToBook"))
            fund.roe = _to_float(info.get("returnOnEquity"))
            fund.payout = _to_float(info.get("payoutRatio"))
            fund.div_12m = div_12m
            fund.div_avg_5y = div_avg_5y
            fund.updated_at = now
            session.add(fund)

            price = _to_float(info.get("currentPrice") or info.get("regularMarketPrice"))
            if price is not None and price > 0:
                asset.current_price = round(price, 2)
                asset.price_updated_at = now
                session.add(asset)
            updated += 1
        except Exception:
            logger.exception("Falha ao coletar fundamentos de %s", asset.ticker)
            failed.append(asset.ticker)

    session.commit()
    return updated, failed
