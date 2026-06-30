from models import Cart, Receipt


def checkout(cart: Cart) -> Receipt:
    subtotal = sum(i.qty * i.unit_price_cents for i in cart.items)
    discount = subtotal * cart.discount_pct // 100
    # bug: forgets to subtract the discount from the total
    return Receipt(subtotal_cents=subtotal, discount_cents=discount,
                   total_cents=subtotal)
