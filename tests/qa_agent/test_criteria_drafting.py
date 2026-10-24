"""qa-agent draft criteria: criteria and questions from a requirement, each grounded in its words."""

import io

import pytest

from qa_agent.cli import main
from qa_agent.criteria_drafts import CriteriaDrafts
from qa_agent.project import TeamProject

CONFIG = "team: t\nservice: bookings\nframeworks: [pytest]\nai:\n  provider: recorded\n  recorded: ai/recorded\n"
REQUIREMENT = """# Cancelling a booking

A passenger can cancel a booking from the app.
Cancel within 24 hours of booking and get all your money back.
After that, no refund is given.
Refunds are paid by the payments service within one working day.
Support can cancel any booking within one working day of it being made, with a full refund.
"""
REPLY = """```yaml
criteria:
  - text: A booking cancelled within 24 hours of being made gets a full refund.
    from: "Cancel within 24 hours of booking and get all your money back"
  - text: A booking cancelled later gets no refund.
    from: "After that,   NO refund is given."
  - text: A cancelled booking sends the passenger an email.
    from: "sends an email to the passenger"
questions:
  - kind: ambiguity
    text: Is a booking cancelled at exactly 24 hours refunded in full?
    from: "within 24 hours"
  - kind: contradiction
    text: The passenger has 24 hours, support has one working day. Which window applies to support cancels?
    from: "within one working day of it being made"
  - kind: omission
    text: Can a cancelled booking be cancelled again?
    from: "A passenger can cancel a booking"
  - kind: dependency
    text: What happens when the payments service is down?
    from: "paid by the payments service"
  - kind: wish
    text: Should refunds be instant?
    from: "Refunds are paid"
```"""


@pytest.fixture
def project(make_project):
    root = make_project({"requirements/cancel.md": REQUIREMENT, "ai/recorded/draft-criteria-cancel.txt": REPLY,
                         "acceptance-criteria.yaml": "criteria:\n  - {id: AC-1, text: A booking can be made.}\n"},
                        config=CONFIG)
    return TeamProject.load(root)


def run(project, capsys):
    code = main(["--project", str(project.root), "draft", "criteria", str(project.root / "requirements/cancel.md")])
    return code, capsys.readouterr().out


def test_grounded_criteria_and_questions_become_drafts_with_ids_from_code(project, capsys):
    human_before = (project.root / "acceptance-criteria.yaml").read_bytes()
    code, out = run(project, capsys)
    assert code == 1                                          # two items refused
    assert "drafted   AC-2: A booking cancelled within 24 hours of being made gets a full refund." in out
    assert "drafted   AC-3: A booking cancelled later gets no refund." in out
    assert "question  Q-1 (ambiguity)" in out and "question  Q-2 (contradiction)" in out
    assert "question  Q-3 (omission)" in out and "question  Q-4 (dependency)" in out
    drafts = CriteriaDrafts.load(project)
    assert drafts.criteria[0]["status"] == "draft"
    assert drafts.criteria[0]["source"] == {"kind": "ai-draft", "model": "recorded:recorded",
                                            "requirement": "requirements/cancel.md",
                                            "quote": "Cancel within 24 hours of booking and get all your money back"}
    assert [q["status"] for q in drafts.questions] == ["open", "open", "open", "open"]
    assert (project.root / "acceptance-criteria.yaml").read_bytes() == human_before            # C3
    assert list(project.read_criteria()) == ["AC-1"]                                           # drafts don't count yet


def test_an_item_that_quotes_words_not_in_the_requirement_is_refused(project, capsys):
    _, out = run(project, capsys)
    assert "refused   A cancelled booking sends the passenger an email.: 'sends an email to the passenger' " \
           "is not in the requirement" in out                                                 # C1
    assert "refused   Should refunds be instant?: kind 'wish' (use ambiguity, omission, contradiction, dependency)" in out
    assert "email" not in (project.root / "acceptance-criteria-drafts.yaml").read_text()


