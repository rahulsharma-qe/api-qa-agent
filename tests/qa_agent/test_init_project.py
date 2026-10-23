"""qa-agent init: a project that works on day one, in either framework."""

import os
from pathlib import Path

from openpyxl import load_workbook

from qa_agent.case_import import import_cases
from qa_agent.cases import load_case_file
from qa_agent.checks import check_project
from qa_agent.cli import main
from qa_agent.project import TeamProject

REPO = Path(__file__).resolve().parents[2]
TEMPLATES = REPO / "qa_agent" / "project_templates"


def test_a_python_project_has_everything_and_its_starter_test(tmp_path, capsys):
    root = tmp_path / "bookings-team"
    assert main(["init", str(root), "--framework", "pytest"]) == 0
    for name in ("qa-agent.yaml", "api/api.yaml", "acceptance-criteria.yaml", "cases/bookings.yaml", "config/environments.yaml",
                 "config/dependencies.yaml", "existing/api_cases_template.xlsx", "requirements.txt", "pytest.ini",
                 ".github/workflows/api-tests.yml", ".gitignore", "README.md", "tests/generated/test_bookings.py"):
        assert (root / name).is_file(), name
    project = TeamProject.load(root)
    assert (project.team, project.frameworks) == ("bookings-team", ("pytest",))
    starter = load_case_file(root / "cases/bookings.yaml").cases[0]
    assert starter.is_approved and starter.review.by == "qa-agent init"
    compile((root / "tests/generated/test_bookings.py").read_text(), "test_bookings.py", "exec")
    assert not check_project(project).has_errors
    assert "python -m env_check --env mock" in capsys.readouterr().out


def test_a_rest_assured_project_has_its_pom_and_maven_wrapper(tmp_path):
    root = tmp_path / "payments"
    assert main(["init", str(root), "--framework", "restassured", "--team", "Payments Team", "--service", "payments"]) == 0
    pom = (root / "pom.xml").read_text()
    assert "<artifactId>payments-team-api-tests</artifactId>" in pom
    assert "<artifactId>restassured-api-framework</artifactId>" in pom
    assert os.access(root / "mvnw", os.X_OK) and (root / ".mvn/wrapper/maven-wrapper.properties").is_file()
    assert (root / "src/test/java/generated/BookingsTest.java").is_file()
    assert "payments:" in (root / "config/environments.yaml").read_text()
    workflow = (root / ".github/workflows/api-tests.yml").read_text()
    assert "qa-agent-team.yml@main" in workflow and "framework: restassured" in workflow and "name: payments-team" in workflow


def test_the_empty_sheet_is_in_the_layout_the_importer_reads(tmp_path):
    root = tmp_path / "team"
    main(["init", str(root), "--framework", "pytest"])
    sheet = root / "existing/api_cases_template.xlsx"
    book = load_workbook(sheet)
    book["Bookings"].append(["TC002", "List bookings", "AC-1", "P2", "", 1, "GET", "/bookings", None, 200, None, None])
    book.save(sheet)
    summary = import_cases(TeamProject.load(root), [sheet])
    assert summary.written == {"cases/bookings.yaml": ["TC002"]}


def test_init_needs_an_empty_folder(tmp_path, capsys):
    (tmp_path / "x.txt").write_text("mine")
    assert main(["init", str(tmp_path), "--framework", "pytest"]) == 2
    assert "is not empty" in capsys.readouterr().err


def test_the_maven_wrapper_is_the_frameworks_own():
    framework = REPO / "frameworks" / "restassured_api"
    for template, original in (("restassured/mvnw", "mvnw"), ("restassured/mvnw.cmd", "mvnw.cmd"),
                               ("restassured/dot-mvn/wrapper/maven-wrapper.properties",
                                ".mvn/wrapper/maven-wrapper.properties")):
        assert (TEMPLATES / template).read_bytes() == (framework / original).read_bytes(), template
