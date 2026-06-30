"""An append-only record of every contract revision, so a change is never silent.

Two files under <project>/revisions/: revisions.jsonl for tools and CHANGELOG.md for
humans. Each entry says what triggered the revision, what changed, why, who approved
it, and the self-check outcome before and after.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


def record(project: Path, *, trigger: str, evidence: str, diff: str,
           justification: str, approved_by: str, applied: bool) -> None:
    out = project / "revisions"
    out.mkdir(exist_ok=True)
    stamp = datetime.now().isoformat(timespec="seconds")
    entry = {
        "time": stamp,
        "trigger": trigger,
        "evidence": evidence,
        "diff": diff,
        "justification": justification,
        "approved_by": approved_by,
        "applied": applied,
    }
    with (out / "revisions.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")

    md = out / "CHANGELOG.md"
    head = "" if md.exists() else "# Contract revisions\n\nEvery change to the contract, with its reason.\n"
    block = [
        f"\n## {stamp}  ({'applied' if applied else 'proposed, not applied'})",
        f"\n**Trigger:** {trigger}",
        f"\n**Why it failed:** {evidence}",
        f"\n**Justification:** {justification}",
        f"\n**Approved by:** {approved_by}",
        "\n\n```diff\n" + (diff or "(no textual diff)") + "\n```\n",
    ]
    with md.open("a", encoding="utf-8") as f:
        if head:
            f.write(head)
        f.write("\n".join(block))
