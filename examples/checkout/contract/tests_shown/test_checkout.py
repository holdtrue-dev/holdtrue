from hypothesis import given, strategies as st

from core import checkout
from models import Cart, LineItem

_items = st.lists(
    st.builds(LineItem, sku=st.text(min_size=1, max_size=8),
              qty=st.integers(min_value=1, max_value=100),
              unit_price_cents=st.integers(min_value=0, max_value=100_000)),
    max_size=8,
)
_carts = st.builds(Cart, items=_items, discount_pct=st.integers(min_value=0, max_value=100))


@given(_carts)
def test_receipt_adds_up(cart: Cart) -> None:
    r = checkout(cart)
    subtotal = sum(i.qty * i.unit_price_cents for i in cart.items)
    discount = subtotal * cart.discount_pct // 100
    assert r.subtotal_cents == subtotal
    assert r.discount_cents == discount
    assert r.total_cents == subtotal - discount
    assert r.total_cents >= 0
