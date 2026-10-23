"""The two teams stay true: shaped like an init project, their cases approved by a person, their
generated tests up to date, and CI calls the reusable workflow once per team."""

from pathlib import Path

import pytest

from qa_agent.cases import load_case_file
from qa_agent.checks import check_project
from qa_agent.cli import main
from qa_agent.generate import generate
from qa_agent.project import TeamProject
from qa_agent.yaml_files import read_yaml

REPO = Path(__file__).resolve().parents[2]
TEAMS = {"bookings-python": "pytest", "refunds-java": "restassured"}


@pytest.mark.parametrize("team, framework", TEAMS.items())
def test_each_team_is_a_whole_project_in_one_stack(team, framework):
    project = TeamProject.load(REPO / "teams" / team)
    assert project.frameworks == (framework,)
    assert not check_project(project).has_errors
    cases = [case for path in project.case_files() for case in load_case_file(path).cases]
    assert len(cases) == 4
    assert all(case.is_approved and case.review.by.endswith("-lead") for case in cases)
    assert not generate(project, check=True).drifted


def test_the_java_team_has_the_init_pom_and_wrapper(tmp_path):
    main(["init", str(tmp_path / "refunds-java"), "--framework", "restassured", "--team", "refunds-java"])
    for name in ("pom.xml", "mvnw", "mvnw.cmd", ".mvn/wrapper/maven-wrapper.properties"):
        assert (REPO / "teams/refunds-java" / name).read_bytes() == (tmp_path / "refunds-java" / name).read_bytes()


def test_ci_calls_the_reusable_workflow_once_per_team():
    teams = read_yaml(REPO / ".github/workflows/teams.yml")["jobs"]
    assert {job["with"]["project-path"]: job["with"]["framework"] for job in teams.values()} == \
        {f"teams/{team}": framework for team, framework in TEAMS.items()}
    assert all(job["uses"] == "./.github/workflows/qa-agent-team.yml" for job in teams.values())
    called = read_yaml(REPO / ".github/workflows/qa-agent-team.yml")
    on = called.get("on", called.get(True))                     # YAML 1.1 reads a bare "on" as true
    assert set(on["workflow_call"]["inputs"]) >= {"framework", "environment", "project-path", "start-reference-api",
                                                  "min-coverage", "platform-ref"}


@pytest.mark.parametrize("team", TEAMS)
def test_each_team_uses_the_reference_apis_current_openapi(team):
    assert (REPO / "teams" / team / "api/source/openapi.json").read_bytes() == \
        (REPO / "demo_api/openapi.json").read_bytes(), f"copy demo_api/openapi.json into teams/{team}/api/source/"
