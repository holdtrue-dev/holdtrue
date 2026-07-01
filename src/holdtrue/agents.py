"""Spawn the two LLM contexts, the author and the implementer, through a Provider.

Each spawn is a fresh context, so the implementer shares nothing with the author.
The implementer's workspace holds only the contract it must satisfy and the src
file it may write. The intent, held-out tests, and reference oracle are simply not
present, so it cannot read them. The curtain is the filesystem, not a promise.

Who does the writing is a Provider (see providers.py): a coding-agent CLI that
edits the workspace, or an API that returns the files for holdtrue to write. The
isolation is identical either way, because it is enforced by what is staged, not
by who is asked.
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Callable

import yaml

from . import providers
from .providers import AGENT, API, OUTPUT_RULES, Provider, write_blocks

_PROMPT = """You are implementing a function to satisfy a contract you did not write.

src/core.py contains a stub for:

    {signature}

The contract is in contract/spec.yaml, with example tests in contract/tests_shown/.
Write the body of `{function}` in src/core.py so the whole contract holds for every
input in its declared domain.

Rules:
- Edit only src/core.py.
- If src/models.py exists, those are the shared contract types: import from it (it is
  already imported at the top of the stub), and do not edit it.
- No `type: ignore`, no `Any`, no casts.
- Satisfy the literal contract. Do not guess at hidden intent.
- Keep the function pure: no IO, no globals, no prints.
"""

_PROMPT_MULTI = """You are implementing several functions to satisfy a contract you did not write.

src/core.py contains stubs for:

{signatures}

The contract is in contract/spec.yaml, with example tests in contract/tests_shown/.
Write the body of every function in src/core.py so the whole contract holds for every
input in its declared domain. The functions belong to one module and may call each
other.

Rules:
- Edit only src/core.py. Implement every function; leave none as a stub.
- If src/models.py exists, those are the shared contract types: import from it (it is
  already imported at the top of the stub), and do not edit it.
