from hypothesis import given, settings, strategies as st

from core import earliest_slot, free_slots, intersect, merge, overlaps
from models import DAY, Interval

settings.register_profile("holdtrue", max_examples=40, deadline=None)
settings.load_profile("holdtrue")


@st.composite
def _interval(draw: st.DrawFn) -> Interval:
    start = draw(st.integers(min_value=0, max_value=DAY - 1))
    end = draw(st.integers(min_value=start + 1, max_value=DAY))
    return Interval(start=start, end=end)


_iv = _interval()
_ivs = st.lists(_iv, max_size=6)


@given(_iv, _iv)
def test_overlaps(a: Interval, b: Interval) -> None:
    assert overlaps(a, b) == (a.start < b.end and b.start < a.end)


@given(_iv, _iv)
def test_intersect(a: Interval, b: Interval) -> None:
    r = intersect(a, b)
    if a.start < b.end and b.start < a.end:
        assert r is not None
        assert r.start == max(a.start, b.start) and r.end == min(a.end, b.end)
    else:
        assert r is None


@given(_ivs)
def test_merge(items: list[Interval]) -> None:
    r = merge(items)
    assert all(r[i].end < r[i + 1].start for i in range(len(r) - 1))
    assert all(any(o.start <= it.start and it.end <= o.end for o in r) for it in items)
    assert all(any(it.start == o.start for it in items)
               and any(it.end == o.end for it in items) for o in r)


@given(_ivs, _iv)
def test_free_slots(busy: list[Interval], window: Interval) -> None:
    r = free_slots(busy, window)
    assert all(window.start <= s.start and s.end <= window.end for s in r)
    assert all(r[i].end < r[i + 1].start for i in range(len(r) - 1))
    assert all(not (s.start < b.end and b.start < s.end) for s in r for b in busy)


@given(_ivs, _iv, st.integers(min_value=1, max_value=DAY))
def test_earliest_slot(busy: list[Interval], window: Interval, duration: int) -> None:
    r = earliest_slot(busy, window, duration)
    if r is not None:
        assert r.end - r.start == duration
        assert window.start <= r.start and r.end <= window.end
        assert all(not (r.start < b.end and b.start < r.end) for b in busy)
