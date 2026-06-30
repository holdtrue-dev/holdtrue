"""Never-silent revision: when the contract itself fails its self-check, propose a
fix back to the human instead of going silent.

A reviser (a separate LLM context) reads the current contract, the self-check
failure, and the intent, and proposes the smallest change that makes the contract
hold, written to a staged copy of the project. holdtrue then enforces that the
revision is not weaker:

  - it still rejects every broken body it rejected before (negative_probe.must_reject
    can only grow), and
  - the reference oracle still satisfies it, and
  - CrossHair still confirms it.

That makes "never weaken a check to pass" a structural invariant, not a promise. The
diff and the reviser's justification are shown, and a revision is applied only with
approval (or, with --auto-revise, when it provably passes the ratchet). Every applied
revision is recorded in a changelog.
"""
from __future__ import annotations

import difflib
import shutil
from pathlib import Path
from typing import Callable

from . import verify
from .providers import API, OUTPUT_RULES, Provider, write_blocks

_REVISER_PROMPT = """You are revising a machine-checkable contract that FAILED its own self-check.
You do NOT write the implementation.

What failed:
{evidence}

The contract is in contract/manifest.yaml (with tests in contract/tests_shown/), and
the author's reference oracle is in contract_private/reference_impl.py. The intent is
in intent/intent.md.

Propose the SMALLEST change that makes the self-check pass: the reference oracle must
satisfy the contract, CrossHair must confirm it over the whole domain, and the contract
must reject every broken body in negative_probe.must_reject.

Hard rules:
- You may strengthen postconditions, fix a wrong precondition, or correct the reference
  oracle so it matches the intent. Keep the EXACT-value postcondition.
- You may ADD entries to negative_probe.must_reject. You must NOT remove any entry to
  make a check pass: that is weakening the contract, and it will be rejected.
- Edit only files under contract/ and contract_private/.
- Write contract/revision_note.md: one short paragraph explaining what was wrong and
  what you changed, in plain language for the human who approves it.
"""


def stage_contract(project: Path, dest: Path) -> Path:
    """Copy the intent and the contract bundle into a scratch dir, so the reviser can
    edit a candidate without touching the real project until it is approved."""
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    for sub in ("intent", "contract", "contract_private"):
        src = project / sub
        if src.exists():
            shutil.copytree(src, dest / sub)
    return dest


def _must_reject(manifest: dict) -> list[str]:
    return manifest.get("negative_probe", {}).get("must_reject", [])


def must_reject_preserved(old: dict, new: dict) -> bool:
    """The revision may add broken bodies to reject, never drop one."""
    return set(_must_reject(old)) <= set(_must_reject(new))


def justification(staged: Path) -> str:
    note = staged / "contract" / "revision_note.md"
    return note.read_text(encoding="utf-8").strip() if note.exists() else "(no justification written)"


def contract_diff(old: dict, new: dict) -> str:
    """A unified diff of the part a human cares about: the proven decorators and the
    must_reject list."""
    def lines(m: dict) -> list[str]:
        decos = m.get("checks", {}).get("crosshair", {}).get("decorators", [])
        return [m.get("signature", "")] + decos + [f"must_reject: {b}" for b in _must_reject(m)]
    diff = difflib.unified_diff(lines(old), lines(new), "current", "proposed", lineterm="")
    return "\n".join(diff)


def self_check(project: Path, manifest: dict) -> tuple[bool, str]:
    """Does the reference oracle satisfy the contract, provably and non-vacuously?"""
    ref = project / "contract_private" / "reference_impl.py"
    sc, _ = verify.run_verification(project, ref, manifest, sandbox_on=False, mutation=False)
    ch, pr = sc.get("crosshair"), sc.get("negative_probe")
    ok = bool(ch and ch.status == "confirmed" and pr and pr.status == "pass")
    why = []
    if not (ch and ch.status == "confirmed"):
        why.append(f"proof: {ch.detail if ch else 'missing'}")
    if not (pr and pr.status == "pass"):
        why.append(f"negative-probe: {pr.detail if pr else 'missing'}")
    return ok, "; ".join(why) or "holds"


def not_weaker(staged: Path, old_manifest: dict, new_manifest: dict) -> tuple[bool, str]:
    """The ratchet: a revision is acceptable only if it preserves every rejected broken
    body and still self-checks (oracle satisfies it, CrossHair confirms)."""
    if not must_reject_preserved(old_manifest, new_manifest):
        dropped = set(_must_reject(old_manifest)) - set(_must_reject(new_manifest))
        return False, f"weaker: dropped must_reject {sorted(dropped)}"
    ok, why = self_check(staged, new_manifest)
    if not ok:
        return False, f"still fails self-check ({why})"
    return True, "stronger or equal, and self-checks"


def apply(staged: Path, project: Path) -> None:
    """Copy the approved contract back over the real project."""
    for sub in ("contract", "contract_private"):
        dst = project / sub
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(staged / sub, dst)


def spawn_reviser(staged: Path, manifest: dict, evidence: str, provider: Provider, *,
                  timeout: float = 420.0,
                  on_output: Callable[[str], None] | None = None) -> str:
    """Run a fresh context that edits the staged contract to fix the self-check."""
    prompt = _REVISER_PROMPT.format(evidence=evidence)
    if provider.kind == API:
        for sub in ("intent/intent.md", "contract/manifest.yaml",
                    "contract_private/reference_impl.py"):
            p = staged / sub
            if p.exists():
                prompt += f"\n\n--- {sub} ---\n{p.read_text(encoding='utf-8')}"
        prompt += OUTPUT_RULES
        out = provider.run(prompt, staged, timeout=timeout, on_output=on_output)
        write_blocks(out, staged, allow=lambda rel: rel.startswith(("contract/", "contract_private/")))
        return out
    return provider.run(prompt, staged, timeout=timeout, on_output=on_output)
