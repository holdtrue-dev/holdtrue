"""The shared type for the scheduler contract. An Interval validates on construction
that it is a real span inside a single day (0 <= start < end <= 1440), so a backwards
or out-of-day interval cannot even be built. Both the contract and the implementation
import this; pydantic validates it on every construction, so the bounds are enforced
at runtime."""
from __future__ import annotations

from pydantic import BaseModel, model_validator

DAY = 1440  # minutes in a day


class Interval(BaseModel):
    start: int
    end: int

    @model_validator(mode="after")
    def _within_day(self) -> "Interval":
        if not (0 <= self.start < self.end <= DAY):
            raise ValueError("interval must satisfy 0 <= start < end <= 1440")
        return self
