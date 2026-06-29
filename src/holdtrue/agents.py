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


def spawn_implementer(workspace: Path, manifest: dict, *,
                      timeout: float = 300.0) -> tuple[Path, str]:
    """Run a fresh, scoped claude session that writes src/core.py. Returns the
    path to the written file and the session's text output."""
    prompt = _PROMPT.format(signature=manifest["signature"],
                            function=manifest.get("function", "clamp"))
    cmd = [CLAUDE, "-p", prompt,
           "--add-dir", str(workspace),
           "--allowed-tools", "Read Edit Write",
           "--permission-mode", "acceptEdits"]
    p = subprocess.run(cmd, cwd=str(workspace), capture_output=True,
                       text=True, timeout=timeout)
    return workspace / "src" / "core.py", (p.stdout or "") + (p.stderr or "")
