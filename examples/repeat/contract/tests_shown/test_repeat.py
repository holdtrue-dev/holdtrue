from hypothesis import given, strategies as st

from core import repeat


@given(st.text(max_size=20), st.integers(min_value=0, max_value=50))
def test_repeat_is_concatenation(s: str, n: int) -> None:
    assert repeat(s, n) == s * n
