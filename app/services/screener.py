"""Screener de oportunidades B3, pontuação qualitativa e Watchlist."""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlmodel import Session, select

from app.database.models import Asset, WatchlistAsset
from app.services.b3_catalog import fetch_b3_liquid_universe
from app.services.fundamentals import fetch_many_snapshots
from app.services.valuation import ValuationInput, ValuationResult, evaluate_asset

logger = logging.getLogger(__name__)

# Universo inicial de ativos líquidos da B3 (Ações BESST/blue-chips + FIIs IFIX)
# Formato: (ticker, class_name, segment, is_perennial)
DEFAULT_UNIVERSE: list[tuple[str, str, str, bool]] = [
    # Bancos (BESST)
    ("BBAS3", "Ações", "Bancos", True),
    ("ITUB4", "Ações", "Bancos", True),
    ("ITSA4", "Ações", "Bancos", True),
    ("SANB11", "Ações", "Bancos", True),
    ("ABCB4", "Ações", "Bancos", True),
    # Energia (BESST)
    ("TAEE11", "Ações", "Energia", True),
    ("EGIE3", "Ações", "Energia", True),
    ("ISAE4", "Ações", "Energia", True),
    ("CPFE3", "Ações", "Energia", True),
    ("CMIG4", "Ações", "Energia", True),
    ("AURE3", "Ações", "Energia", True),
    # Saneamento (BESST)
    ("SAPR11", "Ações", "Saneamento", True),
    ("CSMG3", "Ações", "Saneamento", True),
    ("SBSP3", "Ações", "Saneamento", True),
    # Seguros (BESST)
    ("BBSE3", "Ações", "Seguros", True),
    ("CXSE3", "Ações", "Seguros", True),
    ("PSSA3", "Ações", "Seguros", True),
    ("WIZC3", "Ações", "Seguros", True),
    # Telecom (BESST)
    ("VIVT3", "Ações", "Telecom", True),
    ("TIMS3", "Ações", "Telecom", True),
    # Outros setores relevantes (Commodities / Indústria / Financeiro)
    ("VALE3", "Ações", "Mineração", False),
    ("PETR4", "Ações", "Petróleo", False),
    ("WEGE3", "Ações", "Indústria", False),
    ("KLBN11", "Ações", "Papel e Celulose", False),
    ("B3SA3", "Ações", "Serviços Financeiros", False),
    # FIIs Tijolo & Papel líquidos (IFIX)
    ("HGLG11", "FIIs", "Tijolo · Logística", False),
    ("BTLG11", "FIIs", "Tijolo · Logística", False),
    ("LVBI11", "FIIs", "Tijolo · Logística", False),
    ("XPML11", "FIIs", "Tijolo · Shopping", False),
    ("VISC11", "FIIs", "Tijolo · Shopping", False),
    ("HGRU11", "FIIs", "Tijolo · Renda Urbana", False),
    ("GARE11", "FIIs", "Tijolo · Híbrido", False),
    ("PVBI11", "FIIs", "Tijolo · Lajes", False),
    ("KNCR11", "FIIs", "Papel · High Grade", False),
    ("KNIP11", "FIIs", "Papel · IPCA", False),
    ("MXRF11", "FIIs", "Papel · Híbrido", False),
    ("CPTS11", "FIIs", "Papel", False),
]

BESST_SECTORS = ("Bancos", "Energia", "Saneamento", "Seguros", "Telecom")


@dataclass
class ScreenerItem:
    """Linha avaliada do Screener com valuation, alertas de risco e score qualitativo."""

    record: WatchlistAsset
    valuation: ValuationResult
    score: int
    in_portfolio: bool
    flags: list[str]


@dataclass
class ScreenerReport:
    """Visão filtrada do Screener com métricas de cobertura."""

    items: list[ScreenerItem]
    segments: list[str]
    opportunity_count: int
    watchlist_count: int
    covered_besst: list[str]
    missing_besst: list[str]
    last_updated_at: datetime | None


