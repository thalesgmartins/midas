"""Motor de valuation multi-método (Graham, Bazin/Barsi, Lynch/PEG e FIIs)."""

import math
import statistics
from dataclasses import dataclass

BAZIN_MIN_YIELD = 0.06  # 6% a.a. (Bazin / Barsi)
FII_TARGET_YIELD = 0.11  # 11% a.a. (referência conservadora para FIIs)
LYNCH_MAX_GROWTH_PCT = 25.0  # teto de crescimento para evitar distorções de ROE pontual


@dataclass
class ValuationInput:
    """Dados de mercado e fundamentos para avaliar um ativo."""

    ticker: str
    class_name: str
    current_price: float
    avg_price: float = 0.0
    quantity: float = 0.0
    manual_ceiling: float | None = None
    lpa: float | None = None
    vpa: float | None = None
    pl: float | None = None
    pvp: float | None = None
    roe: float | None = None
    payout: float | None = None
    div_12m: float | None = None
    div_avg_5y: float | None = None


@dataclass
class ValuationResult:
    """Resultado consolidado de valuation e proventos de um ativo."""

    ticker: str
    class_name: str
    current_price: float
    graham: float | None = None
    bazin: float | None = None
    lynch: float | None = None
    fii_pvp_fair: float | None = None
    fii_yield_ceiling: float | None = None
    growth_pct: float | None = None
    peg: float | None = None
    pvp: float | None = None
    pl: float | None = None
    roe_pct: float | None = None
    consensus_ceiling: float | None = None
    effective_ceiling: float | None = None
    using_manual_ceiling: bool = False
    margin_of_safety_pct: float | None = None
    status: str = "sem_dados"  # barato | justo | caro | sem_dados
    dy_pct: float | None = None
    yoc_pct: float | None = None
    div_12m: float | None = None
    est_monthly_income: float = 0.0
    est_annual_income: float = 0.0


def _conservative_dividend(div_12m: float | None, div_avg_5y: float | None) -> float | None:
    """Usa o menor valor positivo entre 12m e média 5a para evitar armadilhas de payout."""
    candidates = [d for d in (div_12m, div_avg_5y) if d is not None and d > 0]
    return min(candidates) if candidates else None


def _graham_price(lpa: float | None, vpa: float | None) -> float | None:
    if lpa is None or vpa is None or lpa <= 0 or vpa <= 0:
        return None
    return round(math.sqrt(22.5 * lpa * vpa), 2)


def _bazin_price(
    div_12m: float | None, div_avg_5y: float | None, min_yield: float = BAZIN_MIN_YIELD
) -> float | None:
    div = _conservative_dividend(div_12m, div_avg_5y)
    if div is None or min_yield <= 0:
        return None
    return round(div / min_yield, 2)


def _lynch_metrics(
    lpa: float | None, pl: float | None, roe: float | None, payout: float | None
) -> tuple[float | None, float | None, float | None]:
    """Calcula Growth sustentável (ROE * (1 - Payout)), PEG e preço justo (PEG = 1)."""
    if roe is None or payout is None or roe <= 0 or not (0 <= payout < 1):
        return None, None, None
    growth_pct = roe * (1.0 - payout) * 100.0
    if growth_pct <= 0:
        return None, None, None
    peg = round(pl / growth_pct, 2) if pl is not None and pl > 0 else None
    fair = round(lpa * min(growth_pct, LYNCH_MAX_GROWTH_PCT), 2) if lpa and lpa > 0 else None
    return round(growth_pct, 1), peg, fair


def _status_from_margin(margin: float | None) -> str:
    if margin is None:
        return "sem_dados"
    if margin >= 15.0:
        return "barato"
    if margin >= 0.0:
        return "justo"
    return "caro"


def evaluate_asset(
    data: ValuationInput,
    bazin_yield: float = BAZIN_MIN_YIELD,
    fii_yield: float = FII_TARGET_YIELD,
) -> ValuationResult:
    """Calcula todos os preços teto aplicáveis, consenso, margem e proventos.

    Args:
        data: Dados de mercado e fundamentos do ativo.
        bazin_yield: Yield mínimo anual para ações (padrão 6%).
        fii_yield: Yield alvo anual para FIIs (padrão 11%).

    Returns:
        Resultado completo de valuation e dividendos.
    """
    is_fii = data.class_name.lower().startswith("fii")
    is_stock = data.class_name.lower().startswith("aç") or data.class_name.lower().startswith("ac")

    graham: float | None = None
    bazin: float | None = None
    lynch: float | None = None
    growth_pct: float | None = None
    peg: float | None = None
    fii_pvp_fair: float | None = None
    fii_yield_ceiling: float | None = None
    ceilings: list[float] = []

    if is_stock:
        graham = _graham_price(data.lpa, data.vpa)
        bazin = _bazin_price(data.div_12m, data.div_avg_5y, bazin_yield)
        growth_pct, peg, lynch = _lynch_metrics(data.lpa, data.pl, data.roe, data.payout)
        ceilings = [c for c in (graham, bazin, lynch) if c is not None and c > 0]
    elif is_fii:
        if data.vpa is not None and data.vpa > 0:
            fii_pvp_fair = round(data.vpa, 2)
        elif data.pvp is not None and data.pvp > 0 and data.current_price > 0:
            fii_pvp_fair = round(data.current_price / data.pvp, 2)
        fii_yield_ceiling = _bazin_price(data.div_12m, data.div_avg_5y, fii_yield)
        ceilings = [c for c in (fii_pvp_fair, fii_yield_ceiling) if c is not None and c > 0]

    consensus = round(statistics.median(ceilings), 2) if ceilings else None
    using_manual = data.manual_ceiling is not None and data.manual_ceiling > 0
    effective = data.manual_ceiling if using_manual else consensus

    margin: float | None = None
    if effective is not None and data.current_price > 0:
        margin = round((effective / data.current_price - 1.0) * 100.0, 1)

    dy_pct = (
        round(data.div_12m / data.current_price * 100.0, 2)
        if data.div_12m is not None and data.div_12m > 0 and data.current_price > 0
        else None
    )
    yoc_pct = (
        round(data.div_12m / data.avg_price * 100.0, 2)
        if data.div_12m is not None and data.div_12m > 0 and data.avg_price > 0
        else None
    )
    est_annual = round((data.div_12m or 0.0) * data.quantity, 2)
    pvp = data.pvp
    if pvp is None and data.vpa and data.vpa > 0 and data.current_price > 0:
        pvp = round(data.current_price / data.vpa, 2)

    return ValuationResult(
        ticker=data.ticker,
        class_name=data.class_name,
        current_price=data.current_price,
        graham=graham,
        bazin=bazin,
        lynch=lynch,
        fii_pvp_fair=fii_pvp_fair,
        fii_yield_ceiling=fii_yield_ceiling,
        growth_pct=growth_pct,
        peg=peg,
        pvp=round(pvp, 2) if pvp is not None else None,
        pl=round(data.pl, 2) if data.pl is not None else None,
        roe_pct=round(data.roe * 100.0, 1) if data.roe is not None else None,
        consensus_ceiling=consensus,
        effective_ceiling=effective,
        using_manual_ceiling=using_manual,
        margin_of_safety_pct=margin,
        status=_status_from_margin(margin),
        dy_pct=dy_pct,
        yoc_pct=yoc_pct,
        div_12m=round(data.div_12m, 4) if data.div_12m is not None else None,
        est_monthly_income=round(est_annual / 12.0, 2),
        est_annual_income=est_annual,
    )
