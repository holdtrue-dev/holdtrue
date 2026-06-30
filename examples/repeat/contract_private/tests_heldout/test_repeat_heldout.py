from hypothesis import given, strategies as st

from core import repeat
from reference_impl import repeat as reference


@given(st.text(max_size=30), st.integers(min_value=0, max_value=80))
def test_repeat_agrees_with_reference(s: str, n: int) -> None:
    assert repeat(s, n) == reference(s, n)
