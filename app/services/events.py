"""Monitor de Fatos Relevantes da CVM (IPE), alertas Telegram e resumo opcional por IA."""

import csv
import io
import json
import logging
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from sqlmodel import Session, col, select

from app.core.config import GEMINI_API_KEY, GEMINI_MODEL, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from app.database.models import Asset, MarketEvent, WatchlistAsset

logger = logging.getLogger(__name__)

CVM_IPE_URL = "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/IPE/DADOS/ipe_cia_aberta_{year}.zip"
FNET_SEARCH_URL = "https://fnet.bmfbovespa.com.br/fnet/publico/pesquisarGerenciadorDocumentosDados"
FNET_DOC_URL = "https://fnet.bmfbovespa.com.br/fnet/publico/exibirDocumento?id={doc_id}"

# CNPJs oficiais verificados na CVM/B3 para consulta rápida no Fundos.NET
FII_TICKER_CNPJ: dict[str, str] = {
    "GARE11": "37295919000160",
    "HGLG11": "11728688000147",
    "MXRF11": "97521225000125",
    "GGRC11": "26614291000100",
    "BTCI11": "09552812000114",
    "XPML11": "28757546000100",
    "VGHF11": "36771692000119",
    "PORD11": "17156502000109",
    "KNCR11": "16706958000132",
    "BTLG11": "11839593000109",
    "LVBI11": "30629603000118",
    "VISC11": "17554274000125",
    "HGRU11": "29641226000153",
    "PVBI11": "35652102000176",
    "KNIP11": "24960430000113",
    "CPTS11": "18979895000113",
}

FII_RELEVANT_TERMS = (
    "fato relevante",
    "relatório gerencial",
    "relatorio gerencial",
    "comunicado ao mercado",
    "rendimentos",
)

# Mapeamento Ticker -> substrings normalizadas do Nome_Companhia na CVM
TICKER_COMPANY_HINTS: dict[str, tuple[str, ...]] = {
    "BBAS3": ("BANCO DO BRASIL",),
    "BBSE3": ("BB SEGURIDADE",),
    "EGIE3": ("ENGIE BRASIL",),
    "ITSA3": ("ITAUSA", "ITAÚSA"),
    "ITSA4": ("ITAUSA", "ITAÚSA"),
    "ITUB4": ("ITAU UNIBANCO", "ITAÚ UNIBANCO"),
    "WIZC3": ("WIZ CO", "WIZ SOLU"),
    "TAEE11": ("TRANSMISSORA ALIANCA", "TAESA"),
    "ISAE4": ("ISA ENERGIA", "CTEEP"),
    "CPFE3": ("CPFL ENERGIA",),
    "CMIG4": ("CEMIG", "ENERGETICA DE MINAS"),
    "AURE3": ("AUREN ENERGIA",),
    "SAPR11": ("SANEPAR", "SANEAMENTO DO PARANA"),
    "CSMG3": ("COPASA", "SANEAMENTO DE MINAS"),
    "SBSP3": ("SABESP", "SANEAMENTO BASICO DO ESTADO DE SAO PAULO"),
    "CXSE3": ("CAIXA SEGURIDADE",),
    "PSSA3": ("PORTO SEGURO",),
    "VIVT3": ("TELEFONICA BRASIL", "TELEFÔNICA BRASIL"),
    "TIMS3": ("TIM S.A.", "TIM S/A"),
    "SANB11": ("BANCO SANTANDER",),
    "ABCB4": ("BANCO ABC BRASIL",),
    "VALE3": ("VALE S.A.",),
    "PETR4": ("PETROLEO BRASILEIRO", "PETROBRAS"),
    "WEGE3": ("WEG S.A.",),
    "KLBN11": ("KLABIN",),
    "B3SA3": ("B3 S.A.",),
}

RELEVANT_CATEGORIES = (
    "fato relevante",
    "aviso aos acionistas",
    "comunicado ao mercado",
)


@dataclass
class EventsReport:
    """Visão filtrada do feed de eventos da CVM."""

    events: list[MarketEvent]
    tickers: list[str]
    unread_count: int
    fatos_count: int
    telegram_enabled: bool
    ai_enabled: bool


