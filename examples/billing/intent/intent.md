# Intent: billing

Total up an invoice, in whole cents. This mixes two kinds of work: small money helpers that are pure arithmetic, and the document-level totals over structured line items.

- **apply rate**: a percentage of an amount, given in basis points (100 basis points is one percent), rounded to the nearest cent, half up. Used for both tax and discounts.
- **non-negative**: a money amount floored at zero, so a total is never negative.
- **line total**: for a line item (a quantity, a unit price, and a per-line discount in basis points), the quantity times the unit price, minus the discount, never below zero.
- **settle**: for a whole invoice (line items, a tax rate in basis points, and a fixed coupon in cents), a receipt with the subtotal (the line totals added up), the tax (the rate applied to the subtotal), and the total (subtotal plus tax minus the coupon, floored at zero).

Four functions. The first two are pure integer arithmetic and can be proven outright; the last two work over the structured types and are enforced at runtime.
