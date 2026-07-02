"""Run the full contract against an implementation and classify the result.

Shared by the CLI and the tests so both exercise the same path.
"""
from __future__ import annotations

import concurrent.futures
import threading
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
    oracle_mutation: bool = False,
    parallel: bool = True,
    on_result: Callable[[engine.CheckResult], None] | None = None,
) -> tuple[dict[str, engine.CheckResult], Classification]:
    if "functions" in manifest:
        return _run_multi(project, impl_path, manifest, sandbox_on=sandbox_on,
                          mutation=mutation, oracle_mutation=oracle_mutation,
                          parallel=parallel, on_result=on_result)
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
    _lock = threading.Lock()

    def emit(r: engine.CheckResult) -> None:
        with _lock:
            results[r.kind] = r
            if on_result:
                on_result(r)

    # Static results (no subprocess): emit before the parallel section so they appear
    # immediately in the streaming UI even when parallel=True.
    if runtime:
        emit(engine.CheckResult(
            "CHK-symbolic", "crosshair", "unconfirmed",
            detail="not attempted: a runtime-enforced contract over rich types "
                   "(pydantic). Enforced on every call, not proven over all inputs."))

    # Build the callable task list.  Every entry is a zero-argument callable that
    # returns a CheckResult; they are all independent and safe to run concurrently.
    tasks: list[Callable[[], engine.CheckResult]] = [
        lambda: engine.run_types("CHK-types", impl_source, extra=shared,
                                 sandbox_on=sandbox_on),
        lambda: engine.run_pytest("CHK-prop-shown", "hypothesis_shown", shown_src,
                                  impl_source, deps=dict(shared), sandbox_on=sandbox_on),
        lambda: engine.run_pytest("CHK-prop-heldout", "hypothesis_heldout", heldout_src,
                                  impl_source,
                                  deps={"reference_impl.py": ref_src, **shared},
                                  sandbox_on=sandbox_on),
    ]

    if runtime:
        prelude = "from models import *\n" if models_src else ""
        tasks.append(
            lambda: engine.run_negative_probe_runtime(
                "CHK-negprobe", signature, decorators, must_reject, shown_src,
                function=func, prelude=prelude, deps=dict(shared),
                sandbox_on=sandbox_on))
    else:
        tasks.append(
            lambda: engine.run_crosshair("CHK-symbolic", decorators, impl_source,
                                         function=func, extra=shared,
                                         sandbox_on=sandbox_on))
        tasks.append(
            lambda: engine.run_negative_probe("CHK-negprobe", signature, decorators,
                                              must_reject, function=func,
                                              sandbox_on=sandbox_on))

    if mutation:
        tasks.append(
            lambda: engine.run_mutation(
                "CHK-mutation", impl_source,
                {"test_shown.py": shown_src, "test_heldout.py": heldout_src,
                 "reference_impl.py": ref_src, **shared},
                threshold, sandbox_on=sandbox_on))

    if oracle_mutation:
        tasks.append(
            lambda: engine.run_oracle_mutation(
                "CHK-oracle-mut", ref_src, shown_src, heldout_src,
                threshold, sandbox_on=sandbox_on))

    _dispatch(tasks, emit, parallel=parallel)
    return results, classify(manifest["intent_id"], results)


def _dispatch(
    tasks: list[Callable[[], engine.CheckResult]],
    emit: Callable[[engine.CheckResult], None],
    *,
    parallel: bool,
) -> None:
    """Run tasks and call emit for each result, in parallel or sequentially."""
    if parallel and len(tasks) > 1:
        with concurrent.futures.ThreadPoolExecutor() as ex:
            futs = [ex.submit(t) for t in tasks]
            for fut in concurrent.futures.as_completed(futs):
                emit(fut.result())
    else:
        for t in tasks:
            emit(t())


