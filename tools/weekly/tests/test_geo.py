"""Tests for geo.py: due-date logic, observation-schema validation, summary maths.
Run: python3 -m pytest tools/weekly/tests/test_geo.py -q   (or: python3 tools/weekly/tests/test_geo.py)
"""
import datetime as dt, json, sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import geo  # noqa: E402

PROMPTS = {
    "U01": {"prompt_id": "U01", "group": "unbranded"},
    "B01": {"prompt_id": "B01", "group": "branded"},
}


def base_row(**over):
    row = {
        "observation_id": "GEO-2026-10-06-01",
        "run_date": "2026-10-06",
        "prompt_id": "U01",
        "group": "unbranded",
        "engine": "claude-web-search",
        "model": "claude-web-search",
        "search_mode": "web search enabled",
        "location": "Karachi, Pakistan",
        "language": "en",
        "prompt": "Which companies provide commercial cleaning services in Karachi?",
        "response_summary": "Named three competitors, no SafaiKaro mention.",
        "brand_mentioned": "no",
        "citation_urls": "",
        "competitors_named_count": 3,
        "accuracy_verdict": "unavailable",
        "accuracy_notes": "",
    }
    row.update(over)
    return row


# ─── due-date logic ───

def test_due_on_first_monday_regardless_of_last_run():
    due, reason = geo.is_due(dt.date(2026, 9, 7), dt.date(2026, 9, 6))  # Sept 7 2026 is a Monday
    assert due and "first Monday" in reason


def test_not_due_mid_month_recent_run():
    due, reason = geo.is_due(dt.date(2026, 9, 14), dt.date(2026, 9, 7))  # 7 days later, not a Monday-in-window edge
    assert not due and "7 days ago" in reason


def test_due_when_last_run_28_days_old():
    due, reason = geo.is_due(dt.date(2026, 10, 8), dt.date(2026, 9, 10))  # 28 days, Thursday, not first Monday
    assert due and "28 days ago" in reason


def test_due_when_never_run():
    due, reason = geo.is_due(dt.date(2026, 9, 20), None)  # a Sunday, not first-Monday window
    assert due and "no recorded run" in reason


def test_cmd_due_reports_reason_and_exit_code(tmp_path):
    last_run = tmp_path / "last-run.json"
    last_run.write_text(json.dumps({"date": "2026-09-10"}))
    with patch.object(geo, "LAST_RUN", last_run), patch.object(geo, "today", return_value=dt.date(2026, 9, 14)):
        assert geo.cmd_due(None) == 1  # 4 days ago, not a Monday-first-week
    with patch.object(geo, "LAST_RUN", last_run), patch.object(geo, "today", return_value=dt.date(2026, 10, 8)):
        assert geo.cmd_due(None) == 0  # 28 days ago


# ─── schema validation ───

def test_valid_unbranded_row_passes():
    assert geo.validate_observation(base_row(), PROMPTS) == []


def test_valid_branded_row_passes():
    row = base_row(prompt_id="B01", group="branded", brand_mentioned="yes", citation_urls="https://safaikaro.pk/",
                    accuracy_verdict="accurate", accuracy_notes="Correctly named services and areas.")
    assert geo.validate_observation(row, PROMPTS) == []


def test_valid_unavailable_row_passes_with_blank_fields():
    row = base_row(engine="unavailable", model="", search_mode="", prompt="", response_summary="chatgpt not reachable this run",
                    brand_mentioned="unavailable", competitors_named_count=0)
    assert geo.validate_observation(row, PROMPTS) == []


def test_unknown_prompt_id_rejected():
    errs = geo.validate_observation(base_row(prompt_id="U99"), PROMPTS)
    assert any("not in geo-prompts.csv" in e for e in errs)


def test_group_mismatch_with_register_rejected():
    errs = geo.validate_observation(base_row(prompt_id="B01", group="unbranded"), PROMPTS)
    assert any("does not match the register" in e for e in errs)


def test_bad_engine_rejected():
    errs = geo.validate_observation(base_row(engine="bing"), PROMPTS)
    assert any("engine must be one of" in e for e in errs)


