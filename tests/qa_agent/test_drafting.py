"""qa-agent draft cases: code finds the gaps, a recorded model replies, code checks the reply."""

import json

import pytest

from qa_agent.ai.models import file_name
from qa_agent.checks import ERROR, check_project
from qa_agent.cli import main
from qa_agent.cases import load_case_file, save_case_file
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


REDO_AC2 = """cases:
  - title: A booking cancelled within 24 hours is refunded in full
    criteria: [AC-2]
    steps:
      - request: {method: POST, path: /bookings, body: {passenger_name: "C {{unique}}", email: c@x.io}}
        expect: {status: 201}
        capture: {pnr: pnr}
      - request: {method: POST, path: "/bookings/{{pnr}}/cancel"}
        expect: {status: 200, exists: [refund_amount]}
"""


def sent_back(project, status="rejected", comment="checks the wrong thing: it should check the refund"):
    """Draft AC-2 (TC002, TC003), then a reviewer sends both back."""
    reply(project, "draft-ac-2", GOOD_AC2)
    main(["--project", str(project.root), "draft", "cases", "--max", "1"])
    case_file = load_case_file(project.root / "cases" / "bookings-drafts.yaml")
    for case in case_file.cases:
        case.review.status, case.review.comment = status, comment
    save_case_file(case_file)


def redo(project, *ids):
    return main(["--project", str(project.root), "draft", "cases", "--redo", *ids])


def test_a_rejected_draft_is_redone_with_the_comment_and_points_to_its_replacement(project, capsys):
    sent_back(project)
    reply(project, "redo-tc002", REDO_AC2)
    capsys.readouterr()
    assert redo(project, "TC002") == 0
    assert "redone    TC002: TC004 -> cases/bookings-drafts.yaml (TC002 is now rejected)" in capsys.readouterr().out
    old, _, new = drafts(project)
    assert new.review.status == "draft" and new.source["replaces"] == "TC002" and new.source["gap"] == "AC-2"
    assert old.review.status == "rejected"
    assert old.review.comment == "checks the wrong thing: it should check the refund (replaced by TC004)"
    sent = json.loads((project.root / "reports" / "ai-audit-log.jsonl").read_text().splitlines()[-1])["sent"]["user"]
    assert "A reviewer sent back an earlier draft for this gap" in sent
    assert "The reviewer's comment: checks the wrong thing: it should check the refund" in sent
    assert "review" not in sent.split("sent back an earlier draft")[1].split("The reviewer's comment")[0]


def test_a_draft_sent_back_with_changes_needed_is_redone_too(project, capsys):
    sent_back(project, status="changes_needed")
    reply(project, "redo-tc002", REDO_AC2)
    assert redo(project, "TC002") == 0
    assert [case.review.status for case in drafts(project)] == ["rejected", "changes_needed", "draft"]


def test_running_the_redo_again_says_it_was_done(project, capsys):
    sent_back(project)
    reply(project, "redo-tc002", REDO_AC2)
    redo(project, "TC002")
    capsys.readouterr()
    assert redo(project, "TC002") == 1
    assert "not redone TC002: already redone as TC004" in capsys.readouterr().out
    assert len(drafts(project)) == 3


@pytest.mark.parametrize("case_id, status, reason", [
    ("TC1", "rejected", "not an AI draft: edit it in its case file"),
    ("TC002", "draft", "it is draft: only a rejected or sent-back draft (changes needed) is redone"),
    ("TC777", "rejected", "no case has this id"),
])
def test_what_cant_be_redone_says_why_and_calls_no_model(project, capsys, case_id, status, reason):
    sent_back(project, status=status)
    log = project.root / "reports" / "ai-audit-log.jsonl"
    calls_before = len(log.read_text().splitlines())
    capsys.readouterr()
    assert redo(project, case_id) == 1
    assert f"not redone {case_id}: {reason}" in capsys.readouterr().out
    assert len(log.read_text().splitlines()) == calls_before


def test_a_refused_redo_leaves_the_old_draft_as_the_reviewer_left_it(project, capsys):
    sent_back(project)
    reply(project, "redo-tc002", "cases:\n  - {title: t, steps: [{request: {method: DELETE, path: /all}, "
                                 "expect: {status: 200}}]}")
    capsys.readouterr()
    assert redo(project, "TC002") == 1
    assert "not redone TC002: the reply was refused: 't' calls DELETE /all, not in api/api.yaml" in capsys.readouterr().out
    assert drafts(project)[0].review.comment == "checks the wrong thing: it should check the refund"


