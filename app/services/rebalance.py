"""Motor de aporte.

Regras, em ordem:

1. Ativos "em revisão", com peso 0 ou acima do preço teto ficam de fora; a meta
   deles é redistribuída entre os demais da mesma classe.
2. Só recebem aporte as classes abaixo da banda de tolerância (em pontos percentuais
   ``± p.p.`` ou relativa ``metade/dobro``). Se nenhuma estiver fora da banda,
   recebem as que estão abaixo da meta.
3. A compra é feita cota a cota, sempre escolhendo a compra que mais reduz o desvio
   quadrático em relação às metas. Comprar 1 cota de preço ``p`` num ativo com
   déficit ``d`` reduz o erro em ``p * (2d - p)``, logo só compra se ``d > p / 2``.
4. Ativos divisíveis (renda fixa) recebem valores quebrados. A sobra final vai para
   o primeiro ativo divisível (reserva) ou fica em caixa.

O preço médio não entra em nenhuma regra, de propósito, para evitar ancoragem.
"""

from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class ClassInput:
    """Meta de uma classe de ativo."""

    name: str
    target_pct: float
    band_pp: float
    band_mode: str = "pp"


@dataclass
class AssetInput:
    """Estado de um ativo para o motor de aporte."""

    ticker: str
    class_name: str
    value: float
    price: float
    weight: float = 1.0
    divisible: bool = False
    frozen: bool = False
    price_ceiling: float | None = None


@dataclass
class ClassReport:
    """Situação de uma classe no momento do aporte."""

    name: str
    value: float
    current_pct: float
    target_pct: float
    band_pp: float
    band_mode: str
    band_low: float
    band_high: float
    target_value_after: float
    deficit_after: float
    eligible: bool = False
    reason: str = ""


@dataclass
class Buy:
    """Compra sugerida."""

    ticker: str
    class_name: str
    units: float
    price: float
    amount: float
    reasons: list[str] = field(default_factory=list)


@dataclass
class Excluded:
    """Ativo fora do aporte e o motivo."""

    ticker: str
    reason: str


@dataclass
class Plan:
    """Resultado completo da simulação de aporte."""

    amount: float
    total_before: float
    total_after: float
    classes: list[ClassReport]
    buys: list[Buy]
    excluded: list[Excluded]
    leftover: float


def format_brl(value: float) -> str:
    """Formata um valor como moeda brasileira (``R$ 1.234,56``)."""
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def format_pct(value: float, digits: int = 1) -> str:
    """Formata um percentual com vírgula decimal (sem o símbolo)."""
    return f"{value:.{digits}f}".replace(".", ",")


def band_bounds(target_pct: float, band_pp: float, band_mode: str = "pp") -> tuple[float, float]:
    """Retorna os limites inferior e superior (em %) da banda de tolerância."""
    if band_mode == "half_double":
        return max(0.0, target_pct / 2), min(100.0, target_pct * 2)
    return max(0.0, target_pct - band_pp), min(100.0, target_pct + band_pp)


def _band_label(band_pp: float, band_mode: str, low: float, high: float) -> str:
    if band_mode == "half_double":
        return f"banda {format_pct(low)}%–{format_pct(high)}% (metade/dobro)"
    return f"banda ±{band_pp:.0f} p.p."


def _class_reports(
    classes: list[ClassInput], assets: list[AssetInput], amount: float
) -> dict[str, ClassReport]:
    total = sum(a.value for a in assets)
    total_after = total + amount
    values: dict[str, float] = defaultdict(float)
    for a in assets:
        values[a.class_name] += a.value

    reports = {}
    for c in classes:
        target_after = total_after * c.target_pct / 100
        low, high = band_bounds(c.target_pct, c.band_pp, c.band_mode)
        reports[c.name] = ClassReport(
            name=c.name,
            value=values[c.name],
            current_pct=values[c.name] / total * 100 if total else 0.0,
            target_pct=c.target_pct,
            band_pp=c.band_pp,
            band_mode=c.band_mode,
            band_low=low,
            band_high=high,
            target_value_after=target_after,
            deficit_after=target_after - values[c.name],
        )

    out_of_band = {r.name for r in reports.values() if r.current_pct < r.band_low}
    if out_of_band:
        eligible, rule = out_of_band, "abaixo da banda"
    else:
        eligible = {r.name for r in reports.values() if r.deficit_after > 0}
        rule = "abaixo da meta (nenhuma classe fora da banda)"

    for r in reports.values():
        prefix = f"{format_pct(r.current_pct)}% vs meta {r.target_pct:.0f}% -> "
        if r.name in eligible:
            r.eligible = True
            r.reason = prefix + rule
        elif r.current_pct > r.target_pct:
            r.reason = prefix + "acima da meta"
        else:
            r.reason = (
                prefix + f"dentro da {_band_label(r.band_pp, r.band_mode, r.band_low, r.band_high)}"
            )
    return reports


