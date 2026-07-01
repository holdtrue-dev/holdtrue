"""Run the full contract against an implementation and classify the result.

Shared by the CLI and the tests so both exercise the same path.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

import yaml

from . import engine
from .classify import (Classification, FAILED, classify, classify_function,
                       classify_multi)


def load_manifest(project: Path, manifest_rel: str) -> dict:
    p = Path(manifest_rel)
    if not p.is_absolute():
        p = project / manifest_rel
    return _normalize_manifest(yaml.safe_load(p.read_text(encoding="utf-8")))


def _normalize_manifest(manifest: dict) -> dict:
    """Accept either shape for a per-function contract's decorators: flat on the
    function entry (`decorators: [...]`) or nested under `checks.crosshair.decorators`,
    which mirrors the single-function schema and is what the author naturally writes.
    Normalise to a flat `decorators` key so the rest of the code reads one shape."""
    for spec in manifest.get("functions") or []:
        if "decorators" not in spec:
            spec["decorators"] = (spec.get("checks", {}).get("crosshair", {})
                                  .get("decorators", []))
    return manifest


def run_verification(
    project: Path,
    impl_path: Path,
    manifest: dict,
    *,
    sandbox_on: bool = True,
    mutation: bool = True,
    on_result: Callable[[engine.CheckResult], None] | None = None,
) -> tuple[dict[str, engine.CheckResult], Classification]:
    if "functions" in manifest:
        return _run_multi(project, impl_path, manifest, sandbox_on=sandbox_on,
                          mutation=mutation, on_result=on_result)
    contract_dir = project / "contract"
    private_dir = project / "contract_private"
    impl_source = impl_path.read_text(encoding="utf-8")

    checks = manifest["checks"]
    decorators = checks["crosshair"]["decorators"]
    signature = manifest["signature"]
    func = manifest.get("function", "clamp")
    shown_src = (contract_dir / checks["hypothesis_shown"]).read_text(encoding="utf-8")
    heldout_src = (private_dir / checks["hypothesis_heldout"]).read_text(encoding="utf-8")
    ref_src = (private_dir / "reference_impl.py").read_text(encoding="utf-8")
    threshold = checks.get("mutation", {}).get("threshold", 0.85)
    must_reject = manifest.get("negative_probe", {}).get("must_reject", [])

    # Rich-type contracts share a pydantic models module and are enforced at runtime
    # rather than proven. CrossHair cannot reason over the models, so it is skipped and
    # the negative-probe runs at runtime: the verdict caps at ENFORCED, honestly.
    models_rel = manifest.get("models")
    models_src = (contract_dir / models_rel).read_text(encoding="utf-8") if models_rel else None
    shared = {"models.py": models_src} if models_src else {}
    runtime = manifest.get("enforcement") == "runtime"

    results: dict[str, engine.CheckResult] = {}

    def emit(r: engine.CheckResult) -> None:
        results[r.kind] = r
        if on_result:
            on_result(r)

    emit(engine.run_types("CHK-types", impl_source, extra=shared, sandbox_on=sandbox_on))
    if runtime:
        emit(engine.CheckResult(
            "CHK-symbolic", "crosshair", "unconfirmed",
            detail="not attempted: a runtime-enforced contract over rich types "
                   "(pydantic). Enforced on every call, not proven over all inputs."))
    else:
        emit(engine.run_crosshair("CHK-symbolic", decorators, impl_source, function=func,
                                  extra=shared, sandbox_on=sandbox_on))
    emit(engine.run_pytest("CHK-prop-shown", "hypothesis_shown", shown_src, impl_source,
                           deps=dict(shared), sandbox_on=sandbox_on))
    emit(engine.run_pytest("CHK-prop-heldout", "hypothesis_heldout", heldout_src,
                           impl_source, deps={"reference_impl.py": ref_src, **shared},
                           sandbox_on=sandbox_on))
    if runtime:
        emit(engine.run_negative_probe_runtime(
            "CHK-negprobe", signature, decorators, must_reject, shown_src, function=func,
            prelude=("from models import *\n" if models_src else ""),
            deps=dict(shared), sandbox_on=sandbox_on))
    else:
        emit(engine.run_negative_probe("CHK-negprobe", signature, decorators, must_reject,
                                       function=func, sandbox_on=sandbox_on))
    if mutation:
        emit(engine.run_mutation(
            "CHK-mutation", impl_source,
            {"test_shown.py": shown_src, "test_heldout.py": heldout_src,
             "reference_impl.py": ref_src, **shared},
            threshold))

    return results, classify(manifest["intent_id"], results)


def _run_multi(
    project: Path,
    impl_path: Path,
    manifest: dict,
    *,
    sandbox_on: bool,
    mutation: bool,
    on_result: Callable[[engine.CheckResult], None] | None,
) -> tuple[dict[str, engine.CheckResult], Classification]:
    """Verify a contract that declares several functions in one module.

    The types, the shown property tests, the held-out differential tests, and the
    mutation run are all over the whole module and are shared. The proof and the
    negative-probe are per function: each function's decorators are spliced onto that
    function alone and proven on its own, so a weak spot in one function cannot borrow
    another function's proof. The overall verdict is the weakest function's verdict.
    """
    contract_dir = project / "contract"
    private_dir = project / "contract_private"
    impl_source = impl_path.read_text(encoding="utf-8")

    checks = manifest["checks"]
    functions = manifest["functions"]
    shown_src = (contract_dir / checks["hypothesis_shown"]).read_text(encoding="utf-8")
    heldout_src = (private_dir / checks["hypothesis_heldout"]).read_text(encoding="utf-8")
    ref_src = (private_dir / "reference_impl.py").read_text(encoding="utf-8")
    threshold = checks.get("mutation", {}).get("threshold", 0.85)

    models_rel = manifest.get("models")
    models_src = (contract_dir / models_rel).read_text(encoding="utf-8") if models_rel else None
    shared = {"models.py": models_src} if models_src else {}

    results: dict[str, engine.CheckResult] = {}

    def emit(key: str, r: engine.CheckResult) -> None:
        results[key] = r
        if on_result:
            on_result(r)

    # Shared checks, over the whole module, once.
    types = engine.run_types("CHK-types", impl_source, extra=shared, sandbox_on=sandbox_on)
    emit("types", types)
    shown = engine.run_pytest("CHK-prop-shown", "hypothesis_shown", shown_src, impl_source,
                              deps=dict(shared), sandbox_on=sandbox_on)
    emit("hypothesis_shown", shown)
    heldout = engine.run_pytest("CHK-prop-heldout", "hypothesis_heldout", heldout_src,
                                impl_source, deps={"reference_impl.py": ref_src, **shared},
                                sandbox_on=sandbox_on)
    emit("hypothesis_heldout", heldout)
    mut = None
    if mutation:
        mut = engine.run_mutation(
            "CHK-mutation", impl_source,
            {"test_shown.py": shown_src, "test_heldout.py": heldout_src,
             "reference_impl.py": ref_src, **shared},
            threshold)
        emit("mutation", mut)

    # Per-function proof and negative-probe, then a per-function verdict.
    per_function: dict[str, Classification] = {}
    for spec in functions:
        name = spec["function"]
        signature = spec["signature"]
        decorators = spec.get("decorators", [])
        if not decorators:
            raise ValueError(
                f"function {name!r} has no contract decorators; expected them under "
                "checks.crosshair.decorators (or a flat decorators: list)")
        must_reject = spec.get("negative_probe", {}).get("must_reject", [])
        runtime = spec.get("enforcement", manifest.get("enforcement")) == "runtime"

        if runtime:
            crosshair = engine.CheckResult(
                f"CHK-symbolic[{name}]", "crosshair", "unconfirmed",
                detail=f"[{name}] not attempted: a runtime-enforced contract over rich "
                       "types. Enforced on every call, not proven over all inputs.")
        else:
            crosshair = engine.run_crosshair(f"CHK-symbolic[{name}]", decorators,
                                             impl_source, function=name, extra=shared,
                                             sandbox_on=sandbox_on)
        crosshair.detail = f"[{name}] {crosshair.detail}"
        emit(f"crosshair[{name}]", crosshair)

        if runtime:
            probe = engine.run_negative_probe_runtime(
                f"CHK-negprobe[{name}]", signature, decorators, must_reject, shown_src,
                function=name, prelude=("from models import *\n" if models_src else ""),
                base_src=ref_src, deps=dict(shared), sandbox_on=sandbox_on)
        else:
            probe = engine.run_negative_probe(f"CHK-negprobe[{name}]", signature,
                                              decorators, must_reject, function=name,
                                              sandbox_on=sandbox_on)
        probe.detail = f"[{name}] {probe.detail}"
        emit(f"negative_probe[{name}]", probe)

        per_function[name] = classify_function(
            manifest["intent_id"], types=types, crosshair=crosshair, probe=probe,
            shown=shown, heldout=heldout)

    overall = classify_multi(manifest["intent_id"], per_function)

    # Module-level shared checks fail once for the whole module. If one failed but no
    # single function was individually blamed (a runtime-enforced shape CrossHair could
    # not refute, caught only by the property tests), surface it as FAILED rather than
    # let a verdict stand on a module that does not type-check or agree with the oracle.
    # Attribute the failure to a function when the failing test names one, since a
    # shared property test cannot self-attribute the way a per-function proof can.
    if overall.classification != FAILED:
        for shared in (types, shown, heldout):
            if shared.status == "fail":
                text = f"{shared.detail or ''} {shared.counterexample or ''}"
                # Longest name first, so test_satisfies_all is charged to satisfies_all,
                # not to satisfies (whose test_ prefix is a substring of it).
                culprit = next((spec["function"] for spec in
                                sorted(functions, key=lambda s: len(s["function"]),
                                       reverse=True)
                                if f"test_{spec['function']}" in text), None)
                evidence = shared.counterexample or shared.detail
                reasons = ["module-wide " + shared.kind + " failed"
                           + (f" (function {culprit!r})" if culprit else "")
                           + f": {evidence}"]
                reasons += [f"{n}: {c.classification}" for n, c in per_function.items()]
                overall = Classification(
                    manifest["intent_id"], FAILED,
                    f"{culprit}::{shared.check_id}" if culprit else shared.check_id,
                    (f"function {culprit!r}: " if culprit else "") + (evidence or ""),
                    requires_human_code_review=True,
                    failed_subtype="buggy-implementation", reasons=reasons)
                break

    return results, overall
