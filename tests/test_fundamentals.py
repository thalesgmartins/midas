"""Testes da coleta de fundamentos e integração com o motor de aporte."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd
from sqlmodel import Session

from app.database.models import Asset, AssetClass
from app.database.session import engine
from app.services import portfolio
from app.services.fundamentals import update_fundamentals


def test_update_fundamentals_e_teto_automatico_no_motor() -> None:
    with Session(engine) as session:
        cls = AssetClass(name="Ações", target_pct=100.0)
        session.add(cls)
        session.commit()
        session.refresh(cls)
        assert cls.id is not None

        asset = Asset(
            ticker="ITSA3",
            asset_class_id=cls.id,
            quantity=10,
            avg_price=10.0,
            current_price=13.0,
        )
        session.add(asset)
        session.commit()

        now = datetime.now(UTC)
        divs = pd.Series(
            [0.60, 0.60],
            index=pd.DatetimeIndex([now - timedelta(days=30), now - timedelta(days=200)]),
        )
        fake_ticker = SimpleNamespace(
            info={
                "trailingEps": 2.0,
                "bookValue": 8.0,
                "trailingPE": 6.5,
                "priceToBook": 1.62,
                "returnOnEquity": 0.22,
                "payoutRatio": 0.45,
                "currentPrice": 13.10,
            },
            dividends=divs,
        )
        fake_yf = SimpleNamespace(Ticker=lambda _sym: fake_ticker)
        with patch.dict("sys.modules", {"yfinance": fake_yf}):
            updated, failed = update_fundamentals(session)

        assert updated == 1
        assert failed == []

        _, engine_assets = portfolio.to_engine_inputs(session)
        # Sem teto manual, o motor recebe o consenso calculado automaticamente
        assert engine_assets[0].price_ceiling is not None
        assert engine_assets[0].price_ceiling > 0
