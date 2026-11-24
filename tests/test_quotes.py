"""Testes da atualização de cotações com mock de yfinance."""

from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd
from sqlmodel import Session

from app.database.models import Asset, AssetClass
from app.database.session import engine
from app.services.quotes import update_quotes


def test_update_quotes_salva_datetime_com_timezone() -> None:
    with Session(engine) as session:
        cls = AssetClass(name="Ações", target_pct=100.0)
        session.add(cls)
        session.commit()
        session.refresh(cls)
        assert cls.id is not None

        asset = Asset(ticker="TAEE11", asset_class_id=cls.id, quantity=10, current_price=30.0)
        session.add(asset)
        session.commit()

        fake_df = {"Close": pd.DataFrame({"TAEE11.SA": [34.5, 35.12]})}
        fake_yf = SimpleNamespace(download=lambda *args, **kwargs: fake_df)
        with patch.dict("sys.modules", {"yfinance": fake_yf}):
            updated, failed = update_quotes(session)

        assert updated == 1
        assert failed == []
        session.refresh(asset)
        assert asset.current_price == 35.12
        assert asset.price_updated_at is not None
        assert asset.price_updated_at.tzinfo is not None
