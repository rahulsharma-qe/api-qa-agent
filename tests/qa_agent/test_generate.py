"""qa-agent generate: only approved, unchanged cases; the output folders belong to qa-agent."""

from qa_agent.cases import load_case_file, save_case_file
from qa_agent.cli import main
from qa_agent.generate import generate
from qa_agent.project import TeamProject

CASES = """
feature: Bookings
cases:
  - id: TC1
    title: Read a booking
    criteria: [AC-1]
    steps:
      - request: {method: GET, path: /bookings/AB12CD}
        expect: {status: 200}
  - id: TC2
    title: Not approved
    steps:
      - request: {method: GET, path: /bookings}
        expect: {status: 200}
"""
BOTH = "team: t\nservice: bookings\nframeworks: [pytest, restassured]\n"


def approved_project(make_project):
    root = make_project({"cases/bookings.yaml": CASES}, config=BOTH)
    case_file = load_case_file(root / "cases/bookings.yaml")
    case = case_file.cases[0]
    case.review.status, case.review.by, case.review.fingerprint = "approved", "qa-lead", case.fingerprint()
    save_case_file(case_file)
    return TeamProject.load(root)


def test_only_approved_cases_become_tests_in_every_stack(make_project):
    project = approved_project(make_project)
    result = generate(project)
    python = (project.root / "tests/generated/test_bookings.py").read_text()
    java = (project.root / "src/test/java/generated/BookingsTest.java").read_text()
    assert "test_tc1_read_a_booking" in python and "test_tc2" not in python
    assert "tc1ReadABooking" in java and "tc2" not in java
    assert result.tests == {"pytest": 1, "restassured": 1}
    assert result.not_generated == ["TC2: not reviewed yet"]


def test_the_same_cases_give_the_same_files(make_project):
    project = approved_project(make_project)
    generate(project)
    again = generate(project)
    assert again.written == [] and len(again.unchanged) == 3            # two test files and the markers file


def test_a_case_edited_after_approval_is_taken_out_and_its_file_removed(make_project):
    project = approved_project(make_project)
    generate(project)
    (project.root / "src/test/java/generated/Notes.java").write_text("// a person's own file\n")
    path = project.root / "cases/bookings.yaml"
    path.write_text(path.read_text().replace("AB12CD", "ZZ99ZZ"))
    result = generate(project)
    assert "TC1: changed after approval; review it again" in result.not_generated
    assert sorted(result.removed) == ["src/test/java/generated/BookingsTest.java", "tests/generated/conftest.py",
                                      "tests/generated/test_bookings.py"]
    assert result.left_alone == ["src/test/java/generated/Notes.java"]


def test_the_command_exits_1_when_a_case_cant_be_written(make_project, capsys):
    project = approved_project(make_project)
    path = project.root / "cases/bookings.yaml"
    case_file = load_case_file(path)
    case = case_file.cases[0]
    case.steps[0].request.method, case.steps[0].request.body = "POST", {"email": None}
    case.review.fingerprint = case.fingerprint()
    save_case_file(case_file)
    assert main(["--project", str(project.root), "generate"]) == 1
    out = capsys.readouterr().out
    assert "problem: restassured: TC1 step 1: a null value" in out and "pytest: 1 tests · restassured: 0 tests" in out


def test_the_drift_check_writes_nothing_and_names_what_is_out_of_date(make_project, capsys):
    project = approved_project(make_project)
    assert main(["--project", str(project.root), "generate", "--check"]) == 1      # nothing generated yet
    assert "tests/generated/test_bookings.py (missing)" in capsys.readouterr().out
    assert not (project.root / "tests/generated").exists()
    generate(project)
    assert main(["--project", str(project.root), "generate", "--check"]) == 0
    java = project.root / "src/test/java/generated/BookingsTest.java"
    java.write_text(java.read_text().replace("statusIs(200)", "statusIs(201)"))
    path = project.cases_dir / "bookings.yaml"
    path.write_text(path.read_text().replace("AB12CD", "ZZ99ZZ"))          # TC1 no longer approved
    assert main(["--project", str(project.root), "generate", "--check"]) == 1
    out = capsys.readouterr().out
    assert "test_bookings.py (left over: its cases are no longer approved)" in out
    assert "BookingsTest.java (left over" in out
