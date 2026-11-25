"""Análise estatística, risco, correlação, cone de cenários e projeção de metas."""

import logging
import math
from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd
from sqlmodel import Session, delete, select

from app.database.models import Asset, PricePoint

logger = logging.getLogger(__name__)

TRADING_DAYS_YEAR = 252
BENCHMARK_TICKER = "^BVSP"
MAX_ABS_DAILY_RETURN = 0.45  # descarta ticks corrompidos do Yahoo (ex: -99% / +75000% em FIIs)
DEFAULT_MILESTONES: tuple[float, ...] = (5_000, 10_000, 25_000, 50_000, 100_000, 250_000)


@dataclass
class AssetRisk:
    """Métricas históricas de risco de um ativo individual."""

    ticker: str
    weight_pct: float
    annual_vol_pct: float
    max_drawdown_pct: float
    return_12m_pct: float | None
    beta_ibov: float | None


@dataclass
class CorrelationPair:
    """Par de ativos com sua correlação histórica de retornos diários."""

    ticker_a: str
    ticker_b: str
    corr: float


@dataclass
class ScenarioHorizon:
    """Faixa provável de patrimônio por simulação bootstrap histórica."""

    label: str
    trading_days: int
    p10_value: float
    p50_value: float
    p90_value: float
    p10_pct: float
    p50_pct: float
    p90_pct: float


@dataclass
class GoalProjection:
    """Estimativa de tempo para atingir um marco de patrimônio."""

    target: float
    progress_pct: float
    months: int
    years: float
    reached: bool


@dataclass
class RiskReport:
    """Relatório estatístico consolidado da carteira."""

    has_history: bool
    total_value: float
    days_analyzed: int
    portfolio_vol_pct: float = 0.0
    weighted_avg_vol_pct: float = 0.0
    diversification_benefit_pct: float = 0.0
    portfolio_max_drawdown_pct: float = 0.0
    var_95_30d_pct: float = 0.0
    var_95_30d_brl: float = 0.0
    portfolio_beta: float | None = None
    asset_risks: list[AssetRisk] = field(default_factory=list)
    corr_tickers: list[str] = field(default_factory=list)
    corr_matrix: list[list[float]] = field(default_factory=list)
    high_corr_pairs: list[CorrelationPair] = field(default_factory=list)
    low_corr_pairs: list[CorrelationPair] = field(default_factory=list)
    scenarios: list[ScenarioHorizon] = field(default_factory=list)
    goals: list[GoalProjection] = field(default_factory=list)


def update_price_history(session: Session, period: str = "2y") -> tuple[int, list[str]]:
    """Baixa fechamentos diários (2 anos) dos ativos da carteira + IBOV em lote.

    Args:
        session: Sessão do banco.
        period: Janela histórica do yfinance (padrão ``"2y"``).

    Returns:
        Quantidade de séries atualizadas e lista de tickers sem dados.
    """
    import yfinance as yf

    assets = [a for a in session.exec(select(Asset)).all() if not a.divisible]
    if not assets:
        return 0, []

    symbol_map = {f"{a.ticker}.SA": a.ticker for a in assets}
    symbol_map[BENCHMARK_TICKER] = BENCHMARK_TICKER
    symbols = list(symbol_map)

    data = yf.download(symbols, period=period, progress=False, auto_adjust=True, threads=True)
    if data.empty or "Close" not in data:
        return 0, [a.ticker for a in assets]
    closes = data["Close"]

    updated = 0
    failed: list[str] = []

    for sym, ticker in symbol_map.items():
        try:
            series = closes[sym].dropna() if isinstance(closes, pd.DataFrame) else closes.dropna()
            if series.empty:
                raise ValueError("série vazia")
        except (KeyError, ValueError, TypeError):
            if ticker != BENCHMARK_TICKER:
                failed.append(ticker)
            continue

        session.exec(delete(PricePoint).where(PricePoint.ticker == ticker))  # type: ignore[arg-type]
        for idx, val in series.items():
            ref = idx.date() if hasattr(idx, "date") else date.fromisoformat(str(idx)[:10])
            close_val = float(val)
            if math.isfinite(close_val) and close_val > 0:
                session.add(PricePoint(ticker=ticker, ref_date=ref, close=round(close_val, 4)))
        if ticker != BENCHMARK_TICKER:
            updated += 1

    session.commit()
    return updated, failed


