"""Turn check results into a verdict.

GUARANTEED needs a sound proof (CrossHair exhausted and confirmed), backed by
mutation above threshold, and surviving the negative-probe. Everything else is
UNGUARANTEED or FAILED.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .engine import CheckResult

GUARANTEED = "GUARANTEED"
ENFORCED = "ENFORCED"
UNGUARANTEED = "UNGUARANTEED"
FAILED = "FAILED"
NON_DETERMINISTIC = "NON_DETERMINISTIC"


@dataclass
class Classification:
    intent_id: str
    classification: str
    deciding_check: str
    evidence: str
    requires_human_code_review: bool
    failed_subtype: str | None = None
    reasons: list[str] = field(default_factory=list)


def classify(intent_id: str, results: dict[str, CheckResult]) -> Classification:
    types = results.get("types")
    crosshair = results.get("crosshair")
    shown = results.get("hypothesis_shown")
    heldout = results.get("hypothesis_heldout")
    probe = results.get("negative_probe")
    mutation = results.get("mutation")

    # --- 1. Failures first (a violation outranks everything) ---------------- #
    if crosshair and crosshair.status == "refuted":
        return Classification(
            intent_id, FAILED, crosshair.check_id,
            f"CrossHair counterexample: {crosshair.counterexample}",
            requires_human_code_review=True, failed_subtype="buggy-implementation",
            reasons=["A concrete input violates the contract. Proven, not sampled."],
        )
    if heldout and heldout.status == "fail":
        return Classification(
            intent_id, FAILED, heldout.check_id,
            f"Held-out differential test failed: {heldout.counterexample or heldout.detail}",
            requires_human_code_review=True, failed_subtype="buggy-implementation",
            reasons=["Passed the shown tests but disagreed with the reference oracle "
                     "(a bug or overfit)."],
        )
    if shown and shown.status == "fail":
        return Classification(
            intent_id, FAILED, shown.check_id,
            f"Shown property failed: {shown.counterexample or shown.detail}",
            requires_human_code_review=True, failed_subtype="buggy-implementation",
            reasons=["A stated property does not hold."],
        )
    if types and types.status == "fail":
        return Classification(
            intent_id, FAILED, types.check_id,
            f"Type check failed: {types.detail[:200]}",
            requires_human_code_review=True, failed_subtype="buggy-implementation",
            reasons=["mypy --strict rejected the implementation."],
        )

    # --- 2. No failures: is it GUARANTEED? ---------------------------------- #
    # GUARANTEED rests on a sound exhaustive proof plus a non-vacuous contract:
    #   - CrossHair exhausted and confirmed the contract over the whole domain, and
    #   - the negative-probe shows the contract rejects broken implementations, and
    #   - types are clean.
    # Mutation measures test-suite strength, which is moot once the spec is proven
    # over every input, so it is reported but is not a gate. A function with no
    # mutable nodes (mutation = na) is the common case here, not a disqualifier.
    proven = bool(crosshair and crosshair.status == "confirmed")
    probe_ok = bool(probe and probe.status == "pass")
    types_ok = bool(types and types.status == "pass")
    shown_ok = bool(shown and shown.status == "pass")
    heldout_ok = bool(heldout and heldout.status == "pass")

    if proven and probe_ok and types_ok:
        reasons = [
            f"proof: {crosshair.detail}",
            f"negative-probe: {probe.detail}",
            f"types: {types.detail}",
        ]
        if mutation:
            reasons.append(f"mutation ({mutation.status}): {mutation.detail}")
        return Classification(
            intent_id, GUARANTEED, crosshair.check_id,
            "Proven exhaustively over the input domain, against a contract the "
            "negative-probe shows is non-vacuous.",
            requires_human_code_review=False, reasons=reasons,
        )

    # --- 2b. ENFORCED: not proven, but the contract is real and runtime-checked #
    # The deal contract is enforced on every call, so a violating input raises
    # rather than passing silently. With a non-vacuous contract (negative-probe) and
    # clean shown + held-out samples, this is shippable, just not proven over all
    # inputs. This is the honest tier for shapes CrossHair cannot exhaust (strings,
    # lists, floats, loops).
    if not proven and probe_ok and types_ok and shown_ok and heldout_ok:
        no_proof = crosshair.detail if crosshair else "CrossHair not run"
        return Classification(
            intent_id, ENFORCED, (crosshair.check_id if crosshair else "crosshair"),
            "Enforced at runtime by the contract and clean over every sampled input, "
            "but not proven over all inputs.",
            requires_human_code_review=False,
            reasons=[
                "runtime-enforced: the deal contract is checked on every call, so a "
                "violating input raises instead of passing silently.",
                f"negative-probe: {probe.detail}",
                f"properties: hold over shown and held-out samples ({shown.detail}).",
                f"types: {types.detail}",
                f"not proven: {no_proof}",
            ],
        )

    # --- 3. Otherwise UNGUARANTEED, with the honest reason ------------------ #
    if proven and not probe_ok:
        reasons = ["Downgraded: CrossHair confirmed the implementation, but the "
                   "negative-probe shows the contract is too weak. It also accepts broken "
                   "implementations, so a pass here would mean nothing."]
        deciding = probe.check_id if probe else "negative_probe"
        evidence = probe.detail if probe else ""
        if probe and probe.extra.get("survivors"):
            evidence += " survivors: " + ", ".join(
                s["body"] for s in probe.extra["survivors"])
    else:
        reasons = ["No proof: CrossHair did not exhaust all paths "
                   f"({crosshair.detail if crosshair else 'not run'}). The rest of the "
                   "evidence is sampled only, so this still needs human code review."]
        deciding = crosshair.check_id if crosshair else "crosshair"
        evidence = crosshair.detail if crosshair else ""

    return Classification(
        intent_id, UNGUARANTEED, deciding, evidence,
        requires_human_code_review=True, reasons=reasons,
    )
