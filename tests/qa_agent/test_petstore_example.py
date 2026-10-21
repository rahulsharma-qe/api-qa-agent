"""The Petstore example stays true: its cases come from the team's sheet, the tests match the
approved cases, and the finding (a pet with no name is accepted) is on the record."""

import shutil
from pathlib import Path

from qa_agent.api_model import load_api_model
from qa_agent.cases import load_case_file
from qa_agent.checks import check_project
from qa_agent.cli import main
from qa_agent.generate import generate
from qa_agent.project import TeamProject
from qa_agent.yaml_files import read_yaml

REPO = Path(__file__).resolve().parents[2]
PETSTORE = REPO / "examples" / "external-apis" / "petstore"


def test_the_petstore_project_is_whole_and_its_tests_are_up_to_date():
    project = TeamProject.load(PETSTORE)
    assert project.stacks == ("python", "restassured")
    assert not check_project(project).has_errors
    assert not generate(project, check=True).drifted


def test_the_cases_are_the_teams_sheet_imported_and_reviewed(tmp_path):
    copy = tmp_path / "petstore"
    shutil.copytree(PETSTORE, copy)
    (copy / "cases/petstore-api.yaml").unlink()
    assert main(["--project", str(copy), "import", "cases", str(copy / "existing/petstore_cases.xlsx")]) == 0
    assert main(["--project", str(copy), "review", "import"]) == 0
    assert (copy / "cases/petstore-api.yaml").read_text() == (PETSTORE / "cases/petstore-api.yaml").read_text()


def test_the_finding_is_held_back_with_the_reason():
    cases = {case.id: case for case in load_case_file(PETSTORE / "cases/petstore-api.yaml").cases}
    assert all(cases[case_id].is_approved for case_id in ("TC101", "TC102", "TC103", "TC104", "TC105"))
    held = cases["TC106"]
    assert held.review.status == "changes_needed" and "accepts a pet with no name" in held.review.comment


def test_the_api_model_is_petstores_own_and_ci_uses_the_docker_image():
    api = load_api_model(PETSTORE / "api/api.yaml")
    assert api.count() == 19
    assert [op.path for op in api.operations("petstore") if op.not_tested] == ["/pet/{petId}/uploadImage"]
    workflow = read_yaml(REPO / ".github/workflows/external-apis.yml")
    assert workflow["jobs"]["petstore"]["services"]["petstore"]["image"] == "swaggerapi/petstore3:unstable"