def _exclusion_reason(asset: AssetInput) -> str | None:
    if asset.frozen:
        return "Em revisão (tese congelada)"
    if asset.weight <= 0:
        return "Peso/meta 0% (não aportar)"
    if asset.price_ceiling and asset.price > asset.price_ceiling:
        price, ceiling = format_brl(asset.price), format_brl(asset.price_ceiling)
        return f"Acima do preço teto ({price} > {ceiling})"
    if not asset.divisible and asset.price <= 0:
        return "Sem cotação"
    return None


def _best_purchase(
    buyable: list[AssetInput], deficit: dict[str, float], cash: float
) -> tuple[AssetInput, float] | None:
    best: tuple[AssetInput, float] | None = None
    best_score = 0.0
    for asset in buyable:
        gap = deficit[asset.ticker]
        if gap <= 0:
            continue
        if asset.divisible:
            spend = min(gap, cash)
        elif asset.price <= cash:
            spend = asset.price
        else:
            continue
        score = spend * (2 * gap - spend)
        if score > best_score:
            best, best_score = (asset, spend), score
    return best


def plan_contribution(amount: float, classes: list[ClassInput], assets: list[AssetInput]) -> Plan:
    """Calcula como distribuir um aporte entre os ativos.

    Args:
        amount: Valor do aporte em reais.
        classes: Metas por classe.
        assets: Estado atual de cada ativo.

    Returns:
        Plano com compras, justificativas e ativos excluídos.
    """
    reports = _class_reports(classes, assets, amount)
    eligible = {name for name, r in reports.items() if r.eligible}

    excluded: list[Excluded] = []
    candidates: list[AssetInput] = []
    for asset in assets:
        reason = _exclusion_reason(asset)
        if reason:
            excluded.append(Excluded(asset.ticker, reason))
        else:
            candidates.append(asset)

    weight_sum: dict[str, float] = defaultdict(float)
    for asset in candidates:
        weight_sum[asset.class_name] += asset.weight
    deficit = {
        a.ticker: reports[a.class_name].target_value_after * a.weight / weight_sum[a.class_name]
        - a.value
        for a in candidates
    }

    buyable = [a for a in candidates if a.class_name in eligible]
    buys: dict[str, Buy] = {}
    cash = amount
    while cash > 0.009 and (choice := _best_purchase(buyable, deficit, cash)):
        asset, spend = choice
        buy = buys.setdefault(asset.ticker, Buy(asset.ticker, asset.class_name, 0, asset.price, 0))
        buy.units += spend if asset.divisible else 1
        buy.amount += spend
        deficit[asset.ticker] -= spend
        cash -= spend

    for asset in candidates:
        if asset.class_name not in eligible and asset.ticker not in buys:
            state = reports[asset.class_name].reason.split("-> ")[-1]
            excluded.append(Excluded(asset.ticker, f"Classe {asset.class_name}: {state}"))

    for buy in buys.values():
        report = reports[buy.class_name]
        remaining = format_brl(max(deficit[buy.ticker], 0))
        buy.reasons += [
            f"{buy.class_name} em {format_pct(report.current_pct)}% "
            f"(meta {report.target_pct:.0f}%)",
            f"ainda faltam {remaining} para a meta do ativo",
        ]

    leftover = round(cash, 2)
    reserve = next((a for a in assets if a.divisible and not a.frozen), None)
    if leftover > 0 and reserve:
        buy = buys.setdefault(reserve.ticker, Buy(reserve.ticker, reserve.class_name, 0, 0, 0))
        buy.units += leftover
        buy.amount += leftover
        buy.reasons.append(f"sobra de {format_brl(leftover)} (não dá para comprar mais cotas)")
        excluded = [e for e in excluded if e.ticker != reserve.ticker]
        leftover = 0.0

    divisible = {a.ticker for a in assets if a.divisible}
    for buy in buys.values():
        buy.amount = round(buy.amount, 2)
        if buy.ticker not in divisible:
            buy.units = int(round(buy.units))

    total = sum(a.value for a in assets)
    return Plan(
        amount=amount,
        total_before=total,
        total_after=total + amount,
        classes=sorted(reports.values(), key=lambda r: -r.target_pct),
        buys=sorted(buys.values(), key=lambda b: -b.amount),
        excluded=excluded,
        leftover=leftover,
    )
