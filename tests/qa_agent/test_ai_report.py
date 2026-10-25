"""qa-agent ai-report: what the AI layer did and who approved it, read from the audit log and the drafts.
No model, no network: the log and the drafts are written by the test."""

import json

from qa_agent.ai_report import build_ai_report
from qa_agent.ai_report_files import render_html, report_data, write_ai_report
from qa_agent.cases import load_case_file, save_case_file
from qa_agent.cli import main
from qa_agent.project import TeamProject

DRAFTS = """
criteria:
  - id: AC-1
    text: A booking can be cancelled
    status: approved
    source: {kind: ai-draft, model: anthropic:m1, requirement: BOOK-1, quote: cancel a booking}
    review: {by: qa-lead, date: '2026-10-24', comment: ''}
  - id: AC-2
    text: Refunds are paid by payments
    status: rejected
    source: {kind: ai-draft, model: anthropic:m1, requirement: BOOK-1, quote: refunds are paid}
    review: {by: qa-lead, date: '2026-10-24', comment: 'Not testable here </script><b>'}
questions:
  - {id: Q-1, kind: ambiguity, text: 'Is 24 hours included?', quote: within 24 hours, requirement: BOOK-1,
     status: answered, answer: 'Yes', answered_by: product-owner, answered_on: '2026-10-24'}
  - {id: Q-2, kind: omission, text: 'What if the PNR is unknown?', quote: a PNR, requirement: BOOK-1, status: open}
"""

STEP = "    steps: [{request: {method: POST, path: /bookings/X1/cancel}, expect: {status: 200}}]\n"
CASES = ("cases:\n"
         "  - id: TC001\n    title: Cancel a booking\n    criteria: [AC-1]\n"
         "    source: {kind: ai-draft, model: anthropic:m1, gap: AC-1}\n    review: {status: approved, by: qa-lead, date: '2026-10-24'}\n" + STEP +
         "  - id: TC002\n    title: Cancel twice\n    criteria: [AC-1]\n"
         "    source: {kind: ai-draft, model: anthropic:m1, gap: AC-1}\n    review: {status: approved, by: qa-lead, date: '2026-10-24'}\n" + STEP +
         "  - id: TC003\n    title: Cancel with no token\n    criteria: [AC-1]\n"
         "    source: {kind: ai-draft, model: anthropic:m1, gap: AC-1}\n    review: {status: approved}\n" + STEP +
         "  - id: TC004\n    title: A new draft for one sent back\n    criteria: [AC-1]\n"
         "    source: {kind: ai-draft, model: anthropic:m1, gap: AC-1, replaces: TC009}\n    review: {status: draft}\n" + STEP +
         "  - id: TC010\n    title: Imported from the manual sheet\n"
         "    source: {format: excel-manual, file: existing/manual.xlsx, sheet: S, row: 2}\n"
         "    review: {status: approved, by: qa-lead, date: '2026-10-21'}\n" + STEP +
         "  - id: TC011\n    title: Written by hand\n    review: {status: approved, by: qa-lead, date: '2026-10-21'}\n" + STEP)


def log_line(name, **extra):
    entry = {"time": "2026-10-24T09:30:00+00:00", "name": name, "provider": "anthropic", "model": "m1",
             "sent": {"system": "s", "user": "u"}, "redactions": {}, "reply": "r", "input_tokens": 1000,
             "output_tokens": 200, "cost_usd": 0.006, "duration_ms": 1200}
    entry.update(extra)
    return json.dumps(entry)


def a_project(make_project, log=True):
    root = make_project({"acceptance-criteria-drafts.yaml": DRAFTS, "cases/bookings.yaml": "feature: Bookings\n" + CASES})
    case_file = load_case_file(root / "cases/bookings.yaml")
    for case in case_file.cases:
        if case.review.status == "approved":
            case.review.fingerprint = case.fingerprint()
    case_file.cases[1].steps[0].expect = {"status": 409}                     # TC002 changed after approval
    save_case_file(case_file)
    if log:
        (root / "reports").mkdir()
        (root / "reports/ai-audit-log.jsonl").write_text("\n".join([
            log_line("draft criteria BOOK-1", redactions={"email": 2}),
            log_line("draft AC-1"),
            log_line("draft POST /bookings"),                                      # its reply was refused
            log_line("draft AC-2", error="timeout", reply="", input_tokens=0, output_tokens=0, cost_usd=None),
        ]) + "\n")
    return TeamProject.load(root)


