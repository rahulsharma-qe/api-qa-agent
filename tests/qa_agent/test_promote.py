"""promote (a person applies it) and suite (a person moves a case, on the record)."""

import pytest

from qa_agent.cases import load_case_file, save_case_file
from qa_agent.cli import main
from qa_agent.project import SetupError, TeamProject
from qa_agent.promote import move_to_suite, promote

CASES = """
feature: Bookings
cases:
  - {id: TC1, title: Stable one, steps: [{request: {method: GET, path: /a}, expect: {status: 200}}]}
  - {id: TC2, title: Flaky one, steps: [{request: {method: GET, path: /b}, expect: {status: 200}}]}
  - {id: TC3, title: Old one, suite: regression, steps: [{request: {method: GET, path: /c}, expect: {status: 200}}]}
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
    assert result.not_yet == ["TC2: failed in run 2 (pytest)"]
    assert result.look_at == ["TC3 (regression): failed in run 2 (pytest)"]
    assert load_case_file(project.cases_dir / "bookings.yaml").cases[0].suite == "functional"


def test_apply_moves_them_keeps_the_approval_and_records_why(make_project, tmp_path):
    project, runs = project_with_runs(make_project, tmp_path)
    promote(project, runs, apply=True)
    case = load_case_file(project.cases_dir / "bookings.yaml").cases[0]
    assert case.suite == "regression" and case.is_approved
    assert "promoted to regression: passed in 3 runs (pytest)" in case.notes


def test_fewer_than_three_runs_is_not_stability(make_project, tmp_path, capsys):
    project, runs = project_with_runs(make_project, tmp_path)
    with pytest.raises(SetupError, match="at least 3 runs"):
        promote(project, runs[:2])
    assert main(["--project", str(project.root), "promote", "--runs", str(runs[0])]) == 2


def test_a_person_moves_a_case_back_with_who_and_why(make_project, tmp_path, capsys):
    project, _ = project_with_runs(make_project, tmp_path)
    assert main(["--project", str(project.root), "suite", "TC3", "functional", "--by", "qa-lead",
                 "--reason", "refund rule changing in the next release"]) == 0
    case = load_case_file(project.cases_dir / "bookings.yaml").cases[2]
    assert case.suite == "functional" and case.is_approved
    assert "moved from regression to functional by qa-lead: refund rule changing in the next release" in case.notes
    assert "TC3: regression -> functional" in capsys.readouterr().out
    with pytest.raises(SetupError, match="no case TC9"):
        move_to_suite(project, "TC9", "functional", "qa-lead", "x")
    with pytest.raises(SetupError, match="say who and why"):
        move_to_suite(project, "TC1", "regression", "qa-lead", " ")


CANCEL = """
feature: Cancellation
cases:
  - {id: TC7, title: Cancel in time, priority: P0, steps: [{request: {method: GET, path: /e}, expect: {status: 200}}]}
  - {id: TC8, title: Cancel copy text, priority: P2, steps: [{request: {method: GET, path: /f}, expect: {status: 200}}]}
"""


def with_a_released_feature(make_project, tmp_path, config=""):
    root = make_project({"cases/bookings.yaml": CASES, "cases/cancellation.yaml": CANCEL},
                        config="team: t\nservice: bookings\nframeworks: [pytest]\n" + config)
    for name in ("bookings", "cancellation"):
        case_file = load_case_file(root / f"cases/{name}.yaml")
        for case in case_file.cases:
            case.review.status, case.review.by, case.review.fingerprint = "approved", "qa-lead", case.fingerprint()
        save_case_file(case_file)
    runs = []
    for number in (1, 2, 3):
        path = tmp_path / f"run{number}.xml"
        names = ("test_tc1_stable_one", "test_tc7_cancel_in_time", "test_tc8_cancel_copy_text")
        path.write_text("<testsuite>" + "".join(f'<testcase name="{name}"/>' for name in names) + "</testsuite>")
        runs.append(path)
    return TeamProject.load(root), runs


def test_a_released_feature_sends_only_its_chosen_priorities_and_names_the_rest(make_project, tmp_path):
    project, runs = with_a_released_feature(make_project, tmp_path)
    result = promote(project, runs, apply=True, feature="cancellation", priorities=("P0", "P1"), reason="released in 4.3")
    assert result.ready == ["TC7"] and result.left_out == ["TC8 (P2)"]
    assert "left out, not P0/P1: TC8 (P2) (stays functional; --priority to include)" in result.as_text(3)
    tc7, tc8 = load_case_file(project.cases_dir / "cancellation.yaml").cases
    assert (tc7.suite, tc8.suite) == ("regression", "functional")
    assert tc7.notes.endswith("promoted to regression: passed in 3 runs (pytest): released in 4.3")
    assert load_case_file(project.cases_dir / "bookings.yaml").cases[0].suite == "functional"   # other features


def test_the_priorities_default_to_the_project_setting(make_project, tmp_path):
    project, runs = with_a_released_feature(make_project, tmp_path, "regression: {priorities: [P0, P1]}\n")
    assert promote(project, runs, feature="cancellation").left_out == ["TC8 (P2)"]
    assert promote(project, runs, feature="cancellation", priorities=("P2",)).ready == ["TC8"]


def test_without_the_setting_every_priority_moves_as_before(make_project, tmp_path):
    project, runs = with_a_released_feature(make_project, tmp_path)
    assert promote(project, runs, feature="Cancellation").ready == ["TC7", "TC8"]


def test_an_unknown_feature_names_the_ones_there(make_project, tmp_path):
    project, runs = with_a_released_feature(make_project, tmp_path)
    with pytest.raises(SetupError, match="no feature 'refunds' \\(the features: Bookings, Cancellation\\)"):
        promote(project, runs, feature="refunds")


def test_a_wrong_priorities_setting_is_a_setup_problem(make_project):
    root = make_project({}, config="team: t\nservice: s\nframeworks: [pytest]\nregression: {priorities: [High]}\n")
    with pytest.raises(SetupError, match="regression: priorities should be a list of P0, P1, P2, P3"):
        TeamProject.load(root)


def test_the_cli_takes_feature_priority_and_reason(make_project, tmp_path, capsys):
    project, runs = with_a_released_feature(make_project, tmp_path)
    assert main(["--project", str(project.root), "promote", "--runs", *map(str, runs), "--feature", "cancellation",
                 "--priority", "P0", "--reason", "released"]) == 0
    assert "ready for regression: TC7" in capsys.readouterr().out
