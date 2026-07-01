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

from . import (agents, changelog, crosscheck, engine, providers, report, revise,
               sandbox, verify)
from .classify import ENFORCED, FAILED, GUARANTEED


def _approve_revision(args: argparse.Namespace) -> tuple[bool, str]:
    """How a contract revision gets applied: human review by default, auto only when
    explicitly opted in (and it has already passed the ratchet)."""
    if args.auto_revise:
        print("  auto-applying (passes the ratchet; --auto-revise).")
        return True, "auto (--auto-revise, ratchet)"
    if args.yes:
        print("  --yes without --auto-revise: proposing only, not applying.")
        return False, "not applied (--yes, no --auto-revise)"
    try:
        ans = input("  apply this revision? [y/N] ").strip().lower()
    except EOFError:
        ans = "n"
    return (ans == "y"), ("human" if ans == "y" else "human (declined)")


def _self_check_with_revision(project: Path, manifest: dict, prov, args: argparse.Namespace):
    """Self-check the contract; on failure, propose a revision and (with approval)
    apply it, bounded by --max-revisions. Returns the manifest to proceed with, or
    None to stop. Every proposal is recorded in the changelog."""
    for attempt in range(args.max_revisions + 1):
        print("\n[2] self-check: does the contract hold for the author's reference oracle?")
        ok, why = revise.self_check(project, manifest)
        if ok:
            return manifest
        print(f"  self-check FAILED: {why}")
        if args.no_revise or attempt >= args.max_revisions:
            print("  not revising (disabled or out of attempts). Stopping.")
            return None
        print(f"\n  proposing a revision in a separate context (provider: {prov.name}) ...")
        staged = revise.stage_contract(project, Path(tempfile.mkdtemp(prefix="holdtrue_revise_")))
        revise.spawn_reviser(staged, manifest, why, prov)
        if not (staged / "contract" / "manifest.yaml").exists():
            print("  reviser produced no contract. Stopping.")
            return None
        new_manifest = verify.load_manifest(staged, "contract/manifest.yaml")
        ok2, reason = revise.not_weaker(staged, manifest, new_manifest)
        diff = revise.contract_diff(manifest, new_manifest)
        note = revise.justification(staged)
        print("\n  proposed revision:")
        print("    " + (diff.replace("\n", "\n    ") if diff else "(no change to the proven lines)"))
        print(f"\n  justification: {note}")
        if not ok2:
            print(f"\n  REFUSED: the revision is {reason}. Not applying (never weaken a check to pass).")
            changelog.record(project, trigger="self-check", evidence=why, diff=diff,
                             justification=note, approved_by="refused (ratchet)", applied=False)
            return None
        approved, who = _approve_revision(args)
        changelog.record(project, trigger="self-check", evidence=why, diff=diff,
                         justification=note, approved_by=who, applied=approved)
        if not approved:
            print("  revision not applied. Stopping.")
            return None
        revise.apply(staged, project)
        manifest = verify.load_manifest(project, args.manifest)
        print("  revision applied. re-checking ...")
    return None


def _provider(args: argparse.Namespace):
    """Resolve the chosen provider, or print why none is usable and return None."""
    try:
        return providers.resolve(getattr(args, "provider", None))
    except providers.ProviderError as e:
        print(f"  {e}")
        return None


def _on_result(r: engine.CheckResult) -> None:
    print(f"  {r.status.upper():11} {r.kind:18} {r.detail[:60]}")


def _print_contract(manifest: dict) -> None:
    """Print the signature(s) and the conditions that must hold, for a single-function
    or a multi-function contract."""
    if "functions" in manifest:
        for f in manifest["functions"]:
            print(f"    {f['signature']}")
            for d in f.get("decorators", []):
                print(f"      {d}")
        return
    print(f"    {manifest.get('signature')}")
    for d in manifest.get("checks", {}).get("crosshair", {}).get("decorators", []):
        print(f"    {d}")