def project_goals(
    current_value: float,
    monthly_contribution: float = 400.0,
    annual_rate_pct: float = 10.0,
    milestones: tuple[float, ...] = DEFAULT_MILESTONES,
) -> list[GoalProjection]:
    """Calcula quantos meses faltam para atingir cada marco de patrimônio.

    Usa a fórmula fechada de juros compostos com aportes mensais constantes.

    Args:
        current_value: Patrimônio atual em reais.
        monthly_contribution: Aporte mensal estimado em reais.
        annual_rate_pct: Taxa de retorno anual esperada (em %).
        milestones: Marcos de patrimônio em reais.

    Returns:
        Lista de projeções ordenadas por marco.
    """
    monthly_rate = (1.0 + max(annual_rate_pct, 0.0) / 100.0) ** (1.0 / 12.0) - 1.0
    pmt = max(monthly_contribution, 0.0)
    pv = max(current_value, 0.0)

    projections: list[GoalProjection] = []
    for target in milestones:
        progress = min(100.0, (pv / target * 100.0) if target > 0 else 100.0)
        if pv >= target:
            projections.append(GoalProjection(target, 100.0, 0, 0.0, True))
            continue

        if monthly_rate <= 0:
            months = math.ceil((target - pv) / pmt) if pmt > 0 else 999
        elif pv * monthly_rate + pmt <= 0:
            months = 999
        else:
            num = target * monthly_rate + pmt
            den = pv * monthly_rate + pmt
            months = math.ceil(math.log(num / den) / math.log(1.0 + monthly_rate))

        months = max(1, min(months, 999))
        projections.append(
            GoalProjection(
                target=target,
                progress_pct=round(progress, 1),
                months=months,
                years=round(months / 12.0, 1),
                reached=False,
            )
        )
    return projections


def _max_drawdown(returns: pd.Series) -> float:
    if returns.empty:
        return 0.0
    cum = (1.0 + returns).cumprod()
    drawdown = cum / cum.cummax() - 1.0
    return round(float(drawdown.min()) * 100.0, 1)


def _bootstrap_scenarios(
    port_returns: np.ndarray, total_value: float, simulations: int = 1000
) -> list[ScenarioHorizon]:
    """Gera cones de cenários (P10, P50, P90) por reamostragem histórica determinística."""
    if len(port_returns) < 20 or total_value <= 0:
        return []
    rng = np.random.default_rng(seed=42)
    horizons = [("30 dias", 21), ("90 dias", 63), ("12 meses", 252)]
    results: list[ScenarioHorizon] = []
    for label, days in horizons:
        sampled = rng.choice(port_returns, size=(simulations, days), replace=True)
        growth = np.prod(1.0 + sampled, axis=1)
        p10, p50, p90 = np.percentile(growth, [10, 50, 90])
        results.append(
            ScenarioHorizon(
                label=label,
                trading_days=days,
                p10_value=round(total_value * float(p10), 2),
                p50_value=round(total_value * float(p50), 2),
                p90_value=round(total_value * float(p90), 2),
                p10_pct=round((float(p10) - 1.0) * 100.0, 1),
                p50_pct=round((float(p50) - 1.0) * 100.0, 1),
                p90_pct=round((float(p90) - 1.0) * 100.0, 1),
            )
        )
    return results