def test_a_redo_and_a_plan_dont_go_together(project, capsys):
    assert main(["--project", str(project.root), "draft", "cases", "--redo", "TC002", "--plan"]) == 2


def test_a_draft_sent_back_is_redone_whatever_other_cases_cover_now(project, capsys):
    sent_back(project)                    # TC002 and TC003 (both AC-2) sent back; a person's case now covers AC-2
    human = project.root / "cases" / "bookings.yaml"
    human.write_text(human.read_text().replace("criteria: [AC-1]", "criteria: [AC-1, AC-2]"))
    reply(project, "redo-tc002", REDO_AC2)
    assert redo(project, "TC002") == 0   # the reviewer asked for it: the reviewer decides on the new draft
    sent = json.loads((project.root / "reports" / "ai-audit-log.jsonl").read_text().splitlines()[-1])["sent"]["user"]
    assert sent.startswith("What the draft was for: Acceptance criterion AC-2: ") and "has no case" not in sent


def test_an_operations_draft_is_redone_with_what_it_was_for(project, capsys):
    reply(project, file_name("draft GET /bookings/search"),
          "cases:\n  - {title: Search, steps: [{request: {method: GET, path: /bookings/search}, expect: {status: 200}}]}")
    for key in [gap.key for gap in pending_gaps(project)[0]]:
        if key != "GET /bookings/search":
            reply(project, file_name(f"draft {key}"), "cases: []\nreason: not in this test")
    main(["--project", str(project.root), "draft", "cases"])
    case_file = load_case_file(project.root / "cases" / "bookings-drafts.yaml")
    old = case_file.cases[0]
    old.review.status, old.review.comment = "rejected", "too thin: check the list has a total"
    save_case_file(case_file)
    reply(project, file_name(f"redo {old.id}"), "cases:\n  - {title: Search has a total, steps: [{request: "
                                                "{method: GET, path: /bookings/search}, expect: {status: 200, exists: [total]}}]}")
    assert redo(project, old.id) == 0
    sent = json.loads((project.root / "reports" / "ai-audit-log.jsonl").read_text().splitlines()[-1])["sent"]["user"]
    assert sent.startswith("What the draft was for: GET /bookings/search, with the response codes the draft below expects")
    assert drafts(project)[-1].source == {"kind": "ai-draft", "model": "recorded:recorded", "gap": "GET /bookings/search",
                                          "replaces": old.id}


def test_a_draft_for_a_criterion_no_longer_approved_is_not_redone(project, capsys):
    sent_back(project)
    criteria = project.root / "acceptance-criteria.yaml"
    criteria.write_text(criteria.read_text().replace("  - {id: AC-2", "  - {status: draft, id: AC-2"))
    capsys.readouterr()
    assert redo(project, "TC002") == 1
    assert "criterion AC-2 is not approved now: approve it first, or reject this case" in capsys.readouterr().out


AC2_COVERS_CANCEL = GOOD_AC2.replace("```\n", "").replace("```yaml\n", "") + """  - title: A booking can't be cancelled twice
    criteria: [AC-2]
    steps:
      - request: {method: POST, path: /bookings, body: {passenger_name: "D {{unique}}", email: d@x.io}}
        expect: {status: 201}
        capture: {pnr: pnr}
      - request: {method: POST, path: "/bookings/{{pnr}}/cancel"}
        expect: {status: 200}
      - request: {method: POST, path: "/bookings/{{pnr}}/cancel"}
        expect: {status: 409}
"""


def test_a_gap_a_draft_in_the_same_run_covered_gets_no_call(project, capsys):
    keys = [gap.key for gap in pending_gaps(project)[0]]
    assert "POST /bookings/{pnr}/cancel" in keys
    reply(project, "draft-ac-2", AC2_COVERS_CANCEL)
    for key in keys[1:]:
        if key != "POST /bookings/{pnr}/cancel":
            reply(project, file_name(f"draft {key}"), "cases: []\nreason: not in this test")
    main(["--project", str(project.root), "draft", "cases"])
    out = capsys.readouterr().out
    assert "covered   POST /bookings/{pnr}/cancel: by a draft made earlier in this run, no call" in out
    sent = [json.loads(line)["name"] for line in (project.root / "reports" / "ai-audit-log.jsonl").read_text().splitlines()]
    assert "draft POST /bookings/{pnr}/cancel" not in sent