def test_running_it_again_adds_nothing(project, capsys):
    run(project, capsys)
    _, out = run(project, capsys)
    assert "0 draft criteria, 0 questions" in out and out.count("already there") == 6            # C4
    assert [c["id"] for c in CriteriaDrafts.load(project).criteria] == ["AC-2", "AC-3"]


@pytest.mark.parametrize("reply, reason", [
    ("criteria: [: nope", "not YAML"),
    ("criteria: 3", "no 'criteria:' and 'questions:' lists"),
    ("criteria: []\nquestions: []", "nothing drafted"),
])
def test_a_reply_that_isnt_the_shape_is_refused_whole(project, capsys, reply, reason):
    (project.root / "ai/recorded/draft-criteria-cancel.txt").write_text(reply)
    code, out = run(project, capsys)
    assert code == 1 and f"refused   the reply: {reason}" in out
    assert not (project.root / "acceptance-criteria-drafts.yaml").exists()


def test_a_missing_requirement_file_is_a_setup_problem(project, capsys):
    assert main(["--project", str(project.root), "draft", "criteria", str(project.root / "nope.md")]) == 2


def test_a_criterion_a_reviewer_reworded_is_still_known_by_its_quote(project, capsys):
    run(project, capsys)
    drafts = CriteriaDrafts.load(project)
    drafts.criteria[0]["text"] = "A booking cancelled up to 24 hours after booking, 24 included, is refunded in full."
    drafts.save()
    _, out = run(project, capsys)
    assert "drafted" not in out and [c["id"] for c in CriteriaDrafts.load(project).criteria] == ["AC-2", "AC-3"]


def test_a_quote_of_a_word_or_two_proves_nothing_and_is_refused(project, capsys):
    (project.root / "ai/recorded/draft-criteria-cancel.txt").write_text(
        "criteria:\n  - text: Refunds are instant.\n    from: Refunds\n")
    code, out = run(project, capsys)
    assert code == 1 and "refused   Refunds are instant.: it must quote at least 3 words of the requirement" in out


def from_stdin(project, capsys, monkeypatch, text, *ref):
    monkeypatch.setattr("sys.stdin", io.StringIO(text))
    code = main(["--project", str(project.root), "draft", "criteria", "-", *ref])
    return code, capsys.readouterr()


def test_a_requirement_pasted_in_points_back_to_its_ref(project, capsys, monkeypatch):
    (project.root / "ai/recorded/draft-criteria-proj-123.txt").write_text(REPLY)
    code, out = from_stdin(project, capsys, monkeypatch, REQUIREMENT, "--ref", "PROJ-123")
    assert code == 1 and "drafted   AC-2" in out.out
    drafts = CriteriaDrafts.load(project)
    assert drafts.criteria[0]["source"]["requirement"] == "PROJ-123"
    assert drafts.questions[0]["requirement"] == "PROJ-123"


def test_a_file_with_a_ref_points_back_to_the_ref(project, capsys):
    (project.root / "ai/recorded/draft-criteria-proj-7.txt").write_text(REPLY)
    main(["--project", str(project.root), "draft", "criteria", str(project.root / "requirements/cancel.md"),
          "--ref", "PROJ-7"])
    assert CriteriaDrafts.load(project).criteria[0]["source"]["requirement"] == "PROJ-7"


@pytest.mark.parametrize("text, ref, message", [
    (REQUIREMENT, [], "reading from stdin needs --ref"),
    ("  \n", ["--ref", "PROJ-1"], "the requirement PROJ-1 is empty"),
])
def test_stdin_needs_a_ref_and_some_words(project, capsys, monkeypatch, text, ref, message):
    code, out = from_stdin(project, capsys, monkeypatch, text, *ref)
    assert code == 2 and message in out.err
    assert not (project.root / "reports" / "ai-audit-log.jsonl").exists()


