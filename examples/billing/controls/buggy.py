"""A buggy implementation. Three functions are right; apply_rate truncates instead of
rounding half up, so it is a cent low whenever the rounding would round up. apply_rate
is a proven (int-only) function, so CrossHair catches it with a concrete counterexample
and the verdict is FAILED, naming apply_rate, even though it is the enforced functions
above it (line_total, settle) that call it."""
from __future__ import annotations

from models import Invoice, LineItem, Receipt


def apply_rate(amount_cents: int, bps: int) -> int:
    # bug: truncates instead of rounding half up (missing the + 5000)
    return (amount_cents * bps) // 10000


def nonneg(cents: int) -> int:
    return max(cents, 0)


def line_total(item: LineItem) -> int:
    gross = item.qty * item.unit_price_cents
    return gross - apply_rate(gross, item.discount_bps)


def settle(invoice: Invoice) -> Receipt:
    subtotal = sum(line_total(i) for i in invoice.items)
    tax = apply_rate(subtotal, invoice.tax_bps)
    total = nonneg(subtotal + tax - invoice.coupon_cents)
    return Receipt(subtotal_cents=subtotal, tax_cents=tax, total_cents=total)
