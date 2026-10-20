"""The committed example project stays true: its API model and its cases come from its inputs, and
check finds exactly the findings its README describes."""

import filecmp
import shutil
from pathlib import Path

from qa_agent.cases import Review, load_case_file, save_case_file
from qa_agent.checks import check_project
from qa_agent.cli import main
from qa_agent.project import TeamProject

REPO = Path(__file__).resolve().parents[2]
EXAMPLE = REPO / "examples" / "bookings-team"
IMPORTED = ["cases/bookings-api.yaml", "cases/refunds.yaml", "cases/bookings-smoke.yaml",
            "cases/cancellation-scenarios.yaml", "data/cancellation-scenarios-tc040.csv"]
WRITTEN_BY_HAND = ["cases/bookings.yaml", "cases/cancellation.yaml"]


def test_the_example_uses_the_reference_apis_current_openapi():
    assert filecmp.cmp(EXAMPLE / "api/source/openapi.json", REPO / "mock_service/openapi.json", shallow=False), \
        "copy mock_service/openapi.json to examples/bookings-team/api/source/openapi.json"


def test_importing_the_examples_sources_again_gives_the_committed_api_model(tmp_path):
    project = tmp_path / "bookings-team"
    shutil.copytree(EXAMPLE, project)
    (project / "api/api.yaml").unlink()
    sources = project / "api/source"
    assert main(["--project", str(project), "import", "api", str(sources / "openapi.json"),
                 str(sources / "cancel_booking.curl")]) == 0
    assert main(["--project", str(project), "import", "api", str(sources / "notifications_health.curl"),
                 "--service", "notifications"]) == 0
    assert (project / "api/api.yaml").read_text() == (EXAMPLE / "api/api.yaml").read_text()


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
    assert main(["--project", str(project), "review", "import"]) == 0
    for name in IMPORTED + WRITTEN_BY_HAND:
        assert (project / name).read_text() == (EXAMPLE / name).read_text(), name


def test_check_on_the_example_finds_what_its_readme_shows():
    report = check_project(TeamProject.load(EXAMPLE))
    assert not report.has_errors
    assert sorted((f.level, f.case_id) for f in report.findings) == [
        ("info", "TC006"), ("info", "TC020"), ("info", "TC021"), ("info", "TC041"),
        ("warning", "TC005"), ("warning", "TC005")]


def test_the_review_left_the_cases_the_readme_describes():
    statuses = {case.id: case.review.status for path in TeamProject.load(EXAMPLE).case_files()
                for case in load_case_file(path).cases}
    approved = sorted(case_id for case_id, status in statuses.items() if status == "approved")
    assert approved == ["TC001", "TC002", "TC003", "TC004", "TC010", "TC011", "TC012", "TC030", "TC040"]
    assert statuses["TC005"] == "changes_needed" and statuses["TC042"] == "rejected"
