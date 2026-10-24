"""`qa-agent draft cases`: a draft case for each coverage gap, for a person to review.

    qa-agent draft cases --plan        the gaps, the calls and an estimate; no model call
    qa-agent draft cases [--max 10]    one model call per gap, up to --max
    qa-agent draft cases --redo TC045  a new draft for one a reviewer rejected or sent back, with the comment

Code decides what is missing (gaps.py); the model writes how to test it; code then checks the reply
before anything is written. The guardrails, all here and none trusted to the prompt:

    G1  review is always draft: whatever the reply says under review is dropped
    G2  ids come from code: the next free id with the project's prefix
    G3  source is written by code: {kind: ai-draft, model, gap}
    G4  a value the model couldn't source is TBD: check makes it an error, so it can't be approved
    G5  only operations in api/api.yaml, only criteria in acceptance-criteria.yaml: else refused
    G6  drafts go to their own files (cases/<area>-drafts.yaml); no file a person wrote is touched
    G7  a gap already drafted (any review status, rejected too) is skipped
    G10 a reply that isn't the case format is refused with the reason; nothing is written for it

A redo goes through the same checks. Only an AI draft a reviewer rejected or sent back can be redone;
the new draft's source says which case it replaces, and the old one is marked rejected and points to it.

Redaction (G8) and the audit log (G9) are in AiSession: every call goes through it.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

from qa_agent.ai.models import ModelError
from qa_agent.ai.prompts import DRAFT_CASES_SYSTEM, draft_cases_user
from qa_agent.ai.session import AiSession
from qa_agent.case_import import id_maker
from qa_agent.checks import plural
from qa_agent.cases import Case, CaseFile, CaseFormatError, load_case_file, parse_case_file, save_case_file
from qa_agent.gaps import Gap, find_gaps
from qa_agent.project import TeamProject
from qa_agent.trace import read_api

DEFAULT_MAX = 10
MAX_CASES_PER_GAP = 3
TEAM_RULES_FILE = Path("ai") / "rules.md"
DRAFTED_BY = "ai-draft"
TOKENS_PER_CHARACTER = 0.25          # a rough estimate for --plan
REPLY_TOKENS_ESTIMATE = 800
SENT_BACK = ("rejected", "changes_needed")


@dataclass
class DraftReport:
    drafted: list = field(default_factory=list)      # (gap key, [case ids], file)
    refused: list = field(default_factory=list)      # (gap key, reason)
    skipped: list = field(default_factory=list)      # gap keys drafted before
    covered: list = field(default_factory=list)      # gap keys a draft made earlier in this run covers
    not_reached: list = field(default_factory=list)  # gap keys over --max
    stopped: str = ""                                # why the run stopped early (the model couldn't be reached)

    def as_text(self) -> str:
        lines = [f"drafted   {key}: {', '.join(ids)} -> {path}" for key, ids, path in self.drafted]
        lines += [f"refused   {key}: {reason}" for key, reason in self.refused]
        lines += [f"skipped   {key}: drafted before" for key in self.skipped]
        lines += [f"covered   {key}: by a draft made earlier in this run, no call" for key in self.covered]
        if self.not_reached:
            lines.append(f"next time {', '.join(self.not_reached)} (over --max)")
        if self.stopped:
            lines.append(f"stopped   {self.stopped}")
        drafted = sum(len(ids) for _, ids, _ in self.drafted)
        lines += ["", f"{plural(drafted, 'draft case')} for {plural(len(self.drafted), 'gap')}, {len(self.refused)} refused. "
                      "Next: qa-agent check, then qa-agent review export: a person decides on each one."]
        return "\n".join(lines)


@dataclass
class RedoReport:
    redone: list = field(default_factory=list)       # (old id, [new ids], file)
    not_redone: list = field(default_factory=list)   # (id, reason)
    stopped: str = ""

    def as_text(self) -> str:
        lines = [f"redone    {old}: {', '.join(ids)} -> {path} ({old} is now rejected)" for old, ids, path in self.redone]
        lines += [f"not redone {key}: {reason}" for key, reason in self.not_redone]
        if self.stopped:
            lines.append(f"stopped   {self.stopped}")
        lines += ["", f"{plural(len(self.redone), 'case')} redone, {len(self.not_redone)} not. "
                      "Next: qa-agent check, then qa-agent review export: a person decides on the new drafts."]
        return "\n".join(lines)


def pending_gaps(project: TeamProject) -> tuple[list, list]:
    """(gaps to draft, gaps drafted before)."""
    drafted_before = {case.source.get("gap") for path in project.case_files()
                      for case in load_case_file(path).cases if case.source.get("kind") == DRAFTED_BY}
    gaps = find_gaps(project)
    return [gap for gap in gaps if gap.key not in drafted_before], [gap.key for gap in gaps if gap.key in drafted_before]


def plan(project: TeamProject, max_gaps: int = DEFAULT_MAX, session: Optional[AiSession] = None) -> str:
    to_draft, skipped = pending_gaps(project)
    lines = [f"{plural(len(to_draft), 'gap')} to draft; {len(skipped)} drafted before."]
    total_tokens = 0
    for number, gap in enumerate(to_draft, start=1):
        marker = "" if number <= max_gaps else "   (over --max: next time)"
        lines.append(f"  {gap.key:<30} {gap.short()}{marker}")
        if number <= max_gaps:
            total_tokens += _estimate_tokens(project, gap)
    calls = min(len(to_draft), max_gaps)
    estimate = (f"at most {plural(calls, 'model call')} (a gap an earlier draft covers needs none), "
                f"about {total_tokens:,} tokens in and {calls * REPLY_TOKENS_ESTIMATE:,} out")
    if session is not None:
        cost = session.cost(total_tokens, calls * REPLY_TOKENS_ESTIMATE)
        if cost is not None:
            estimate += f", about ${cost:.2f}"
    return "\n".join(lines + ["", estimate + ". Nothing was sent: run without --plan to draft."])


def draft_cases(project: TeamProject, session: AiSession, max_gaps: int = DEFAULT_MAX) -> DraftReport:
    """One call per gap, up to max_gaps calls. The gaps are counted again before each call: a draft
    for a criterion often covers an operation's codes too, and that gap then needs no call."""
    report = DraftReport()
    to_draft, report.skipped = pending_gaps(project)
    calls = 0
    for number, planned in enumerate(to_draft):
        if calls == max_gaps:
            report.not_reached = [gap.key for gap in to_draft[number:]]
            break
        gap = {gap.key: gap for gap in find_gaps(project)}.get(planned.key)
        if gap is None:
            report.covered.append(planned.key)
            continue
        calls += 1
        try:
            reply = session.ask(f"draft {gap.key}", DRAFT_CASES_SYSTEM, _user_prompt(project, gap), max_tokens=3000)
        except ModelError as error:
            report.stopped = f"at {gap.key}: {error}"
            report.not_reached = [g.key for g in to_draft[number:]]
            break
        result = _write_drafts(project, gap, reply, f"{session.model.provider}:{session.model.model}")
        if isinstance(result, str):
            report.refused.append((gap.key, result))
        else:
            report.drafted.append((gap.key, *result))
    return report


