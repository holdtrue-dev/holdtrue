from datetime import date, timedelta

from hypothesis import given, strategies as st

from core import nights
from models import Stay
from reference_impl import nights as reference


@st.composite
def _stays(draw: st.DrawFn) -> Stay:
    ci = draw(st.dates(min_value=date(2000, 1, 1), max_value=date(2200, 1, 1)))
    n = draw(st.integers(min_value=1, max_value=9000))
    return Stay(checkin=ci, checkout=ci + timedelta(days=n))


@given(_stays())
def test_agrees_with_reference(stay: Stay) -> None:
    assert nights(stay) == reference(stay)
