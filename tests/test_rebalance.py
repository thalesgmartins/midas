"""Testes unitários do motor de aporte."""

from app.services.rebalance import AssetInput, Buy, ClassInput, Plan, plan_contribution

CLASSES = [ClassInput(n, 25.0, 5.0) for n in ("Ações", "FIIs", "ETFs", "Renda Fixa")]


def make_portfolio(
    frozen: set[str] | None = None, ceilings: dict[str, float] | None = None
) -> list[AssetInput]:
    """Monta uma carteira de referência para os testes."""
    frozen = frozen or set()
    ceilings = ceilings or {}
    acoes = {
        "EGIE3": (6, 24.79),
        "BBAS3": (10, 14.20),
        "ITSA3": (10, 13.16),
        "WIZC3": (20, 6.24),
        "BBSE3": (2, 36.51),
    }
    fiis = {
        "GARE11": (62, 7.84, 1),
        "HGLG11": (2, 140.69, 1),
        "MXRF11": (30, 8.32, 1),
        "GGRC11": (30, 8.00, 1),
        "BTCI11": (30, 7.62, 1),
        "XPML11": (2, 83.00, 1),
        "VGHF11": (33, 3.70, 0),
        "PORD11": (16, 7.54, 1),
        "XPCA11": (16, 6.40, 1),
        "KNCR11": (1, 101.71, 0),
    }
    items = [
        AssetInput(t, "Ações", q * p, p, frozen=t in frozen, price_ceiling=ceilings.get(t))
        for t, (q, p) in acoes.items()
    ]
    items += [AssetInput(t, "FIIs", q * p, p, weight=w) for t, (q, p, w) in fiis.items()]
    items.append(AssetInput("WRLD11", "ETFs", 159.36, 159.36))
    items.append(AssetInput("CDB", "Renda Fixa", 791.73, 0, divisible=True))
    return items


def by_ticker(plan: Plan) -> dict[str, Buy]:
    """Indexa as compras sugeridas pelo ticker."""
    return {b.ticker: b for b in plan.buys}


def test_aporte_400_carteira_atual() -> None:
    plan = plan_contribution(400, CLASSES, make_portfolio())
    buys = by_ticker(plan)
    assert round(plan.total_before, 2) == 3669.76
    assert buys["WRLD11"].units == 2
    assert buys["BBSE3"].units == 2
    assert not any(b.class_name == "FIIs" for b in plan.buys)
    assert round(sum(b.amount for b in plan.buys), 2) == 400.00


def test_ativo_em_revisao_nao_recebe() -> None:
    plan = plan_contribution(2000, CLASSES, make_portfolio(frozen={"BBAS3", "WIZC3"}))
    buys = by_ticker(plan)
    assert "BBAS3" not in buys and "WIZC3" not in buys
    assert any(e.ticker == "BBAS3" for e in plan.excluded)


def test_preco_teto_bloqueia() -> None:
    plan = plan_contribution(400, CLASSES, make_portfolio(ceilings={"BBSE3": 30.0}))
    assert "BBSE3" not in by_ticker(plan)
    assert any(e.ticker == "BBSE3" and "teto" in e.reason for e in plan.excluded)


def test_banda_metade_dobro() -> None:
    classes = [
        ClassInput(n, 25.0, 5.0, band_mode="half_double")
        for n in ("Ações", "FIIs", "ETFs", "Renda Fixa")
    ]
    plan = plan_contribution(400, classes, make_portfolio())
    # Meta 25% -> banda 12,5% a 50%: Ações (16,9%) fica dentro; só ETFs (4,3%) abaixo.
    by_class = {c.name: c for c in plan.classes}
    assert by_class["ETFs"].eligible is True
    assert by_class["Ações"].eligible is False
    assert by_class["ETFs"].band_low == 12.5
    assert by_class["ETFs"].band_high == 50.0
