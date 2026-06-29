```text
██   ██  ██████  ██      ██████  ████████ ██████  ██    ██ ███████
██   ██ ██    ██ ██      ██   ██    ██    ██   ██ ██    ██ ██
███████ ██    ██ ██      ██   ██    ██    ██████  ██    ██ █████
██   ██ ██    ██ ██      ██   ██    ██    ██   ██ ██    ██ ██
██   ██  ██████  ███████ ██████     ██    ██   ██  ██████  ███████

  prove it. don't read it.
```

holdtrue checks an implementation against a contract you approve, then tells you what is actually guaranteed. You review the contract, not the code.

It runs the contract and reports, per intent:

- `GUARANTEED`: proven over all inputs, with a contract strong enough to catch injected bugs and reject broken stand-ins.
- `UNGUARANTEED`: only sampled evidence. Still needs human review.
- `FAILED`: a counterexample, with the input that breaks it.

## Try it

```
uv run python -m holdtrue.cli verify examples/clamp \
  --impl examples/clamp/controls/correct.py
```

Swap in `controls/buggy.py` for a FAILED, or add `--manifest contract/manifest_weak.yaml` to watch a correct function get refused a guarantee because the contract itself is too weak.

## Status

Early. Python pure functions, one domain, proven end to end. Both the contract author and the implementer run as separate LLM contexts (`holdtrue author` / `holdtrue implement`), with your review in between. A single orchestrated run is next.

Stack: deal + CrossHair (proof), Hypothesis (properties), cosmic-ray (mutation), mypy, bubblewrap. Python 3.12, managed with uv.
