# Intent

`clamp(x, lo, hi)` returns `x` confined to the range `[lo, hi]`.

- Requires `lo <= hi`.
- If `x < lo`, return `lo`.
- If `x > hi`, return `hi`.
- Otherwise return `x`.
- Should never throw.

All three inputs and the return value are numbers.