def _sandbox_ok(args: argparse.Namespace) -> bool:
    """Fail closed. holdtrue runs AI-written code, so it will not run it unsandboxed by
    default: if bwrap is missing, refuse unless --no-sandbox is explicit. With
    --no-sandbox, warn plainly that the code runs directly on the machine."""
    if getattr(args, "no_sandbox", False):
        print("  WARNING: --no-sandbox: AI-written code will run directly on this "
              "machine, with no isolation.")
        return True
    if not engine.sandbox.bwrap_available():
        print("  bubblewrap (bwrap) not found. holdtrue sandboxes the AI-written code "
              "it runs and will not run it unsandboxed by default.\n"
              "  Install bwrap (Linux only), or pass --no-sandbox to run directly on "
              "this machine.")
        return False
    return True


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
    if not _sandbox_ok(args):
        return 1
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
    prov = _provider(args)
    if prov is None:
        return 1
    project = Path(args.project).resolve()
    manifest = verify.load_manifest(project, args.manifest)
    ws = Path(tempfile.mkdtemp(prefix="holdtrue_impl_"))
    agents.stage_workspace(project, manifest, ws)
    print(f"\nholdtrue implement  {manifest['intent_id']}")
    print(f"  spawning implementer in a separate context (provider: {prov.name}, "
          "sees only the contract) ...")
    impl_path, _ = agents.spawn_implementer(ws, manifest, prov)
    if not impl_path.exists() or "NotImplementedError" in impl_path.read_text():
        print("  implementer did not produce an implementation.")
        return 1
    print("-" * 72)
    print(impl_path.read_text().rstrip())
    print("-" * 72)
    if args.no_verify:
        print(f"  implementation: {impl_path}\n")
        return 0
    if not _sandbox_ok(args):
        return 1
    sb = not args.no_sandbox
    if args.no_mutation:
        print("  (mutation skipped)")
    results, cls = verify.run_verification(
        project, impl_path, manifest,
        sandbox_on=sb, mutation=not args.no_mutation, on_result=_on_result)
    _finish(project, "implementer (llm)", manifest, results, cls, sb)
    return 0


def cmd_author(args: argparse.Namespace) -> int:
    prov = _provider(args)
    if prov is None:
        return 1
    project = Path(args.project).resolve()
    if not (project / "intent" / "intent.md").exists():
        print("no intent/intent.md in the project.")
        return 1
    template = Path(args.template).resolve()
    print(f"\nholdtrue author  {project.name}")
    print(f"  spawning contract author in a separate context (provider: {prov.name}) ...")
    agents.spawn_author(project, template, prov)
    if not (project / "contract" / "manifest.yaml").exists():
        print("  author did not produce contract/manifest.yaml.")
        return 1
    manifest = verify.load_manifest(project, "contract/manifest.yaml")
    print("-" * 72)
    print(f"  intent_id : {manifest.get('intent_id')}")
    print(f"  summary   : {manifest.get('summary')}")
    print("  contract (must hold):")
    _print_contract(manifest)
    print("-" * 72)
    ref = project / "contract_private" / "reference_impl.py"
    if args.no_check or not ref.exists():
        print("  (self-check skipped)\n")
        return 0
    if not _sandbox_ok(args):
        return 1
    print("  self-check: does the author's own reference oracle satisfy the contract?")
    _, cls = verify.run_verification(project, ref, manifest,
                                     sandbox_on=not args.no_sandbox, mutation=False,
                                     on_result=_on_result)
    ok = cls.classification in (GUARANTEED, ENFORCED)
    print("-" * 72)
    if ok:
        print(f"  contract self-checks ({cls.classification}). Review it, then run "
              "`holdtrue implement`.\n")
        return 0
    print(f"  WARNING: contract did not self-check ({cls.classification}: the reference "
          "oracle does not satisfy it, or the contract is too weak). Review before "
          "implementing.\n")
    return 1


