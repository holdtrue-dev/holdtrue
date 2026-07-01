from hypothesis import given, strategies as st

from core import add_seconds, is_am, minutes_between, to_seconds
from reference_impl import add_seconds as r_add
from reference_impl import is_am as r_is_am
from reference_impl import minutes_between as r_between
from reference_impl import to_seconds as r_to_seconds

_sec = st.integers(min_value=0, max_value=86399)
_delta = st.integers(min_value=-86400, max_value=86400)


@given(st.integers(min_value=0, max_value=23),
       st.integers(min_value=0, max_value=59),
       st.integers(min_value=0, max_value=59))
def test_to_seconds_agrees(h: int, m: int, s: int) -> None:
    assert to_seconds(h, m, s) == r_to_seconds(h, m, s)


@given(_sec, _delta)
def test_add_agrees(sec: int, delta: int) -> None:
    assert add_seconds(sec, delta) == r_add(sec, delta)


@given(_sec)
def test_is_am_agrees(sec: int) -> None:
    assert is_am(sec) == r_is_am(sec)


@given(_sec, _sec)
def test_between_agrees(a: int, b: int) -> None:
    assert minutes_between(a, b) == r_between(a, b)