def redo(project: TeamProject, session: AiSession, case_ids: list) -> RedoReport:
    """A new draft for each case a reviewer rejected or sent back, with the old draft and the comment."""
    report = RedoReport()
    for case_id in case_ids:
        cases = {case.id: case for path in project.case_files() for case in load_case_file(path).cases}
        old = cases.get(case_id)
        reason = _why_not_redo(case_id, old, cases)
        gap = None
        if not reason:
            sent_back = frozenset(case.id for case in cases.values() if case.review.status in SENT_BACK)
            gap = next((g for g in find_gaps(project, sent_back) if g.key == old.source.get("gap")), None)
            if gap is None:
                # the drafts reviewers sent back don't count: they are being redone
                reason = f"its gap {old.source.get('gap')} is covered by another case now (see qa-agent trace): reject this one in the review sheet"
        if reason:
            report.not_redone.append((case_id, reason))
            continue
        returned = {"case": _example(old), "comment": old.review.comment}
        try:
            reply = session.ask(f"redo {case_id}", DRAFT_CASES_SYSTEM, _user_prompt(project, gap, returned),
                                max_tokens=3000)
        except ModelError as error:
            report.stopped = f"at {case_id}: {error}"
            break
        result = _write_drafts(project, gap, reply, f"{session.model.provider}:{session.model.model}", replaces=case_id)
        if isinstance(result, str):
            report.not_redone.append((case_id, f"the reply was refused: {result}"))
            continue
        _mark_replaced(project, case_id, result[0])
        report.redone.append((case_id, *result))
    return report


def _why_not_redo(case_id: str, old: Optional[Case], cases: dict) -> str:
    if old is None:
        return "no case has this id"
    if old.source.get("kind") != DRAFTED_BY:
        return "not an AI draft: edit it in its case file"
    newer = [case.id for case in cases.values() if case.source.get("replaces") == case_id]
    if newer:
        return f"already redone as {', '.join(newer)}"
    if old.review.status not in SENT_BACK:
        return f"it is {old.review.status.replace('_', ' ')}: only a rejected or sent-back draft (changes needed) is redone"
    return ""


def _mark_replaced(project: TeamProject, case_id: str, new_ids: list) -> None:
    for path in project.case_files():
        case_file = load_case_file(path)
        for case in case_file.cases:
            if case.id == case_id:
                note = f"replaced by {', '.join(new_ids)}"
                case.review.status = "rejected"
                case.review.comment = f"{case.review.comment} ({note})" if case.review.comment else note
                save_case_file(case_file)
                return


