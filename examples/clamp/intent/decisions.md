# Decisions: clamp

How the questions were resolved. Author-side notes, not shown to the implementer.

- `lo > hi` is a precondition. `lo <= hi` is required; behaviour is undefined otherwise.
- Bounds are inclusive. `x == lo` and `x == hi` both return `x`.
- `int` only for v1. Floats are out of scope and would not reach a proof.
- No exceptions. A bad range is a precondition, not an error.
- When `x` is in range it must return `x`. A bounds-only postcondition
  (`lo <= result <= hi`) is satisfied by `return lo`, so the contract also pins
  the exact value (`result == min(max(x, lo), hi)`). The negative-probe catches
  the case where that pin is missing.
