from hypothesis import given, settings, strategies as st

from core import apply_rate, line_total, nonneg, settle
from models import Invoice, LineItem
from reference_impl import apply_rate as r_apply_rate
from reference_impl import line_total as r_line_total
from reference_impl import nonneg as r_nonneg
from reference_impl import settle as r_settle

settings.register_profile("holdtrue", max_examples=40, deadline=None)
settings.load_profile("holdtrue")

_items = st.builds(
    LineItem,
    qty=st.integers(min_value=1, max_value=100),
    unit_price_cents=st.integers(min_value=0, max_value=100_000),
    discount_bps=st.integers(min_value=0, max_value=10_000),
)
_invoices = st.builds(
    Invoice,
    items=st.lists(_items, max_size=8),
    tax_bps=st.integers(min_value=0, max_value=10_000),
    coupon_cents=st.integers(min_value=0, max_value=100_000),
)


@given(st.integers(min_value=0, max_value=10_000_000), st.integers(min_value=0, max_value=10_000))
def test_apply_rate_agrees(amount: int, bps: int) -> None:
    assert apply_rate(amount, bps) == r_apply_rate(amount, bps)


@given(st.integers(min_value=-1000, max_value=1000))
def test_nonneg_agrees(cents: int) -> None:
    assert nonneg(cents) == r_nonneg(cents)


@given(_items)
def test_line_total_agrees(item: LineItem) -> None:
    assert line_total(item) == r_line_total(item)


@given(_invoices)
def test_settle_agrees(invoice: Invoice) -> None:
    assert settle(invoice) == r_settle(invoice)
