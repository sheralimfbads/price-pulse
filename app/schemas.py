
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class Product(BaseModel):
    product_code: str
    product_name_uz: str | None = None
    product_name_ru: str | None = None
    product_name_en: str | None = None
    product_name_uz_cyrillic: str | None = None


class PaginatedProducts(BaseModel):
    items: list[Product]
    total: int
    limit: int
    offset: int


class PriceObservation(BaseModel):
    product_code: str
    product_name_en: str | None = None
    month_start: date
    current_price_uzs_per_kg: Decimal | None = None
    current_price_status: str
    previous_month_start: date | None = None
    previous_price_uzs_per_kg: Decimal | None = None
    previous_price_status: str | None = None
    change_uzs_per_kg: Decimal | None = None
    change_percent: Decimal | None = None


class PaginatedPrices(BaseModel):
    product: Product
    items: list[PriceObservation]
    total: int
    limit: int
    offset: int


class Overview(BaseModel):
    latest_month: date | None = None
    product_count: int
    available_observations: int
    unavailable_observations: int
    total_observations: int
    latest_source_snapshot: str | None = None
    latest_source_fetched_at_utc: datetime | None = None


class Mover(BaseModel):
    product_code: str
    product_name_en: str | None = None
    month_start: date
    comparison_month_start: date | None = None
    current_price_uzs_per_kg: Decimal | None = None
    price_12_months_ago_uzs_per_kg: Decimal | None = None
    change_uzs_per_kg: Decimal | None = None
    yoy_change_percent: Decimal | None = None
    rank: int = Field(ge=1)


class LatestMovers(BaseModel):
    comparison_month: date | None = None
    latest_month: date | None = None
    increases: list[Mover]
    decreases: list[Mover]


class HealthLive(BaseModel):
    status: Literal["ok"] = "ok"


class HealthReady(BaseModel):
    status: Literal["ok"] = "ok"
    database: Literal["ready"] = "ready"
