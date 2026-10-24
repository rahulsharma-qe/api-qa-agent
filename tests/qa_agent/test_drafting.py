"""qa-agent draft cases: code finds the gaps, a recorded model replies, code checks the reply."""

import json

import pytest

from qa_agent.checks import ERROR, check_project
from qa_agent.cli import main
from qa_agent.cases import load_case_file
from qa_agent.drafting import pending_gaps
from qa_agent.project import TeamProject

from tests.qa_agent.conftest import API, CRITERIA

CONFIG = "team: t\nservice: bookings\nframeworks: [pytest]\nai:\n  provider: recorded\n  recorded: ai/recorded\n"
HUMAN_CASES = """# Written by a person: drafting must never touch this file.
feature: Bookings
cases:
  - id: TC1
    title: A booking can be made
    criteria: [AC-1]
    steps:
      - request: {method: POST, path: /bookings, body: {passenger_name: "A {{unique}}", email: ana@example.com}}
        expect: {status: 201, exists: [pnr]}
"""
GOOD_AC2 = """```yaml
cases:
  - id: TC999
    title: A booking cancelled within 24 hours is refunded in full
    criteria: [AC-2]
    priority: P1
    review: {status: approved, by: the-model}
    steps:
      - request: {method: POST, path: /bookings, body: {passenger_name: "B {{unique}}", email: b@x.io}}
        expect: {status: 201}
        capture: {pnr: pnr}
      - request: {method: POST, path: "/bookings/{{pnr}}/cancel"}
        expect: {status: 200, fields: {refund_amount: TBD}}
    notes: the refund amount is not in the criteria; confirm it
  - title: An unknown booking can't be cancelled
    criteria: [AC-2]
    steps:
      - request: {method: POST, path: /bookings/NOPE00/cancel}
        expect: {status: 404, exists: [detail]}
```
"""


@pytest.fixture
def project(make_project):
    root = make_project({"api/api.yaml": API, "acceptance-criteria.yaml": CRITERIA, "cases/bookings.yaml": HUMAN_CASES,
                         "ai/rules.md": "Every case names its criterion."}, config=CONFIG)
    return TeamProject.load(root)


def reply(project, gap_file, text):
    path = project.root / "ai" / "recorded" / f"{gap_file}.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def drafts(project):
    path = project.root / "cases" / "bookings-drafts.yaml"
    return load_case_file(path).cases if path.is_file() else []


def test_the_plan_lists_the_gaps_and_calls_no_model(project, capsys):
    assert main(["--project", str(project.root), "draft", "cases", "--plan", "--max", "2"]) == 0
    out = capsys.readouterr().out
    assert "5 gaps to draft" in out and "(over --max: next time)" in out and "2 model calls" in out
    assert not (project.root / "reports" / "ai-audit-log.jsonl").exists()


def test_a_reply_becomes_draft_cases_that_code_numbers_sources_and_keeps_as_drafts(project, capsys):
    reply(project, "draft-ac-2", GOOD_AC2)
    human_before = (project.root / "cases" / "bookings.yaml").read_bytes()
    assert main(["--project", str(project.root), "draft", "cases", "--max", "1"]) == 0
    assert "drafted   AC-2: TC002, TC003 -> cases/bookings-drafts.yaml" in capsys.readouterr().out
    first, second = drafts(project)
    assert (first.id, second.id) == ("TC002", "TC003")                                       # G2: not TC999
    assert first.review.status == "draft" and first.review.by == ""                           # G1: not approved
    assert first.source == {"kind": "ai-draft", "model": "recorded:recorded", "gap": "AC-2"}  # G3
    assert first.suite == "functional"
    assert (project.root / "cases" / "bookings.yaml").read_bytes() == human_before          # G6


