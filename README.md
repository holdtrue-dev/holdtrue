![holdtrue: prove it, don't read it.](assets/banner.png)

[![ci](https://github.com/holdtrue-dev/holdtrue/actions/workflows/ci.yml/badge.svg)](https://github.com/holdtrue-dev/holdtrue/actions/workflows/ci.yml)
![python 3.12](https://img.shields.io/badge/python-3.12-2bbf57)
![verify: GUARANTEED](https://img.shields.io/badge/verify-GUARANTEED-33ff66)

holdtrue checks an implementation against a contract you approve, then tells you what is actually guaranteed. You review the contract, not the code.

It runs the contract and reports, per intent:

- `GUARANTEED`: proven over all inputs, with a contract strong enough to catch injected bugs and reject broken stand-ins.
- `UNGUARANTEED`: only sampled evidence. Still needs human review.
- `FAILED`: a counterexample, with the input that breaks it.

## How it works

![holdtrue architecture](assets/architecture.png)

## Try it

```
uv run python -m holdtrue.cli verify examples/clamp \
  --impl examples/clamp/controls/correct.py
```

Swap in `controls/buggy.py` for a FAILED, or add `--manifest contract/manifest_weak.yaml` to watch a correct function get refused a guarantee because the contract itself is too weak.

Watch it run live in a TUI:

```
uv run python -m holdtrue.cli tui examples/clamp --impl examples/clamp/controls/correct.py
```
