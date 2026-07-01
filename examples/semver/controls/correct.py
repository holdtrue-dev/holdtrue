"""A correct implementation. compare is written with an explicit field-by-field walk
and max_satisfying with max(), so the held-out test compares two independent
derivations."""
from __future__ import annotations

from models import Constraint, Op, Version


def compare(a: Version, b: Version) -> int:
    for x, y in ((a.major, b.major), (a.minor, b.minor), (a.patch, b.patch)):
        if x != y:
            return 1 if x > y else -1
    return 0


def satisfies(v: Version, c: Constraint) -> bool:
    cmp = compare(v, c.version)
    if c.op == Op.EQ:
        return cmp == 0
    if c.op == Op.GTE:
        return cmp >= 0
    if c.op == Op.GT:
        return cmp > 0
    if c.op == Op.LTE:
        return cmp <= 0
    if c.op == Op.LT:
        return cmp < 0
    if c.op == Op.CARET:
        return v.major == c.version.major and cmp >= 0
    return v.major == c.version.major and v.minor == c.version.minor and cmp >= 0


def satisfies_all(v: Version, constraints: list[Constraint]) -> bool:
    return all(satisfies(v, c) for c in constraints)


def max_satisfying(versions: list[Version], c: Constraint) -> Version | None:
    ok = [v for v in versions if satisfies(v, c)]
    if not ok:
        return None
    return max(ok, key=lambda v: (v.major, v.minor, v.patch))
