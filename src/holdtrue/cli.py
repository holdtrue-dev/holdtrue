"""holdtrue CLI.

`holdtrue verify <project> --impl <file>` runs the contract against an
implementation and writes an evidence report. For now a human or script plays
both author and implementer; the two-context LLM split comes next.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import engine, report, verify


def cmd_verify(args: argparse.Namespace) -> int:
    project = Path(args.project).resolve()
    manifest = verify.load_manifest(project, args.manifest)
    sb = not args.no_sandbox

    print(f"\nholdtrue verify  {manifest['intent_id']}  impl={Path(args.impl).name}"
          f"  sandbox={'bwrap' if sb and engine.sandbox.bwrap_available() else 'off'}")
    print("-" * 72)

    def on_result(r: engine.CheckResult) -> None:
        print(f"  {r.status.upper():11} {r.kind:18} {r.detail[:60]}")

    if args.no_mutation:
        print("  (mutation skipped)")
    results, cls = verify.run_verification(
        project, Path(args.impl).resolve(), manifest,
        sandbox_on=sb, mutation=not args.no_mutation, on_result=on_result)

    rep = report.build_report(manifest, Path(args.impl).name, results, cls,
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
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="holdtrue",
                                description="review the guarantee, not the code")
    sub = p.add_subparsers(dest="command", required=True)
    v = sub.add_parser("verify", help="run a contract against an implementation")
    v.add_argument("project", help="path to the project-under-contract")
    v.add_argument("--impl", required=True, help="implementation file to verify")
    v.add_argument("--manifest", default="contract/manifest.yaml",
                   help="manifest path (relative to project, or absolute)")
    v.add_argument("--no-sandbox", action="store_true", help="run unsandboxed")
    v.add_argument("--no-mutation", action="store_true", help="skip mutation testing")
    v.set_defaults(func=cmd_verify)
    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
