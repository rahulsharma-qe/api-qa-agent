"""The committed example project stays true: its API model comes from its sources, and check finds
exactly the findings its README describes."""

import filecmp
import shutil
from pathlib import Path

from qa_agent.checks import check_project
from qa_agent.cli import main
from qa_agent.project import TeamProject

REPO = Path(__file__).resolve().parents[2]
EXAMPLE = REPO / "examples" / "bookings-team"


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


def test_check_on_the_example_finds_what_its_readme_shows():
    report = check_project(TeamProject.load(EXAMPLE))
    assert not report.has_errors
    assert sorted((f.level, f.case_id) for f in report.findings) == [("info", "TC006"), ("warning", "TC005"),
                                                                   ("warning", "TC005")]
