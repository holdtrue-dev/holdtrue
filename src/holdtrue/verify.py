"""Run the full contract against an implementation and classify the result.

Shared by the CLI and the tests so both exercise the same path.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

import yaml

from . import engine
from .classify import Classification, classify


def load_manifest(project: Path, manifest_rel: str) -> dict:
    p = Path(manifest_rel)
    if not p.is_absolute():
        p = project / manifest_rel
    return yaml.safe_load(p.read_text(encoding="utf-8"))


def run_verification(
    project: Path,
    impl_path: Path,
    manifest: dict,
    *,
    sandbox_on: bool = True,
    mutation: bool = True,
    on_result: Callable[[engine.CheckResult], None] | None = None,
) -> tuple[dict[str, engine.CheckResult], Classification]:
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
