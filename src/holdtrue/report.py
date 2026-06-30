"""The evidence report: the thing the human signs off on, not a diff.

Per intent it gives the verdict, the deciding check and its evidence, the
mutation score, the negative-probe result, which intent axes were interrogated,
and whether human code review is still needed.
"""
from __future__ import annotations

import json
from dataclasses import asdict

from .classify import Classification, ENFORCED, GUARANTEED, UNGUARANTEED, FAILED
from .engine import CheckResult

_BADGE = {GUARANTEED: "GUARANTEED", ENFORCED: "ENFORCED", UNGUARANTEED: "UNGUARANTEED",
          FAILED: "FAILED", "NON_DETERMINISTIC": "NON-DETERMINISTIC"}


def build_report(manifest: dict, impl_label: str, results: dict[str, CheckResult],
                 classification: Classification, sandboxed: bool) -> dict:
    return {
        "intent_id": manifest.get("intent_id"),
        "summary": manifest.get("summary"),
        "signature": manifest.get("signature"),
        "implementation": impl_label,
        "classification": classification.classification,
        "deciding_check": classification.deciding_check,
        "evidence": classification.evidence,
        "failed_subtype": classification.failed_subtype,
        "requires_human_code_review": classification.requires_human_code_review,
        "reasons": classification.reasons,
        "intent_coverage": {
            "interrogated_axes": manifest.get("interrogated_axes", []),
            "note": "Axes not listed were never interrogated. Confirming the contract is "
                    "complete is the human's job.",
        },
        "execution": {
            "sandboxed": sandboxed,
            "sandbox": "bubblewrap" if sandboxed else "direct subprocess (UNSANDBOXED)",
        },
        "checks": {cid: _check_dict(r) for cid, r in results.items()},
    }


def _check_dict(r: CheckResult) -> dict:
    d = asdict(r)
    return {k: v for k, v in d.items() if v not in (None, "", {}, [])}


def render_md(report: dict) -> str:
    c = report["classification"]
    lines = [
        "# holdtrue evidence report",
        "",
        f"**Intent `{report['intent_id']}`**: {report['summary']}",
        "",
        f"`{report['signature']}`  ·  implementation: `{report['implementation']}`",
        "",
        f"## Verdict: {_BADGE.get(c, c)}",
        "",
    ]
    if report.get("failed_subtype"):
        lines.append(f"- **Failure class:** {report['failed_subtype']}")
    lines += [
        f"- **Deciding check:** `{report['deciding_check']}`",
        f"- **Evidence:** {report['evidence']}",
        f"- **Still requires human code review:** "
        f"{'YES' if report['requires_human_code_review'] else 'no'}",
        "",
        "### Why",
    ]
    for reason in report["reasons"]:
        lines.append(f"- {reason}")

    lines += ["", "### Checks", "",
              "| check | kind | status | detail |",
              "| --- | --- | --- | --- |"]
    for cid, ch in report["checks"].items():
        detail = (ch.get("detail", "") or "").replace("\n", " ")[:90]
        lines.append(f"| `{cid}` | {ch['kind']} | **{ch['status']}** | {detail} |")

    cov = report["intent_coverage"]
    lines += ["", "### Intent coverage", "",
              "Interrogated axes (what the contract was built to cover):"]
    for ax in cov["interrogated_axes"]:
        lines.append(f"- {ax}")
    lines += ["", f"> {cov['note']}", "",
              "### Execution",
              f"- Sandbox: **{report['execution']['sandbox']}**", ""]
    if c == GUARANTEED:
        lines.append("> GUARANTEED means the code provably satisfies the approved "
                     "contract over all inputs. It does not mean the contract matches "
                     "what you meant. You still own the contract.")
    elif c == ENFORCED:
        lines.append("> ENFORCED means the contract is checked at runtime on every call "
                     "(a violating input raises, it does not pass silently) and holds over "
                     "every sampled input, but it was not proven over all inputs. Ship it "
                     "with the contract attached. You still own the contract.")
    elif c == UNGUARANTEED:
        lines.append("> UNGUARANTEED is a normal result. holdtrue got all the evidence it "
                     "soundly can; this intent still needs human code review.")
    return "\n".join(lines) + "\n"


def to_json(report: dict) -> str:
    return json.dumps(report, indent=2)
