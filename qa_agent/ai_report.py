"""qa-agent ai-report: what the AI layer did, and what people decided about it.

    AI calls          reports/ai-audit-log.jsonl: every call, its purpose, model, tokens, cost, redactions
    AI drafts         acceptance-criteria-drafts.yaml and cases/*.yaml: each draft, its status, who decided
    Questions         the questions the model raised about a requirement, and who answered them
    Approved cases    where the cases that become tests came from: drafted by AI, imported, written by hand
    Look at first     approved then changed, approved with no reviewer, drafts with no call in the log,
                      failed calls, drafts and questions still waiting

Read-only: it reads the files the other commands write, and changes none of them. Evidence of how AI was
used and reviewed, not a compliance decision. ai_report_files.py writes it as HTML, Markdown and JSON.
"""

from collections import Counter
from datetime import datetime, timezone
from dataclasses import dataclass, field
from pathlib import Path
from statistics import median
from typing import Optional

from qa_agent.ai.audit import AuditLog
from qa_agent.ai.session import LOG_FILE
from qa_agent.cases import load_case_file
from qa_agent.checks import plural
from qa_agent.criteria_drafts import CriteriaDrafts
from qa_agent.drafting import DRAFTED_BY
from qa_agent.project import TeamProject

STATUSES = {                                    # the order of the tallies in the report
    "approved": "Approved",
    "changes_needed": "Changes needed",
    "rejected": "Rejected",
    "draft": "Waiting for review",
    "changed_since": "Approved, then changed",
}
PURPOSES = {"draft criteria": "Criteria from a requirement", "redo": "A new draft for one sent back",
            "draft": "Cases for a coverage gap"}
RECORDED = "recorded replies"          # the model name shown for the recorded provider: no model was called
NO_DRAFT_KEPT = "no draft kept: the reply was refused by the checks, or held nothing new"


@dataclass
class Call:
    name: str                   # "draft AC-3": what the call was for, as the audit log names it
    time: str
    model: str                  # provider:model
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: Optional[float] = None
    duration_ms: int = 0
    redactions: dict = field(default_factory=dict)
    error: str = ""

    @property
    def purpose(self) -> str:
        for prefix, label in PURPOSES.items():         # "draft criteria" before "draft"
            if self.name.startswith(prefix + " "):
                return label
        return "Other"


@dataclass
class Draft:
    id: str
    kind: str                   # criterion or case
    text: str
    status: str                 # a key of STATUSES
    by: str = ""
    date: str = ""
    comment: str = ""
    model: str = ""
    requirement: str = ""       # the requirement it came from (a case: through its criteria)
    criteria: list = field(default_factory=list)     # a case: the criteria it tests
    gap: str = ""               # a case: the coverage gap it was drafted for
    replaces: str = ""          # a case: the rejected draft it replaces
    call: str = ""              # the audit log's name for the call that drafted it
    file: str = ""


