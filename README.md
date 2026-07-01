![holdtrue: prove it, don't read it.](assets/banner.png)

[![ci](https://github.com/holdtrue-dev/holdtrue/actions/workflows/ci.yml/badge.svg)](https://github.com/holdtrue-dev/holdtrue/actions/workflows/ci.yml)
![python 3.12](https://img.shields.io/badge/python-3.12-2bbf57)
![verify: GUARANTEED](https://img.shields.io/badge/verify-GUARANTEED-33ff66)

**prove it. don't read it.**

AI writes the code. You approve a contract. holdtrue proves it holds.

Site: https://holdtrue-dev.github.io

## how it works

One intent, end to end:

1. **intent** (you): what the code should do, in plain language.
2. **contract author** (ai, context A): drafts the contract from your intent.
3. **the contract** (you): you read it and approve. this, not the code.
4. **the curtain**: the implementer sees only the contract, not your intent, not the held-out tests, not the reference oracle.
5. **implementer** (ai, context B): writes the code from the contract alone.
6. **verify** (holdtrue, sandboxed): types, proof, properties, negative-probe, mutation.
7. **the verdict** (you): guaranteed, enforced, unguaranteed, or failed, with evidence.

![holdtrue architecture](assets/architecture.gif)

The two AI contexts run on an assistant you choose: a coding-agent CLI (`claude`, `aider`, `gemini`, `codex`), a chat API (Anthropic, OpenAI, Ollama), or your own command via `HOLDTRUE_AGENT_CMD`. `holdtrue providers` lists what is usable; `--provider` picks one. Any assistant, any model: the proof is the same.

## the intent

Plain language in. Here is the whole intent for the `clamp` example:

> # intent: clamp
>
> Clamp a number into a range. Given `x`, `lo`, `hi`, return `x` if it sits inside `[lo, hi]`, otherwise return the nearest bound.

You write this. The rest is proof.

## the contract

The author turns that intent into a machine-checkable contract. Every line, in plain words:

```python
@deal.pre(lambda x, lo, hi: lo <= hi)
@deal.ensure(lambda x, lo, hi, result: lo <= result <= hi)
@deal.ensure(lambda x, lo, hi, result: result == min(max(x, lo), hi))
@deal.raises()
def clamp(x: int, lo: int, hi: int) -> int: ...
```

- **precondition** (`@deal.pre`): only promised for a valid range.
- **in range** (`@deal.ensure`): the result lands inside `[lo, hi]`.
- **exact value** (`@deal.ensure`): it equals the clamped number, not just some value in range.
- **no surprises** (`@deal.raises()`): it raises nothing.
- **signature**: the name and types the implementer must match.

This, not the code, is what you read and approve.

## the verdict

No answer without evidence. holdtrue reports, per intent, one of:

- `GUARANTEED`: proven over all inputs, and the contract catches injected bugs and rejects broken stand-ins.
- `ENFORCED`: checked at runtime on every call and clean over every sample, but not proven over all inputs. This is the honest tier for shapes CrossHair cannot exhaust (strings, lists, floats, loops): a violating input raises instead of passing silently.
- `UNGUARANTEED`: only sampled evidence. Still needs human review.
- `FAILED`: a counterexample, with the input that breaks it.

## getting started

Clone, sync, verify:

```
git clone https://github.com/holdtrue-dev/holdtrue
cd holdtrue && uv sync
source .venv/bin/activate

holdtrue verify examples/clamp --impl examples/clamp/controls/correct.py
```

Swap in `controls/buggy.py` for a `FAILED`. Point at `examples/checkout` for a realistic `ENFORCED`: a pydantic shopping-cart total CrossHair cannot prove, but the contract enforces it on every call (`examples/nights` and `examples/pagination` are the same idea over dates and page maths). Or add `--manifest contract/manifest_weak.yaml` to watch a correct function get refused a guarantee because the contract itself is too weak.

## see it run

Watch a verification stream live in a TUI:

```
holdtrue tui examples/clamp --impl examples/clamp/controls/correct.py
```

Drive the whole loop in a TUI: pick a provider and model, type an intent, approve the contract, watch it run to a verdict:

```
holdtrue studio
```

Or run the loop from the command line (author, self-check, approve, implement, verify):

```
holdtrue run examples/clamp --yes
```

## never-silent revision

When verification shows the contract was wrong, holdtrue does not go silent. A self-check failure proposes a fix back to you; a second author cross-checks for an axis the contract misses (`holdtrue cross-check`); a run that cannot pass is diagnosed. A ratchet forbids weakening a check to pass, every change waits for your approval, and each one is recorded in `<project>/revisions/`.

## powered by

deal (contracts) · CrossHair (proof) · cosmic-ray (mutation) · mypy (types) · bubblewrap (sandbox)
