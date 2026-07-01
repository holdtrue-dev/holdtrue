"""The shared types for the billing contract. pydantic validates them on every
construction, so the field bounds (a quantity is positive, a price is not negative, a
rate is 0..10000 basis points) are enforced at runtime. CrossHair cannot reason over
these, so the functions that take them are ENFORCED, not proven."""
from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field, NonNegativeInt, PositiveInt

Bps = Annotated[int, Field(ge=0, le=10000)]  # basis points: 0..100%


class LineItem(BaseModel):
    qty: PositiveInt
    unit_price_cents: NonNegativeInt
    discount_bps: Bps


class Invoice(BaseModel):
    items: list[LineItem]
    tax_bps: Bps
    coupon_cents: NonNegativeInt


class Receipt(BaseModel):
    subtotal_cents: NonNegativeInt
    tax_cents: NonNegativeInt
    total_cents: NonNegativeInt
