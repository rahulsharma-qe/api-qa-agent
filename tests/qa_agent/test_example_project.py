"""The committed example project stays true: its API model and its cases come from its inputs, and
check finds exactly the findings its README describes."""

import filecmp
import os
import shutil
from pathlib import Path

from qa_agent.api_model import load_api_model
from qa_agent.cases import Review, load_case_file, save_case_file
from qa_agent.checks import check_project
from qa_agent.cli import main
from qa_agent.project import TeamProject

REPO = Path(__file__).resolve().parents[2]
EXAMPLE = REPO / "examples" / "bookings-team"
IMPORTED = ["cases/bookings-api.yaml", "cases/refunds.yaml", "cases/bookings-smoke.yaml",
            "cases/cancellation-scenarios.yaml", "data/cancellation-scenarios-tc040.csv"]
WRITTEN_BY_HAND = ["cases/bookings.yaml", "cases/cancellation.yaml"]
GENERATED = ["tests/generated", "src/test/java/generated"]


def test_the_example_uses_the_reference_apis_current_openapi():
    assert filecmp.cmp(EXAMPLE / "api/source/openapi.json", REPO / "demo_api/openapi.json", shallow=False), \
        "copy demo_api/openapi.json to examples/bookings-team/api/source/openapi.json"


def test_importing_the_examples_sources_again_gives_the_committed_api_model(tmp_path):
    project = tmp_path / "bookings-team"
    shutil.copytree(EXAMPLE, project)
    (project / "api/api.yaml").unlink()
    sources = project / "api/source"
    assert main(["--project", str(project), "import", "api", str(sources / "openapi.json"),
                 str(sources / "cancel_booking.curl")]) == 0
    assert main(["--project", str(project), "import", "api", str(sources / "notifications_health.curl"),
                 "--service", "notifications"]) == 0
    committed = load_api_model(EXAMPLE / "api/api.yaml")
    for operations in committed.services.values():
        for operation in operations:
            operation.not_tested = ""                # written by a person, not by the import
    assert load_api_model(project / "api/api.yaml").to_dict() == committed.to_dict()


def test_importing_again_into_the_model_keeps_what_a_person_added():
    project_api = load_api_model(EXAMPLE / "api/api.yaml")
    assert {op.path: op.not_tested for op in project_api.operations("bookings") if op.not_tested} == {
        "/health-check": "env_check calls it before every run",
        "/test/reset": "a test-only route; it resets the data"}


def test_importing_the_existing_cases_and_the_filled_review_sheet_gives_the_committed_cases(tmp_path):
    project = tmp_path / "bookings-team"
    shutil.copytree(EXAMPLE, project)
    for name in IMPORTED:
        (project / name).unlink()
    for name in WRITTEN_BY_HAND:                     # back to drafts, as before the review
        case_file = load_case_file(project / name)
        for case in case_file.cases:
            case.review = Review()
        save_case_file(case_file)
    existing = sorted(str(path) for path in (project / "existing").iterdir())
    assert main(["--project", str(project), "import", "cases", *existing]) == 0
    assert main(["--project", str(project), "review", "apply"]) == 0
    for name in IMPORTED + WRITTEN_BY_HAND:
        assert (project / name).read_text() == (EXAMPLE / name).read_text(), name


def test_generating_again_gives_the_committed_tests(tmp_path):
    project = tmp_path / "bookings-team"
    shutil.copytree(EXAMPLE, project)
    for folder in GENERATED:
        shutil.rmtree(project / folder)
    assert main(["--project", str(project), "generate"]) == 0
    for folder in GENERATED:
        written = sorted(path.name for path in (project / folder).iterdir())
        assert written == sorted(path.name for path in (EXAMPLE / folder).iterdir() if path.suffix in (".py", ".java"))
        for name in written:
            assert (project / folder / name).read_text() == (EXAMPLE / folder / name).read_text(), name


def test_the_example_is_built_like_a_project_from_init(tmp_path):
    made = tmp_path / "bookings"
    assert main(["init", str(made), "--framework", "restassured", "--team", "bookings"]) == 0
    for name in ("pom.xml", "mvnw", "mvnw.cmd", ".mvn/wrapper/maven-wrapper.properties"):
        assert (EXAMPLE / name).read_bytes() == (made / name).read_bytes(), name
    assert os.access(EXAMPLE / "run_all.sh", os.X_OK)


def test_check_on_the_example_finds_what_its_readme_shows(tmp_path):
    """The README's check comes right after the import, before the review: the imported cases as drafts."""
    project = tmp_path / "bookings-team"
    shutil.copytree(EXAMPLE, project, ignore=shutil.ignore_patterns("__pycache__", "reports", "target"))
    for name in IMPORTED:
        (project / name).unlink()
    assert main(["--project", str(project), "import", "cases", *(str(path) for path in
                 sorted((project / "existing").iterdir()))]) == 0
    report = check_project(TeamProject.load(project))
    assert not report.has_errors
    assert sorted((f.level, f.case_id) for f in report.findings) == [
        ("info", "TC006"), ("info", "TC020"), ("info", "TC021"), ("info", "TC022"), ("info", "TC041"),
        ("warning", "TC005"), ("warning", "TC005"), ("warning", "TC022"), ("warning", "TC030"), ("warning", "TC042")]
    assert [f.message for f in report.for_case("TC022") if f.same_as] == [
        "TC022: same steps as TC020 (cases/refunds.yaml). Fix: reject one in the review sheet, or remove it"]


def test_the_review_left_the_cases_the_readme_describes():
    statuses = {case.id: case.review.status for path in TeamProject.load(EXAMPLE).case_files()
                for case in load_case_file(path).cases}
    approved = sorted(case_id for case_id, status in statuses.items() if status == "approved")
    assert approved == ["TC001", "TC002", "TC003", "TC004", "TC010", "TC011", "TC012", "TC030", "TC040"]
    assert statuses["TC005"] == "changes_needed" and statuses["TC042"] == "rejected"
    assert statuses["TC022"] == "rejected"                     # the duplicate of TC020


def test_the_examples_seeded_bugs_file_lists_every_seeded_bug():
    from demo_api.seeded_bugs import BUGS
    from qa_agent.yaml_files import read_yaml
    seeded = read_yaml(EXAMPLE / "seeded-bugs.yaml")
    assert list(seeded["bugs"]) == list(BUGS)