def test_tbd_is_a_check_error_so_the_draft_cant_be_approved(project):
    reply(project, "draft-ac-2", GOOD_AC2)
    main(["--project", str(project.root), "draft", "cases", "--max", "1"])
    errors = [f.message for f in check_project(project).for_case("TC002") if f.level == ERROR]
    assert errors == ["TC002 step 2: has TBD, a value still to confirm. Fix: replace TBD with the value the API "
                      "should give (see the case's notes)"]
    assert not [f for f in check_project(project).for_case("TC003") if f.level == ERROR]


@pytest.mark.parametrize("text, reason", [
    ("cases: [: oops", "the reply is not YAML"),
    ("just some words", "the reply has no 'cases:' list"),
    ("cases: []\nreason: no operation lists bookings by date", "the model drafted nothing: no operation lists bookings"),
    ("cases:\n  - {title: t, criteria: [AC-9], steps: [{request: {method: GET, path: /bookings/search}, "
     "expect: {status: 200}}]}", "names criteria not in acceptance-criteria.yaml: AC-9"),
    ("cases:\n  - {title: t, steps: [{request: {method: DELETE, path: /everything}, expect: {status: 200}}]}",
     "calls DELETE /everything, not in api/api.yaml"),
    ("cases:\n  - {title: t, priority: P9, steps: [{request: {method: GET, path: /bookings/search}, "
     "expect: {status: 200}}]}", "not the case format"),
    ("cases: [{title: a}, {title: b}, {title: c}, {title: d}]", "4 cases for one gap (at most 3)"),
])
def test_a_reply_that_breaks_a_rule_is_refused_and_nothing_is_written(project, capsys, text, reason):
    reply(project, "draft-ac-2", text)
    assert main(["--project", str(project.root), "draft", "cases", "--max", "1"]) == 1
    assert reason in capsys.readouterr().out
    assert drafts(project) == []


def test_a_gap_drafted_before_is_skipped_even_once_rejected(project):
    reply(project, "draft-ac-2", GOOD_AC2)
    main(["--project", str(project.root), "draft", "cases", "--max", "1"])
    path = project.root / "cases" / "bookings-drafts.yaml"
    path.write_text(path.read_text().replace("status: draft", "status: rejected"))
    to_draft, skipped = pending_gaps(project)
    assert skipped == ["AC-2"] and "AC-2" not in [gap.key for gap in to_draft]


def test_a_model_that_cant_answer_stops_the_run_and_says_where(project, capsys):
    reply(project, "draft-ac-2", GOOD_AC2)
    assert main(["--project", str(project.root), "draft", "cases", "--max", "3"]) == 2
    out = capsys.readouterr().out
    assert "stopped   at POST /bookings: recorded: no reply for 'draft POST /bookings'" in out
    assert "next time POST /bookings, GET /bookings/{pnr}" in out
    assert len(drafts(project)) == 2                       # what was drafted before the stop is kept


def test_what_is_sent_is_redacted_and_logged_with_the_examples_and_the_team_rules(project):
    reply(project, "draft-ac-2", GOOD_AC2)
    main(["--project", str(project.root), "draft", "cases", "--max", "1"])
    entry = json.loads((project.root / "reports" / "ai-audit-log.jsonl").read_text().splitlines()[0])
    sent = entry["sent"]["user"]
    assert "The gap: Acceptance criterion AC-2 has no case" in sent
    assert "POST /bookings · responses: 201, 422 · required body fields: passenger_name, email" in sent
    assert "The team's own rules:\nEvery case names its criterion." in sent
    assert "ana@example.com" not in sent and entry["redactions"] == {}       # draft examples: approved cases only


def test_without_ai_settings_draft_says_what_to_add(make_project, capsys):
    root = make_project({"api/api.yaml": API, "acceptance-criteria.yaml": CRITERIA})
    assert main(["--project", str(root), "draft", "cases"]) == 2
    assert "no ai: settings" in capsys.readouterr().err
    assert main(["--project", str(root), "draft", "cases", "--plan"]) == 0
