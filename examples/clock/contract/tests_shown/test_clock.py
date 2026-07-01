from hypothesis import given, strategies as st

from core import add_seconds, is_am, minutes_between, to_seconds

_sec = st.integers(min_value=0, max_value=86399)
_delta = st.integers(min_value=-86400, max_value=86400)


@given(st.integers(min_value=0, max_value=23),
       st.integers(min_value=0, max_value=59),
       st.integers(min_value=0, max_value=59))
def test_to_seconds(h: int, m: int, s: int) -> None:
    assert to_seconds(h, m, s) == h * 3600 + m * 60 + s


@given(_sec, _delta)
def test_add_seconds(sec: int, delta: int) -> None:
    result = add_seconds(sec, delta)
    assert result == (sec + delta) % 86400
    assert 0 <= result <= 86399


@given(_sec)
def test_is_am(sec: int) -> None:
    assert is_am(sec) == (sec < 43200)


@given(_sec, _sec)
def test_minutes_between(a: int, b: int) -> None:
    assert minutes_between(a, b) == ((b - a) % 86400) // 60
