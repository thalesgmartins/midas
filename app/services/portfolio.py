"""Consultas e agregações da carteira usadas pelas telas."""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime

from sqlmodel import Session, col, select

from app.database.models import Asset, AssetClass, AssetFundamentals, AssetStatus
from app.services.rebalance import AssetInput, ClassInput, band_bounds
from app.services.valuation import ValuationInput, ValuationResult, evaluate_asset


@dataclass
class PositionRow:
    """Linha da tabela de posições."""

    asset: Asset
    pct: float
    ideal: float


@dataclass
class ClassGroup:
    """Classe com suas posições e situação frente à meta."""

    asset_class: AssetClass
    value: float
    pct: float
    diff: float
    band_low: float
    band_high: float
    state: str
    rows: list[PositionRow] = field(default_factory=list)


@dataclass
class Summary:
    """Visão consolidada da carteira."""

    total: float
    groups: list[ClassGroup]
    segments: dict[str, list[tuple[str, float, float]]]
    variable_cost: float
    variable_value: float
    adherence_pct: float
    asset_count: int
    review_count: int
    last_quote_at: datetime | None


@dataclass
class ValuationSummary:
    """Resumo de valuation multi-método e proventos da carteira."""

    stocks: list[ValuationResult]
    fiis: list[ValuationResult]
    others: list[ValuationResult]
    est_monthly_income: float
    est_annual_income: float
    weighted_dy_pct: float
    weighted_yoc_pct: float
    opportunity_count: int
    evaluated_count: int
    last_updated_at: datetime | None


def load(session: Session) -> tuple[list[AssetClass], list[Asset]]:
    """Carrega classes (ordenadas) e ativos."""
    classes = list(session.exec(select(AssetClass).order_by(col(AssetClass.sort_order))).all())
    return classes, list(session.exec(select(Asset)).all())


def _load_fundamentals_map(session: Session) -> dict[int, AssetFundamentals]:
    rows = session.exec(select(AssetFundamentals)).all()
    return {f.asset_id: f for f in rows}


def _evaluate_for_asset(
    asset: Asset, class_name: str, fund: AssetFundamentals | None
) -> ValuationResult:
    return evaluate_asset(
        ValuationInput(
            ticker=asset.ticker,
            class_name=class_name,
            current_price=asset.current_price,
            avg_price=asset.avg_price,
            quantity=asset.quantity,
            manual_ceiling=asset.price_ceiling,
            lpa=fund.lpa if fund else None,
            vpa=fund.vpa if fund else None,
            pl=fund.pl if fund else None,
            pvp=fund.pvp if fund else None,
            roe=fund.roe if fund else None,
            payout=fund.payout if fund else None,
            div_12m=fund.div_12m if fund else None,
            div_avg_5y=fund.div_avg_5y if fund else None,
        )
    )


def _class_state(pct: float, low: float, high: float) -> str:
    if pct < low:
        return "abaixo"
    if pct > high:
        return "acima"
    return "ok"


def _group(asset_class: AssetClass, assets: list[Asset], total: float) -> ClassGroup:
    items = sorted(
        (a for a in assets if a.asset_class_id == asset_class.id), key=lambda a: -a.value
    )
    value = sum(a.value for a in items)
    pct = value / total * 100 if total else 0.0
    diff = pct - asset_class.target_pct
    low, high = band_bounds(asset_class.target_pct, asset_class.band_pp, asset_class.band_mode)
    active_weight = sum(a.weight for a in items if a.status == AssetStatus.ATIVO and a.weight > 0)
    rows = [
        PositionRow(
            asset=a,
            pct=a.value / total * 100 if total else 0.0,
            ideal=(
                asset_class.target_pct * a.weight / active_weight
                if active_weight and a.status == AssetStatus.ATIVO
                else 0.0
            ),
        )
        for a in items
    ]
    return ClassGroup(
        asset_class=asset_class,
        value=value,
        pct=pct,
        diff=diff,
        band_low=low,
        band_high=high,
        state=_class_state(pct, low, high),
        rows=rows,
    )