def _normalize(text: str) -> str:
    return " ".join(text.upper().strip().split())


def _match_ticker(company_name: str, tracked: set[str]) -> str | None:
    norm = _normalize(company_name)
    for ticker in tracked:
        hints = TICKER_COMPANY_HINTS.get(ticker)
        if hints and any(h in norm for h in hints):
            return ticker
    return None


def _is_relevant_category(category: str) -> bool:
    low = category.strip().lower()
    return any(cat in low for cat in RELEVANT_CATEGORIES)


def parse_cvm_ipe_csv(
    csv_text: str, tracked_tickers: set[str], days_back: int = 90
) -> list[MarketEvent]:
    """Filtra o CSV oficial CVM IPE para os tickers monitorados nos últimos ``days_back`` dias.

    Args:
        csv_text: Conteúdo CSV (delimitado por ``;``).
        tracked_tickers: Conjunto de tickers (carteira + watchlist).
        days_back: Janela máxima em dias a partir de hoje.

    Returns:
        Lista de ``MarketEvent`` prontos para persistência.
    """
    cutoff = date.today() - timedelta(days=days_back)
    reader = csv.DictReader(io.StringIO(csv_text.lstrip("\ufeff")), delimiter=";")
    now = datetime.now(UTC)
    events: list[MarketEvent] = []

    for row in reader:
        category = (row.get("Categoria") or "").strip()
        if not _is_relevant_category(category):
            continue

        company = (row.get("Nome_Companhia") or "").strip()
        ticker = _match_ticker(company, tracked_tickers)
        if ticker is None:
            continue

        raw_date = (row.get("Data_Entrega") or row.get("Data_Referencia") or "").strip()[:10]
        try:
            pub_date = date.fromisoformat(raw_date)
        except ValueError:
            continue
        if pub_date < cutoff:
            continue

        protocol = (row.get("Protocolo_Entrega") or "").strip()
        url = (row.get("Link_Download") or "").strip()
        subject = (row.get("Assunto") or row.get("Tipo") or category).strip()
        if not protocol or not url:
            continue

        events.append(
            MarketEvent(
                protocol=protocol,
                ticker=ticker,
                company_name=company,
                category=category,
                subject=subject,
                published_at=pub_date,
                document_url=url,
                created_at=now,
            )
        )
    return events


def _download_cvm_ipe_csv(year: int, timeout: int = 30) -> str | None:
    url = CVM_IPE_URL.format(year=year)
    req = Request(url, headers={"User-Agent": "Midas/1.0"})
    try:
        with urlopen(req, timeout=timeout) as resp:  # noqa: S310
            raw = resp.read()
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            csv_names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
            if not csv_names:
                return None
            return zf.read(csv_names[0]).decode("latin-1", errors="replace")
    except (URLError, TimeoutError, zipfile.BadZipFile, OSError):
        logger.warning("Não foi possível baixar CVM IPE de %d.", year)
        return None


