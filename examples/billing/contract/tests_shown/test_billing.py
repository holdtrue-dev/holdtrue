from hypothesis import given, settings, strategies as st

from core import apply_rate, line_total, nonneg, settle
from models import Invoice, LineItem

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
    items=st.lists(_items, max_size=6),
    tax_bps=st.integers(min_value=0, max_value=10_000),
    coupon_cents=st.integers(min_value=0, max_value=100_000),
)


@given(st.integers(min_value=0, max_value=10_000_000), st.integers(min_value=0, max_value=10_000))
def test_apply_rate(amount: int, bps: int) -> None:
    assert apply_rate(amount, bps) == (amount * bps + 5000) // 10000


@given(st.integers(min_value=-1000, max_value=1000))
def test_nonneg(cents: int) -> None:
    assert nonneg(cents) == max(cents, 0)


@given(_items)
def test_line_total(item: LineItem) -> None:
    gross = item.qty * item.unit_price_cents
    assert line_total(item) == gross - (gross * item.discount_bps + 5000) // 10000
    assert line_total(item) >= 0


@given(_invoices)
def test_settle(invoice: Invoice) -> None:
    r = settle(invoice)
    subtotal = sum(line_total(i) for i in invoice.items)
    tax = (subtotal * invoice.tax_bps + 5000) // 10000
    assert r.subtotal_cents == subtotal
    assert r.tax_cents == tax
    assert r.total_cents == max(subtotal + tax - invoice.coupon_cents, 0)
