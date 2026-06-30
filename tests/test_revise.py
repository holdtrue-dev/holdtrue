"""Never-silent revision: the parts that must hold without running an LLM or a prover.

The ratchet (never weaken), the diff, the changelog, and staging. The live reviser
and the CrossHair self-check are exercised manually."""
import json
import pathlib

from holdtrue import changelog, revise


def _m(must_reject, sig="clamp(x: int, lo: int, hi: int) -> int", decos=None):
    return {
        "signature": sig,
        "checks": {"crosshair": {"decorators": decos or ["@deal.ensure(lambda x, r: True)"]}},
        "negative_probe": {"must_reject": must_reject},
    }


def test_ratchet_allows_growing_must_reject():
    old = _m(["return lo", "return hi"])
    same = _m(["return lo", "return hi"])
    stronger = _m(["return lo", "return hi", "return x"])
    assert revise.must_reject_preserved(old, same)
    assert revise.must_reject_preserved(old, stronger)


def test_ratchet_blocks_dropping_a_must_reject():
    old = _m(["return lo", "return hi", "return x"])
    weaker = _m(["return lo"])  # dropped two broken bodies it used to reject
    assert not revise.must_reject_preserved(old, weaker)


def test_contract_diff_shows_added_postcondition_and_probe():
    old = _m(["return lo"], decos=["@deal.ensure(lambda x, r: lo <= r <= hi)"])
    new = _m(["return lo", "return hi"],
             decos=["@deal.ensure(lambda x, r: lo <= r <= hi)",
                    "@deal.ensure(lambda x, r: r == min(max(x, lo), hi))"])
    diff = revise.contract_diff(old, new)
    assert "+@deal.ensure(lambda x, r: r == min(max(x, lo), hi))" in diff
    assert "+must_reject: return hi" in diff


def test_changelog_records_jsonl_and_markdown(tmp_path: pathlib.Path):
    changelog.record(tmp_path, trigger="self-check", evidence="negative-probe failed",
                     diff="+must_reject: return x", justification="tightened the postcondition",
                     approved_by="human", applied=True)
    line = (tmp_path / "revisions" / "revisions.jsonl").read_text().strip()
    rec = json.loads(line)
    assert rec["trigger"] == "self-check" and rec["applied"] is True
    assert rec["approved_by"] == "human"
    md = (tmp_path / "revisions" / "CHANGELOG.md").read_text()
    assert "tightened the postcondition" in md and "applied" in md


def test_stage_and_apply_round_trip(tmp_path: pathlib.Path):
    proj = tmp_path / "proj"
    (proj / "contract").mkdir(parents=True)
    (proj / "contract_private").mkdir(parents=True)
    (proj / "intent").mkdir(parents=True)
    (proj / "contract" / "manifest.yaml").write_text("version: 1\n")
    (proj / "contract_private" / "reference_impl.py").write_text("def f(): ...\n")
    (proj / "intent" / "intent.md").write_text("# intent\n")

    staged = revise.stage_contract(proj, tmp_path / "staged")
    assert (staged / "contract" / "manifest.yaml").exists()
    # edit the staged contract, then apply it back
    (staged / "contract" / "manifest.yaml").write_text("version: 2\n")
    revise.apply(staged, proj)
    assert (proj / "contract" / "manifest.yaml").read_text() == "version: 2\n"
