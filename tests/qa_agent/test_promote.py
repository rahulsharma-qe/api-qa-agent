"""promote (a person applies it) and track (a person moves a case, on the record)."""

import pytest

from qa_agent.cases import load_case_file, save_case_file
from qa_agent.cli import main
from qa_agent.project import SetupError, TeamProject
from qa_agent.promote import move_track, promote

CASES = """
feature: Bookings
cases:
  - {id: TC1, title: Stable one, steps: [{request: {method: GET, path: /a}, expect: {status: 200}}]}
  - {id: TC2, title: Flaky one, steps: [{request: {method: GET, path: /b}, expect: {status: 200}}]}
  - {id: TC3, title: Old one, track: regression, steps: [{request: {method: GET, path: /c}, expect: {status: 200}}]}
  - {id: TC4, title: Not approved, steps: [{request: {method: GET, path: /d}, expect: {status: 200}}]}
"""


def project_with_runs(make_project, tmp_path, flaky_run=2):
    root = make_project({"cases/bookings.yaml": CASES})
    case_file = load_case_file(root / "cases/bookings.yaml")
    for case in case_file.cases[:3]:
        case.review.status, case.review.by, case.review.fingerprint = "approved", "qa-lead", case.fingerprint()
    save_case_file(case_file)
    runs = []
    for number in (1, 2, 3):
        failed = "<failure message='x'/>" if number == flaky_run else ""
        cases = (f'<testcase name="test_tc1_stable_one"/><testcase name="test_tc2_flaky_one">{failed}</testcase>'
                 f'<testcase name="test_tc3_old_one">{failed}</testcase>')
        path = tmp_path / f"run{number}.xml"
        path.write_text(f"<testsuite>{cases}</testsuite>")
        runs.append(path)
    return TeamProject.load(root), runs


def test_only_cases_that_passed_every_run_are_ready_and_nothing_changes_without_apply(make_project, tmp_path):
    project, runs = project_with_runs(make_project, tmp_path)
    result = promote(project, runs)
    assert result.ready == ["TC1"]
    assert result.not_yet == ["TC2: failed in run 2 (python)"]
    assert result.look_at == ["TC3 (regression): failed in run 2 (python)"]
    assert load_case_file(project.cases_dir / "bookings.yaml").cases[0].track == "functional"


def test_apply_moves_them_keeps_the_approval_and_records_why(make_project, tmp_path):
    project, runs = project_with_runs(make_project, tmp_path)
    promote(project, runs, apply=True)
    case = load_case_file(project.cases_dir / "bookings.yaml").cases[0]
    assert case.track == "regression" and case.is_approved
    assert "promoted to regression: passed in 3 runs (python)" in case.notes


def test_fewer_than_three_runs_is_not_stability(make_project, tmp_path, capsys):
    project, runs = project_with_runs(make_project, tmp_path)
    with pytest.raises(SetupError, match="at least 3 runs"):
        promote(project, runs[:2])
    assert main(["--project", str(project.root), "promote", "--runs", str(runs[0])]) == 2


def test_a_person_moves_a_case_back_with_who_and_why(make_project, tmp_path, capsys):
    project, _ = project_with_runs(make_project, tmp_path)
    assert main(["--project", str(project.root), "track", "TC3", "functional", "--by", "qa-lead",
                 "--reason", "refund rule changing in the next release"]) == 0
    case = load_case_file(project.cases_dir / "bookings.yaml").cases[2]
    assert case.track == "functional" and case.is_approved
    assert "moved from regression to functional by qa-lead: refund rule changing in the next release" in case.notes
    assert "TC3: regression -> functional" in capsys.readouterr().out
    with pytest.raises(SetupError, match="no case TC9"):
        move_track(project, "TC9", "functional", "qa-lead", "x")
    with pytest.raises(SetupError, match="say who and why"):
        move_track(project, "TC1", "regression", "qa-lead", " ")