def notify_telegram(event: MarketEvent) -> bool:
    """Envia alerta de evento relevante via Telegram (se configurado no ``.env``)."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False

    lines = [
        f"[{event.ticker}] {event.category}",
        f"{event.subject}",
        f"Data: {event.published_at.strftime('%d/%m/%Y')}",
    ]
    if event.ai_summary:
        lines.append(f"Resumo: {event.ai_summary}")
    lines.append(f"Documento CVM: {event.document_url}")

    payload = json.dumps({"chat_id": TELEGRAM_CHAT_ID, "text": "\n".join(lines)}).encode("utf-8")
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    req = Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(req, timeout=10) as resp:  # noqa: S310
            return int(resp.status) == 200
    except (URLError, TimeoutError, OSError):
        logger.error("Falha ao enviar alerta Telegram para %s.", event.ticker)
        return False


def summarize_event_with_ai(event: MarketEvent) -> tuple[str, str] | None:
    """Gera resumo objetivo e sentimento via Gemini REST API (opcional).

    Returns:
        Tupla ``(sentimento, resumo)`` ou ``None`` se ``GEMINI_API_KEY`` não estiver configurada.
    """
    if not GEMINI_API_KEY:
        return None

    prompt = (
        "Você é um analista fundamentalista objetivo. Analise o cabeçalho deste documento "
        "oficial da CVM e responda APENAS em JSON com as chaves "
        '"sentiment" ("positivo", "neutro" ou "negativo") e "summary" (máximo 2 frases curtas '
        "em português explicando o possível impacto para o acionista de longo prazo).\n\n"
        f"Ticker: {event.ticker}\n"
        f"Companhia: {event.company_name}\n"
        f"Categoria: {event.category}\n"
        f"Assunto: {event.subject}\n"
        f"Data: {event.published_at.isoformat()}"
    )
    body = json.dumps(
        {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": 0.2},
        }
    ).encode("utf-8")
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    )
    req = Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(req, timeout=20) as resp:  # noqa: S310
            data = json.loads(resp.read().decode("utf-8"))
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        parsed = json.loads(text)
        sentiment = str(parsed.get("sentiment", "neutro")).lower().strip()
        if sentiment not in ("positivo", "neutro", "negativo"):
            sentiment = "neutro"
        summary = str(parsed.get("summary", "")).strip()
        return (sentiment, summary) if summary else None
    except (URLError, TimeoutError, KeyError, IndexError, ValueError, OSError):
        logger.error("Falha ao gerar resumo por IA para %s.", event.ticker)
        return None


def parse_fnet_payload(ticker: str, payload: dict[str, object]) -> list[MarketEvent]:
    """Converte a resposta JSON do Fundos.NET (B3) em ``MarketEvent`` relevantes."""
    rows = payload.get("data")
    if not isinstance(rows, list):
        return []
    now = datetime.now(UTC)
    out: list[MarketEvent] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        doc_id = row.get("id")
        cat = str(row.get("categoriaDocumento") or "").strip()
        tipo = str(row.get("tipoDocumento") or "").strip()
        combined = f"{cat} {tipo}".lower()
        if not doc_id or not any(term in combined for term in FII_RELEVANT_TERMS):
            continue

        raw_dt = str(row.get("dataEntrega") or "").strip()[:10]
        try:
            pub_date = datetime.strptime(raw_dt, "%d/%m/%Y").date()
        except ValueError:
            continue

        label_cat = tipo if "relat" in tipo.lower() else (cat or tipo)
        assunto = str(row.get("assunto") or "").strip()
        subject = assunto or (f"{cat} — {tipo}".strip(" —") if tipo else cat)
        company = str(row.get("descricaoFundo") or ticker).strip()

        out.append(
            MarketEvent(
                protocol=f"FNET-{doc_id}",
                ticker=ticker,
                company_name=company,
                category=label_cat,
                subject=subject,
                published_at=pub_date,
                document_url=FNET_DOC_URL.format(doc_id=doc_id),
                created_at=now,
            )
        )
    return out


def _fetch_fii_fnet_events(ticker: str, cnpj: str, days_back: int = 90) -> list[MarketEvent]:
    ini = (date.today() - timedelta(days=days_back)).strftime("%d/%m/%Y")
    fim = date.today().strftime("%d/%m/%Y")
    params = urlencode(
        {
            "d": 0,
            "s": 0,
            "l": 20,
            "o[0][dataEntrega]": "desc",
            "tipoFundo": 1,
            "idCategoriaDocumento": 0,
            "dataInicial": ini,
            "dataFinal": fim,
            "cnpjFundo": cnpj,
        }
    )
    req = Request(
        f"{FNET_SEARCH_URL}?{params}",
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
            "X-Requested-With": "XMLHttpRequest",
        },
    )
    try:
        with urlopen(req, timeout=12) as resp:  # noqa: S310
            payload = json.loads(resp.read().decode("utf-8"))
        return parse_fnet_payload(ticker, payload)
    except (URLError, TimeoutError, ValueError, OSError):
        logger.warning("Falha ao consultar Fundos.NET para %s.", ticker)
        return []


def sync_cvm_events(session: Session, days_back: int = 90) -> tuple[int, int]:
    """Baixa documentos da CVM (ações) e do Fundos.NET/B3 (FIIs), persiste novos e alerta.

    Args:
        session: Sessão do banco.
        days_back: Janela em dias para buscar documentos.

    Returns:
        Tupla ``(novos_eventos, alertas_enviados)``.
    """
    portfolio_tickers = {
        a.ticker.upper() for a in session.exec(select(Asset)).all() if not a.divisible
    }
    watchlist_tickers = {
        w.ticker.upper()
        for w in session.exec(
            select(WatchlistAsset).where(WatchlistAsset.in_watchlist.is_(True))  # type: ignore[attr-defined]
        ).all()
    }
    tracked = portfolio_tickers | watchlist_tickers
    if not tracked:
        return 0, 0

    parsed: list[MarketEvent] = []

    # 1. Ações via CVM Dados Abertos (IPE)
    csv_text = _download_cvm_ipe_csv(date.today().year)
    if csv_text is not None:
        parsed.extend(parse_cvm_ipe_csv(csv_text, tracked, days_back=days_back))

    # 2. FIIs via Fundos.NET (B3) em paralelo
    fii_targets = [(tk, FII_TICKER_CNPJ[tk]) for tk in tracked if tk in FII_TICKER_CNPJ]
    if fii_targets:
        with ThreadPoolExecutor(max_workers=min(3, len(fii_targets))) as pool:
            futures = [
                pool.submit(_fetch_fii_fnet_events, tk, cnpj, days_back) for tk, cnpj in fii_targets
            ]
            for fut in as_completed(futures):
                parsed.extend(fut.result())

    if not parsed:
        return 0, 0

    existing_protocols = {row for row in session.exec(select(MarketEvent.protocol)).all()}

    created = 0
    notified = 0
    for ev in parsed:
        if ev.protocol in existing_protocols:
            continue
        if GEMINI_API_KEY and "fato relevante" in ev.category.lower():
            ai = summarize_event_with_ai(ev)
            if ai is not None:
                ev.sentiment, ev.ai_summary = ai
        if "fato relevante" in ev.category.lower() and notify_telegram(ev):
            ev.notified = True
            notified += 1
        session.add(ev)
        existing_protocols.add(ev.protocol)
        created += 1

    if created:
        session.commit()
    return created, notified


def events_report(
    session: Session,
    ticker_filter: str = "",
    category_filter: str = "",
    only_unread: bool = False,
) -> EventsReport:
    """Retorna o feed de eventos filtrado e contadores para a tela ``/eventos``."""
    all_events = list(
        session.exec(
            select(MarketEvent).order_by(
                col(MarketEvent.published_at).desc(), col(MarketEvent.id).desc()
            )
        ).all()
    )
    tickers = sorted({e.ticker for e in all_events})
    unread_count = sum(1 for e in all_events if not e.is_read)
    fatos_count = sum(1 for e in all_events if "fato relevante" in e.category.lower())

    filtered = all_events
    if ticker_filter:
        filtered = [e for e in filtered if e.ticker == ticker_filter]
    if category_filter:
        filtered = [e for e in filtered if category_filter.lower() in e.category.lower()]
    if only_unread:
        filtered = [e for e in filtered if not e.is_read]

    return EventsReport(
        events=filtered[:100],
        tickers=tickers,
        unread_count=unread_count,
        fatos_count=fatos_count,
        telegram_enabled=bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID),
        ai_enabled=bool(GEMINI_API_KEY),
    )


def toggle_read(session: Session, event_id: int) -> MarketEvent | None:
    """Alterna o status de lido de um evento."""
    ev = session.get(MarketEvent, event_id)
    if ev is None:
        return None
    ev.is_read = not ev.is_read
    session.add(ev)
    session.commit()
    session.refresh(ev)
    return ev


def summarize_by_id(session: Session, event_id: int) -> MarketEvent | None:
    """Gera e persiste o resumo por IA sob demanda para um evento salvo."""
    ev = session.get(MarketEvent, event_id)
    if ev is None:
        return None
    if not ev.ai_summary:
        ai = summarize_event_with_ai(ev)
        if ai is not None:
            ev.sentiment, ev.ai_summary = ai
            session.add(ev)
            session.commit()
            session.refresh(ev)
    return ev
