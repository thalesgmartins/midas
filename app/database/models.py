"""Modelos persistidos da carteira."""

from datetime import datetime
from enum import StrEnum

from sqlmodel import Field, Relationship, SQLModel


class AssetStatus(StrEnum):
    """Situação de um ativo perante o motor de aporte."""

    ATIVO = "ativo"
    EM_REVISAO = "em_revisao"  # tese congelada: sem aporte e sem sugestão de venda


class AssetClass(SQLModel, table=True):
    """Classe de ativo (Ações, FIIs, ETFs, Renda Fixa...) com meta e banda de tolerância."""

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True)
    target_pct: float = 0.0
    band_pp: float = 5.0
    sort_order: int = 0

    assets: list["Asset"] = Relationship(back_populates="asset_class")


class Asset(SQLModel, table=True):
    """Posição em um ativo. Ativos divisíveis (renda fixa) usam ``balance`` em vez de cotas."""

    id: int | None = Field(default=None, primary_key=True)
    ticker: str = Field(index=True, unique=True)
    asset_class_id: int = Field(foreign_key="assetclass.id")
    segment: str = ""

    quantity: float = 0.0
    avg_price: float = 0.0
    current_price: float = 0.0

    divisible: bool = False
    balance: float = 0.0

    weight: float = 1.0
    status: AssetStatus = AssetStatus.ATIVO
    price_ceiling: float | None = None
    notes: str = ""

    price_updated_at: datetime | None = None

    asset_class: AssetClass | None = Relationship(back_populates="assets")

    @property
    def value(self) -> float:
        """Valor de mercado atual da posição."""
        return self.balance if self.divisible else self.quantity * self.current_price

    @property
    def cost(self) -> float:
        """Custo de aquisição da posição (quantidade x preço médio)."""
        return self.balance if self.divisible else self.quantity * self.avg_price

    @property
    def variation_pct(self) -> float | None:
        """Variação do preço atual sobre o preço médio, em %."""
        if self.divisible or not self.avg_price:
            return None
        return (self.current_price / self.avg_price - 1) * 100
