"""Testes de jobs em background, agendador de pregão e catálogo B3."""

import io
import json
import time
from datetime import datetime
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.services import jobs
from app.services.b3_catalog import fetch_b3_liquid_universe
from app.services.scheduler import BRT, is_b3_trading_hours


def test_is_b3_trading_hours() -> None:
    # Terça-feira 11:30 BRT -> dentro do pregão
    assert is_b3_trading_hours(datetime(2026, 11, 24, 11, 30, tzinfo=BRT)) is True
    # Terça-feira 19:00 BRT -> fora do pregão
    assert is_b3_trading_hours(datetime(2026, 11, 24, 19, 0, tzinfo=BRT)) is False
    # Sábado 11:30 BRT -> fim de semana
    assert is_b3_trading_hours(datetime(2026, 11, 28, 11, 30, tzinfo=BRT)) is False


def test_job_background_e_endpoint_polling() -> None:
    jobs.reset_all()

    def fake_job(_session, on_progress) -> str:  # type: ignore[no-untyped-def]
        on_progress(2, 4)
        time.sleep(0.05)
        on_progress(4, 4)
        return "4 itens concluidos"

    state = jobs.trigger("teste", fake_job, "Rodando...")
    assert state.status == "running"

    deadline = time.time() + 2.0
    while time.time() < deadline and jobs.get_state("teste").status == "running":
        time.sleep(0.02)

    done_state = jobs.get_state("teste")
    assert done_state.status == "done"
    assert done_state.done == 4
    assert done_state.pct == 100
    assert done_state.message == "4 itens concluidos"

    with TestClient(app) as client:
        resp = client.get("/jobs/teste")
        assert resp.status_code == 200
        assert resp.headers.get("HX-Refresh") == "true"
        assert "4 itens concluidos" in resp.text


def test_fetch_b3_liquid_universe_filtra_liquidez() -> None:
    payload = {
        "stocks": [
            {
                "stock": "PETR4",
                "type": "stock",
                "sector": "Energy Minerals",
                "volume": 1000000,
                "close": 38.0,
            },
            {"stock": "HGLG11", "type": "fund", "sector": None, "volume": 50000, "close": 140.0},
            {
                "stock": "MICO3",
                "type": "stock",
                "sector": "Retail Trade",
                "volume": 100,
                "close": 1.0,
            },
        ]
    }
    fake_resp = io.BytesIO(json.dumps(payload).encode("utf-8"))
    fake_resp.__enter__ = lambda self: self  # type: ignore[method-assign]
    fake_resp.__exit__ = lambda self, *args: None  # type: ignore[method-assign]

    with patch("app.services.b3_catalog.urlopen", return_value=fake_resp):
        items = fetch_b3_liquid_universe()

    tickers = [t for t, *_ in items]
    assert "PETR4" in tickers
    assert "HGLG11" in tickers
    assert "MICO3" not in tickers
