from hypothesis import given, strategies as st

from core import checkout
from models import Cart, LineItem
from reference_impl import checkout as reference

_items = st.lists(
    st.builds(LineItem, sku=st.text(min_size=1, max_size=8),
              qty=st.integers(min_value=1, max_value=100),
              unit_price_cents=st.integers(min_value=0, max_value=100_000)),
    max_size=10,
)
_carts = st.builds(Cart, items=_items, discount_pct=st.integers(min_value=0, max_value=100))


@given(_carts)
def test_agrees_with_reference(cart: Cart) -> None:
    assert checkout(cart) == reference(cart)
