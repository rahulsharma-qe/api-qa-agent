"""qa-agent impact-analysis: the API now against the API at a git ref, and the cases to run."""

import subprocess

import pytest

from qa_agent.cases import load_case_file, save_case_file
from qa_agent.cli import main
from qa_agent.impact_analysis import impact_analysis
from qa_agent.project import SetupError, TeamProject

CONFIG = "team: t\nservice: bookings\nframeworks: [pytest, restassured]\n"
API_V1 = """
services:
  bookings:
    operations:
      - {method: POST, path: /bookings, body_required: [passenger_name, email], responses: [201, 422]}
      - {method: POST, path: "/bookings/{pnr}/cancel", responses: [200, 404, 409]}
      - {method: DELETE, path: "/bookings/{pnr}", responses: [204, 404]}
      - {method: GET, path: /bookings/search, responses: [200]}
"""
API_V2 = """
services:
  bookings:
    operations:
      - {method: POST, path: /bookings, body_required: [passenger_name, email, phone], responses: [201, 422]}
      - {method: POST, path: "/bookings/{pnr}/cancel", responses: [200, 404, 409, 410]}
      - {method: GET, path: "/bookings/{pnr}/invoice", responses: [200]}
      - {method: GET, path: /bookings/search, responses: [200]}
"""
CASES = """
feature: Cancellation
cases:
  - id: TC1
    title: A booking can be cancelled
    priority: P2
    steps:
      - request: {method: POST, path: /bookings, body: {passenger_name: A, email: a@x.io}}
        expect: {status: 201}
        capture: {pnr: pnr}
      - request: {method: POST, path: "/bookings/{{pnr}}/cancel"}
        expect: {status: 200}
  - id: TC2
    title: Cancelling twice is refused
    priority: P0
    steps:
      - request: {method: POST, path: /bookings/AB12CD/cancel}
        expect: {status: 409}
  - id: TC3
    title: A deleted booking is gone
    priority: P1
    steps:
      - request: {method: DELETE, path: /bookings/AB12CD}
        expect: {status: 204}
  - id: TC4
    title: Search works
    steps:
      - request: {method: GET, path: /bookings/search}
        expect: {status: 200}
  - id: TC5
    title: Still a draft
    priority: P1
    steps:
      - request: {method: POST, path: /bookings/AB12CD/cancel}
        expect: {status: 404}
"""


def git(root, *args):
    subprocess.run(["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@x.io", *args],
                   check=True, capture_output=True)


@pytest.fixture
def project(make_project):
    root = make_project({"api/api.yaml": API_V1, "cases/cancellation.yaml": CASES}, config=CONFIG)
    case_file = load_case_file(root / "cases/cancellation.yaml")
    for case in case_file.cases[:4]:
        case.review.status, case.review.fingerprint = "approved", case.fingerprint()
    save_case_file(case_file)
    git(root, "init", "-q")
    git(root, "add", ".")
    git(root, "commit", "-q", "-m", "v1")
    git(root, "tag", "v1")
    (root / "api/api.yaml").write_text(API_V2)
    return TeamProject.load(root)


def test_changed_added_and_removed_operations_and_the_cases_they_affect(project):
    text = impact_analysis(project, "v1").as_text()
    assert "changed   POST /bookings/{pnr}/cancel   responses: +410" in text
    assert "changed   POST /bookings                required body fields: +phone" in text
    assert "added     GET /bookings/{pnr}/invoice   no case yet: draft one (qa-agent draft cases), or write one" in text
    assert "removed   DELETE /bookings/{pnr}        TC3 still calls it: check reports it" in text
    assert "          1 operation unchanged" in text


def test_affected_cases_come_highest_priority_first_and_only_approved_ones_run(project):
    report = impact_analysis(project, "v1")
    assert [case.id for _, case in report.affected] == ["TC2", "TC3", "TC5", "TC1"]     # TC4 calls nothing changed
    assert "TC5     P1  draft           Still a draft   (not a test yet)" in report.as_text()
    assert report.run_commands() == [
        'pytest -k "test_tc2_ or test_tc3_ or test_tc1_"',
        './mvnw test -Dtest="CancellationTest#tc2CancellingTwiceIsRefused+tc3ADeletedBookingIsGone'
        '+tc1ABookingCanBeCancelled"']


def test_nothing_changed_says_so(project):
    git(project.root, "commit", "-q", "-am", "v2")
    assert "No operation changed since HEAD." in impact_analysis(project, "HEAD").as_text()


def test_an_api_file_that_wasnt_there_makes_every_operation_added(project):
    git(project.root, "commit", "-q", "--allow-empty", "-m", "empty")
    git(project.root, "rm", "-q", "--cached", "api/api.yaml")
    git(project.root, "commit", "-q", "-m", "no api")
    text = impact_analysis(project, "HEAD").as_text()
    assert "api/api.yaml was not there at HEAD: every operation counts as added." in text
    assert "No case calls a changed or removed operation." in text


@pytest.mark.parametrize("ref, message", [("v9", "no v9 in git: give a tag, a branch or a commit")])
def test_an_unknown_ref_is_a_setup_problem(project, capsys, ref, message):
    assert main(["--project", str(project.root), "impact-analysis", "--since", ref]) == 2
    assert message in capsys.readouterr().err


def test_a_project_outside_git_is_a_setup_problem(make_project, tmp_path):
    root = make_project({"api/api.yaml": API_V1}, config=CONFIG)
    with pytest.raises(SetupError, match="is not in a git repository"):
        impact_analysis(TeamProject.load(root), "v1")
