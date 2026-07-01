"""The shared types for the semver contract: a version, a constraint operator, and a
constraint. pydantic validates them on construction (the numbers are non-negative).
CrossHair cannot reason over these, so the functions are enforced at runtime."""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, NonNegativeInt


class Op(str, Enum):
    EQ = "=="
    GTE = ">="
    GT = ">"
    LTE = "<="
    LT = "<"
    CARET = "^"
    TILDE = "~"


class Version(BaseModel):
    major: NonNegativeInt
    minor: NonNegativeInt
    patch: NonNegativeInt


class Constraint(BaseModel):
    op: Op
    version: Version