def cmd_tui(args: argparse.Namespace) -> int:
    if not _sandbox_ok(args):
        return 1
    project = Path(args.project).resolve()
    manifest = verify.load_manifest(project, args.manifest)
    try:
        from . import tui
    except ModuleNotFoundError:
        print("textual is not installed (needed for the TUI): uv add textual")
        return 1
    tui.run_dashboard(project, Path(args.impl).resolve(), manifest,
                      sandbox_on=not args.no_sandbox, mutation=not args.no_mutation)
    return 0


def _cross_check(project: Path, manifest: dict, prov, template: Path, args: argparse.Namespace) -> dict:
    """A second author writes a contract from the same intent; any axis it pins that
    the approved contract misses is proposed as a (non-weakening) addition. Returns the
    possibly-strengthened manifest."""
    print(f"\n  cross-check: a second author writes a contract from the same intent "
          f"(provider: {prov.name}) ...")
    b_dir = Path(tempfile.mkdtemp(prefix="holdtrue_author2_"))
    crosscheck.second_author_contract(project, template, prov, b_dir)
    if not (b_dir / "contract" / "manifest.yaml").exists():
        print("  second author produced no contract; skipping cross-check.")
        return manifest

    staged = revise.stage_contract(project, Path(tempfile.mkdtemp(prefix="holdtrue_merge_")))
    crosscheck.propose_merge(staged, b_dir, prov)
    merged = verify.load_manifest(staged, "contract/manifest.yaml")
    if not crosscheck.added_anything(manifest, merged):
        print("  no missing axis: the contract already covers what the second author pinned.")
        return manifest

    diff = revise.contract_diff(manifest, merged)
    note = revise.justification(staged)
    print("\n  the second author pinned an axis the contract was missing:")
    print("    " + diff.replace("\n", "\n    "))
    print(f"\n  justification: {note}")
    ok, reason = revise.not_weaker(staged, manifest, merged)
    if not ok:
        print(f"\n  REFUSED: the proposed addition is {reason}. Keeping the contract as-is.")
        changelog.record(project, trigger="second-author", evidence="missing axis",
                         diff=diff, justification=note, approved_by="refused (ratchet)", applied=False)
        return manifest
    approved, who = _approve_revision(args)
    changelog.record(project, trigger="second-author", evidence="missing axis",
                     diff=diff, justification=note, approved_by=who, applied=approved)
    if not approved:
        print("  addition not applied.")
        return manifest
    revise.apply(staged, project)
    print("  addition applied.")
    return verify.load_manifest(project, args.manifest)


