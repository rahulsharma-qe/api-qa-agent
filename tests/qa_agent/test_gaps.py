"""The gaps code finds: what qa-agent draft cases drafts for, and nothing else."""

from qa_agent.gaps import find_gaps
from qa_agent.project import TeamProject

from tests.qa_agent.conftest import API, CRITERIA

WAITING_FOR_REVIEW = """
feature: Bookings
cases:
  - id: TC1
    title: A booking can be made
    criteria: [AC-1]
    steps:
      - request: {method: POST, path: /bookings, body: {passenger_name: x, email: y}}
        expect: {status: 201}
  - id: TC2
    title: Rejected, so it covers nothing
    criteria: [AC-2]
    review: {status: rejected}
    steps:
      - request: {method: GET, path: /bookings/search}
        expect: {status: 200}
"""


def test_gaps_are_criteria_with_no_case_and_codes_no_case_expects(make_project):
    project = TeamProject.load(make_project({"api/api.yaml": API, "acceptance-criteria.yaml": CRITERIA,
                                             "cases/bookings.yaml": WAITING_FOR_REVIEW}))
    gaps = find_gaps(project)
    assert [gap.key for gap in gaps] == ["AC-2", "POST /bookings", "GET /bookings/{pnr}", "GET /bookings/search",
                                         "POST /bookings/{pnr}/cancel"]
    assert [gap.short() for gap in gaps][:2] == ["no case: A booking can be cancelled", "no case expects 422"]
    assert gaps[1].describe() == "POST /bookings: no case expects 422"


def test_a_project_without_an_api_description_has_only_criteria_gaps(make_project):
    project = TeamProject.load(make_project({"acceptance-criteria.yaml": CRITERIA}))
    assert [gap.kind for gap in find_gaps(project)] == ["criterion", "criterion"]
