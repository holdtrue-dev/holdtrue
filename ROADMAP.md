# Roadmap

Where holdtrue is and what comes next. Short and honest.

## Done

The verification loop, proven end to end on pure Python functions:

- intent to a machine-checkable contract (types, deal + CrossHair, Hypothesis)
- separate author and implementer steps; the human approves the contract
- verify: types, symbolic proof, shown + held-out tests, negative-probe, mutation
- honest verdict: `GUARANTEED`, `UNGUARANTEED`, or `FAILED`
- bubblewrap sandbox, evidence report, CI, a worked example and a demo

## Next: two LLM contexts

The implementer now runs as its own LLM context (`holdtrue implement`). holdtrue
stages a workspace holding only the contract (spec plus shown tests) and an empty
src file, spawns a fresh `claude` session scoped to it with `--add-dir` and tool
limits, and verifies whatever it writes against the full contract. The intent,
held-out tests, and reference oracle are absent from that workspace, so the curtain
is the filesystem. Reuses existing auth, no API key.

Still to do:

- give the contract author its own context: read the intent, interrogate it, write
  the contract bundle
- have the orchestrator drive both, and re-spawn the implementer with pass/fail and
  a counterexample until the stopping condition holds

## Then: never-silent revision

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