def ensure_default_universe(session: Session) -> int:
    """Popula o universo inicial de candidatos caso a tabela esteja vazia."""
    existing = {w.ticker for w in session.exec(select(WatchlistAsset)).all()}
    if existing:
        return 0
    created = 0
    for ticker, class_name, segment, is_perennial in DEFAULT_UNIVERSE:
        session.add(
            WatchlistAsset(
                ticker=ticker,
                class_name=class_name,
                segment=segment,
                is_perennial=is_perennial,
            )
        )
        created += 1
    session.commit()
    return created


_FINANCIAL_SEGMENTS = ("bancos", "seguros", "holding", "financeiro")


def _is_financial(segment: str) -> bool:
    low = segment.lower()
    return any(term in low for term in _FINANCIAL_SEGMENTS)


def risk_flags(record: WatchlistAsset, val: ValuationResult) -> list[str]:
    """Detecta sinais clássicos de armadilha de valor (value trap).

    Args:
        record: Dados brutos do ativo candidato.
        val: Resultado do valuation multi-método.

    Returns:
        Lista de alertas curtos (vazia se o ativo estiver saudável).
    """
    flags: list[str] = []
    if record.drawdown_52w is not None and record.drawdown_52w <= -30.0:
        flags.append(f"Queda forte ({record.drawdown_52w:.0f}%)")

    is_fii = record.class_name.lower().startswith("fii")
    if is_fii:
        if val.pvp is not None and val.pvp < 0.65:
            flags.append("Desconto extremo (revisar)")
        return flags

    if (
        not _is_financial(record.segment)
        and record.debt_to_equity is not None
        and record.debt_to_equity > 150.0
    ):
        flags.append("Alavancagem alta")
    if record.profit_margin is not None and record.profit_margin < 0.05:
        flags.append("Margem baixa")
    if (val.pl is not None and 0 < val.pl < 3.0) or (val.dy_pct is not None and val.dy_pct > 18.0):
        flags.append("Possível distorção")
    return flags


def score_candidate(record: WatchlistAsset, val: ValuationResult) -> int:
    """Calcula um score objetivo (0 a 100) com filtros anti-armadilha de valor.

    Args:
        record: Dados brutos do ativo candidato.
        val: Resultado do motor de valuation multi-método.

    Returns:
        Pontuação inteira de 0 a 100.
    """
    score = 0
    margin = val.margin_of_safety_pct
    if margin is not None:
        if margin >= 25.0:
            score += 30
        elif margin >= 10.0:
            score += 22
        elif margin >= 0.0:
            score += 12
        elif margin >= -10.0:
            score += 4

    # Penalidade de faca caindo (momentum fortemente negativo)
    if record.drawdown_52w is not None:
        if record.drawdown_52w <= -45.0:
            score -= 25
        elif record.drawdown_52w <= -30.0:
            score -= 15

    is_fii = record.class_name.lower().startswith("fii")
    if is_fii:
        if val.pvp is not None and val.pvp > 0:
            if 0.70 <= val.pvp <= 0.95:
                score += 25
            elif val.pvp <= 1.02:
                score += 15
            elif val.pvp < 0.65:
                score -= 10
        if val.dy_pct is not None:
            if 10.0 <= val.dy_pct <= 16.0:
                score += 25
            elif val.dy_pct >= 8.5:
                score += 15
            elif val.dy_pct > 18.0:
                score -= 10
        if record.div_avg_5y and record.div_avg_5y > 0:
            score += 15
        return max(0, min(100, score))

    # Ações: rentabilidade, margem, alavancagem, múltiplos e dividendos
    if val.roe_pct is not None:
        if val.roe_pct >= 15.0:
            score += 18
        elif val.roe_pct >= 10.0:
            score += 10
        elif val.roe_pct > 0:
            score += 4

    if record.profit_margin is not None:
        if record.profit_margin >= 0.12:
            score += 12
        elif record.profit_margin >= 0.07:
            score += 6
        elif record.profit_margin < 0.05:
            score -= 12

    if not _is_financial(record.segment) and record.debt_to_equity is not None:
        if record.debt_to_equity <= 80.0:
            score += 10
        elif record.debt_to_equity > 150.0:
            score -= 15

    if val.pl is not None and val.pl > 0:
        if 3.0 <= val.pl <= 10.0:
            score += 12
        elif 10.0 < val.pl <= 15.0:
            score += 6
        elif val.pl < 3.0:
            score -= 10

    if val.peg is not None and 0 < val.peg <= 1.0:
        score += 8
    if val.dy_pct is not None:
        if 6.0 <= val.dy_pct <= 16.0:
            score += 10
        elif val.dy_pct > 18.0:
            score -= 10
    if record.div_avg_5y and record.div_avg_5y > 0:
        score += 5
    if record.is_perennial:
        score += 5
    return max(0, min(100, score))


