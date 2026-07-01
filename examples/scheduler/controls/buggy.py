"""A buggy implementation. Four functions are right; merge forgets to sort its input
first, so on out-of-order intervals it swallows or misplaces spans. The contract
requires the merged output to be sorted, disjoint, and to cover every input, so the
verdict is FAILED and names merge."""
from __future__ import annotations

from models import Interval


def overlaps(a: Interval, b: Interval) -> bool:
    return a.start < b.end and b.start < a.end


def intersect(a: Interval, b: Interval) -> Interval | None:
    lo = max(a.start, b.start)
    hi = min(a.end, b.end)
    return Interval(start=lo, end=hi) if lo < hi else None


def merge(items: list[Interval]) -> list[Interval]:
    out: list[Interval] = []
    for it in items:  # bug: not sorted first
        if out and it.start <= out[-1].end:
            out[-1] = Interval(start=out[-1].start, end=max(out[-1].end, it.end))
        else:
            out.append(it)
    return out


def free_slots(busy: list[Interval], window: Interval) -> list[Interval]:
    out: list[Interval] = []
    cursor = window.start
    for b in merge(sorted(busy, key=lambda x: x.start)):
        s = max(b.start, window.start)
        e = min(b.end, window.end)
        if e <= window.start or s >= window.end:
            continue
        if s > cursor:
            out.append(Interval(start=cursor, end=s))
        cursor = max(cursor, e)
    if cursor < window.end:
        out.append(Interval(start=cursor, end=window.end))
    return out


def earliest_slot(busy: list[Interval], window: Interval,
                  duration: int) -> Interval | None:
    for slot in free_slots(busy, window):
        if slot.end - slot.start >= duration:
            return Interval(start=slot.start, end=slot.start + duration)
    return None
