from hypothesis import given, settings, strategies as st

from core import earliest_slot, free_slots, intersect, merge, overlaps
from models import DAY, Interval
from reference_impl import earliest_slot as r_earliest
from reference_impl import free_slots as r_free
from reference_impl import intersect as r_intersect
from reference_impl import merge as r_merge
from reference_impl import overlaps as r_overlaps

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
def test_overlaps_agrees(a: Interval, b: Interval) -> None:
    assert overlaps(a, b) == r_overlaps(a, b)


@given(_iv, _iv)
def test_intersect_agrees(a: Interval, b: Interval) -> None:
    assert intersect(a, b) == r_intersect(a, b)


@given(_ivs)
def test_merge_agrees(items: list[Interval]) -> None:
    assert merge(items) == r_merge(items)


@given(_ivs, _iv)
def test_free_slots_agrees(busy: list[Interval], window: Interval) -> None:
    assert free_slots(busy, window) == r_free(busy, window)


@given(_ivs, _iv, st.integers(min_value=1, max_value=DAY))
def test_earliest_agrees(busy: list[Interval], window: Interval, duration: int) -> None:
    assert earliest_slot(busy, window, duration) == r_earliest(busy, window, duration)
