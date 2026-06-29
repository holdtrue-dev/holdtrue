"""holdtrue CLI.

`holdtrue verify <project> --impl <file>` runs the contract against an
implementation. `holdtrue implement <project>` spawns a separate LLM context that
writes the implementation from the contract alone, then verifies it.
"""
from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

from . import agents, engine, report, verify


def _on_result(r: engine.CheckResult) -> None:
    print(f"  {r.status.upper():11} {r.kind:18} {r.detail[:60]}")


def _finish(project: Path, impl_label: str, manifest: dict, results: dict,
            cls, sb: bool) -> None:
    rep = report.build_report(manifest, impl_label, results, cls,
                              sandboxed=(sb and engine.sandbox.bwrap_available()))
    out_dir = project / "reports"
    out_dir.mkdir(exist_ok=True)
    (out_dir / "evidence_report.json").write_text(report.to_json(rep), encoding="utf-8")
    (out_dir / "evidence_report.md").write_text(report.render_md(rep), encoding="utf-8")
    print("-" * 72)
    badge = report._BADGE.get(cls.classification, cls.classification)
    print(f"  VERDICT: {badge}    (deciding: {cls.deciding_check})")
    for reason in cls.reasons:
        print(f"    - {reason}")
    print(f"  human code review still required: "
          f"{'YES' if cls.requires_human_code_review else 'no'}")
    print(f"  report: {out_dir / 'evidence_report.md'}\n")


def cmd_verify(args: argparse.Namespace) -> int:
    project = Path(args.project).resolve()
    manifest = verify.load_manifest(project, args.manifest)
    sb = not args.no_sandbox
    print(f"\nholdtrue verify  {manifest['intent_id']}  impl={Path(args.impl).name}"
          f"  sandbox={'bwrap' if sb and engine.sandbox.bwrap_available() else 'off'}")
    print("-" * 72)
    if args.no_mutation:
        print("  (mutation skipped)")
    results, cls = verify.run_verification(
        project, Path(args.impl).resolve(), manifest,
        sandbox_on=sb, mutation=not args.no_mutation, on_result=_on_result)
    _finish(project, Path(args.impl).name, manifest, results, cls, sb)
    return 0


def cmd_implement(args: argparse.Namespace) -> int:
    if not agents.available():
        print("claude CLI not found; cannot spawn the implementer.")
        return 1
    project = Path(args.project).resolve()
    manifest = verify.load_manifest(project, args.manifest)
    ws = Path(tempfile.mkdtemp(prefix="holdtrue_impl_"))
    agents.stage_workspace(project, manifest, ws)
    print(f"\nholdtrue implement  {manifest['intent_id']}")
    print("  spawning implementer in a separate context (sees only the contract) ...")
    impl_path, _ = agents.spawn_implementer(ws, manifest)
    if not impl_path.exists() or "NotImplementedError" in impl_path.read_text():
        print("  implementer did not produce an implementation.")
        return 1
    print("-" * 72)
    print(impl_path.read_text().rstrip())
    print("-" * 72)
    if args.no_verify:
        print(f"  implementation: {impl_path}\n")
        return 0
    sb = not args.no_sandbox
    if args.no_mutation:
        print("  (mutation skipped)")
    results, cls = verify.run_verification(
        project, impl_path, manifest,
        sandbox_on=sb, mutation=not args.no_mutation, on_result=_on_result)
    _finish(project, "implementer (llm)", manifest, results, cls, sb)
    return 0


def cmd_author(args: argparse.Namespace) -> int:
    if not agents.available():
        print("claude CLI not found; cannot spawn the author.")
        return 1
    project = Path(args.project).resolve()
    if not (project / "intent" / "intent.md").exists():
        print("no intent/intent.md in the project.")
        return 1
    template = Path(args.template).resolve()
    print(f"\nholdtrue author  {project.name}")
    print("  spawning contract author in a separate context (reads intent, writes contract) ...")
    agents.spawn_author(project, template)
    if not (project / "contract" / "manifest.yaml").exists():
        print("  author did not produce contract/manifest.yaml.")
        return 1
    manifest = verify.load_manifest(project, "contract/manifest.yaml")
    print("-" * 72)
    print(f"  intent_id : {manifest.get('intent_id')}")
    print(f"  summary   : {manifest.get('summary')}")
    print(f"  signature : {manifest.get('signature')}")
    print("  contract (must hold):")
    for d in manifest.get("checks", {}).get("crosshair", {}).get("decorators", []):
        print(f"    {d}")
    print("-" * 72)
    ref = project / "contract_private" / "reference_impl.py"
    if args.no_check or not ref.exists():
        print("  (self-check skipped)\n")
        return 0
    print("  self-check: does the author's own reference oracle satisfy the contract?")
    results, _ = verify.run_verification(project, ref, manifest,
                                         sandbox_on=False, mutation=False, on_result=_on_result)
    ch, pr = results.get("crosshair"), results.get("negative_probe")
    ok = bool(ch and ch.status == "confirmed" and pr and pr.status == "pass")
    print("-" * 72)
    if ok:
        print("  contract is provable and non-vacuous. Review it, then run `holdtrue implement`.\n")
        return 0
    print("  WARNING: contract did not self-check (the reference oracle does not satisfy it,")
    print("  or the contract is not CrossHair-provable). Review before implementing.\n")
    return 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="holdtrue",
                                description="review the guarantee, not the code")
    sub = p.add_subparsers(dest="command", required=True)

    v = sub.add_parser("verify", help="run a contract against an implementation")
    v.add_argument("project", help="path to the project-under-contract")
    v.add_argument("--impl", required=True, help="implementation file to verify")
    v.add_argument("--manifest", default="contract/manifest.yaml")
    v.add_argument("--no-sandbox", action="store_true", help="run unsandboxed")
    v.add_argument("--no-mutation", action="store_true", help="skip mutation testing")
    v.set_defaults(func=cmd_verify)

    im = sub.add_parser("implement",
                        help="spawn a separate LLM context to implement, then verify")
    im.add_argument("project", help="path to the project-under-contract")
    im.add_argument("--manifest", default="contract/manifest.yaml")
    im.add_argument("--no-verify", action="store_true", help="implement only, skip verify")
    im.add_argument("--no-sandbox", action="store_true")
    im.add_argument("--no-mutation", action="store_true")
    im.set_defaults(func=cmd_implement)

    au = sub.add_parser("author",
                        help="spawn a separate LLM context to write the contract from intent")
    au.add_argument("project", help="path to the project-under-contract")
    au.add_argument("--template", default="examples/clamp",
                    help="a contract bundle to use as a format example")
    au.add_argument("--no-check", action="store_true",
                    help="skip the reference-oracle self-check")
    au.set_defaults(func=cmd_author)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
