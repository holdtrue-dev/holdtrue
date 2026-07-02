"""Python language plugin — migrates the single-function, multi-function, and stateful
verification paths from verify.py into the Language interface."""
from __future__ import annotations

import concurrent.futures
import threading
from pathlib import Path
from typing import Callable

from .. import engine
from ..classify import Classification, FAILED, classify, classify_function, classify_multi
from .base import Language, dispatch, make_emit


class PythonLanguage(Language):
    name = "python"
    display_name = "Python"
    file_extension = ".py"
    verdict_ceiling = "GUARANTEED"

    def available(self) -> bool:
        return True

    def author_instructions(self) -> str:
        return """\
Write a Python contract. The manifest must NOT set `language:` (Python is the default).

Two kinds of contract:
- PROVABLE: ALL inputs are `int` or `bool`, no collections. CrossHair exhausts int
  domains quickly. Aim for GUARANTEED.
- ENFORCED: anything with List, Sequence, Tuple, Set, Dict, str, float, or pydantic
  types. Add `enforcement: runtime`. Aim for ENFORCED.

Tools: mypy --strict (types), CrossHair (proof), Hypothesis (properties),
       deal (contracts), cosmic-ray (mutation).
"""

    def run_checks(
        self,
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
        if "functions" in manifest:
            return self._run_multi(project, impl_path, manifest,
                                   sandbox_on=sandbox_on, mutation=mutation,
                                   oracle_mutation=oracle_mutation, parallel=parallel,
                                   on_result=on_result)
        if "stateful" in manifest.get("checks", {}):
            return self._run_stateful(project, impl_path, manifest,
                                      sandbox_on=sandbox_on, mutation=mutation,
                                      parallel=parallel, on_result=on_result)
        return self._run_single(project, impl_path, manifest,
                                sandbox_on=sandbox_on, mutation=mutation,
                                oracle_mutation=oracle_mutation, parallel=parallel,
                                on_result=on_result)

    def _run_single(
        self,
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

        models_rel = manifest.get("models")
        models_src = (contract_dir / models_rel).read_text(encoding="utf-8") if models_rel else None
        shared = {"models.py": models_src} if models_src else {}
        runtime = manifest.get("enforcement") == "runtime"

        results: dict[str, engine.CheckResult] = {}
        emit = make_emit(results, on_result)

        if runtime:
            emit(engine.CheckResult(
                "CHK-symbolic", "crosshair", "unconfirmed",
                detail="not attempted: a runtime-enforced contract over rich types "
                       "(pydantic). Enforced on every call, not proven over all inputs."))

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

        dispatch(tasks, emit, parallel=parallel)
        return results, classify(manifest["intent_id"], results)

    def _run_multi(
        self,
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

        if parallel and len(keyed_tasks) > 1:
            with concurrent.futures.ThreadPoolExecutor() as ex:
                fut_map = {ex.submit(task): key for key, task in keyed_tasks}
                for fut in concurrent.futures.as_completed(fut_map):
                    emit(fut_map[fut], fut.result())
        else:
            for key, task in keyed_tasks:
                emit(key, task())

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

        if overall.classification != FAILED:
            for shared_r in (types, shown, heldout):
                if shared_r and shared_r.status == "fail":
                    text = f"{shared_r.detail or ''} {shared_r.counterexample or ''}"
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

    def _run_stateful(
        self,
        project: Path,
        impl_path: Path,
        manifest: dict,
        *,
        sandbox_on: bool,
        mutation: bool,
        parallel: bool,
        on_result: Callable[[engine.CheckResult], None] | None,
    ) -> tuple[dict[str, engine.CheckResult], Classification]:
        contract_dir = project / "contract"
        private_dir = project / "contract_private"
        impl_source = impl_path.read_text(encoding="utf-8")

        checks = manifest["checks"]
        stateful_src = (contract_dir / checks["stateful"]).read_text(encoding="utf-8")
        shown_src = (contract_dir / checks["hypothesis_shown"]).read_text(encoding="utf-8")
        heldout_src = (private_dir / checks["hypothesis_heldout"]).read_text(encoding="utf-8")
        ref_src = (private_dir / "reference_impl.py").read_text(encoding="utf-8")
        threshold = checks.get("mutation", {}).get("threshold", 0.80)

        results: dict[str, engine.CheckResult] = {}
        emit = make_emit(results, on_result)

        emit(engine.CheckResult(
            "CHK-symbolic", "crosshair", "unconfirmed",
            detail="not attempted: stateful class contract. "
                   "CrossHair cannot exhaust class-instance state spaces. "
                   "Verdict is capped at ENFORCED."))

        tasks: list[Callable[[], engine.CheckResult]] = [
            lambda: engine.run_types("CHK-types", impl_source, sandbox_on=sandbox_on),
            lambda: engine.run_stateful("CHK-stateful", stateful_src, impl_source,
                                        sandbox_on=sandbox_on),
            lambda: engine.run_pytest("CHK-prop-shown", "hypothesis_shown", shown_src,
                                      impl_source, sandbox_on=sandbox_on),
            lambda: engine.run_pytest("CHK-prop-heldout", "hypothesis_heldout", heldout_src,
                                      impl_source, deps={"reference_impl.py": ref_src},
                                      sandbox_on=sandbox_on),
        ]

        if mutation:
            tasks.append(
                lambda: engine.run_mutation(
                    "CHK-mutation", impl_source,
                    {"test_shown.py": shown_src, "test_heldout.py": heldout_src,
                     "test_stateful.py": stateful_src, "reference_impl.py": ref_src},
                    threshold, sandbox_on=sandbox_on))

        dispatch(tasks, emit, parallel=parallel)
        return results, classify(manifest["intent_id"], results)
