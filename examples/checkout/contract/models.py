"""The shared types for the checkout contract. Both the contract and the
implementation import these; pydantic validates them on every construction, so the
field bounds (a quantity is positive, a price is not negative, a discount is a
percentage) are enforced at runtime."""
from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field, NonNegativeInt, PositiveInt


class LineItem(BaseModel):
    sku: str
    qty: PositiveInt
    unit_price_cents: NonNegativeInt


class Cart(BaseModel):
    items: list[LineItem]
    discount_pct: Annotated[int, Field(ge=0, le=100)]


class Receipt(BaseModel):
    subtotal_cents: NonNegativeInt
    discount_cents: NonNegativeInt
    total_cents: NonNegativeInt
