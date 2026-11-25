"""Modelos persistidos da carteira."""

from datetime import date, datetime
from enum import StrEnum
from typing import Optional

from sqlalchemy import Column, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlmodel import Field, Relationship, SQLModel


class AssetStatus(StrEnum):
    """Situação de um ativo perante o motor de aporte."""

    ATIVO = "ativo"
    EM_REVISAO = "em_revisao"  # tese congelada: sem aporte e sem sugestão de venda


class BandMode(StrEnum):
    """Regra de banda de desbalanceamento de uma classe."""

    PP = "pp"  # faixa fixa em pontos percentuais: [meta - banda, meta + banda]
    HALF_DOUBLE = "half_double"  # regra metade/dobro: [meta / 2, meta * 2]


class AssetClass(SQLModel, table=True):
    """Classe de ativo (Ações, FIIs, ETFs, Renda Fixa...) com meta e banda de tolerância."""

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True)
    target_pct: float = 0.0
    band_pp: float = 5.0
    band_mode: BandMode = Field(
        default=BandMode.PP,
        sa_column=Column(
            SAEnum(BandMode, values_callable=lambda enum: [member.value for member in enum]),
            nullable=False,
            server_default=BandMode.PP.value,
        ),
    )
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
    fundamentals: Optional["AssetFundamentals"] = Relationship(  # noqa: UP045
        back_populates="asset", sa_relationship_kwargs={"uselist": False}
    )

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


class AssetFundamentals(SQLModel, table=True):
    """Indicadores fundamentalistas e proventos coletados para um ativo."""

    id: int | None = Field(default=None, primary_key=True)
    asset_id: int = Field(foreign_key="asset.id", unique=True, index=True)

    lpa: float | None = None  # Lucro por ação (12m)
    vpa: float | None = None  # Valor patrimonial por ação/cota
    pl: float | None = None  # Preço / Lucro
    pvp: float | None = None  # Preço / Valor Patrimonial
    roe: float | None = None  # Retorno sobre patrimônio líquido (decimal, ex: 0.20 = 20%)
    payout: float | None = None  # Payout (decimal, ex: 0.40 = 40%)
    div_12m: float | None = None  # Proventos por cota nos últimos 12 meses (R$)
    div_avg_5y: float | None = None  # Média anual de proventos até 5 anos (R$)

    updated_at: datetime | None = None

    asset: Asset | None = Relationship(back_populates="fundamentals")


class WatchlistAsset(SQLModel, table=True):
    """Ativo candidato monitorado no Screener e na Watchlist."""

    id: int | None = Field(default=None, primary_key=True)
    ticker: str = Field(index=True, unique=True)
    class_name: str = "Ações"
    segment: str = ""
    is_perennial: bool = False
    in_watchlist: bool = False

    current_price: float | None = None
    lpa: float | None = None
    vpa: float | None = None
    pl: float | None = None
    pvp: float | None = None
    roe: float | None = None
    payout: float | None = None
    div_12m: float | None = None
    div_avg_5y: float | None = None
    profit_margin: float | None = None  # Margem líquida (decimal, ex: 0.15 = 15%)
    debt_to_equity: float | None = None  # Dívida / PL em % (ex: 120.0 = 120%)
    drawdown_52w: float | None = None  # Queda desde a máxima de 52 semanas em % (negativo)
    updated_at: datetime | None = None


class PricePoint(SQLModel, table=True):
    """Fechamento diário histórico usado para volatilidade, correlação e cenários."""

    __table_args__ = (UniqueConstraint("ticker", "ref_date", name="uq_pricepoint_ticker_date"),)

    id: int | None = Field(default=None, primary_key=True)
    ticker: str = Field(index=True)
    ref_date: date = Field(index=True)
    close: float
