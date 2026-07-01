"""Reference oracle. Author-side, used by the held-out differential test only.

Five independent, correct implementations over the shared Interval type. The
differential test pins the parts the runtime contract cannot state in a single
lambda: that merge covers exactly the union, that free_slots leaves no free minute
behind, and that earliest_slot really returns the earliest fit.
"""
from __future__ import annotations

from models import Interval


def overlaps(a: Interval, b: Interval) -> bool:
    return a.start < b.end and b.start < a.end


def intersect(a: Interval, b: Interval) -> Interval | None:
    lo = max(a.start, b.start)
    hi = min(a.end, b.end)
    if lo < hi:
        return Interval(start=lo, end=hi)
    return None


def merge(items: list[Interval]) -> list[Interval]:
    out: list[Interval] = []
    for it in sorted(items, key=lambda x: x.start):
        if out and it.start <= out[-1].end:
            last = out[-1]
            out[-1] = Interval(start=last.start, end=max(last.end, it.end))
        else:
            out.append(it)
    return out


def free_slots(busy: list[Interval], window: Interval) -> list[Interval]:
    out: list[Interval] = []
    cursor = window.start
    for b in merge(busy):
        if b.end <= window.start or b.start >= window.end:
            continue
        s = max(b.start, window.start)
        if s > cursor:
            out.append(Interval(start=cursor, end=s))
        cursor = max(cursor, min(b.end, window.end))
    if cursor < window.end:
        out.append(Interval(start=cursor, end=window.end))
    return out


def earliest_slot(busy: list[Interval], window: Interval,
                  duration: int) -> Interval | None:
    for slot in free_slots(busy, window):
        if slot.end - slot.start >= duration:
            return Interval(start=slot.start, end=slot.start + duration)
    return None
