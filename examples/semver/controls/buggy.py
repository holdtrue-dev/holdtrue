"""A buggy implementation. Three functions are right; satisfies_all uses any() instead
of all(), so a version passes as long as it meets one constraint rather than every
one (and an empty set wrongly matches nothing). The contract pins satisfies_all as the
conjunction of the constraints, so the verdict is FAILED, naming satisfies_all."""
from __future__ import annotations

from models import Constraint, Op, Version


def compare(a: Version, b: Version) -> int:
    ta = (a.major, a.minor, a.patch)
    tb = (b.major, b.minor, b.patch)
    return (ta > tb) - (ta < tb)


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
    return any(satisfies(v, c) for c in constraints)  # bug: any instead of all


def max_satisfying(versions: list[Version], c: Constraint) -> Version | None:
    ok = [v for v in versions if satisfies(v, c)]
    if not ok:
        return None
    return max(ok, key=lambda v: (v.major, v.minor, v.patch))
