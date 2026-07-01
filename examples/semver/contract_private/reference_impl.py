"""Reference oracle. Author-side, used by the held-out differential test only."""
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
    return all(satisfies(v, c) for c in constraints)


def max_satisfying(versions: list[Version], c: Constraint) -> Version | None:
    ok = [v for v in versions if satisfies(v, c)]
    if not ok:
        return None
    best = ok[0]
    for v in ok[1:]:
        if compare(v, best) > 0:
            best = v
    return best
