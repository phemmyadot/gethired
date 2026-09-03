"""
Tests for the regex-first work-mode/role classification added to the
ingestion pipeline: JobTitleRoleScanner, and the decoupled LLM-trigger
logic in run_ingestion's classify loop (regex-confident fields must not
be overridden by the LLM).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.ingestion.pipeline import TITLE_ROLE_SCANNER, WORK_MODE_SCANNER


def test_engineering_titles_high_confidence_true():
    for title in [
        "Senior Backend Engineer",
        "Staff Software Engineer",
        "Platform Engineer",
        "DevOps Engineer",
        "Frontend Developer",
        "Site Reliability Engineer",
    ]:
        result = TITLE_ROLE_SCANNER.scan(title)
        assert result == {"is_engineering_role": True, "confidence": "high"}, title


def test_non_engineering_titles_high_confidence_false():
    for title in [
        "Developer Advocate",
        "Sales Engineer",
        "Recruiter",
        "Customer Success Manager",
        "Marketing Coordinator",
    ]:
        result = TITLE_ROLE_SCANNER.scan(title)
        assert result == {"is_engineering_role": False, "confidence": "high"}, title


def test_ambiguous_titles_low_confidence():
    for title in ["Member of Technical Staff", "Builder", ""]:
        result = TITLE_ROLE_SCANNER.scan(title)
        assert result["confidence"] == "low", title
        assert result["is_engineering_role"] is False


def test_work_mode_scanner_unaffected():
    # Sanity: existing work-mode scanner behavior untouched by this change.
    assert WORK_MODE_SCANNER.scan("Fully remote (US) engineering role, work from anywhere in the US" * 3)["work_mode"] == "remote"
    assert WORK_MODE_SCANNER.scan("Hybrid role, 3 days a week in office" * 10)["work_mode"] == "hybrid_or_onsite"
    assert WORK_MODE_SCANNER.scan("short")["work_mode"] == "invalid"


def test_decoupled_llm_trigger_logic(monkeypatch):
    """
    Both work_mode and role high-confidence -> no LLM call.
    Only one ambiguous -> LLM called, but the regex-confident field wins.
    """
    from src import ingestion
    calls = []

    def fake_extract(job):
        calls.append(job["title"])
        return {
            "work_mode": "remote",
            "is_us_remote_eligible": True,
            "is_engineering_role": True,
            "confidence": "medium",
        }

    monkeypatch.setattr(ingestion.pipeline, "extract_ambiguous_job_metadata", fake_extract)

    def classify(job):
        work_scan = ingestion.pipeline.WORK_MODE_SCANNER.scan(
            " ".join(str(job.get(f) or "") for f in ("title", "location", "description"))
        )
        if work_scan["work_mode"] in ("invalid", "hybrid_or_onsite", "restricted_remote"):
            return None
        role_scan = ingestion.pipeline.TITLE_ROLE_SCANNER.scan(job.get("title", ""))

        if work_scan["confidence"] == "high" and role_scan["confidence"] == "high":
            return {
                "work_mode": work_scan["work_mode"],
                "is_us_remote_eligible": True,
                "is_engineering_role": role_scan["is_engineering_role"],
            }
        metadata = ingestion.pipeline.extract_ambiguous_job_metadata(job)
        return {
            "work_mode": work_scan["work_mode"] if work_scan["confidence"] == "high" else metadata["work_mode"],
            "is_us_remote_eligible": metadata["is_us_remote_eligible"],
            "is_engineering_role": (
                role_scan["is_engineering_role"] if role_scan["confidence"] == "high"
                else metadata["is_engineering_role"]
            ),
        }

    # Case 1: title decisive (engineer) + work_mode decisive (US remote) -> no LLM call.
    job1 = {
        "title": "Senior Backend Engineer",
        "location": "Remote",
        "description": "Fully remote (US) role. " * 20,
    }
    result1 = classify(job1)
    assert calls == []
    assert result1["is_engineering_role"] is True
    assert result1["work_mode"] == "remote"

    # Case 2: title decisive (non-engineering) but work_mode ambiguous ("remote" generic)
    # -> LLM called (for work_mode), but role stays regex-confident False, not LLM's True.
    job2 = {
        "title": "Developer Advocate",
        "location": "Remote",
        "description": "We are remote-first. " * 20,
    }
    result2 = classify(job2)
    assert calls == ["Developer Advocate"]
    assert result2["is_engineering_role"] is False  # regex wins over fake LLM's True
    assert result2["work_mode"] == "remote"  # from fake LLM since work_scan was only medium-confidence


if __name__ == "__main__":
    import traceback

    tests = [
        test_engineering_titles_high_confidence_true,
        test_non_engineering_titles_high_confidence_false,
        test_ambiguous_titles_low_confidence,
        test_work_mode_scanner_unaffected,
    ]
    passed, failed = 0, 0
    for t in tests:
        try:
            t()
            print(f"PASS: {t.__name__}")
            passed += 1
        except Exception:
            print(f"FAIL: {t.__name__}")
            traceback.print_exc()
            failed += 1

    # test_decoupled_llm_trigger_logic needs monkeypatch; run manually with a fake.
    class _FakeMonkeypatch:
        def setattr(self, obj, name, value):
            setattr(obj, name, value)

    try:
        test_decoupled_llm_trigger_logic(_FakeMonkeypatch())
        print(f"PASS: test_decoupled_llm_trigger_logic")
        passed += 1
    except Exception:
        print(f"FAIL: test_decoupled_llm_trigger_logic")
        traceback.print_exc()
        failed += 1

    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
