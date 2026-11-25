"""Rotas web (páginas HTML e fragmentos HTMX)."""

import logging
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlmodel import Session

from app.core.config import BASE_DIR
from app.database.models import Asset, AssetStatus, BandMode
from app.database.session import get_session
from app.services import jobs, portfolio, scheduler, screener
from app.services.importer import ensure_classes, import_portfolio_csv, parse_brl
from app.services.rebalance import format_brl, format_pct, plan_contribution

logger = logging.getLogger(__name__)


def _format_brt(dt: datetime | None) -> str:
    if dt is None:
        return "—"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(scheduler.BRT).strftime("%d/%m %H:%M")


router = APIRouter()
templates = Jinja2Templates(directory=BASE_DIR / "app" / "web" / "templates")
templates.env.filters["brl"] = lambda v: "—" if v is None else format_brl(v)
templates.env.filters["pct"] = lambda v, d=1: "—" if v is None else f"{format_pct(v, d)}%"
templates.env.filters["brt"] = _format_brt

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


@router.get("/valuation", response_class=HTMLResponse)
def valuation_page(request: Request, session: SessionDep) -> HTMLResponse:
    """Valuation multi-método (Graham, Bazin, Lynch/PEG, FIIs) e proventos."""
    ensure_classes(session)
    summary = portfolio.summary(session)
    report = portfolio.valuation_report(session)
    context = {
        "active_nav": "valuation",
        "v": report,
        "last_quote_at": summary.last_quote_at,
    }
    return templates.TemplateResponse(request, "valuation.html", context)


@router.get("/jobs/{job_name}", response_class=HTMLResponse)
def job_status(request: Request, job_name: str) -> HTMLResponse:
    """Devolve o status/progresso da tarefa em background para polling HTMX."""
    state = jobs.get_state(job_name)
    headers = {"HX-Refresh": "true"} if state.status == "done" else {}
    return templates.TemplateResponse(
        request, "partials/job_status.html", {"job": state}, headers=headers
    )


@router.post("/valuation/atualizar", response_class=HTMLResponse)
def atualizar_fundamentos(request: Request) -> HTMLResponse:
    """Dispara a coleta paralela de fundamentos em background."""
    state = jobs.trigger(
        "fundamentals", scheduler.run_fundamentals_job, "Coletando fundamentos e dividendos..."
    )
    return templates.TemplateResponse(request, "partials/job_status.html", {"job": state})


@router.get("/screener", response_class=HTMLResponse)
def screener_page(
    request: Request,
    session: SessionDep,
    classe: str = "todos",
    escopo: str = "todos",
    segmento: str = "",
) -> HTMLResponse:
    """Screener de oportunidades fora da carteira e Watchlist."""
    ensure_classes(session)
    summary = portfolio.summary(session)
    report = screener.screener_report(
        session, class_filter=classe, scope=escopo, segment_filter=segmento
    )
    context = {
        "active_nav": "screener",
        "sc": report,
        "classe": classe,
        "escopo": escopo,
        "segmento": segmento,
        "last_quote_at": summary.last_quote_at,
    }
    return templates.TemplateResponse(request, "screener.html", context)


@router.post("/screener/atualizar", response_class=HTMLResponse)
def screener_atualizar(request: Request) -> HTMLResponse:
    """Dispara a sincronização da B3 e avaliação paralela do Screener em background."""
    state = jobs.trigger(
        "screener", scheduler.run_screener_job, "Sincronizando ativos líquidos da B3..."
    )
    return templates.TemplateResponse(request, "partials/job_status.html", {"job": state})


@router.post("/screener/adicionar")
def screener_adicionar(
    session: SessionDep,
    ticker: Annotated[str, Form()],
    class_name: Annotated[str, Form()] = "Ações",
    segment: Annotated[str, Form()] = "",
) -> RedirectResponse:
    """Adiciona um ativo personalizado ao Screener e à Watchlist."""
    if ticker.strip():
        screener.add_candidate(session, ticker=ticker, class_name=class_name, segment=segment)
    return RedirectResponse("/screener?escopo=watchlist", status_code=303)


@router.post("/screener/{candidate_id}/watchlist")
def screener_toggle_watchlist(candidate_id: int, session: SessionDep) -> Response:
    """Marca ou desmarca um ativo na Watchlist pessoal."""
    rec = screener.toggle_watchlist(session, candidate_id)
    if rec is None:
        raise HTTPException(status_code=404, detail="Candidato não encontrado")
    return Response(headers={"HX-Refresh": "true"})


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
    return templates.TemplateResponse(
        request, "partials/plan.html", {"plan": plan, "oob_priorities": True}
    )


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
def atualizar_cotacoes(request: Request) -> HTMLResponse:
    """Dispara a atualização de cotações em background."""
    state = jobs.trigger("quotes", scheduler.run_quotes_job, "Buscando cotações na B3...")
    return templates.TemplateResponse(request, "partials/job_status.html", {"job": state})
