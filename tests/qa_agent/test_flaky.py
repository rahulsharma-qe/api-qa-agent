"""qa-agent flaky: passed in some runs and failed in others; failing in every run apart; what it refuses."""

import pytest

from qa_agent.cli import main
from qa_agent.flaky import find_flaky
from qa_agent.project import SetupError, TeamProject

CASES = """
feature: Refunds
cases:
  - id: TC7
    title: Refund status
    steps:
      - request: {method: GET, path: /bookings/AB12CD/refund}
        expect: {status: 200}
"""
PROPERTY = '<properties><property name="case_id" value="{}" /></properties>'


def run(path, tests):
    """tests: (name, outcome, message, case id); outcome passed, failed, error or skipped."""
    cases = []
    for name, outcome, message, case_id in tests:
        body = PROPERTY.format(case_id) if case_id else ""
        if outcome in ("failed", "error"):
            tag = "failure" if outcome == "failed" else "error"
            body += f'<{tag} message="{message}">the stack trace</{tag}>'
        elif outcome == "skipped":
            body += "<skipped/>"
        cases.append(f'<testcase classname="c" name="{name}">{body}</testcase>')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'<?xml version="1.0"?><testsuites><testsuite name="s">{"".join(cases)}</testsuite></testsuites>')
    return path


@pytest.fixture
def project(make_project):
    return TeamProject.load(make_project({"cases/refunds.yaml": CASES}))


def test_a_test_that_passed_and_failed_is_flaky_with_its_case_and_last_failure(project, tmp_path):
    runs = [run(tmp_path / "r1.xml", [("test_tc7_refund_status", "passed", "", ""), ("test_tc8_x", "failed", "500", "TC8")]),
            run(tmp_path / "r2.xml", [("test_tc7_refund_status", "failed", "Timeout: no reply in 8 s", ""),
                                      ("test_tc8_x", "error", "expected 401, got 500", "TC8")]),
            run(tmp_path / "r3.xml", [("test_tc7_refund_status", "passed", "", ""),
                                      ("test_tc8_x", "failed", "expected 401, got 500", "TC8")])]
    report = find_flaky(project, runs)
    assert [(item.case_id, item.test) for item in report.flaky] == [("TC7", "test_tc7_refund_status")]
    assert report.flaky[0].as_line() == ("TC7     test_tc7_refund_status   passed 2 of 3   "
                                         "last failure, run 2: Timeout: no reply in 8 s")
    assert [(item.case_id, item.last_failure) for item in report.failing] == [("TC8", "run 3: expected 401, got 500")]
    assert report.stable == 0 and report.compared == 2


def test_data_rows_are_compared_one_by_one_and_skipped_counts_neither_way(project, tmp_path):
    runs = [run(tmp_path / "r1.xml", [("t[23 hours]", "passed", "", ""), ("t[25 hours]", "failed", "500", ""),
                                      ("s", "skipped", "", "")]),
            run(tmp_path / "r2.xml", [("t[23 hours]", "passed", "", ""), ("t[25 hours]", "failed", "500", ""),
                                      ("s", "passed", "", "")])]
    report = find_flaky(project, runs)
    assert report.flaky == []                                   # each row did the same both times
    assert [item.test for item in report.failing] == ["t[25 hours]"]
    assert report.stable == 2                                   # t[23 hours], and s (skipped once, passed once)


def test_a_test_missing_from_a_run_is_compared_where_it_ran_and_named(project, tmp_path):
    runs = [run(tmp_path / "r1.xml", [("a", "passed", "", ""), ("b", "passed", "", "")]),
            run(tmp_path / "r2.xml", [("a", "failed", "boom", "")])]
    report = find_flaky(project, runs)
    assert [item.test for item in report.flaky] == ["a"]
    assert report.not_in_every_run == ["b"]


def test_it_refuses_one_run_an_empty_run_and_runs_with_nothing_in_common(project, tmp_path):
    one = run(tmp_path / "r1.xml", [("a", "passed", "", "")])
    with pytest.raises(SetupError, match="at least 2 runs"):
        find_flaky(project, [one])
    with pytest.raises(SetupError, match="no test results in: .*r2.xml"):
        find_flaky(project, [one, run(tmp_path / "r2.xml", [])])
    with pytest.raises(SetupError, match="no test in common"):
        find_flaky(project, [one, run(tmp_path / "r3.xml", [("b", "passed", "", "")])])


def test_the_command_prints_writes_flaky_md_and_exits_0_even_with_flaky_tests(project, tmp_path, capsys):
    run(project.root / "reports/r1.xml", [("test_tc7_refund_status", "passed", "", "")])
    run(project.root / "reports/r2.xml", [("test_tc7_refund_status", "failed",
                                           "api_test_framework.expect.ExpectationFailed: Timeout&#10;GET /x", "")])
    code = main(["--project", str(project.root), "flaky", "--runs", "reports/r1.xml", "reports/r2.xml"])
    assert code == 0
    out = capsys.readouterr().out
    assert "Flaky (1): passed in some runs, failed in others" in out and "Written: reports/flaky.md" in out
    markdown = (project.root / "reports/flaky.md").read_text()
    assert "| TC7 | `test_tc7_refund_status` | 1 of 2 | run 2: ExpectationFailed: Timeout |" in markdown
    assert main(["--project", str(project.root), "flaky", "--runs", "reports/r1.xml", "reports/none.xml"]) == 2
