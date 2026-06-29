"""Spawn the implementer as a separate LLM context, via the claude CLI.

Each spawn is a fresh `claude -p` session, so it shares no context with the
contract author. The implementer's workspace holds only the contract it must
satisfy and the src file it may write. The intent, held-out tests, and reference
oracle are simply not present, so it cannot read them. The curtain is the
filesystem, not a promise.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import yaml

CLAUDE = shutil.which("claude")

_PROMPT = """You are implementing a function to satisfy a contract you did not write.

src/core.py contains a stub for:

    {signature}

The contract is in contract/spec.yaml, with example tests in contract/tests_shown/.
Write the body of `{function}` in src/core.py so the whole contract holds for every
input in its declared domain.

Rules:
- Edit only src/core.py.
- No `type: ignore`, no `Any`, no casts.
- Satisfy the literal contract. Do not guess at hidden intent.
- Keep the function pure: no IO, no globals, no prints.
"""


def available() -> bool:
    return CLAUDE is not None


def _impl_spec(manifest: dict) -> dict:
    """The slice of the contract the implementer is allowed to see: the signature
    and the conditions that must hold. Held-out tests, the reference oracle, the
    mutation config, and the negative-probe stay behind the curtain."""
    return {
        "summary": manifest.get("summary"),
        "signature": manifest["signature"],
        "function": manifest.get("function"),
        "must_hold": manifest["checks"]["crosshair"]["decorators"],
    }


def stage_workspace(project: Path, manifest: dict, dest: Path) -> Path:
    if dest.exists():
        shutil.rmtree(dest)
    (dest / "contract" / "tests_shown").mkdir(parents=True)
    (dest / "src").mkdir(parents=True)

    (dest / "contract" / "spec.yaml").write_text(
        yaml.safe_dump(_impl_spec(manifest), sort_keys=False), encoding="utf-8")
    shown = project / "contract" / manifest["checks"]["hypothesis_shown"]
    shutil.copy(shown, dest / "contract" / "tests_shown" / shown.name)

    summary = manifest.get("summary", "").replace('"', "'")
    stub = f'def {manifest["signature"]}:\n    """{summary}"""\n    raise NotImplementedError\n'
    (dest / "src" / "core.py").write_text(stub, encoding="utf-8")
    return dest


def spawn_implementer(workspace: Path, manifest: dict, *, feedback: str | None = None,
                      timeout: float = 300.0) -> tuple[Path, str]:
    """Run a fresh, scoped claude session that writes src/core.py. Returns the
    path to the written file and the session's text output.

    On a re-spawn, `feedback` carries the counterexample from the failed round; the
    previous attempt is still in src/core.py for the session to fix."""
    prompt = _PROMPT.format(signature=manifest["signature"],
                            function=manifest.get("function", "clamp"))
    if feedback:
        prompt += ("\n\nThe current src/core.py is a previous attempt that FAILED "
                   f"verification:\n{feedback}\nFix src/core.py so the contract holds for "
                   "that input and for every other input in the domain.")
    cmd = [CLAUDE, "-p", prompt,
           "--add-dir", str(workspace),
           "--allowed-tools", "Read Edit Write",
           "--permission-mode", "acceptEdits"]
    p = subprocess.run(cmd, cwd=str(workspace), capture_output=True,
                       text=True, timeout=timeout)
    return workspace / "src" / "core.py", (p.stdout or "") + (p.stderr or "")


_AUTHOR_PROMPT = """You are the contract author. From a natural-language intent you write a
machine-checkable contract. You do NOT write the implementation of the function.

Read intent/intent.md. Then write a contract bundle in exactly this layout. A worked
example you can read for format is at __TEMPLATE__ :

  contract/manifest.yaml
  contract/tests_shown/test_<name>.py
  contract_private/tests_heldout/test_<name>_heldout.py
  contract_private/reference_impl.py

manifest.yaml must contain:
  version: 1
  intent_id: <SHORT-ID>
  summary: "<one line of what is true>"
  signature: "<func>(<typed args>) -> <type>"
  function: <func>
  interrogated_axes: [<the behavioural axes you pinned down>]
  checks:
    crosshair:
      decorators:
        - "@deal.pre(lambda <args>: <precondition>)"      # only if inputs are restricted
        - "@deal.ensure(lambda <args>, result: <postcondition>)"
        - "@deal.raises()"                                 # if the function raises nothing
      guarantee_if_exhausted: GUARANTEED
    hypothesis_shown: "tests_shown/test_<name>.py"
    hypothesis_heldout: "tests_heldout/test_<name>_heldout.py"
    mutation: { threshold: 0.85 }
  negative_probe:
    must_reject:
      - "<a wrong one-line body>"
  acceptance: { target_class: GUARANTEED }

Hard rules:
- Use only int and other types CrossHair can reason over. No float, no IO, no
  unbounded loops.
- The postcondition MUST pin the EXACT result (result == <formula>), not just a
  range. A range-only contract is too weak and will be rejected.
- contract/tests_shown/test_<name>.py: `from core import <func>`, one hypothesis
  property over bounded integers (e.g. st.integers(min_value=-1000, max_value=1000)).
- contract_private/tests_heldout/test_<name>_heldout.py: `from core import <func>`
  and `from reference_impl import <func> as reference`, assert they agree.
- contract_private/reference_impl.py: an independent, correct implementation, using the
  EXACT typed signature from the manifest (e.g. `def <func>(x: int) -> int:`). Type
  annotations are required: CrossHair uses them to bound the inputs, and an unannotated
  function is refuted.
- negative_probe.must_reject: at least three wrong one-line bodies the contract
  must reject (e.g. "return 0", "return x").
- Write only those four files. Do not write src/ or implement the function anywhere
  except reference_impl.py, which is the private oracle.
"""


def spawn_author(project: Path, template: Path, *, timeout: float = 420.0) -> str:
    """Run a fresh, scoped claude session that writes the contract bundle from the
    intent. Separate context from the implementer."""
    prompt = _AUTHOR_PROMPT.replace("__TEMPLATE__", str(template))
    cmd = [CLAUDE, "-p", prompt,
           "--add-dir", str(project), "--add-dir", str(template),
           "--allowed-tools", "Read Edit Write",
           "--permission-mode", "acceptEdits"]
    p = subprocess.run(cmd, cwd=str(project), capture_output=True,
                       text=True, timeout=timeout)
    return (p.stdout or "") + (p.stderr or "")
