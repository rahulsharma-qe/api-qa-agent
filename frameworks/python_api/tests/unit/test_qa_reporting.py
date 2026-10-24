"""Phase 1b: what QA teams read after a run (Allure, evidence, retries, smoke and priority)."""

import json

ENVIRONMENTS = """
environments:
  demo:
    services: {bookings: "http://bookings.test"}
  staging:
    services: {bookings: "http://staging.test"}
    read_only: true
"""

CHAIN_TEST = """
import httpx
import pytest
from api_test_framework import ApiClient, Expect

def fake_api(context, *answers):
    answers = iter(answers)
    return ApiClient("http://bookings.test", httpx.Client(transport=httpx.MockTransport(lambda r: next(answers))),
                     context=context)

@pytest.mark.smoke
@pytest.mark.case("TC001")
@pytest.mark.priority("P0")
def test_passes(context):
    api = fake_api(context, httpx.Response(201, json={"pnr": "AB12CD"}))
    Expect(api.post("/bookings", json={"amount": 1})).status_is(201)

@pytest.mark.case("TC002")
def test_fails(context):
    api = fake_api(context, httpx.Response(404, json={"error": {}}))
    Expect(api.get("/bookings/AB12CD")).status_is(200)
"""


def make_project(pytester, code):
    pytester.makefile(".yaml", **{"config/environments": ENVIRONMENTS})
    pytester.makepyfile(code)


def test_smoke_and_priority_are_markers_and_go_into_junit(pytester):
    make_project(pytester, CHAIN_TEST)
    result = pytester.runpytest("-m", "smoke", "--junitxml=report.xml")
    result.assert_outcomes(passed=1, deselected=1)
    report = (pytester.path / "report.xml").read_text()
    assert '<property name="case_id" value="TC001"' in report and '<property name="priority" value="P0"' in report


def test_a_priority_is_also_a_marker_so_m_p0_runs_the_p0_tests(pytester):
    make_project(pytester, """
        import pytest

        @pytest.mark.priority("P0")
        def test_top():
            pass

        @pytest.mark.priority("P2")
        def test_lower():
            pass

        def test_no_priority():
            pass
    """)
    result = pytester.runpytest("-m", "p0", "--strict-markers")
    result.assert_outcomes(passed=1, deselected=2)
    pytester.runpytest("-m", "p0 or p2", "--strict-markers").assert_outcomes(passed=2, deselected=1)


def test_an_unknown_priority_is_a_usage_error(pytester):
    make_project(pytester, """
        import pytest

        @pytest.mark.priority("urgent")
        def test_x():
            pass
    """)
    result = pytester.runpytest()
    result.stderr.fnmatch_lines(["*priority must be one of P0, P1, P2, P3, not 'urgent'*"])
    assert result.ret == 4          # pytest's usage error: nothing ran


def test_evidence_is_written_for_every_test_pass_fail_or_skipped(pytester):
    make_project(pytester, CHAIN_TEST + """
@pytest.mark.writes
def test_skipped_on_read_only():
    pass
""")
    pytester.runpytest("--env", "staging", "--evidence", "evidence").assert_outcomes(passed=1, failed=1, skipped=1)
    files = {path.name: path.read_text() for path in (pytester.path / "evidence").iterdir()}
    passed = next(text for name, text in files.items() if "test_passes" in name)
    failed = next(text for name, text in files.items() if "test_fails" in name)
    skipped = next(text for name, text in files.items() if "test_skipped" in name)
    assert "result:  passed" in passed and "case:    TC001" in passed and "POST http://bookings.test/bookings" in passed
    assert "result:  failed" in failed and "expected status 200, got 404" in failed
    assert "result:  skipped" in skipped


def test_a_pass_on_retry_is_listed_separately(pytester):
    make_project(pytester, """
        from pathlib import Path

        def test_flaky():
            marker = Path("attempted")
            if not marker.exists():
                marker.write_text("1")
                assert False, "first try fails"
    """)
    result = pytester.runpytest("--reruns", "1", "--junitxml=report.xml")
    outcomes = result.parseoutcomes()
    assert (outcomes["passed"], outcomes["rerun"]) == (1, 1)
    result.stdout.fnmatch_lines(["*Passed on retry: look at these, they may be flaky*", "*test_flaky*"])
    assert '<property name="passed_on_retry" value="true"' in (pytester.path / "report.xml").read_text()


def test_allure_gets_every_step_and_the_severity(pytester):
    make_project(pytester, CHAIN_TEST)
    # In a separate process: Allure keeps global state, which an outer run with --alluredir would share
    pytester.runpytest_subprocess("--alluredir", "allure-results").assert_outcomes(passed=1, failed=1)
    results = [json.loads(path.read_text()) for path in (pytester.path / "allure-results").glob("*-result.json")]
    passed = next(result for result in results if result["name"] == "test_passes")
    labels = {(label["name"], label["value"]) for label in passed["labels"]}
    assert ("severity", "blocker") in labels and ("case_id", "TC001") in labels
    attachment = passed["attachments"][0]
    assert attachment["name"] == "step 1: POST http://bookings.test/bookings -> 201"
    step = json.loads((pytester.path / "allure-results" / attachment["source"]).read_text())
    assert step["response"]["body"] == {"pnr": "AB12CD"}