def summary(session: Session) -> Summary:
    """Monta a visão consolidada: totais, classes vs metas, aderência e segmentos."""
    classes, assets = load(session)
    total = sum(a.value for a in assets)
    groups = [_group(c, assets, total) for c in classes]

    by_segment: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for a in assets:
        class_name = a.asset_class.name if a.asset_class else "?"
        by_segment[class_name][a.segment or "Sem segmento"] += a.value
    segments = {
        name: sorted(
            ((seg, val, val / sum(values.values()) * 100) for seg, val in values.items()),
            key=lambda item: -item[1],
        )
        for name, values in by_segment.items()
    }
    variable = [a for a in assets if not a.divisible]
    total_abs_dev = sum(abs(g.pct - g.asset_class.target_pct) for g in groups)
    adherence = max(0.0, 100.0 - total_abs_dev / 2.0) if total else 0.0
    timestamps = [a.price_updated_at for a in assets if a.price_updated_at is not None]
    return Summary(
        total=total,
        groups=groups,
        segments=segments,
        variable_cost=sum(a.cost for a in variable),
        variable_value=sum(a.value for a in variable),
        adherence_pct=adherence,
        asset_count=len(assets),
        review_count=sum(1 for a in assets if a.status == AssetStatus.EM_REVISAO),
        last_quote_at=max(timestamps) if timestamps else None,
    )


def valuation_report(session: Session) -> ValuationSummary:
    """Calcula valuation multi-método e proventos projetados para toda a carteira."""
    classes, assets = load(session)
    names = {c.id: c.name for c in classes}
    funds = _load_fundamentals_map(session)

    stocks: list[ValuationResult] = []
    fiis: list[ValuationResult] = []
    others: list[ValuationResult] = []

    total_annual = 0.0
    rv_value = 0.0
    rv_cost = 0.0

    for asset in assets:
        if asset.divisible or asset.id is None:
            continue
        cname = names.get(asset.asset_class_id, "")
        res = _evaluate_for_asset(asset, cname, funds.get(asset.id))
        total_annual += res.est_annual_income
        rv_value += asset.value
        rv_cost += asset.cost
        lower = cname.lower()
        if lower.startswith("aç") or lower.startswith("ac"):
            stocks.append(res)
        elif lower.startswith("fii"):
            fiis.append(res)
        else:
            others.append(res)

    def _sort_key(item: ValuationResult) -> float:
        return -(item.margin_of_safety_pct if item.margin_of_safety_pct is not None else -9999.0)

    stocks.sort(key=_sort_key)
    fiis.sort(key=_sort_key)
    all_eval = stocks + fiis + others
    evaluated = [r for r in all_eval if r.effective_ceiling is not None]
    opportunities = [r for r in evaluated if (r.margin_of_safety_pct or -1) >= 0]
    timestamps = [f.updated_at for f in funds.values() if f.updated_at is not None]

    return ValuationSummary(
        stocks=stocks,
        fiis=fiis,
        others=others,
        est_monthly_income=round(total_annual / 12.0, 2),
        est_annual_income=round(total_annual, 2),
        weighted_dy_pct=round(total_annual / rv_value * 100.0, 2) if rv_value > 0 else 0.0,
        weighted_yoc_pct=round(total_annual / rv_cost * 100.0, 2) if rv_cost > 0 else 0.0,
        opportunity_count=len(opportunities),
        evaluated_count=len(evaluated),
        last_updated_at=max(timestamps) if timestamps else None,
    )


def to_engine_inputs(session: Session) -> tuple[list[ClassInput], list[AssetInput]]:
    """Converte o estado do banco para as entradas do motor de aporte.

    Quando o ativo não tem preço teto manual, utiliza o preço teto consenso
    calculado pelos fundamentos (se disponível).
    """
    classes, assets = load(session)
    names = {c.id: c.name for c in classes}
    funds = _load_fundamentals_map(session)
    engine_assets: list[AssetInput] = []
    for a in assets:
        cname = names[a.asset_class_id]
        ceiling = a.price_ceiling
        if ceiling is None and not a.divisible and a.id is not None and a.id in funds:
            ceiling = _evaluate_for_asset(a, cname, funds[a.id]).consensus_ceiling
        engine_assets.append(
            AssetInput(
                ticker=a.ticker,
                class_name=cname,
                value=a.value,
                price=a.current_price,
                weight=a.weight,
                divisible=a.divisible,
                frozen=a.status == AssetStatus.EM_REVISAO,
                price_ceiling=ceiling,
            )
        )
    return [
        ClassInput(c.name, c.target_pct, c.band_pp, c.band_mode) for c in classes
    ], engine_assets
