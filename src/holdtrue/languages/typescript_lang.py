"""TypeScript language plugin."""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from .. import engine
from ..classify import Classification, classify
from .base import Language, dispatch, make_emit


class TypeScriptLanguage(Language):
    name = "typescript"
    display_name = "TypeScript"
    file_extension = ".ts"
    verdict_ceiling = "ENFORCED"

    def available(self) -> bool:
        import shutil
        return shutil.which("node") is not None

    def author_instructions(self) -> str:
        return """\
Write a TypeScript contract. Set `language: typescript` in the manifest.

Layout:
  contract/manifest.yaml          (language: typescript)
  contract/tests_shown/test_<name>.test.ts
  contract_private/tests_heldout/test_<name>_heldout.test.ts
  contract_private/reference_impl.ts

Tests use fast-check and jest. The implementer writes core.ts; import with
`import { <func> } from './core'`. The heldout test also imports
`import { <func> as oracle } from './reference_impl'`.

GUARANTEED is not achievable (no symbolic prover for TypeScript). Aim for ENFORCED.
Set `acceptance: { target_class: ENFORCED }`.
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
        contract_dir = project / "contract"
        private_dir = project / "contract_private"
        impl_source = impl_path.read_text(encoding="utf-8")

        checks = manifest["checks"]
        shown_src = (contract_dir / checks["hypothesis_shown"]).read_text(encoding="utf-8")
        heldout_src = (private_dir / checks["hypothesis_heldout"]).read_text(encoding="utf-8")
        ref_src = (private_dir / "reference_impl.ts").read_text(encoding="utf-8")
        threshold = checks.get("mutation", {}).get("threshold", 0.75)
        must_reject = manifest.get("negative_probe", {}).get("must_reject", [])
        impl_template = manifest.get("negative_probe", {}).get("impl_template", "")

        results: dict[str, engine.CheckResult] = {}
        emit = make_emit(results, on_result)

        emit(engine.CheckResult(
            "CHK-symbolic", "crosshair", "unconfirmed",
            detail="not attempted: TypeScript has no symbolic prover. "
                   "GUARANTEED is not achievable; the maximum is ENFORCED."))

        tasks: list[Callable[[], engine.CheckResult]] = [
            lambda: engine.run_types_ts("CHK-types", impl_source),
            lambda: engine.run_jest("CHK-prop-shown", "hypothesis_shown",
                                    shown_src, impl_source),
            lambda: engine.run_jest("CHK-prop-heldout", "hypothesis_heldout",
                                    heldout_src, impl_source,
                                    extra_files={"reference_impl.ts": ref_src}),
        ]

        if must_reject and impl_template:
            tasks.append(
                lambda: engine.run_ts_probe("CHK-negprobe", must_reject,
                                            shown_src, impl_template))

        if mutation:
            tasks.append(
                lambda: engine.run_stryker("CHK-mutation", impl_source, shown_src,
                                           threshold))

        dispatch(tasks, emit, parallel=parallel)
        return results, classify(manifest["intent_id"], results)
