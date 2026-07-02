# Intent

A `Counter` class with three operations:

- `up()` — increment the counter by 1, up to a maximum (inclusive).
- `down()` — decrement the counter by 1, down to zero (inclusive).
- `reset()` — set the counter back to zero.
- `value() -> int` — return the current count.

The counter is constructed with a non-negative integer `maximum`.  After
construction `value()` returns 0.  `up()` and `down()` are capped silently
(they do nothing when already at the boundary), so the counter is always in
the range `[0, maximum]`.  `reset()` always returns the counter to 0.
