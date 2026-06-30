"""The shared types for the pagination contract. The bounds (a non-negative total, a
page size from 1 to 100, a page number from 1) are validated on construction, so a
request out of those bounds cannot be built."""
from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field, NonNegativeInt, PositiveInt


class PageRequest(BaseModel):
    total: NonNegativeInt
    page_size: Annotated[int, Field(ge=1, le=100)]
    page: PositiveInt


class Page(BaseModel):
    offset: NonNegativeInt
    limit: PositiveInt
    total_pages: NonNegativeInt
