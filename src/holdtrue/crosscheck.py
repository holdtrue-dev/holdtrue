"""Second-author cross-check: catch a missing axis before it ships as GUARANTEED.

A single author can write a contract that is self-consistent and provable yet still
miss a behavioural axis the intent cares about. So a second author writes a contract
from the SAME intent, blind to the first one, and a merge step looks for any axis the
second author pinned that the approved contract does not actually enforce.

Because a gap is closed by ADDING a postcondition, the proposal is just a revision of
the approved contract, and it goes through the same ratchet as stage 1: it may only
strengthen, the reference oracle must still satisfy it, and CrossHair must still confirm
it. An over-reaching proposal (one the oracle does not satisfy) is refused.
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Callable

from . import agents, verify
from .providers import API, OUTPUT_RULES, Provider, write_blocks

_MERGE_PROMPT = """A second author independently wrote a contract from the SAME intent (in
intent/intent.md). Find any behavioural axis the second author pinned that the current
contract (contract/manifest.yaml) does NOT actually enforce, and that matters for the
intent, and ADD it to the current contract.

The second author's contract:
{second}

Rules:
- Only ADD. Strengthen the current contract with postconditions (and matching
  negative_probe.must_reject entries) for any genuine gap. Never remove or weaken
  anything, and keep the exact-value postcondition.
- Add an axis only if the current reference oracle in
  contract_private/reference_impl.py already satisfies it. You are pinning a property the
  correct function already has that was just left unstated. If unsure it holds for the
  oracle, do not add it.
- If the current contract already covers everything the second author pinned, make NO
  change at all.
- Edit only files under contract/ and contract_private/. Write contract/revision_note.md
  explaining each addition, or saying no gap was found.
"""


def render_contract(manifest: dict) -> str:
    decos = manifest.get("checks", {}).get("crosshair", {}).get("decorators", [])
    axes = manifest.get("interrogated_axes", [])
    lines = [f"signature: {manifest.get('signature', '')}"]
    lines += [f"  {d}" for d in decos]
    lines += ["interrogated axes:"] + [f"  - {a}" for a in axes]
    return "\n".join(lines)


def second_author_contract(project: Path, template: Path, provider: Provider, dest: Path, *,
                           on_output: Callable[[str], None] | None = None) -> Path:
    """Run a second author from the intent alone, blind to the approved contract."""
    if dest.exists():
        shutil.rmtree(dest)
    (dest / "intent").mkdir(parents=True)
    shutil.copy(project / "intent" / "intent.md", dest / "intent" / "intent.md")
    agents.spawn_author(dest, template, provider, on_output=on_output)
    return dest


def added_anything(old: dict, new: dict) -> bool:
    """Did the merge actually add a postcondition, a must_reject body, or an axis?"""
    def parts(m: dict) -> tuple[set, set, set]:
        return (
            set(m.get("checks", {}).get("crosshair", {}).get("decorators", [])),
            set(m.get("negative_probe", {}).get("must_reject", [])),
            set(m.get("interrogated_axes", [])),
        )
    od, om, oa = parts(old)
    nd, nm, na = parts(new)
    return bool((nd - od) or (nm - om) or (na - oa))


def propose_merge(staged_a: Path, second_dir: Path, provider: Provider, *,
                  timeout: float = 420.0,
                  on_output: Callable[[str], None] | None = None) -> str:
    """Strengthen the staged approved contract with any axis the second author pinned
    that it misses. Edits staged_a in place (or writes file blocks for an API)."""
    mb = verify.load_manifest(second_dir, "contract/manifest.yaml")
    prompt = _MERGE_PROMPT.format(second=render_contract(mb))
    if provider.kind == API:
        for sub in ("intent/intent.md", "contract/manifest.yaml",
                    "contract_private/reference_impl.py"):
            p = staged_a / sub
            if p.exists():
                prompt += f"\n\n--- {sub} ---\n{p.read_text(encoding='utf-8')}"
        prompt += OUTPUT_RULES
        out = provider.run(prompt, staged_a, timeout=timeout, on_output=on_output)
        write_blocks(out, staged_a, allow=lambda rel: rel.startswith(("contract/", "contract_private/")))
        return out
    return provider.run(prompt, staged_a, timeout=timeout, on_output=on_output)