def sync_b3_universe(session: Session) -> int:
    """Sincroniza novos ativos líquidos listados na B3 (via brapi.dev) no Screener.

    Mantém os segmentos curados dos ativos já existentes.

    Args:
        session: Sessão do banco.

    Returns:
        Quantidade de novos ativos adicionados.
    """
    ensure_default_universe(session)
    existing = {w.ticker.upper() for w in session.exec(select(WatchlistAsset)).all()}
    catalog = fetch_b3_liquid_universe()
    added = 0
    for ticker, class_name, segment, is_perennial in catalog:
        if ticker in existing:
            continue
        session.add(
            WatchlistAsset(
                ticker=ticker,
                class_name=class_name,
                segment=segment,
                is_perennial=is_perennial,
            )
        )
        existing.add(ticker)
        added += 1
    if added:
        session.commit()
    return added


def update_screener_data(
    session: Session,
    only_watchlist: bool = False,
    on_progress: Callable[[int, int], None] | None = None,
) -> tuple[int, list[str]]:
    """Atualiza cotações, fundamentos e dividendos dos ativos do Screener em paralelo.

    Args:
        session: Sessão do banco.
        only_watchlist: Se True, atualiza apenas os ativos favoritados na Watchlist.
        on_progress: Callback opcional ``(concluidos, total)``.

    Returns:
        Quantidade de ativos atualizados e lista de tickers que falharam.
    """
    ensure_default_universe(session)
    stmt = select(WatchlistAsset)
    if only_watchlist:
        stmt = stmt.where(WatchlistAsset.in_watchlist.is_(True))  # type: ignore[attr-defined]
    records = list(session.exec(stmt).all())
    if not records:
        return 0, []

    snapshots, failed = fetch_many_snapshots([r.ticker for r in records], on_progress=on_progress)
    now = datetime.now(UTC)
    updated = 0

    for rec in records:
        snap = snapshots.get(rec.ticker)
        if snap is None:
            continue
        if snap.price is not None:
            rec.current_price = snap.price
        rec.lpa = snap.lpa
        rec.vpa = snap.vpa
        rec.pl = snap.pl
        rec.pvp = snap.pvp
        rec.roe = snap.roe
        rec.payout = snap.payout
        rec.div_12m = snap.div_12m
        rec.div_avg_5y = snap.div_avg_5y
        rec.profit_margin = snap.profit_margin
        rec.debt_to_equity = snap.debt_to_equity
        rec.drawdown_52w = snap.drawdown_52w
        rec.updated_at = now
        session.add(rec)
        updated += 1

    session.commit()
    return updated, failed