CHANGED = REQUIREMENT.replace("Cancel within 24 hours of booking and get all your money back.",
                              "Cancel within 48 hours of booking and get all your money back.")
REPLY_48 = """criteria:
  - text: A booking cancelled within 48 hours of being made gets a full refund.
    from: "Cancel within 48 hours of booking"
"""


def changed_run(project, capsys, monkeypatch, *extra):
    """A first run from PROJ-123, AC-2 approved, then PROJ-123 changes from 24 to 48 hours."""
    (project.root / "ai/recorded/draft-criteria-proj-123.txt").write_text(REPLY)
    from_stdin(project, capsys, monkeypatch, REQUIREMENT, "--ref", "PROJ-123")
    drafts = CriteriaDrafts.load(project)
    drafts.criteria[0].update(status="approved", review={"by": "qa-lead", "date": "2026-10-20", "comment": ""})
    drafts.save()
    (project.root / "ai/recorded/draft-criteria-proj-123.txt").write_text(REPLY_48)
    return from_stdin(project, capsys, monkeypatch, CHANGED, "--ref", "PROJ-123", *extra)


def test_a_criterion_whose_words_left_the_requirement_goes_back_to_review(project, capsys, monkeypatch):
    code, out = changed_run(project, capsys, monkeypatch)
    assert code == 0
    assert "changed   AC-2: 'Cancel within 24 hours of booking and get all your money back' is no longer in the " \
           "requirement: back to changes needed" in out.out
    assert "drafted   AC-4: A booking cancelled within 48 hours of being made gets a full refund." in out.out
    ac2, ac3, _ = CriteriaDrafts.load(project).criteria
    assert ac2["status"] == "changes_needed" and ac2["review"]["by"] == "qa-agent"
    assert "is no longer in PROJ-123 (it was approved by qa-lead, 2026-10-20)" in ac2["review"]["comment"]
    assert ac3["status"] == "draft"                                    # its words are still there
    assert "AC-2" not in project.read_criteria()                        # cases linked to it now get a warning
    sent = (project.root / "reports" / "ai-audit-log.jsonl").read_text().splitlines()[-1]
    assert "no longer in the requirement" in sent and "AC-2: A booking cancelled within 24 hours" in sent


def test_the_plan_shows_the_change_and_sends_and_writes_nothing(project, capsys, monkeypatch):
    code, out = changed_run(project, capsys, monkeypatch, "--plan")
    assert code == 0
    assert "PROJ-123: 2 criteria drafted from it before (AC-2, AC-3)." in out.out
    assert "changed   AC-2: 'Cancel within 24 hours of booking and get all your money back' is no longer in it" in out.out
    assert "1 model call" in out.out and "Nothing was sent or written" in out.out
    assert CriteriaDrafts.load(project).criteria[0]["status"] == "approved"
    assert len((project.root / "reports" / "ai-audit-log.jsonl").read_text().splitlines()) == 1


def test_running_it_again_after_a_change_marks_nothing_twice(project, capsys, monkeypatch):
    changed_run(project, capsys, monkeypatch)
    code, out = from_stdin(project, capsys, monkeypatch, CHANGED, "--ref", "PROJ-123")
    assert "changed" not in out.out.split("\n\n")[0] and "0 draft criteria" in out.out


def test_a_different_ref_is_a_different_requirement(project, capsys, monkeypatch):
    (project.root / "ai/recorded/draft-criteria-proj-123.txt").write_text(REPLY)
    from_stdin(project, capsys, monkeypatch, REQUIREMENT, "--ref", "PROJ-123")
    (project.root / "ai/recorded/draft-criteria-proj-999.txt").write_text(REPLY_48)
    _, out = from_stdin(project, capsys, monkeypatch, CHANGED, "--ref", "PROJ-999")
    assert "changed " not in out.out
    assert CriteriaDrafts.load(project).criteria[0]["status"] == "draft"
