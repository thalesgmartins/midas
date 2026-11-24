"""Atualização de cotações (fechamento mais recente) via yfinance."""

import logging
from datetime import datetime

from sqlmodel import Session, select

from app.database.models import Asset

logger = logging.getLogger(__name__)


def update_quotes(session: Session) -> tuple[int, list[str]]:
    """Atualiza o preço atual dos ativos negociados na B3.

    Args:
        session: Sessão do banco.

    Returns:
        Quantidade de ativos atualizados e lista de tickers que falharam.
    """
    import yfinance as yf

    assets = [a for a in session.exec(select(Asset)).all() if not a.divisible]
    if not assets:
        return 0, []
    by_symbol = {f"{a.ticker}.SA": a for a in assets}
    data = yf.download(list(by_symbol), period="5d", progress=False, auto_adjust=False)
    closes = data["Close"]

    updated, failed = 0, []
    for symbol, asset in by_symbol.items():
        try:
            series = closes[symbol].dropna() if symbol in closes else closes.dropna()
            asset.current_price = round(float(series.iloc[-1]), 2)
        except (KeyError, IndexError, TypeError, ValueError):
            logger.error("Sem cotação para %s", asset.ticker)
            failed.append(asset.ticker)
            continue
        asset.price_updated_at = datetime.now()
        session.add(asset)
        updated += 1
    session.commit()
    return updated, failed
