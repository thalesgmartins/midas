"""Testes unitários do motor de valuation multi-método."""

from app.services.valuation import ValuationInput, evaluate_asset


def test_valuation_acao_multi_metodo() -> None:
    res = evaluate_asset(
        ValuationInput(
            ticker="BBSE3",
            class_name="Ações",
            current_price=36.0,
            avg_price=30.0,
            quantity=10,
            lpa=4.0,
            vpa=10.0,
            pl=9.0,
            roe=0.25,
            payout=0.40,
            div_12m=3.60,
            div_avg_5y=3.00,  # menor que 12m -> Bazin usa 3,00 / 0,06 = 50,00
        )
    )
    assert res.graham == 30.0  # sqrt(22.5 * 4 * 10) = 30.0
    assert res.bazin == 50.0  # 3.0 / 0.06
    assert res.growth_pct == 15.0  # 0.25 * (1 - 0.40) * 100
    assert res.peg == 0.6  # 9.0 / 15.0
    assert res.lynch == 60.0  # 4.0 * 15.0
    assert res.consensus_ceiling == 50.0  # mediana(30, 50, 60)
    assert res.effective_ceiling == 50.0
    assert res.status == "barato"
    assert res.dy_pct == 10.0
    assert res.yoc_pct == 12.0
    assert res.est_annual_income == 36.0
    assert res.est_monthly_income == 3.0


def test_valuation_fii_e_sobrescrita_manual() -> None:
    res = evaluate_asset(
        ValuationInput(
            ticker="HGLG11",
            class_name="FIIs",
            current_price=140.0,
            avg_price=150.0,
            quantity=12,
            manual_ceiling=135.0,
            vpa=160.0,
            pvp=0.875,
            div_12m=13.20,
            div_avg_5y=13.20,
        )
    )
    assert res.fii_pvp_fair == 160.0
    assert res.fii_yield_ceiling == 120.0  # 13.20 / 0.11
    assert res.consensus_ceiling == 140.0  # mediana(160, 120)
    assert res.using_manual_ceiling is True
    assert res.effective_ceiling == 135.0
    assert res.status == "caro"  # 140 > 135
    assert res.est_monthly_income == 13.2


def test_valuation_sem_dados() -> None:
    res = evaluate_asset(ValuationInput(ticker="WRLD11", class_name="ETFs", current_price=159.0))
    assert res.consensus_ceiling is None
    assert res.status == "sem_dados"
