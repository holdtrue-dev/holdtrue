# Security

holdtrue runs code that an LLM wrote, in order to verify it. Treat that code as
untrusted. This page states what holdtrue does to contain it, and what it does not.

## What is sandboxed

Every verification check that executes the implementation runs inside a
[bubblewrap](https://github.com/containers/bubblewrap) sandbox:

- no network (`--unshare-all`),
- read-only system and Python environment (`/usr`, the venv, the base interpreter),
- writes confined to a per-run scratch directory, with `/tmp` on a tmpfs and `HOME`
  redirected there,
- its own session and process group, killed with the parent.

This covers the type check, the CrossHair symbolic run, the shown and held-out
property tests, the negative-probe, and mutation testing (cosmic-ray imports and runs
mutated copies of the code, so both its init and exec steps run boxed).

## Fail closed

holdtrue will not run AI-written code unsandboxed by accident. If sandboxing is
requested but bubblewrap is missing, the run stops and tells you to install bwrap or
pass `--no-sandbox`. Running without the sandbox is only ever an explicit choice, and
it prints a warning.

## Limits (know these before you rely on it)

- **Linux only.** bubblewrap does not exist on macOS or Windows. There, the only way
  to run holdtrue is `--no-sandbox`, which runs the AI-written code directly on your
  machine with your permissions. The sandbox guarantee does not apply.
- **The agent contexts are not sandboxed.** The contract author and the implementer
  run through whatever coding-agent CLI or chat API you choose. Those processes run
  with your user's permissions, and coding-agent CLIs are invoked non-interactively
  and may auto-accept their own edits and commands. Only the verification checks are
  boxed. Point holdtrue at providers and models you trust.
- **It is unprivileged containment, not a hard boundary.** bubblewrap blocks network
  and out-of-scope file access, which stops the common accidents. It is not a defense
  against a kernel-level exploit. Do not run holdtrue on inputs you believe are
  actively hostile at that level.
- **API keys** are read from the environment by the provider you pick and are never
  logged by holdtrue, but they are visible to the agent process you invoke.

## Reporting a vulnerability

Email holdtrue-dev@proton.me, or open a private GitHub security advisory on the
repository. Please do not open a public issue for a security report.
