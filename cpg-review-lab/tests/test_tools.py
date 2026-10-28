"""Tests for the review tooling itself (offline: dry-run fixtures, no API calls)."""
import json
import textwrap
from pathlib import Path

import pytest

import bloat_check
import judge_pipeline
import llm

ROOT = Path(__file__).resolve().parent.parent
LEGACY = ROOT / "src" / "procurement_legacy.py"
FIXED = ROOT / "src" / "procurement_fixed.py"


@pytest.fixture(autouse=True)
def dry_run(monkeypatch):
    monkeypatch.setenv("CPG_DRY_RUN", "1")
    llm.reset()
    yield
    llm.reset()


# -------------------------------------------------------------- bloat_check ----
def test_bloat_check_finds_the_planted_bloat_in_legacy():
    findings = bloat_check.analyze(LEGACY, also_scan=[ROOT / "tests"])
    messages = " ".join(f.message for f in findings)
    kinds = {f.kind for f in findings}

    assert kinds == {"unused-import", "unused-code", "single-impl-abc", "swallowed-error", "impossible-check"}
    for dead in ("format_currency_legacy", "_calc_moving_average", "_normalize_supplier_name_v2", "legacy_csv_export"):
        assert dead in messages
    assert "AbstractSupplierRepository" in messages
    assert len(findings) >= 15


def test_bloat_check_is_clean_on_the_fixed_module():
    assert bloat_check.analyze(FIXED, also_scan=[ROOT / "tests"]) == []


def test_bloat_check_cli_exit_codes():
    assert bloat_check.main([str(LEGACY), "--also-scan", str(ROOT / "tests")]) == 1
    assert bloat_check.main([str(FIXED), "--also-scan", str(ROOT / "tests")]) == 0
    assert bloat_check.main([str(LEGACY), "--also-scan", str(ROOT / "tests"), "--max-findings", "99"]) == 0


def test_bloat_check_does_not_flag_legitimate_none_checks(tmp_path):
    source = tmp_path / "ok.py"
    source.write_text(textwrap.dedent('''
        def lookup(conn, key):
            row = conn.execute("SELECT 1 WHERE ?", (key,)).fetchone()
            if row is None:
                return None
            return row[0]
    '''))
    assert bloat_check.analyze(source, also_scan=[]) == [bloat_check.Finding("unused-code", 2, "function `lookup` is never referenced")]


# ----------------------------------------------------------- judge parsing ----
VALID = {"verdict": "approve", "summary": "ok", "bloat_score": 1, "findings": []}


@pytest.mark.parametrize(
    "wrapper",
    ["{}", "```json\n{}\n```", "Here is my review:\n{}\nHope that helps!"],
)
def test_parse_verdict_tolerates_fences_and_chatter(wrapper):
    assert judge_pipeline.parse_verdict(wrapper.format(json.dumps(VALID)))["verdict"] == "approve"


@pytest.mark.parametrize(
    "bad",
    ["no json here", "{not json}", json.dumps({"verdict": "approve"}), json.dumps({**VALID, "verdict": "maybe"})],
)
def test_parse_verdict_rejects_malformed_replies(bad):
    with pytest.raises(ValueError):
        judge_pipeline.parse_verdict(bad)


def test_parse_verdict_sorts_findings_by_severity():
    findings = [
        {"severity": "low", "category": "bloat", "evidence": "a", "issue": "a", "fix": "a"},
        {"severity": "high", "category": "security", "evidence": "b", "issue": "b", "fix": "b"},
        {"severity": "medium", "category": "bloat", "evidence": "c", "issue": "c", "fix": "c"},
    ]
    parsed = judge_pipeline.parse_verdict(json.dumps({**VALID, "verdict": "revise", "findings": findings}))
    assert [f["severity"] for f in parsed["findings"]] == ["high", "medium", "low"]


def test_extract_code_prefers_the_fenced_block():
    assert llm.extract_code("Sure!\n```python\nx = 1\n```\nDone.") == "x = 1\n"
    assert llm.extract_code("x = 1") == "x = 1\n"


# ------------------------------------------------------ generate-judge loop ----
def test_generate_loop_converges_to_lean_code_that_meets_the_spec():
    task = (ROOT / "tasks" / "risk_score_task.md").read_text()

    code, history, approved = judge_pipeline.run_generate(task, max_rounds=3)

    assert approved is True
    assert [h["verdict"]["verdict"] for h in history] == ["revise", "approve"]
    assert len(history[0]["code"].splitlines()) > 3 * len(code.splitlines())  # bloat removed, not added

    namespace = {}
    exec(compile(code, "generated_risk.py", "exec"), namespace)  # noqa: S102 - our own canned fixture
    risk = namespace["supplier_risk"]
    deliveries = [
        {"promised": "2026-09-10", "delivered": "2026-09-10"},
        {"promised": "2026-09-10", "delivered": "2026-09-15"},
        {"promised": "2026-09-10", "delivered": None},
        {"promised": "2026-01-10", "delivered": "2026-01-20"},  # outside the 90-day window
    ]
    assert risk(deliveries, "2026-10-01") == {"late_pct": 50.0, "bucket": "High", "sample_size": 2}
    assert risk([], "2026-10-01") == {"late_pct": None, "bucket": "Unknown", "sample_size": 0}
    with pytest.raises(ValueError):
        risk(deliveries, "not-a-date")


def test_generate_gives_up_after_max_rounds(monkeypatch):
    monkeypatch.setattr(judge_pipeline, "judge", lambda task, code, role="judge": {
        "verdict": "revise", "summary": "no", "bloat_score": 9, "findings": [],
    })
    _, history, approved = judge_pipeline.run_generate("task", max_rounds=2)
    assert approved is False
    assert len(history) == 2


def test_review_command_gates_on_the_verdict(capsys):
    assert judge_pipeline.main(["review", str(LEGACY)]) == 1
    assert judge_pipeline.main(["review", str(LEGACY), "--no-fail"]) == 0
    assert "A05:2025 Injection" in capsys.readouterr().out