def cmd_crosscheck(args: argparse.Namespace) -> int:
    prov = _provider(args)
    if prov is None:
        return 1
    project = Path(args.project).resolve()
    manifest = verify.load_manifest(project, args.manifest)
    print(f"\nholdtrue cross-check  {manifest.get('intent_id')}")
    _cross_check(project, manifest, prov, Path(args.template).resolve(), args)
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    """The full loop: author -> self-check -> approve -> implement -> verify,
    re-spawning the implementer with a counterexample on a FAILED round."""
    prov = _provider(args)
    if prov is None:
        return 1
    project = Path(args.project).resolve()
    if not (project / "intent" / "intent.md").exists():
        print("no intent/intent.md in the project.")
        return 1
    if not _sandbox_ok(args):
        return 1
    sb = not args.no_sandbox

    if not args.skip_author:
        print(f"\n[1] author: writing the contract in a separate context (provider: {prov.name}) ...")
        agents.spawn_author(project, Path(args.template).resolve(), prov)
    if not (project / "contract" / "manifest.yaml").exists():
        print("  no contract present.")
        return 1
    manifest = verify.load_manifest(project, args.manifest)

    revised = _self_check_with_revision(project, manifest, prov, args)
    if revised is None:
        return 1
    manifest = revised

    if args.cross_check:
        manifest = _cross_check(project, manifest, prov, Path(args.template).resolve(), args)

    print("\n  contract:")
    _print_contract(manifest)
    if not args.yes:
        try:
            ans = input("\n[3] approve this contract and implement? [y/N] ").strip().lower()
        except EOFError:
            ans = "n"
        if ans != "y":
            print("  not approved. Stopping (the contract is yours).")
            return 0
    else:
        print("\n[3] contract approved (--yes).")

    ws = Path(tempfile.mkdtemp(prefix="holdtrue_run_"))
    agents.stage_workspace(project, manifest, ws)
    feedback, results, cls = None, None, None
    for rnd in range(1, args.max_rounds + 1):
        print(f"\n[4] implement (round {rnd}/{args.max_rounds}) in a separate context "
              f"(provider: {prov.name}) ...")
        impl_path, _ = agents.spawn_implementer(ws, manifest, prov, feedback=feedback)
        if not impl_path.exists() or "NotImplementedError" in impl_path.read_text():
            print("  implementer produced nothing.")
            return 1
        print(impl_path.read_text().rstrip())
        results, cls = verify.run_verification(project, impl_path, manifest,
                                               sandbox_on=sb, mutation=not args.no_mutation,
                                               on_result=_on_result)
        if cls.classification != FAILED:
            break
        cex = (results.get("crosshair").counterexample if results.get("crosshair") else None)
        feedback = f"{cls.evidence}" + (f" counterexample: {cex}" if cex else "")
        print(f"  round {rnd} FAILED; re-spawning with: {cex or cls.evidence}")

    _finish(project, "run (author + implementer)", manifest, results, cls, sb)
    if cls and cls.classification == FAILED:
        print("  reached max rounds without passing: UNRESOLVED.")
        if not args.no_revise:
            cex = (results.get("crosshair").counterexample if results and results.get("crosshair") else None)
            evidence = (cls.evidence or "") + (f" counterexample: {cex}" if cex else "")
            print(f"\n  diagnosing why it is stuck (provider: {prov.name}) ...")
            diag = revise.diagnose(project, evidence, prov)
            print(f"  diagnosis: {diag}")
            changelog.record(project, trigger="failed-exhausted", evidence=evidence or "(none)",
                             diff="", justification=diag, approved_by="diagnosis (not applied)",
                             applied=False)
    return 0


def cmd_providers(args: argparse.Namespace) -> int:
    avail = {p.name for p in providers.discover()}
    print("\nholdtrue providers")
    print("-" * 72)
    for p in providers.all_providers():
        mark = "available" if p.name in avail else "not found"
        print(f"  [{'x' if p.name in avail else ' '}] {p.name:14} {p.kind:6} {p.detail}  ({mark})")
    print()
    return 0


