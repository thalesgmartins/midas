"""Leitura da planilha da carteira (CSV separado por ';', formato pt-BR)."""

import csv
import io

from sqlmodel import Session, select

from app.database.models import Asset, AssetClass

DEFAULT_CLASSES: list[tuple[str, float, float, int]] = [
    ("Ações", 25.0, 5.0, 1),
    ("FIIs", 25.0, 5.0, 2),
    ("ETFs", 25.0, 5.0, 3),
    ("Renda Fixa", 25.0, 5.0, 4),
]

DEFAULT_SEGMENTS: dict[str, str] = {
    "EGIE3": "Energia",
    "BBAS3": "Bancos",
    "ITSA3": "Holding (Bancos)",
    "WIZC3": "Seguros (Corretora)",
    "BBSE3": "Seguros",
    "GARE11": "Tijolo · Híbrido (Varejo/Logística)",
    "HGLG11": "Tijolo · Logística",
    "MXRF11": "Papel · Híbrido",
    "GGRC11": "Tijolo · Logística",
    "BTCI11": "Papel",
    "XPML11": "Tijolo · Shopping",
    "VGHF11": "Papel · Multiestratégia",
    "PORD11": "Papel",
    "XPCA11": "Fiagro · Papel",
    "KNCR11": "Papel · High Grade",
    "WRLD11": "Global (MSCI World)",
}


def parse_brl(raw: str | None) -> float:
    """Converte textos como ``"R$ 1.234,56"`` ou ``"-11,86%"`` para float.

    Args:
        raw: Texto no formato brasileiro; vazio ou ``None`` vira 0.

    Returns:
        Valor numérico.

    Raises:
        ValueError: Se o texto não for numérico.
    """
    if not raw:
        return 0.0
    cleaned = raw.replace("R$", "").replace("%", "").replace("\xa0", "").strip()
    if not cleaned:
        return 0.0
    return float(cleaned.replace(".", "").replace(",", "."))


def ensure_classes(session: Session) -> dict[str, AssetClass]:
    """Garante que as classes padrão existam e retorna todas indexadas por nome."""
    existing = {c.name: c for c in session.exec(select(AssetClass)).all()}
    for name, target, band, order in DEFAULT_CLASSES:
        if name not in existing:
            existing[name] = AssetClass(
                name=name, target_pct=target, band_pp=band, sort_order=order
            )
            session.add(existing[name])
    session.commit()
    return existing


def import_portfolio_csv(session: Session, content: str) -> int:
    """Cria ou atualiza ativos a partir do CSV da planilha.

    Reimportar atualiza quantidades e preços, preservando status, preço teto e
    segmento editados na interface. O "% Ideal" vira peso relativo dentro da classe.

    Args:
        session: Sessão do banco.
        content: Conteúdo do CSV.

    Returns:
        Número de ativos importados/atualizados.
    """
    classes = ensure_classes(session)
    reader = csv.DictReader(io.StringIO(content.lstrip("\ufeff")), delimiter=";")
    count = 0
    for row in reader:
        class_name = (row.get("Tipo de ativo") or "").strip()
        ticker = (row.get("Ativo") or "").strip()
        if not class_name or not ticker:
            continue
        if class_name not in classes:
            classes[class_name] = AssetClass(name=class_name, sort_order=99)
            session.add(classes[class_name])
            session.flush()

        asset_class_id = classes[class_name].id
        if asset_class_id is None:
            raise ValueError(f"Classe {class_name} sem id após flush")
        asset = session.exec(select(Asset).where(Asset.ticker == ticker)).first()
        if asset is None:
            asset = Asset(ticker=ticker, asset_class_id=asset_class_id)

        quantity = parse_brl(row.get("Quant."))
        asset.asset_class_id = asset_class_id
        asset.divisible = quantity == 0
        if asset.divisible:
            asset.balance = parse_brl(row.get("Saldo"))
        else:
            asset.quantity = quantity
            asset.avg_price = parse_brl(row.get("Preço Médio"))
            asset.current_price = parse_brl(row.get("Preço Atual"))
        asset.weight = parse_brl(row.get("% Ideal"))
        if not asset.segment:
            fallback = "Renda Fixa · Pós-fixado" if asset.divisible else ""
            asset.segment = DEFAULT_SEGMENTS.get(ticker, fallback)
        session.add(asset)
        count += 1
    session.commit()
    return count