def add_candidate(
    session: Session, ticker: str, class_name: str, segment: str = "", in_watchlist: bool = True
) -> WatchlistAsset:
    """Adiciona ou atualiza um ticker personalizado no Screener/Watchlist."""
    clean = ticker.strip().upper()
    existing = session.exec(select(WatchlistAsset).where(WatchlistAsset.ticker == clean)).first()
    if existing is not None:
        existing.in_watchlist = existing.in_watchlist or in_watchlist
        if segment.strip():
            existing.segment = segment.strip()
        session.add(existing)
        session.commit()
        session.refresh(existing)
        return existing

    seg = segment.strip()
    is_perennial = any(b.lower() in seg.lower() for b in BESST_SECTORS)
    rec = WatchlistAsset(
        ticker=clean,
        class_name=class_name,
        segment=seg,
        is_perennial=is_perennial,
        in_watchlist=in_watchlist,
    )
    session.add(rec)
    session.commit()
    session.refresh(rec)
    return rec


def toggle_watchlist(session: Session, candidate_id: int) -> WatchlistAsset | None:
    """Alterna o destaque de um ativo na Watchlist pessoal."""
    rec = session.get(WatchlistAsset, candidate_id)
    if rec is None:
        return None
    rec.in_watchlist = not rec.in_watchlist
    session.add(rec)
    session.commit()
    session.refresh(rec)
    return rec


def screener_report(
    session: Session,
    class_filter: str = "todos",
    scope: str = "todos",
    segment_filter: str = "",
) -> ScreenerReport:
    """Gera o ranking filtrado do Screener com cobertura dos setores BESST."""
    ensure_default_universe(session)
    records = list(session.exec(select(WatchlistAsset)).all())
    portfolio_assets = list(session.exec(select(Asset)).all())
    owned_tickers = {a.ticker.upper() for a in portfolio_assets}
    owned_segments = " ".join(a.segment.lower() for a in portfolio_assets)

    covered_besst = [s for s in BESST_SECTORS if s.lower() in owned_segments]
    missing_besst = [s for s in BESST_SECTORS if s not in covered_besst]

    all_items: list[ScreenerItem] = []
    for rec in records:
        val = evaluate_asset(
            ValuationInput(
                ticker=rec.ticker,
                class_name=rec.class_name,
                current_price=rec.current_price or 0.0,
                lpa=rec.lpa,
                vpa=rec.vpa,
                pl=rec.pl,
                pvp=rec.pvp,
                roe=rec.roe,
                payout=rec.payout,
                div_12m=rec.div_12m,
                div_avg_5y=rec.div_avg_5y,
            )
        )
        all_items.append(
            ScreenerItem(
                record=rec,
                valuation=val,
                score=score_candidate(rec, val),
                in_portfolio=rec.ticker.upper() in owned_tickers,
                flags=risk_flags(rec, val),
            )
        )

    opportunities = [
        item
        for item in all_items
        if not item.in_portfolio
        and not item.flags
        and (item.valuation.margin_of_safety_pct or -1) >= 0
    ]
    watchlist_count = sum(1 for item in all_items if item.record.in_watchlist)
    segments = sorted({item.record.segment for item in all_items if item.record.segment})
    timestamps = [r.updated_at for r in records if r.updated_at is not None]

    filtered = all_items
    if class_filter in ("Ações", "FIIs"):
        filtered = [i for i in filtered if i.record.class_name == class_filter]
    if scope == "qualidade":
        filtered = [i for i in filtered if not i.flags]
    elif scope == "watchlist":
        filtered = [i for i in filtered if i.record.in_watchlist]
    elif scope == "fora":
        filtered = [i for i in filtered if not i.in_portfolio]
    elif scope == "besst":
        filtered = [i for i in filtered if i.record.is_perennial]
    if segment_filter:
        filtered = [i for i in filtered if i.record.segment == segment_filter]

    filtered.sort(
        key=lambda i: (
            -i.score,
            -(i.valuation.margin_of_safety_pct or -9999.0),
            i.record.ticker,
        )
    )
    return ScreenerReport(
        items=filtered,
        segments=segments,
        opportunity_count=len(opportunities),
        watchlist_count=watchlist_count,
        covered_besst=covered_besst,
        missing_besst=missing_besst,
        last_updated_at=max(timestamps) if timestamps else None,
    )