def cmd_studio(args: argparse.Namespace) -> int:
    if not _sandbox_ok(args):
        return 1
    try:
        from . import studio
    except ModuleNotFoundError:
        print("textual is not installed (needed for studio): uv add textual")
        return 1
    project = Path(args.project).resolve() if args.project else None
    intent = args.intent
    if intent and intent.startswith("@"):
        intent = Path(intent[1:]).expanduser().read_text(encoding="utf-8")
    studio.run_studio(project, Path(args.template).resolve(),
                      sandbox_on=not args.no_sandbox, mutation=not args.no_mutation,
                      provider_name=args.provider, model=args.model,
                      name=args.name, intent=intent)
    return 0


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
    im.add_argument("--provider", help="which LLM provider to use (default: claude)")
    im.set_defaults(func=cmd_implement)

    au = sub.add_parser("author",
                        help="spawn a separate LLM context to write the contract from intent")
    au.add_argument("project", help="path to the project-under-contract")
    au.add_argument("--template", default="examples/clamp",
                    help="a contract bundle to use as a format example")
    au.add_argument("--no-check", action="store_true",
                    help="skip the reference-oracle self-check")
    au.add_argument("--no-sandbox", action="store_true",
                    help="run the self-check unsandboxed (runs code directly)")
    au.add_argument("--provider", help="which LLM provider to use (default: claude)")
    au.set_defaults(func=cmd_author)

    tu = sub.add_parser("tui", help="live dashboard: run a verification and watch it stream")
    tu.add_argument("project", help="path to the project-under-contract")
    tu.add_argument("--impl", required=True, help="implementation file to verify")
    tu.add_argument("--manifest", default="contract/manifest.yaml")
    tu.add_argument("--no-sandbox", action="store_true")
    tu.add_argument("--no-mutation", action="store_true")
    tu.set_defaults(func=cmd_tui)

    ru = sub.add_parser("run",
                        help="full loop: author -> approve -> implement -> verify (re-spawn on failure)")
    ru.add_argument("project", help="path to the project-under-contract")
    ru.add_argument("--manifest", default="contract/manifest.yaml")
    ru.add_argument("--template", default="examples/clamp",
                    help="a contract bundle the author uses as a format example")
    ru.add_argument("--skip-author", action="store_true",
                    help="use the existing contract; do not re-author")
    ru.add_argument("--yes", action="store_true", help="approve the contract without prompting")
    ru.add_argument("--max-rounds", type=int, default=3)
    ru.add_argument("--no-sandbox", action="store_true")
    ru.add_argument("--no-mutation", action="store_true")
    ru.add_argument("--provider", help="which LLM provider to use (default: claude)")
    ru.add_argument("--max-revisions", type=int, default=2,
                    help="how many times to let the contract be revised on a self-check failure")
    ru.add_argument("--no-revise", action="store_true",
                    help="do not propose contract revisions; stop on a self-check failure")
    ru.add_argument("--auto-revise", action="store_true",
                    help="apply a revision automatically when it passes the ratchet (else ask)")
    ru.add_argument("--cross-check", action="store_true",
                    help="a second author cross-checks the contract for a missing axis")
    ru.set_defaults(func=cmd_run)

    cc = sub.add_parser("cross-check",
                        help="a second author writes a contract from the same intent; "
                             "propose any axis the approved contract misses")
    cc.add_argument("project", help="path to the project-under-contract")
    cc.add_argument("--manifest", default="contract/manifest.yaml")
    cc.add_argument("--template", default="examples/clamp",
                    help="a contract bundle the second author uses as a format example")
    cc.add_argument("--provider", help="which LLM provider to use (default: claude)")
    cc.add_argument("--yes", action="store_true")
    cc.add_argument("--auto-revise", action="store_true",
                    help="apply an addition automatically when it passes the ratchet (else ask)")
    cc.set_defaults(func=cmd_crosscheck)

    st = sub.add_parser("studio",
                        help="interactive TUI: pick a provider, type an intent, run the loop")
    st.add_argument("project", nargs="?", default=None,
                    help="project dir to create or reuse (default: a new temp project)")
    st.add_argument("--template", default="examples/clamp",
                    help="a contract bundle the author uses as a format example")
    st.add_argument("--no-sandbox", action="store_true")
    st.add_argument("--no-mutation", action="store_true")
    st.add_argument("--provider", help="provider to use (skips the picker)")
    st.add_argument("--model", help="model for an API provider (skips the model screen)")
    st.add_argument("--name", help="project name, when no project dir is given")
    st.add_argument("--intent", help="the intent text, or @path to read it from a file "
                                     "(skips the intent screen)")
    st.set_defaults(func=cmd_studio)

    pr = sub.add_parser("providers", help="list discovered LLM providers")
    pr.set_defaults(func=cmd_providers)

    args = p.parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        sandbox.abort_all()
        print("\naborted.")
        return 130


if __name__ == "__main__":
    sys.exit(main())
