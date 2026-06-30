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

## Next: never-silent revision

- [ ] When verification shows the contract or the intent was wrong, propose the change back to the human with its justification
- [ ] Record every revision in a changelog
- [ ] Never weaken a check to pass
- [ ] Optional second author to diff two contracts and catch a missing axis

## Later: widen the domain

- [ ] Typed API layer with pydantic: runtime-enforced, reported as enforced, not proven
- [ ] More provable shapes: more types, simple stateful tests
- [ ] A second language (TypeScript: fast-check, Stryker, tsc). No CrossHair there, so the `GUARANTEED` tier is narrower, and the report says so

## Hardening

- [ ] seccomp and Docker sandbox tiers
- [ ] Mutation on the reference oracle as a second cross-check
- [ ] Parallel checks
- [ ] Packaging
