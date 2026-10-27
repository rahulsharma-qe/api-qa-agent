"""The ai-report, three ways, from one set of data: index.html (to read and share), ai-report.md (to diff and
review in a pull request), ai-report.json (for CI and other tools).

The report holds no prompt and no reply: those stay in the audit log, so sharing the report shares only
names, counts and decisions.
"""

import json
from pathlib import Path

from qa_agent import __version__
from qa_agent.ai_report import NO_DRAFT_KEPT, STATUSES, AiReport

TEMPLATE = Path(__file__).parent / "ai_report_template.html"
DISCLAIMER = ("Evidence of how AI was used and reviewed in this project, not a compliance decision. Built from the "
              "audit log and the project's files: it can't show that the log wasn't edited.")


def report_data(report: AiReport) -> dict:
    calls_by_name = {}
    for call in report.calls:
        calls_by_name.setdefault(call.name, []).append(call)
    return {
        "team": report.team,
        "since": report.since_shown,
        "recorded": report.recorded,
        "generated_by": f"qa-agent {__version__}",
        "disclaimer": DISCLAIMER,
        "statuses": STATUSES,
        "log": {"file": report.log_file, "found": report.log_found, "lines": len(report.calls),
                "first": report.calls[0].time if report.calls else "", "last": report.calls[-1].time if report.calls else ""},
        "totals": {"calls": len(report.calls), "failed": len(report.failed), "usage": report.usage_line(),
                   "input_tokens": sum(c.input_tokens for c in report.calls),
                   "output_tokens": sum(c.output_tokens for c in report.calls), "cost_usd": report.cost(),
                   "median_ms": report.median_ms(), "redactions": dict(sorted(report.redactions().items())),
                   "calls_redacted": sum(1 for c in report.calls if c.redactions)},
        "counts": report.status_counts(),
        "origins": report.origins,
        "look_at_first": [{"title": title, "ids": ids, "why": why} for title, ids, why in report.look_at_first()],
        "no_draft_kept": {"why": NO_DRAFT_KEPT, "calls": report.calls_without_drafts()},
        "calls": [{"name": c.name, "purpose": c.purpose, "time": c.time, "model": c.model, "input_tokens": c.input_tokens,
                   "output_tokens": c.output_tokens, "cost_usd": c.cost_usd, "duration_ms": c.duration_ms,
                   "redactions": c.redactions, "error": c.error} for c in report.calls],
        "drafts": [dict(vars(d), calls=len(calls_by_name.get(d.call, []))) for d in report.drafts],
        "questions": [{key: q.get(key, "") for key in ("id", "kind", "text", "quote", "requirement", "status", "answer",
                                                         "answered_by", "answered_on", "call")} for q in report.questions],
    }


def render_markdown(report: AiReport) -> str:
    data = report_data(report)
    totals, log = data["totals"], data["log"]
    lines = [f"# AI report: {report.team}" + (f", since {report.since_shown}" if report.since else ""), ""]
    if report.recorded:
        lines += ["_Recorded replies, not a live model: this shows the workflow, not real usage._", ""]
    lines += [f"{totals['calls']} AI calls, {totals['failed']} failed; {totals['usage']}. "
              f"Log: {log['file']}" + (f", {log['lines']} lines, {log['first']} to {log['last']}." if log["lines"] else
                                       (" (missing)." if not log["found"] else " (empty).")), ""]
    lines += ["## Look at first", ""]
    lines += [f"- **{item['title']}**" + (f": {', '.join(item['ids'])} ({item['why']})." if item["ids"] else f": {item['why']}.")
              for item in data["look_at_first"]] or ["Nothing: every AI draft is decided, by a named person, and unchanged since."]
    lines += ["", "## AI drafts and decisions", "",
              ", ".join(f"{n} {STATUSES[key].lower()}" for key, n in data["counts"].items()) + ".", "",
              "| Draft | What | Decision | By, on | From |", "|---|---|---|---|---|"]
    for draft in report.drafts:
        source = (f"requirement {draft.requirement}" if draft.kind == "criterion" else
                  f"gap {draft.gap}" + (f", replaces {draft.replaces}" if draft.replaces else ""))
        decision = STATUSES.get(draft.status, draft.status) + (f": {draft.comment}" if draft.comment else "")
        lines.append(f"| {draft.id} | {_cell(draft.text)} | {_cell(decision)} | "
                     f"{_cell(draft.by or 'nobody named')}{', ' + draft.date if draft.date else ''} | {_cell(source)} |")
    if report.questions:
        lines += ["", "## Questions the model raised", "", "| Question | Kind | Status | Answer, by |", "|---|---|---|---|"]
        for q in data["questions"]:
            answer = f"{q['answer']} ({q['answered_by']}, {q['answered_on']})" if q["status"] == "answered" else "open"
            lines.append(f"| {q['id']}: {_cell(q['text'])} | {q['kind']} | {q['status']} | {_cell(answer)} |")
    lines += ["", "## Where the approved cases came from", "",
              ", ".join(f"{n} {where}" for where, n in data["origins"].items()) + ".", "",
              "## AI calls", "", "| Call | Purpose | Model | Redacted |", "|---|---|---|---|"]
    for call in data["calls"]:
        redacted = ", ".join(f"{n} {kind}" for kind, n in sorted(call["redactions"].items())) or "nothing"
        lines.append(f"| {_cell(call['name'])} | {call['purpose']} | {call['model']} | {redacted}"
                     + (f"; failed: {_cell(call['error'])}" if call["error"] else "") + " |")
    if data["no_draft_kept"]["calls"]:
        lines += ["", f"Calls with {NO_DRAFT_KEPT}: {', '.join(data['no_draft_kept']['calls'])}."]
    lines += ["", f"_{DISCLAIMER} Generated by {data['generated_by']}._", ""]
    return "\n".join(lines)


def render_html(report: AiReport) -> str:
    payload = json.dumps(report_data(report), ensure_ascii=False).replace("<", "\\u003c")   # nothing can close the script
    return (TEMPLATE.read_text(encoding="utf-8").replace("__DATA__", payload)
            .replace("__TEAM__", _html(report.team)).replace("__VERSION__", __version__))


def write_ai_report(report: AiReport, folder: Path) -> list:
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    written = {"index.html": render_html(report), "ai-report.md": render_markdown(report),
               "ai-report.json": json.dumps(report_data(report), indent=2, ensure_ascii=False) + "\n"}
    for name, text in written.items():
        (folder / name).write_text(text, encoding="utf-8")
    return [folder / name for name in written]


def _cell(text) -> str:
    return str(text).replace("|", "/").replace("\n", " ")


def _html(text) -> str:
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
