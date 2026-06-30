"""The shared types for the nights contract. A Stay validates on construction that
the check-out is after the check-in, so an out-of-order stay cannot even be built."""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel, model_validator


class Stay(BaseModel):
    checkin: date
    checkout: date

    @model_validator(mode="after")
    def _checkout_after_checkin(self) -> "Stay":
        if self.checkout <= self.checkin:
            raise ValueError("checkout must be after checkin")
        return self
