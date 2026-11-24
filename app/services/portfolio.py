"""Consultas e agregações da carteira usadas pelas telas."""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime

from sqlmodel import Session, col, select

from app.database.models import Asset, AssetClass, AssetStatus
from app.services.rebalance import AssetInput, ClassInput, band_bounds


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


def load(session: Session) -> tuple[list[AssetClass], list[Asset]]:
    """Carrega classes (ordenadas) e ativos."""
    classes = list(session.exec(select(AssetClass).order_by(col(AssetClass.sort_order))).all())
    return classes, list(session.exec(select(Asset)).all())


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


def to_engine_inputs(session: Session) -> tuple[list[ClassInput], list[AssetInput]]:
    """Converte o estado do banco para as entradas do motor de aporte."""
    classes, assets = load(session)
    names = {c.id: c.name for c in classes}
    return (
        [ClassInput(c.name, c.target_pct, c.band_pp, c.band_mode) for c in classes],
        [
            AssetInput(
                ticker=a.ticker,
                class_name=names[a.asset_class_id],
                value=a.value,
                price=a.current_price,
                weight=a.weight,
                divisible=a.divisible,
                frozen=a.status == AssetStatus.EM_REVISAO,
                price_ceiling=a.price_ceiling,
            )
            for a in assets
        ],
    )