@dataclass
class AiReport:
    team: str
    log_file: str
    log_found: bool
    calls: list = field(default_factory=list)            # Call, in the log's order
    drafts: list = field(default_factory=list)           # Draft: criteria first, then cases
    questions: list = field(default_factory=list)        # dicts, as in acceptance-criteria-drafts.yaml
    origins: dict = field(default_factory=dict)          # approved cases by where they came from
    unknown_calls: list = field(default_factory=list)    # draft ids whose call isn't in the log

    @property
    def recorded(self) -> bool:
        return any(call.model == RECORDED for call in self.calls)

    @property
    def failed(self) -> list:
        return [call for call in self.calls if call.error]

    def calls_without_drafts(self) -> list:
        kept = {draft.call for draft in self.drafts} | {question.get("call", "") for question in self.questions}
        return sorted({call.name for call in self.calls if not call.error and call.name not in kept})

    def cost(self) -> Optional[float]:
        """Total in US dollars, or None when a successful call has no price (qa-agent.yaml sets none)."""
        done = [call for call in self.calls if not call.error]
        if not done or any(call.cost_usd is None for call in done):
            return None
        return round(sum(call.cost_usd for call in done), 6)

    def usage_line(self) -> str:
        if self.recorded:
            return "tokens and cost: none, the replies were recorded"
        cost = self.cost()
        return (f"tokens {sum(c.input_tokens for c in self.calls)} in, {sum(c.output_tokens for c in self.calls)} out · "
                + (f"cost ${cost:.4f}" if cost is not None else "cost: prices not set in qa-agent.yaml"))

    def median_ms(self) -> int:
        done = [call.duration_ms for call in self.calls if not call.error]
        return int(median(done)) if done else 0

    def redactions(self) -> Counter:
        total = Counter()
        for call in self.calls:
            total.update(call.redactions)
        return total

    def status_counts(self) -> dict:
        counts = Counter(draft.status for draft in self.drafts)
        return {key: counts.get(key, 0) for key in STATUSES}

    def look_at_first(self) -> list:
        """(title, ids, why): what a reviewer or auditor should look at before anything else."""
        items = []
        changed = [d.id for d in self.drafts if d.status == "changed_since"]
        if changed:
            items.append(("Approved, then changed", changed, "the steps changed after approval: generate leaves "
                          "them out until a person approves them again"))
        unnamed = [d.id for d in self.drafts if d.status in ("approved", "changed_since") and not d.by]
        if unnamed:
            items.append(("Approved with no reviewer named", unnamed, "the review has no 'by': who approved it "
                          "can't be shown"))
        if self.drafts and not self.log_found:
            items.append(("No audit log", [], f"{self.log_file} is missing: the calls behind "
                          f"{plural(len(self.drafts), 'AI draft')} can't be shown"))
        elif self.unknown_calls:
            items.append(("AI drafts with no call in the log", self.unknown_calls, "the log was cleared or moved, "
                          "or the draft's source was edited by hand"))
        if self.failed:
            items.append(("Calls that failed", [call.name for call in self.failed], "the model or the network "
                          "returned an error; nothing was drafted from them"))
        waiting = [d.id for d in self.drafts if d.status == "draft"]
        waiting += [q["id"] for q in self.questions if q.get("status", "open") == "open"]
        if waiting:
            items.append(("Waiting for a decision", waiting, "drafts not reviewed yet, and questions not answered"))
        return items

    def as_text(self) -> str:
        counts = self.status_counts()
        decided = ", ".join(f"{n} {STATUSES[key].lower()}" for key, n in counts.items() if n) or "none"
        redacted = self.redactions()
        questions = Counter(q.get("status", "open") for q in self.questions)
        origins = self.origins
        lines = [f"ai-report for {self.team}" + (" (recorded replies, not a live model)" if self.recorded else ""),
                 f"AI calls        {len(self.calls)}, {len(self.failed)} failed · {self.usage_line()}",
                 "Redacted        " + (", ".join(f"{n} {kind}" for kind, n in sorted(redacted.items()))
                                       or "nothing: no email, token, key or secret found in what was sent"),
                 f"AI drafts       {len(self.drafts)}: {decided}",
                 f"Questions       {len(self.questions)}: {questions.get('answered', 0)} answered, "
                 f"{questions.get('open', 0)} open",
                 f"Approved cases  {sum(origins.values())}: " + ", ".join(f"{n} {where}" for where, n in origins.items())]
        attention = self.look_at_first()
        lines.append("Look at first" + ("   nothing" if not attention else ""))
        lines += [f"  {title}: {', '.join(ids)}" + (f" ({why})" if why else "") if ids else f"  {title}: {why}"
                  for title, ids, why in attention]
        without = self.calls_without_drafts()
        if without:
            lines.append(f"Calls with {NO_DRAFT_KEPT}: {', '.join(without)}")
        if not self.calls and not self.drafts:
            lines.append("No AI used in this project yet: qa-agent draft criteria or draft cases would show here.")
        return "\n".join(lines)