def _run_multi(
    project: Path,
    impl_path: Path,
    manifest: dict,
    *,
    sandbox_on: bool,
    mutation: bool,
    oracle_mutation: bool,
    parallel: bool,
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
    _lock = threading.Lock()

    def emit(key: str, r: engine.CheckResult) -> None:
        with _lock:
            results[key] = r
            if on_result:
                on_result(r)

    # Build all runnable tasks with their result keys.
    # Static (no-subprocess) results for runtime-enforced functions are emitted
    # before the parallel section so they appear immediately in the streaming UI.
    keyed_tasks: list[tuple[str, Callable[[], engine.CheckResult]]] = [
        ("types", lambda: engine.run_types("CHK-types", impl_source, extra=shared,
                                           sandbox_on=sandbox_on)),
        ("hypothesis_shown", lambda: engine.run_pytest(
            "CHK-prop-shown", "hypothesis_shown", shown_src, impl_source,
            deps=dict(shared), sandbox_on=sandbox_on)),
        ("hypothesis_heldout", lambda: engine.run_pytest(
            "CHK-prop-heldout", "hypothesis_heldout", heldout_src, impl_source,
            deps={"reference_impl.py": ref_src, **shared}, sandbox_on=sandbox_on)),
    ]

    if mutation:
        keyed_tasks.append(
            ("mutation", lambda: engine.run_mutation(
                "CHK-mutation", impl_source,
                {"test_shown.py": shown_src, "test_heldout.py": heldout_src,
                 "reference_impl.py": ref_src, **shared},
                threshold, sandbox_on=sandbox_on)))

    if oracle_mutation:
        keyed_tasks.append(
            ("oracle_mutation", lambda: engine.run_oracle_mutation(
                "CHK-oracle-mut", ref_src, shown_src, heldout_src,
                threshold, sandbox_on=sandbox_on)))

    # Per-function tasks, one crosshair and one probe per function.
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
            # Emit the no-op crosshair result immediately; only the probe is a task.
            _ch = engine.CheckResult(
                f"CHK-symbolic[{name}]", "crosshair", "unconfirmed",
                detail=f"[{name}] not attempted: a runtime-enforced contract over rich "
                       "types. Enforced on every call, not proven over all inputs.")
            emit(f"crosshair[{name}]", _ch)
            prelude = "from models import *\n" if models_src else ""

            def _make_probe_rt(n=name, sig=signature, decs=decorators,
                               mrej=must_reject, prel=prelude):
                def _run():
                    r = engine.run_negative_probe_runtime(
                        f"CHK-negprobe[{n}]", sig, decs, mrej, shown_src,
                        function=n, prelude=prel, base_src=ref_src,
                        deps=dict(shared), sandbox_on=sandbox_on)
                    r.detail = f"[{n}] {r.detail}"
                    return r
                return _run

            keyed_tasks.append((f"negative_probe[{name}]", _make_probe_rt()))
        else:
            def _make_crosshair(n=name, decs=decorators):
                def _run():
                    r = engine.run_crosshair(
                        f"CHK-symbolic[{n}]", decs, impl_source, function=n,
                        extra=shared, sandbox_on=sandbox_on)
                    r.detail = f"[{n}] {r.detail}"
                    return r
                return _run

            def _make_probe(n=name, sig=signature, decs=decorators, mrej=must_reject):
                def _run():
                    r = engine.run_negative_probe(
                        f"CHK-negprobe[{n}]", sig, decs, mrej, function=n,
                        sandbox_on=sandbox_on)
                    r.detail = f"[{n}] {r.detail}"
                    return r
                return _run

            keyed_tasks.append((f"crosshair[{name}]", _make_crosshair()))
            keyed_tasks.append((f"negative_probe[{name}]", _make_probe()))

    # Run all tasks, collecting results.
    def keyed_emit(key: str, r: engine.CheckResult) -> None:
        emit(key, r)

    if parallel and len(keyed_tasks) > 1:
        with concurrent.futures.ThreadPoolExecutor() as ex:
            fut_map = {ex.submit(task): key for key, task in keyed_tasks}
            for fut in concurrent.futures.as_completed(fut_map):
                keyed_emit(fut_map[fut], fut.result())
    else:
        for key, task in keyed_tasks:
            keyed_emit(key, task())

    # Per-function classification (sequential; all results are now available).
    types = results.get("types")
    shown = results.get("hypothesis_shown")
    heldout = results.get("hypothesis_heldout")

    per_function: dict[str, Classification] = {}
    for spec in functions:
        name = spec["function"]
        crosshair = results.get(f"crosshair[{name}]")
        probe = results.get(f"negative_probe[{name}]")
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
        for shared_r in (types, shown, heldout):
            if shared_r and shared_r.status == "fail":
                text = f"{shared_r.detail or ''} {shared_r.counterexample or ''}"
                # Longest name first, so test_satisfies_all is charged to satisfies_all,
                # not to satisfies (whose test_ prefix is a substring of it).
                culprit = next((spec["function"] for spec in
                                sorted(functions, key=lambda s: len(s["function"]),
                                       reverse=True)
                                if f"test_{spec['function']}" in text), None)
                evidence = shared_r.counterexample or shared_r.detail
                reasons = ["module-wide " + shared_r.kind + " failed"
                           + (f" (function {culprit!r})" if culprit else "")
                           + f": {evidence}"]
                reasons += [f"{n}: {c.classification}" for n, c in per_function.items()]
                overall = Classification(
                    manifest["intent_id"], FAILED,
                    f"{culprit}::{shared_r.check_id}" if culprit else shared_r.check_id,
                    (f"function {culprit!r}: " if culprit else "") + (evidence or ""),
                    requires_human_code_review=True,
                    failed_subtype="buggy-implementation", reasons=reasons)
                break

    return results, overall