def _user_prompt(project: TeamProject, gap: Gap, sent_back: Optional[dict] = None) -> str:
    api = read_api(project)
    service = gap.service or project.main_service
    operations = [op for op in (api.operations(service) if api else []) if not op.not_tested]
    rules_path = project.root / TEAM_RULES_FILE
    rules = rules_path.read_text(encoding="utf-8") if rules_path.is_file() else ""
    return draft_cases_user(gap, project.read_criteria(), operations, _examples(project, gap), rules, sent_back)


def _examples(project: TeamProject, gap: Gap, limit: int = 2) -> list:
    """Approved cases with steps, the ones calling the gap's path first: the team's style."""
    approved = [case for path in project.case_files() for case in load_case_file(path).cases
                if case.is_approved and case.steps]
    path = gap.operation.path if gap.operation else ""
    approved.sort(key=lambda case: not any(step.request.path.split("/")[1:2] == path.split("/")[1:2]
                                           for step in case.steps))
    return [_example(case) for case in approved[:limit]]


def _example(case: Case) -> dict:
    """What the model sees of a case: what it tests, not who reviewed it."""
    data = case.to_dict()
    return {key: data[key] for key in ("title", "criteria", "priority", "tags", "steps", "notes") if key in data}


def _write_drafts(project: TeamProject, gap: Gap, reply: str, model_name: str, replaces: str = ""):
    """The draft cases written: ([ids], file). Or the reason the reply was refused (str)."""
    raw_cases = _read_reply(reply)
    if isinstance(raw_cases, str):
        return raw_cases
    criteria = project.read_criteria()
    api = read_api(project)
    files = {path: load_case_file(path) for path in project.case_files()}
    next_id = id_maker(project, files, [])
    entries = []
    for raw in raw_cases:
        entry = {key: value for key, value in raw.items() if key not in ("id", "review", "source", "suite")}  # G1-G3
        entry.update(id=next_id(), suite="functional", review={"status": "draft"},
                     source={"kind": DRAFTED_BY, "model": model_name, "gap": gap.key,
                             **({"replaces": replaces} if replaces else {})})
        entries.append(entry)
    try:
        drafted = parse_case_file({"feature": "drafts", "cases": entries}, Path("reply")).cases
    except CaseFormatError as error:                                                                # G10
        return "not the case format: " + "; ".join(error.problems)
    for case in drafted:
        unknown = [item for item in case.criteria if item not in criteria]
        if unknown:                                                                                  # G5
            return f"{case.title!r} names criteria not in acceptance-criteria.yaml: {', '.join(unknown)}"
        for step in case.steps:
            service = step.request.service or project.main_service
            if api is None or api.find(service, step.request.method, step.request.path) is None:
                return f"{case.title!r} calls {step.request.method} {step.request.path}, not in api/api.yaml"
        if not case.steps:
            return f"{case.title!r} has no steps"
    path = _drafts_file(project, drafted[0])                                                        # G6
    case_file = files.get(path) or CaseFile(path, f"{_area(drafted[0]).capitalize()} (drafted)")
    case_file.cases.extend(drafted)
    path.parent.mkdir(parents=True, exist_ok=True)
    save_case_file(case_file)
    return [case.id for case in drafted], project.relative(path)


def _read_reply(reply: str):
    """The list of cases in the reply, or why there is none."""
    text = re.sub(r"^\s*```(?:ya?ml)?\s*\n|\n```\s*$", "", reply.strip())
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as error:
        return f"the reply is not YAML ({str(error).splitlines()[0]})"
    if not isinstance(data, dict) or not isinstance(data.get("cases"), list):
        return "the reply has no 'cases:' list"
    if not data["cases"]:
        return f"the model drafted nothing: {data.get('reason') or 'no reason given'}"
    if len(data["cases"]) > MAX_CASES_PER_GAP:
        return f"{len(data['cases'])} cases for one gap (at most {MAX_CASES_PER_GAP})"
    if not all(isinstance(raw, dict) for raw in data["cases"]):
        return "a case in the reply is not a mapping"
    return data["cases"]


def _area(case) -> str:
    """The first part of the first step's path: /bookings/{pnr}/cancel -> bookings."""
    first = case.steps[0].request.path.strip("/").split("/")[0] if case.steps else ""
    return re.sub(r"[^a-z0-9]+", "-", first.lower()).strip("-") or "api"


def _drafts_file(project: TeamProject, case) -> Path:
    return project.cases_dir / f"{_area(case)}-drafts.yaml"


def _estimate_tokens(project: TeamProject, gap: Gap) -> int:
    return int((len(DRAFT_CASES_SYSTEM) + len(_user_prompt(project, gap))) * TOKENS_PER_CHARACTER)
