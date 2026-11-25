"""Testes unitários do módulo de estatística, risco, correlação e metas."""

from datetime import date, timedelta

from sqlmodel import Session

from app.database.models import Asset, AssetClass, PricePoint
from app.database.session import engine
from app.services.analytics import BENCHMARK_TICKER, build_risk_report, project_goals


def test_project_goals_calcula_meses_e_marcos_atingidos() -> None:
    goals = project_goals(
        current_value=6000.0,
        monthly_contribution=500.0,
        annual_rate_pct=12.0,
        milestones=(5000.0, 10000.0, 50000.0),
    )
    assert goals[0].reached is True
    assert goals[0].months == 0
    assert 6 <= goals[1].months <= 9
    assert goals[2].months > goals[1].months


def test_build_risk_report_com_historico_sintetico() -> None:
    with Session(engine) as session:
        cls = AssetClass(name="Ações", target_pct=100.0)
        session.add(cls)
        session.commit()
        session.refresh(cls)
        assert cls.id is not None

        session.add(Asset(ticker="AAA3", asset_class_id=cls.id, quantity=10, current_price=100.0))
        session.add(Asset(ticker="BBB3", asset_class_id=cls.id, quantity=10, current_price=100.0))

        start = date(2026, 1, 1)
        p_a, p_b, p_idx = 100.0, 100.0, 100_000.0
        for i in range(60):
            d = start + timedelta(days=i)
            # AAA3 e BBB3 com movimentos opostos -> baixa/negativa correlação
            step = 0.015 if i % 2 == 0 else -0.012
            p_a *= 1.0 + step
            p_b *= 1.0 - step * 0.8 + 0.002
            p_idx *= 1.0 + step * 0.9
            session.add(PricePoint(ticker="AAA3", ref_date=d, close=round(p_a, 2)))
            session.add(PricePoint(ticker="BBB3", ref_date=d, close=round(p_b, 2)))
            session.add(PricePoint(ticker=BENCHMARK_TICKER, ref_date=d, close=round(p_idx, 2)))
        session.commit()

        report = build_risk_report(session)
        assert report.has_history is True
        assert report.days_analyzed >= 55
        assert report.diversification_benefit_pct > 0
        assert len(report.scenarios) == 3
        assert (
            report.scenarios[0].p10_value
            <= report.scenarios[0].p50_value
            <= report.scenarios[0].p90_value
        )
        assert len(report.corr_tickers) == 2
        assert report.low_corr_pairs[0].corr < 0


def test_sanitiza_tick_corrompido_do_yahoo() -> None:
    with Session(engine) as session:
        cls = AssetClass(name="FIIs", target_pct=100.0)
        session.add(cls)
        session.commit()
        session.refresh(cls)
        assert cls.id is not None

        session.add(Asset(ticker="XPML11", asset_class_id=cls.id, quantity=10, current_price=83.0))
        start = date(2026, 1, 1)
        for i in range(40):
            d = start + timedelta(days=i)
            # Simula o glitch real do Yahoo: cai 99% em 1 dia e volta +9900% no seguinte
            close = 0.83 if i == 15 else 83.0 + (i % 3) * 0.5
            session.add(PricePoint(ticker="XPML11", ref_date=d, close=close))
        session.commit()

        report = build_risk_report(session)
        assert report.has_history is True
        assert report.portfolio_vol_pct < 30.0
        assert report.scenarios[0].p90_pct < 50.0
