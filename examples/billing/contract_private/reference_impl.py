"""Reference oracle. Author-side, used by the held-out differential test only.

Two pure-integer money helpers and two document-level functions built on them.
"""
from __future__ import annotations

from models import Invoice, LineItem, Receipt


def apply_rate(amount_cents: int, bps: int) -> int:
    return (amount_cents * bps + 5000) // 10000


def nonneg(cents: int) -> int:
    return cents if cents > 0 else 0


def line_total(item: LineItem) -> int:
    gross = item.qty * item.unit_price_cents
    return gross - apply_rate(gross, item.discount_bps)


def settle(invoice: Invoice) -> Receipt:
    subtotal = sum(line_total(i) for i in invoice.items)
    tax = apply_rate(subtotal, invoice.tax_bps)
    total = nonneg(subtotal + tax - invoice.coupon_cents)
    return Receipt(subtotal_cents=subtotal, tax_cents=tax, total_cents=total)
