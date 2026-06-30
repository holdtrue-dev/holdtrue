# Roadmap

Where holdtrue is and what comes next. Short and honest.

## Shipped

- [x] Intent to a machine-checkable contract: types, deal + CrossHair, Hypothesis
- [x] Separate author and implementer contexts, with the human approving the contract
- [x] Verify: types, symbolic proof, shown + held-out tests, negative-probe, mutation
- [x] Honest verdict: `GUARANTEED`, `UNGUARANTEED`, or `FAILED`, with evidence
- [x] bubblewrap sandbox, evidence report, CI, a worked example and a demo
- [x] `holdtrue run`: the full loop in one command, re-spawning on a `FAILED` round
- [x] Pluggable providers: coding-agent CLIs (claude, ...) or chat APIs (Anthropic, OpenAI, Ollama), chosen with `--provider`
- [x] `holdtrue studio`: pick a provider and model, type an intent, watch it run live to a verdict
- [x] Never-silent revision: a self-check failure proposes a contract fix; a ratchet forbids weakening; human-approved; recorded in a changelog
- [x] Second-author cross-check: a second author catches an axis the approved contract does not enforce, proposed as a non-weakening addition
- [x] On an unresolved run, a diagnosis of why it is stuck (the contract may be ambiguous, or the intent wrong)
- [x] The revision flow is surfaced live in `holdtrue run`, `cross-check`, and studio

## Next: widen the domain

- [x] `ENFORCED` tier: shapes CrossHair cannot prove (strings, lists, floats, loops) are reported as enforced at runtime, not proven. A `repeat` example demonstrates it
- [x] Typed API layer with pydantic: rich models and constrained types, validated at the boundary and reported as `ENFORCED` (checkout, nights, pagination examples)
- [ ] More provable shapes: simple stateful tests
- [ ] A second language (TypeScript: fast-check, Stryker, tsc). No CrossHair there, so the `GUARANTEED` tier is narrower, and the report says so

## Hardening

- [ ] seccomp and Docker sandbox tiers
- [ ] Mutation on the reference oracle as a second cross-check
- [ ] Parallel checks
- [ ] Packaging
