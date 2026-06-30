# Roadmap

Where holdtrue is and what comes next. Short and honest.

## Done

The verification loop, proven end to end on pure Python functions:

- intent to a machine-checkable contract (types, deal + CrossHair, Hypothesis)
- separate author and implementer steps; the human approves the contract
- verify: types, symbolic proof, shown + held-out tests, negative-probe, mutation
- honest verdict: `GUARANTEED`, `UNGUARANTEED`, or `FAILED`
- bubblewrap sandbox, evidence report, CI, a worked example and a demo

## Two LLM contexts (done)

Both contexts run as separate `claude` sessions, and neither sees the other:

- `holdtrue author` reads the intent, writes the contract bundle, and self-checks
  that its own reference oracle satisfies the contract.
- you review and approve the contract.
- `holdtrue implement` writes the code in a fresh context scoped to the contract
  alone (the intent, held-out tests, and oracle are absent), then verifies it.

Shown end to end on a fresh `abs` intent: a separate implementer satisfied an
author-written contract, verdict GUARANTEED.

## One orchestrated loop (done)

`holdtrue run` chains it all in one command: the author writes the contract,
holdtrue self-checks it against the reference oracle, you approve, then the
implementer fills it in and it gets verified. A FAILED round re-spawns the
implementer with the counterexample, bounded by `--max-rounds`. Shown on a fresh
`square` intent: GUARANTEED in one round.

## Pluggable providers (done)

The two contexts run through a Provider, so `claude` is no longer hardwired.
`holdtrue providers` lists what is usable; `--provider <name>` picks one. Two
shapes are supported: a coding-agent CLI that edits the workspace (claude, plus
best-effort adapters for aider, gemini, codex, or any command via
`HOLDTRUE_AGENT_CMD`), and a chat API that returns the files for holdtrue to write
(Anthropic, OpenAI, Ollama). The curtain is the staged filesystem, so the
isolation holds whoever is asked.

`holdtrue studio` runs the loop in a TUI: discover providers, pick one, type the
intent, approve the contract, watch it verify to a verdict.

## Next: never-silent revision

When verification shows the contract or the intent was wrong, propose the change
back to the human with its justification, record it in a changelog, and re-run.
Never weaken a check to pass. Optional second author to diff two contracts and
catch a missing axis.

## Later: widen the domain

- typed API layer with pydantic: runtime-enforced, reported as enforced, not proven
- more provable shapes: more types, simple stateful tests
- a second language (TypeScript: fast-check, Stryker, tsc). No CrossHair there, so
  the `GUARANTEED` tier is narrower, and the report says so

## Hardening

seccomp and Docker sandbox tiers, mutation on the reference oracle as a second
cross-check, parallel checks, packaging.
