"""Rotas web (páginas HTML e fragmentos HTMX)."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlmodel import Session

from app.core.config import BASE_DIR
from app.database.models import Asset, AssetStatus, BandMode
from app.database.session import get_session
from app.services import portfolio
from app.services.importer import ensure_classes, import_portfolio_csv, parse_brl
from app.services.rebalance import format_brl, format_pct, plan_contribution

logger = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory=BASE_DIR / "app" / "web" / "templates")
templates.env.filters["brl"] = lambda v: "—" if v is None else format_brl(v)
templates.env.filters["pct"] = lambda v, d=1: "—" if v is None else f"{format_pct(v, d)}%"

SessionDep = Annotated[Session, Depends(get_session)]
DEFAULT_CONTRIBUTION = 400.0


def _parse_number(raw: str) -> float:
    """Aceita tanto ``1234.5`` quanto ``1.234,50``."""
    return parse_brl(raw) if "," in raw else float(raw)


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request, session: SessionDep) -> HTMLResponse:
    """Dashboard operacional: simulador de aporte rápido, prioridades e plano."""
    ensure_classes(session)
    summary = portfolio.summary(session)
    classes, assets = portfolio.to_engine_inputs(session)
    plan = plan_contribution(DEFAULT_CONTRIBUTION, classes, assets) if summary.total > 0 else None
    context = {
        "active_nav": "dashboard",
        "s": summary,
        "plan": plan,
        "default_amount": int(DEFAULT_CONTRIBUTION),
        "last_quote_at": summary.last_quote_at,
    }
    return templates.TemplateResponse(request, "dashboard.html", context)


@router.get("/estatisticas", response_class=HTMLResponse)
def estatisticas_page(request: Request, session: SessionDep, q: str = "") -> HTMLResponse:
    """Visão analítica: KPIs, mapa de alocação, segmentos e tabela completa."""
    ensure_classes(session)
    summary = portfolio.summary(session)
    context = {
        "active_nav": "estatisticas",
        "s": summary,
        "statuses": list(AssetStatus),
        "query": q.strip(),
        "last_quote_at": summary.last_quote_at,
    }
    return templates.TemplateResponse(request, "estatisticas.html", context)


@router.get("/aporte", response_class=HTMLResponse)
def aporte_page(request: Request, session: SessionDep) -> HTMLResponse:
    """Página dedicada de simulação de aporte."""
    summary = portfolio.summary(session)
    context = {
        "active_nav": "aporte",
        "default_amount": int(DEFAULT_CONTRIBUTION),
        "last_quote_at": summary.last_quote_at,
    }
    return templates.TemplateResponse(request, "aporte.html", context)


@router.post("/aporte/simular", response_class=HTMLResponse)
def aporte_simular(
    request: Request, session: SessionDep, valor: Annotated[str, Form()]
) -> HTMLResponse:
    """Calcula o plano de aporte e devolve o fragmento HTML."""
    classes, assets = portfolio.to_engine_inputs(session)
    plan = plan_contribution(_parse_number(valor), classes, assets)
    return templates.TemplateResponse(request, "partials/plan.html", {"plan": plan})


@router.post("/ativos/{asset_id}")
def update_asset(
    asset_id: int,
    session: SessionDep,
    status: Annotated[str | None, Form()] = None,
    weight: Annotated[str | None, Form()] = None,
    price_ceiling: Annotated[str | None, Form()] = None,
    segment: Annotated[str | None, Form()] = None,
) -> Response:
    """Edição inline de um ativo; força o recarregamento da página via HTMX."""
    asset = session.get(Asset, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Ativo não encontrado")
    if status is not None:
        asset.status = AssetStatus(status)
    if weight and weight.strip():
        asset.weight = _parse_number(weight)
    if price_ceiling is not None:
        asset.price_ceiling = _parse_number(price_ceiling) if price_ceiling.strip() else None
    if segment is not None:
        asset.segment = segment.strip()
    session.add(asset)
    session.commit()
    return Response(headers={"HX-Refresh": "true"})


@router.get("/metas", response_class=HTMLResponse)
def metas_page(request: Request, session: SessionDep) -> HTMLResponse:
    """Edição das metas e bandas por classe."""
    ensure_classes(session)
    classes, _ = portfolio.load(session)
    summary = portfolio.summary(session)
    context = {
        "active_nav": "metas",
        "classes": classes,
        "band_modes": list(BandMode),
        "last_quote_at": summary.last_quote_at,
    }
    return templates.TemplateResponse(request, "metas.html", context)


@router.post("/metas")
async def metas_save(request: Request, session: SessionDep) -> RedirectResponse:
    """Salva metas e bandas."""
    form = await request.form()
    for asset_class in portfolio.load(session)[0]:
        target = form.get(f"target_{asset_class.id}")
        band = form.get(f"band_{asset_class.id}")
        mode = form.get(f"mode_{asset_class.id}")
        if isinstance(target, str) and target.strip():
            asset_class.target_pct = _parse_number(target)
        if isinstance(band, str) and band.strip():
            asset_class.band_pp = _parse_number(band)
        if isinstance(mode, str) and mode.strip():
            asset_class.band_mode = BandMode(mode)
        session.add(asset_class)
    session.commit()
    return RedirectResponse("/metas?ok=1", status_code=303)


@router.get("/importar", response_class=HTMLResponse)
def importar_page(request: Request, session: SessionDep) -> HTMLResponse:
    """Formulário de importação da planilha."""
    summary = portfolio.summary(session)
    context = {"active_nav": "importar", "last_quote_at": summary.last_quote_at}
    return templates.TemplateResponse(request, "importar.html", context)


@router.post("/importar", response_class=HTMLResponse)
async def importar(request: Request, session: SessionDep, arquivo: UploadFile) -> HTMLResponse:
    """Importa o CSV enviado."""
    raw = await arquivo.read()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
    count = import_portfolio_csv(session, text)
    summary = portfolio.summary(session)
    context = {
        "active_nav": "importar",
        "msg": f"{count} ativos importados/atualizados.",
        "last_quote_at": summary.last_quote_at,
    }
    return templates.TemplateResponse(request, "importar.html", context)


@router.post("/cotacoes/atualizar", response_class=HTMLResponse)
def atualizar_cotacoes(session: SessionDep) -> HTMLResponse:
    """Busca as cotações mais recentes."""
    from app.services.quotes import update_quotes

    try:
        updated, failed = update_quotes(session)
    except Exception as exc:  # yfinance propaga erros de rede de várias bibliotecas
        logger.exception("Falha ao atualizar cotações")
        return HTMLResponse(f'<span class="text-xs text-rose-400">Erro: {exc}</span>')
    msg = f"{updated} cotações atualizadas."
    if failed:
        msg += f" Falharam: {', '.join(failed)}"
    return HTMLResponse(
        f'<span class="text-xs text-sage">{msg}</span>',
        headers={"HX-Refresh": "true"},
    )