def build_risk_report(
    session: Session,
    monthly_contribution: float = 400.0,
    annual_rate_pct: float = 10.0,
) -> RiskReport:
    """Computa volatilidade, drawdown, correlação, VaR, cenários e metas da carteira."""
    assets = list(session.exec(select(Asset)).all())
    total_value = sum(a.value for a in assets)
    goals = project_goals(total_value, monthly_contribution, annual_rate_pct)

    variable = [a for a in assets if not a.divisible and a.value > 0]
    if not variable:
        return RiskReport(has_history=False, total_value=total_value, days_analyzed=0, goals=goals)

    tickers = [a.ticker for a in variable]
    points = list(
        session.exec(
            select(PricePoint).where(
                PricePoint.ticker.in_(tickers + [BENCHMARK_TICKER])  # type: ignore[attr-defined]
            )
        ).all()
    )
    if not points:
        return RiskReport(has_history=False, total_value=total_value, days_analyzed=0, goals=goals)

    df = pd.DataFrame(
        [(p.ref_date, p.ticker, p.close) for p in points], columns=["date", "ticker", "close"]
    )
    prices = df.pivot_table(index="date", columns="ticker", values="close").sort_index().ffill()
    returns = prices.pct_change().dropna(how="all")
    # Descarta glitches do Yahoo Finance (splits mal ajustados ou cotação dividida por 100)
    returns = returns.where(returns.abs() <= MAX_ABS_DAILY_RETURN)

    available = [
        a for a in variable if a.ticker in returns.columns and returns[a.ticker].count() >= 20
    ]
    if not available:
        return RiskReport(has_history=False, total_value=total_value, days_analyzed=0, goals=goals)

    bench = returns[BENCHMARK_TICKER] if BENCHMARK_TICKER in returns.columns else None
    bench_var = float(bench.var()) if bench is not None and bench.count() >= 20 else 0.0

    # Pesos sobre o patrimônio total (renda fixa contribui com retorno ~0,04%/dia e vol ~0)
    avail_tickers = [a.ticker for a in available]
    weights = {a.ticker: a.value / total_value for a in available}
    rf_weight = max(0.0, 1.0 - sum(weights.values()))
    rf_daily = (1.105 ** (1.0 / TRADING_DAYS_YEAR)) - 1.0

    asset_returns = returns[avail_tickers].fillna(0.0)
    port_daily = sum(asset_returns[t] * w for t, w in weights.items()) + rf_weight * rf_daily
    port_daily = pd.Series(port_daily, index=asset_returns.index).dropna()

    asset_risks: list[AssetRisk] = []
    weighted_vol_sum = 0.0
    for asset in sorted(available, key=lambda a: -a.value):
        s = returns[asset.ticker].dropna()
        vol = float(s.std()) * math.sqrt(TRADING_DAYS_YEAR) * 100.0
        weighted_vol_sum += weights[asset.ticker] * vol
        dd = _max_drawdown(s)
        tail_12m = s.tail(TRADING_DAYS_YEAR)
        ret_12m = (
            round((float((1.0 + tail_12m).prod()) - 1.0) * 100.0, 1) if len(tail_12m) >= 2 else None
        )
        beta: float | None = None
        if bench is not None and bench_var > 0:
            aligned = pd.concat([s, bench], axis=1, join="inner").dropna()
            if len(aligned) >= 20:
                cov = float(aligned.iloc[:, 0].cov(aligned.iloc[:, 1]))
                beta = round(cov / float(aligned.iloc[:, 1].var()), 2)
        asset_risks.append(
            AssetRisk(
                ticker=asset.ticker,
                weight_pct=round(weights[asset.ticker] * 100.0, 1),
                annual_vol_pct=round(vol, 1),
                max_drawdown_pct=dd,
                return_12m_pct=ret_12m,
                beta_ibov=beta,
            )
        )

    port_vol = round(float(port_daily.std()) * math.sqrt(TRADING_DAYS_YEAR) * 100.0, 1)
    weighted_avg_vol = round(weighted_vol_sum, 1)
    div_benefit = round(max(0.0, weighted_avg_vol - port_vol), 1)
    port_dd = _max_drawdown(port_daily)

    port_beta: float | None = None
    if bench is not None and bench_var > 0:
        aligned_p = pd.concat([port_daily, bench], axis=1, join="inner").dropna()
        if len(aligned_p) >= 20:
            port_beta = round(
                float(aligned_p.iloc[:, 0].cov(aligned_p.iloc[:, 1]))
                / float(aligned_p.iloc[:, 1].var()),
                2,
            )

    # VaR 95% para 30 dias (21 pregões) via bootstrap
    scenarios = _bootstrap_scenarios(port_daily.to_numpy(dtype=float), total_value)
    rng = np.random.default_rng(seed=99)
    sim_30d = np.prod(1.0 + rng.choice(port_daily.to_numpy(dtype=float), size=(1000, 21)), axis=1)
    var_pct = round(min(0.0, (float(np.percentile(sim_30d, 5)) - 1.0) * 100.0), 1)
    var_brl = round(abs(var_pct) / 100.0 * total_value, 2)

    # Matriz de correlação (top 10 ativos por peso para legibilidade)
    top_tickers = [r.ticker for r in asset_risks[:10]]
    corr_df = returns[top_tickers].corr().fillna(0.0)
    corr_matrix = [[round(float(v), 2) for v in row] for row in corr_df.to_numpy()]

    pairs: list[CorrelationPair] = []
    for i, t_a in enumerate(top_tickers):
        for j in range(i + 1, len(top_tickers)):
            pairs.append(CorrelationPair(t_a, top_tickers[j], corr_matrix[i][j]))
    pairs_desc = sorted(pairs, key=lambda p: -p.corr)
    high_corr = [p for p in pairs_desc if p.corr >= 0.45][:5]
    low_corr = sorted(pairs, key=lambda p: p.corr)[:4]

    return RiskReport(
        has_history=True,
        total_value=total_value,
        days_analyzed=len(port_daily),
        portfolio_vol_pct=port_vol,
        weighted_avg_vol_pct=weighted_avg_vol,
        diversification_benefit_pct=div_benefit,
        portfolio_max_drawdown_pct=port_dd,
        var_95_30d_pct=var_pct,
        var_95_30d_brl=var_brl,
        portfolio_beta=port_beta,
        asset_risks=asset_risks,
        corr_tickers=top_tickers,
        corr_matrix=corr_matrix,
        high_corr_pairs=high_corr,
        low_corr_pairs=low_corr,
        scenarios=scenarios,
        goals=goals,
    )