- No `type: ignore`, no `Any`, no casts.
- Satisfy the literal contract. Do not guess at hidden intent.
- Keep the functions pure: no IO, no globals, no prints.
"""

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

Two kinds of contract, pick by the intent:
- PROVABLE (preferred for pure integer arithmetic with no loops): keep to int so
  CrossHair can exhaust it, and aim for GUARANTEED. This is the default.
- ENFORCED (for rich types: strings, dates, money, structured data): follow the
  worked example's pydantic pattern. Define the types in contract/models.py, add
  `models: "models.py"` and `enforcement: runtime` to the manifest, and use those
  types in the signature. CrossHair is skipped; the contract is checked at runtime.
  Aim for ENFORCED. If the worked example has a contract/models.py, read it and
  mirror its style.

MANY FUNCTIONS: if the intent describes several functions, do NOT force them into one.
Drop the top-level `signature`/`function`/`checks.crosshair` and instead list them
under a top-level `functions:` key. Each entry mirrors the single-function shape:

  functions:
    - function: <func_a>
      signature: "<func_a>(<typed args>) -> <type>"
      checks:
        crosshair:
          decorators:
            - "@deal.ensure(lambda <args>, result: <postcondition>)"
            - "@deal.raises()"
      negative_probe:
        must_reject: ["<wrong one-line body>", ...]
    - function: <func_b>
      ...

Keep the shared `hypothesis_shown`, `hypothesis_heldout`, and `mutation` under the
top-level `checks:`. Both test files import EVERY function from `core` (the held-out
one also imports each from `reference_impl`), and reference_impl.py defines every
function. Each function is proven on its own and the overall verdict is the weakest.

Hard rules:
- No IO, no globals, no prints, no unbounded loops in the contract conditions.
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


def available() -> bool:
    """At least one provider looks usable."""
    return bool(providers.discover())


def _impl_spec(manifest: dict) -> dict:
    """The slice of the contract the implementer is allowed to see: the signature(s)
    and the conditions that must hold. Held-out tests, the reference oracle, the
    mutation config, and the negative-probe stay behind the curtain."""
    if "functions" in manifest:
        return {
            "summary": manifest.get("summary"),
            "functions": [
                {"signature": f["signature"], "function": f["function"],
                 "must_hold": f.get("decorators")
                 or f.get("checks", {}).get("crosshair", {}).get("decorators", [])}
                for f in manifest["functions"]
            ],
        }
    return {
        "summary": manifest.get("summary"),
        "signature": manifest["signature"],
        "function": manifest.get("function"),
        "must_hold": manifest["checks"]["crosshair"]["decorators"],
    }


def _stub_body(summary: str) -> str:
    return f'    """{summary}"""\n    raise NotImplementedError\n'


def stage_workspace(project: Path, manifest: dict, dest: Path) -> Path:
    if dest.exists():
        shutil.rmtree(dest)
    (dest / "contract" / "tests_shown").mkdir(parents=True)
    (dest / "src").mkdir(parents=True)

    (dest / "contract" / "spec.yaml").write_text(
        yaml.safe_dump(_impl_spec(manifest), sort_keys=False), encoding="utf-8")
    shown = project / "contract" / manifest["checks"]["hypothesis_shown"]
    shutil.copy(shown, dest / "contract" / "tests_shown" / shown.name)

    # A rich-type contract ships its shared pydantic models. The implementer imports
    # them and must not edit them, so the signature's types resolve in src/core.py.
    prelude = ""
    models_rel = manifest.get("models")
    if models_rel:
        models_src = (project / "contract" / models_rel).read_text(encoding="utf-8")
        (dest / "src" / "models.py").write_text(models_src, encoding="utf-8")
        prelude = "from models import *  # shared contract types: do not edit\n\n\n"

    summary = manifest.get("summary", "").replace('"', "'")
    if "functions" in manifest:
        stubs = [f'def {f["signature"]}:\n{_stub_body(summary)}'
                 for f in manifest["functions"]]
        stub = prelude + "\n\n".join(stubs)
    else:
        stub = prelude + f'def {manifest["signature"]}:\n{_stub_body(summary)}'
    (dest / "src" / "core.py").write_text(stub, encoding="utf-8")
    return dest


def _inline_dir(root: Path, rels: list[str]) -> str:
    """Render some workspace files as labelled text, for providers that cannot read
    the filesystem (api) or read only their cwd (non-claude agents)."""
    out = []
    for rel in rels:
        p = root / rel
        if p.exists():
            out.append(f"--- {rel} ---\n{p.read_text(encoding='utf-8')}")
    return "\n\n".join(out)


def _inline_contract(workspace: Path) -> str:
    rels = ["contract/spec.yaml", "src/core.py"]
    shown = workspace / "contract" / "tests_shown"
    if shown.is_dir():
        rels += [f"contract/tests_shown/{f.name}" for f in sorted(shown.glob("*.py"))]
    return "\n\nThe contract and stub (read-only context):\n\n" + _inline_dir(workspace, rels)


def _inline_template(template: Path) -> str:
    rels = ["contract/manifest.yaml"]
    shown = template / "contract" / "tests_shown"
    if shown.is_dir():
        rels += [f"contract/tests_shown/{f.name}" for f in sorted(shown.glob("*.py"))]
    return "\n\nWorked example to copy the format from:\n\n" + _inline_dir(template, rels)


def spawn_implementer(workspace: Path, manifest: dict, provider: Provider, *,
                      feedback: str | None = None, timeout: float = 300.0,
                      on_output: Callable[[str], None] | None = None) -> tuple[Path, str]:
    """Run a fresh, scoped context that writes src/core.py. Returns the path to the
    written file and the run's text output. `on_output`, if given, receives the
    provider's output as it arrives.

    On a re-spawn, `feedback` carries the counterexample from the failed round; the
    previous attempt is still in src/core.py for the context to fix."""
    if "functions" in manifest:
        sigs = "\n".join(f"    {f['signature']}" for f in manifest["functions"])
        prompt = _PROMPT_MULTI.format(signatures=sigs)
    else:
        prompt = _PROMPT.format(signature=manifest["signature"],
                                function=manifest.get("function", "clamp"))
    if feedback:
        prompt += ("\n\nThe current src/core.py is a previous attempt that FAILED "
                   f"verification:\n{feedback}\nFix src/core.py so the contract holds for "
                   "that input and for every other input in the domain.")
    if provider.kind == API:
        prompt += _inline_contract(workspace) + OUTPUT_RULES
        out = provider.run(prompt, workspace, timeout=timeout, on_output=on_output)
        write_blocks(out, workspace, allow=lambda rel: rel == "src/core.py")
    else:
        out = provider.run(prompt, workspace, timeout=timeout, on_output=on_output)
    return workspace / "src" / "core.py", out


def spawn_author(project: Path, template: Path, provider: Provider, *,
                 timeout: float = 600.0,
                 on_output: Callable[[str], None] | None = None) -> str:
    """Run a fresh, scoped context that writes the contract bundle from the intent.
    Separate context from the implementer."""
    can_read_outside = provider.kind == AGENT and getattr(provider, "accepts_dirs", False)
    if can_read_outside:
        prompt = _AUTHOR_PROMPT.replace("__TEMPLATE__", str(template))
        return provider.run(prompt, project, extra_dirs=(template,), timeout=timeout,
                            on_output=on_output)

    prompt = _AUTHOR_PROMPT.replace("__TEMPLATE__", "the worked example below")
    prompt += _inline_template(template)
    if provider.kind == API:
        intent = project / "intent" / "intent.md"
        if intent.exists():
            prompt += f"\n\nThe intent (intent/intent.md):\n\n{intent.read_text(encoding='utf-8')}"
        prompt += OUTPUT_RULES
        out = provider.run(prompt, project, timeout=timeout, on_output=on_output)
        write_blocks(out, project,
                     allow=lambda rel: rel.startswith(("contract/", "contract_private/")))
        return out
    return provider.run(prompt, project, timeout=timeout, on_output=on_output)
