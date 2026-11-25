"""Testes unitários do Screener de oportunidades e Watchlist."""

from sqlmodel import Session

from app.database.models import Asset, AssetClass, WatchlistAsset
from app.database.session import engine
from app.services.screener import (
    add_candidate,
    risk_flags,
    score_candidate,
    screener_report,
    toggle_watchlist,
)
from app.services.valuation import ValuationInput, evaluate_asset


def test_score_acao_perene_com_margem_e_qualidade() -> None:
    rec = WatchlistAsset(
        ticker="TAEE11",
        class_name="Ações",
        segment="Energia",
        is_perennial=True,
        current_price=30.0,
        lpa=4.5,
        vpa=20.0,
        pl=6.7,
        roe=0.22,
        payout=0.50,
        div_12m=3.20,
        div_avg_5y=3.00,
        profit_margin=0.45,
        debt_to_equity=70.0,
        drawdown_52w=-5.0,
    )
    val = evaluate_asset(
        ValuationInput(
            ticker=rec.ticker,
            class_name=rec.class_name,
            current_price=30.0,
            lpa=rec.lpa,
            vpa=rec.vpa,
            pl=rec.pl,
            roe=rec.roe,
            payout=rec.payout,
            div_12m=rec.div_12m,
            div_avg_5y=rec.div_avg_5y,
        )
    )
    assert risk_flags(rec, val) == []
    assert score_candidate(rec, val) >= 85


def test_value_trap_penalizado_e_sinalizado() -> None:
    trap = WatchlistAsset(
        ticker="TEND3",
        class_name="Ações",
        segment="Construção",
        is_perennial=False,
        current_price=8.0,
        lpa=3.5,
        vpa=15.0,
        pl=2.3,
        roe=0.20,
        payout=0.10,
        profit_margin=0.03,
        debt_to_equity=260.0,
        drawdown_52w=-48.0,
    )
    val = evaluate_asset(
        ValuationInput(
            ticker=trap.ticker,
            class_name=trap.class_name,
            current_price=8.0,
            lpa=trap.lpa,
            vpa=trap.vpa,
            pl=trap.pl,
            roe=trap.roe,
            payout=trap.payout,
        )
    )
    flags = risk_flags(trap, val)
    assert any("Queda forte" in f for f in flags)
    assert "Alavancagem alta" in flags
    assert "Margem baixa" in flags
    assert "Possível distorção" in flags
    assert score_candidate(trap, val) <= 20


def test_screener_cobertura_besst_e_watchlist() -> None:
    with Session(engine) as session:
        cls = AssetClass(name="Ações", target_pct=100.0)
        session.add(cls)
        session.commit()
        session.refresh(cls)
        assert cls.id is not None

        session.add(
            Asset(
                ticker="EGIE3",
                asset_class_id=cls.id,
                segment="Energia",
                quantity=5,
                current_price=25,
            )
        )
        session.commit()

        cand = add_candidate(session, ticker="SAPR11", class_name="Ações", segment="Saneamento")
        assert cand.id is not None
        assert cand.in_watchlist is True
        assert cand.is_perennial is True

        report = screener_report(session, scope="watchlist")
        assert len(report.items) == 1
        assert report.items[0].record.ticker == "SAPR11"
        assert "Energia" in report.covered_besst
        assert "Saneamento" in report.missing_besst

        toggled = toggle_watchlist(session, cand.id)
        assert toggled is not None
        assert toggled.in_watchlist is False
