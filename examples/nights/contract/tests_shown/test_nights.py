from datetime import date, timedelta

from hypothesis import given, strategies as st

from core import nights
from models import Stay


@st.composite
def _stays(draw: st.DrawFn) -> Stay:
    ci = draw(st.dates(min_value=date(2000, 1, 1), max_value=date(2100, 1, 1)))
    n = draw(st.integers(min_value=1, max_value=3650))
    return Stay(checkin=ci, checkout=ci + timedelta(days=n))


@given(_stays())
def test_nights_is_the_day_span(stay: Stay) -> None:
    assert nights(stay) == (stay.checkout - stay.checkin).days
    assert nights(stay) >= 1