def build_ai_report(project: TeamProject) -> AiReport:
    log_path = project.root / LOG_FILE
    report = AiReport(project.team, project.relative(log_path), log_path.is_file())
    report.calls = [_call(entry) for entry in AuditLog(log_path).entries()]
    drafts = CriteriaDrafts.load(project)
    report.drafts = [_criterion(entry, project) for entry in drafts.criteria
                     if (entry.get("source") or {}).get("kind") == DRAFTED_BY]
    requirement_of = {draft.id: draft.requirement for draft in report.drafts}
    report.questions = [dict(question, call=_criteria_call(question.get("requirement", "")))
                        for question in drafts.questions]
    origins = Counter()
    for path in project.case_files():
        for case in load_case_file(path).cases:
            if case.source.get("kind") == DRAFTED_BY:
                draft = _case(case, project.relative(path))
                draft.requirement = ", ".join(sorted({requirement_of[c] for c in case.criteria if c in requirement_of}))
                report.drafts.append(draft)
            if case.is_approved:
                origins[_origin(case.source)] += 1
    report.origins = {where: origins.get(where, 0) for where in ("drafted by AI", "imported", "written by hand")}
    names = {call.name for call in report.calls}
    report.unknown_calls = [draft.id for draft in report.drafts if draft.call not in names]
    return report


def _call(entry: dict) -> Call:
    provider = str(entry.get("provider", ""))
    return Call(str(entry.get("name", "")), when(str(entry.get("time", ""))),
                RECORDED if provider == "recorded" else f"{provider}:{entry.get('model', '')}", int(entry.get("input_tokens") or 0),
                int(entry.get("output_tokens") or 0), entry.get("cost_usd"), int(entry.get("duration_ms") or 0),
                dict(entry.get("redactions") or {}), str(entry.get("error", "")))


def _criterion(entry: dict, project: TeamProject) -> Draft:
    source, review = entry.get("source") or {}, entry.get("review") or {}
    return Draft(str(entry.get("id")), "criterion", str(entry.get("text", "")), str(entry.get("status") or "draft"),
                 str(review.get("by", "")), str(review.get("date", "")), str(review.get("comment", "")),
                 _model(source), requirement=str(source.get("requirement", "")),
                 call=_criteria_call(str(source.get("requirement", ""))),
                 file=project.relative(project.criteria_drafts_path))


def _criteria_call(requirement: str) -> str:
    """The call's name: the ref (BOOK-101) as is, a file (requirements/cancel.md) by its name without .md."""
    path = Path(requirement)
    short = path.stem if "/" in requirement or path.suffix in (".md", ".txt") else requirement
    return f"draft criteria {short}"


def _case(case, file: str) -> Draft:
    review, source = case.review, case.source
    status = "changed_since" if case.changed_after_approval else review.status
    replaces = str(source.get("replaces", ""))
    return Draft(case.id, "case", case.title, status, review.by, review.date, review.comment,
                 _model(source), criteria=list(case.criteria), gap=str(source.get("gap", "")),
                 replaces=replaces, call=f"redo {replaces}" if replaces else f"draft {source.get('gap', '')}", file=file)


def _model(source: dict) -> str:
    model = str(source.get("model", ""))
    return RECORDED if model.startswith("recorded:") else model


def _origin(source: dict) -> str:
    if source.get("kind") == DRAFTED_BY:
        return "drafted by AI"
    return "imported" if source.get("format") else "written by hand"


def when(time: str) -> str:
    """2026-10-25T17:04:53+00:00 -> 25 Oct 2026, 17:04 UTC: as people read it."""
    try:
        return datetime.fromisoformat(time).astimezone(timezone.utc).strftime("%d %b %Y, %H:%M UTC").lstrip("0")
    except ValueError:
        return time