def test_completed_row_requires_prompt_and_response():
    errs = geo.validate_observation(base_row(prompt="", response_summary=""), PROMPTS)
    assert any("prompt is required" in e for e in errs)
    assert any("response_summary is required" in e for e in errs)


def test_completed_branded_row_requires_accuracy():
    row = base_row(prompt_id="B01", group="branded", brand_mentioned="yes")
    errs = geo.validate_observation(row, PROMPTS)
    assert any("accuracy_verdict is required" in e for e in errs)
    assert any("accuracy_notes is required" in e for e in errs)


def test_negative_competitor_count_rejected():
    errs = geo.validate_observation(base_row(competitors_named_count=-1), PROMPTS)
    assert any("competitors_named_count" in e for e in errs)


def test_bad_run_date_rejected():
    errs = geo.validate_observation(base_row(run_date="10-06-2026"), PROMPTS)
    assert any("run_date must be" in e for e in errs)


def test_missing_field_rejected():
    row = base_row()
    del row["citation_urls"]
    errs = geo.validate_observation(row, PROMPTS)
    assert any("missing field: citation_urls" in e for e in errs)


def test_empty_prompts_dict_skips_register_cross_check():
    # No geo-prompts.csv on disk (e.g. a fresh checkout mid-edit): the row is still schema-valid.
    assert geo.validate_observation(base_row(prompt_id="whatever-not-registered"), {}) == []


# ─── summary maths ───

def unbranded_row(engine, mentioned, cited, obs_id):
    return {"observation_id": obs_id, "group": "unbranded", "engine": engine,
            "brand_mentioned": "yes" if mentioned else "no",
            "citation_urls": "https://safaikaro.pk/" if cited else "",
            "accuracy_verdict": "unavailable"}


def branded_row(engine, verdict, obs_id):
    return {"observation_id": obs_id, "group": "branded", "engine": engine,
            "brand_mentioned": "yes", "citation_urls": "https://safaikaro.pk/", "accuracy_verdict": verdict}


def test_summary_unbranded_rates():
    rows = [
        unbranded_row("claude-web-search", True, True, "o1"),
        unbranded_row("claude-web-search", True, False, "o2"),
        unbranded_row("claude-web-search", False, False, "o3"),
    ]
    s = geo.summarize_rows(rows)
    assert s["unbranded"]["mention_rate"] == round(2 / 3, 4)
    assert s["unbranded"]["citation_rate"] == round(1 / 3, 4)
    assert s["unbranded"]["by_engine"]["claude-web-search"]["n"] == 3


def test_summary_branded_accuracy_rate():
    rows = [branded_row("claude-web-search", "accurate", "b1"), branded_row("claude-web-search", "partial", "b2")]
    s = geo.summarize_rows(rows)
    assert s["branded"]["accuracy_rate"] == 0.5
    assert s["branded"]["by_engine"]["claude-web-search"]["accuracy_rate"] == 0.5


def test_summary_excludes_unavailable_from_completed_but_counts_it():
    rows = [
        unbranded_row("claude-web-search", True, True, "o1"),
        {"observation_id": "o2", "group": "unbranded", "engine": "unavailable", "brand_mentioned": "unavailable",
         "citation_urls": "", "accuracy_verdict": "unavailable"},
    ]
    s = geo.summarize_rows(rows)
    assert s["observation_counts"]["total"] == 2
    assert s["observation_counts"]["unbranded_completed"] == 1
    assert s["observation_counts"]["unavailable"] == 1
    assert s["unbranded"]["mention_rate"] == 1.0
    assert "unavailable" not in s["unbranded"]["by_engine"]


def test_summary_empty_rows_gives_none_rates_not_crash():
    s = geo.summarize_rows([])
    assert s["unbranded"]["mention_rate"] is None
    assert s["branded"]["accuracy_rate"] is None
    assert s["observation_counts"]["total"] == 0


if __name__ == "__main__":
    for k, v in list(globals().items()):
        if k.startswith("test_"):
            try:
                v(tmp_path=Path("/tmp/geo-test-tmp")) if "tmp_path" in v.__code__.co_varnames[:v.__code__.co_argcount] else v()
            except TypeError:
                v()
            print("ok", k)
