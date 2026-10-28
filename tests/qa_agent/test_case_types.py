"""Case types: positive, negative, auth and edge, read from the steps and tags; and the happy-path-only criteria."""

from types import SimpleNamespace

from qa_agent.ai.prompts import DRAFT_CASES_SYSTEM
from qa_agent.case_types import case_types
from qa_agent.cases import Case, Request, Step, load_case_file, save_case_file
from qa_agent.cli import main
from qa_agent.project import TeamProject
from qa_agent.trace import build_trace


def case(*statuses, tags=(), data_file=None):
    steps = [Step(Request("GET", "/bookings"), {"status": status}) for status in statuses]
    return Case("TC1", "a case", tags=list(tags), data_file=data_file, steps=steps)


def test_the_type_comes_from_the_statuses_the_steps_expect(tmp_path):
    project = SimpleNamespace(root=tmp_path)
    assert case_types(case(201, 200), project) == {"positive"}
    assert case_types(case(201, 409), project) == {"negative"}
    assert case_types(case(201, 422, 200), project) == {"negative"}     # refused, then read back: unchanged
    assert case_types(case(401), project) == {"auth"}
    assert case_types(case(201, 403), project) == {"auth"}
    assert case_types(case("TBD"), project) == set()
    no_status = case(201)
    no_status.steps.append(Step(Request("GET", "/bookings/AB12CD"), {"fields": {"status": "cancelled"}}))
    assert case_types(no_status, project) == {"positive"}           # a step that checks fields only
    assert case_types(Case("TC2", "in words", manual_steps=["cancel it"]), project) == set()


def test_edge_comes_from_the_tags_on_top_of_the_status(tmp_path):
    project = SimpleNamespace(root=tmp_path)
    assert case_types(case(201, 200, tags=["boundary"]), project) == {"positive", "edge"}
    assert case_types(case(201, 409, tags=["Edge"]), project) == {"negative", "edge"}
    assert case_types(case("TBD", tags=["edge"]), project) == set()       # no status yet: no type yet


def test_a_data_driven_case_has_the_type_of_every_row(tmp_path):
    (tmp_path / "rows.csv").write_text("pnr,status\nAB12CD,200\nNOPE99,404\nNOTOKEN,401\n")
    project = SimpleNamespace(root=tmp_path)
    assert case_types(case("{{row.status}}", data_file="rows.csv"), project) == {"positive", "negative", "auth"}
    (tmp_path / "rows.csv").write_text("pnr,status\nNOPE99,404\n")
    assert case_types(case(201, "{{row.status}}", data_file="rows.csv"), project) == {"negative"}


CRITERIA = """
criteria:
  - {id: AC-1, text: make}
  - {id: AC-2, text: cancel}
  - {id: AC-3, text: refund}
"""
CASES = """
feature: Bookings
cases:
  - id: TC1
    title: Make one
    criteria: [AC-1]
    steps:
      - request: {method: POST, path: /bookings, body: {amount: 1}}
        expect: {status: 201}
  - id: TC2
    title: Cancel one
    criteria: [AC-2]
    steps:
      - request: {method: POST, path: /bookings/AB12CD/cancel}
        expect: {status: 200}
  - id: TC3
    title: Cancel twice
    criteria: [AC-2]
    steps:
      - request: {method: POST, path: /bookings/AB12CD/cancel}
        expect: {status: 409}
  - id: TC4
    title: Refund at exactly 24 hours
    criteria: [AC-3]
    tags: [edge]
    steps:
      - request: {method: GET, path: /bookings/AB12CD/refund}
        expect: {status: 200}
  - id: TC5
    title: Not approved yet
    criteria: [AC-1]
    steps:
      - request: {method: POST, path: /bookings, body: {}}
        expect: {status: 422}
"""


def test_the_trace_counts_types_and_names_the_criteria_tested_on_the_happy_path_only(make_project, capsys):
    root = make_project({"acceptance-criteria.yaml": CRITERIA, "cases/bookings.yaml": CASES})
    case_file = load_case_file(root / "cases/bookings.yaml")
    for item in case_file.cases[:4]:
        item.review.status, item.review.by, item.review.fingerprint = "approved", "qa-lead", item.fingerprint()
    save_case_file(case_file)
    report = build_trace(TeamProject.load(root))
    assert report.types_line() == "4 approved: 3 positive · 1 negative · 0 auth · 1 edge (a case can be of more than one type)"
    assert report.happy_path_only == ["AC-1"]           # TC5's 422 isn't approved: it doesn't count
    assert {row.case_id: row.types for row in report.rows if row.case_id} == {
        "TC1": "positive", "TC5": "-", "TC2": "positive", "TC3": "negative", "TC4": "positive, edge"}
    assert main(["--project", str(root), "trace"]) == 0
    out = capsys.readouterr().out
    assert "Case types      4 approved: 3 positive · 1 negative · 0 auth · 1 edge (a case can be" in out
    assert "Happy path only AC-1: no negative, auth or edge case" in out
    markdown = (root / "reports/trace.md").read_text()
    assert "Happy path only: AC-1 (no negative, auth or edge case)" in markdown
    assert "| AC-2 | TC3 | Cancel twice | negative | approved |" in markdown


def test_the_drafting_prompt_asks_for_the_edge_tag():
    assert "has the tag edge" in DRAFT_CASES_SYSTEM
