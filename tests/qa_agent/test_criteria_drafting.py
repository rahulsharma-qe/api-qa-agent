"""qa-agent draft criteria: criteria and questions from a requirement, each grounded in its words."""

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
    assert "0 draft criteria, 0 question(s)" in out and out.count("already there") == 6            # C4
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