def test_every_ai_draft_with_its_decision_and_who_made_it(make_project):
    report = build_ai_report(a_project(make_project))
    status = {draft.id: draft.status for draft in report.drafts}
    assert status == {"AC-1": "approved", "AC-2": "rejected", "TC001": "approved", "TC002": "changed_since",
                      "TC003": "approved", "TC004": "draft"}                  # imported and hand-written are not AI drafts
    assert report.status_counts() == {"approved": 3, "changes_needed": 0, "rejected": 1, "draft": 1, "changed_since": 1}
    tc001 = next(d for d in report.drafts if d.id == "TC001")
    assert (tc001.requirement, tc001.call, tc001.by) == ("BOOK-1", "draft AC-1", "qa-lead")
    assert report.origins == {"drafted by AI": 2, "imported": 1, "written by hand": 1}   # TC002 isn't approved now


def test_the_calls_their_cost_and_what_was_redacted(make_project):
    report = build_ai_report(a_project(make_project))
    assert len(report.calls) == 4 and [c.name for c in report.failed] == ["draft AC-2"]
    assert report.cost() == 0.018 and report.redactions() == {"email": 2}
    assert report.calls[0].time == "24 Oct 2026, 09:30 UTC" and report.calls[0].purpose == "Criteria from a requirement"
    assert report.calls_without_drafts() == ["draft POST /bookings"]


def test_what_to_look_at_first(make_project):
    attention = {title: ids for title, ids, _ in build_ai_report(a_project(make_project)).look_at_first()}
    assert attention["Approved, then changed"] == ["TC002"]
    assert attention["Approved with no reviewer named"] == ["TC003"]
    assert attention["AI drafts with no call in the log"] == ["TC004"]       # "redo TC009" isn't in the log
    assert attention["Calls that failed"] == ["draft AC-2"]
    assert attention["Waiting for a decision"] == ["TC004", "Q-2"]


def test_a_missing_log_is_said_not_shown_as_zero(make_project):
    report = build_ai_report(a_project(make_project, log=False))
    assert ("No audit log", []) in [(title, ids) for title, ids, _ in report.look_at_first()]
    assert "AI drafts with no call in the log" not in [title for title, _, _ in report.look_at_first()]


def test_a_project_with_no_ai_says_so(make_project):
    report = build_ai_report(TeamProject.load(make_project({})))
    assert not report.look_at_first() and "No AI used in this project yet" in report.as_text()


def test_the_report_holds_no_prompt_or_reply_and_nothing_can_break_out_of_the_page(make_project):
    report = build_ai_report(a_project(make_project))
    data = json.dumps(report_data(report))
    assert '"sent"' not in data and '"reply"' not in data
    html = render_html(report)
    assert "</script><b>" not in html and "Not testable here \\u003c/script>" in html
    assert "<script src" not in html and "fonts.googleapis" not in html            # one file, nothing to fetch


def test_the_command_writes_html_markdown_and_json(make_project, capsys):
    project = a_project(make_project)
    assert main(["--project", str(project.root), "ai-report"]) == 0
    out = capsys.readouterr().out
    assert "AI drafts       6: 3 approved, 1 rejected, 1 waiting for review, 1 approved, then changed" in out
    folder = project.root / "reports" / "ai-report"
    assert sorted(p.name for p in folder.iterdir()) == ["ai-report.json", "ai-report.md", "index.html"]
    md = (folder / "ai-report.md").read_text()
    assert "**Approved, then changed**: TC002 (the steps changed after approval" in md and "| TC003 | Cancel with no token | Approved | nobody named |" in md
    first = (folder / "ai-report.json").read_text()
    write_ai_report(build_ai_report(project), folder)
    assert (folder / "ai-report.json").read_text() == first                     # the same project, the same report
