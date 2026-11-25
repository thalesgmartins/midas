"""Sincronização automática de ativos líquidos listados na B3 via brapi.dev."""

import json
import logging
import re
from urllib.error import URLError
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

BRAPI_LIST_URL = "https://brapi.dev/api/quote/list?sortBy=volume&sortOrder=desc&limit=400"
MIN_DAILY_VOLUME = 500_000  # filtra ativos sem liquidez
MAX_STOCKS = 50
MAX_FIIS = 25

_STOCK_RE = re.compile(r"^[A-Z]{4}(3|4|5|6|11)$")
_FII_RE = re.compile(r"^[A-Z]{4}11$")

_SECTOR_MAP: dict[str, tuple[str, bool]] = {
    "finance": ("Bancos", True),
    "utilities": ("Energia", True),
    "communications": ("Telecom", True),
    "energy minerals": ("Petróleo", False),
    "non-energy minerals": ("Mineração", False),
    "process industries": ("Indústria", False),
    "producer manufacturing": ("Indústria", False),
    "retail trade": ("Varejo", False),
    "consumer non-durables": ("Consumo", False),
    "consumer services": ("Serviços", False),
    "health services": ("Saúde", False),
    "health technology": ("Saúde", False),
    "technology services": ("Tecnologia", False),
    "transportation": ("Logística", False),
    "commercial services": ("Serviços", False),
    "industrial services": ("Serviços Industriais", False),
}


def _map_sector(raw_sector: str | None, asset_type: str) -> tuple[str, bool]:
    if asset_type == "fund":
        return "FII", False
    if not raw_sector:
        return "Outros", False
    key = raw_sector.strip().lower()
    if key in _SECTOR_MAP:
        return _SECTOR_MAP[key]
    return raw_sector.strip(), False


def fetch_b3_liquid_universe(timeout: int = 15) -> list[tuple[str, str, str, bool]]:
    """Busca ações e FIIs líquidos da B3 na API pública da brapi.dev.

    Args:
        timeout: Timeout da requisição HTTP em segundos.

    Returns:
        Lista de tuplas ``(ticker, class_name, segment, is_perennial)``.
        Retorna lista vazia se a API estiver indisponível.
    """
    req = Request(BRAPI_LIST_URL, headers={"User-Agent": "Midas/1.0"})
    try:
        with urlopen(req, timeout=timeout) as resp:  # noqa: S310
            payload = json.loads(resp.read().decode("utf-8"))
    except (URLError, TimeoutError, ValueError, OSError):
        logger.warning("Não foi possível consultar catálogo B3 na brapi.dev; mantendo lista atual.")
        return []

    raw_items = payload.get("stocks") or []
    stocks: list[tuple[str, str, str, bool]] = []
    fiis: list[tuple[str, str, str, bool]] = []

    for item in raw_items:
        ticker = str(item.get("stock") or "").strip().upper()
        asset_type = str(item.get("type") or "").strip().lower()
        volume = float(item.get("volume") or 0)
        close = float(item.get("close") or 0)
        if not ticker or close <= 0 or (volume * close) < MIN_DAILY_VOLUME:
            continue

        if asset_type == "fund" and _FII_RE.match(ticker) and len(fiis) < MAX_FIIS:
            seg, perennial = _map_sector(item.get("sector"), asset_type)
            fiis.append((ticker, "FIIs", seg, perennial))
        elif asset_type == "stock" and _STOCK_RE.match(ticker) and len(stocks) < MAX_STOCKS:
            seg, perennial = _map_sector(item.get("sector"), asset_type)
            stocks.append((ticker, "Ações", seg, perennial))

    return stocks + fiis
