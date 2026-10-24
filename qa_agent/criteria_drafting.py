"""`qa-agent draft criteria <requirement>`: acceptance criteria and questions, drafted from plain words.

    qa-agent draft criteria requirements/cancellation.md
    qa-agent draft criteria - --ref PROJ-123          the text from stdin (pasted, or piped from a tool)

--ref names where the requirement lives (a ticket, a page): the criteria point back to it, and the
next run with the same ref finds what changed. Without it, the file's path is the name.

    qa-agent draft criteria - --ref PROJ-123 --plan   what changed since the last run; no model call

C5  changed requirement, found by code before any model call: a drafted criterion from the same
    requirement whose quoted words are no longer in it goes back to changes_needed, with a comment
    saying so. The cases linked to it then get a warning from check until a person decides again.

One model call. The reply is checked item by item before anything is written:

    C1  grounded: every criterion and question quotes at least three words that are really in the
        requirement (spacing and case aside); an item that doesn't is refused, so nothing is added
        that the requirement doesn't say
    C2  ids (AC-<next>, Q-<next>) and status (draft, open) come from code
    C3  written to acceptance-criteria-drafts.yaml only; a person's acceptance-criteria.yaml is never touched
    C4  a criterion or question already there is skipped, so running it again is safe: the same words,
        or the same quote from the requirement (a criterion a reviewer reworded is still known)

Questions are what a requirement review finds: ambiguity (a rule read two ways, or a boundary not
settled), omission (something a tester needs isn't said at all), contradiction (two parts disagree)
and dependency (another feature or system it relies on). A
person approves each criterion and answers each question in the review sheet.
"""

import datetime
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

from qa_agent.ai.prompts import DRAFT_CRITERIA_SYSTEM, draft_criteria_user
from qa_agent.ai.session import AiSession
from qa_agent.criteria_drafts import QUESTION_KINDS, CriteriaDrafts
from qa_agent.checks import plural
from qa_agent.project import SetupError, TeamProject

DRAFTED_BY = "ai-draft"
TOKENS_PER_CHARACTER = 0.25          # a rough estimate for --plan
REPLY_TOKENS_ESTIMATE = 1500
MIN_QUOTE_WORDS = 3            # a word or two ("the", "refund") is in almost any requirement: no proof


@dataclass
class CriteriaDraftReport:
    criteria: list = field(default_factory=list)        # (id, text)
    questions: list = field(default_factory=list)       # (id, kind, text)
    refused: list = field(default_factory=list)         # (what, reason)
    skipped: list = field(default_factory=list)         # text already there
    changed: list = field(default_factory=list)         # (id, quote) no longer in the requirement

    def as_text(self) -> str:
        lines = [f"changed   {key}: '{quote}' is no longer in the requirement: back to changes needed"
                 for key, quote in self.changed]
        lines += [f"drafted   {key}: {text}" for key, text in self.criteria]
        lines += [f"question  {key} ({kind}): {text}" for key, kind, text in self.questions]
        lines += [f"refused   {what}: {reason}" for what, reason in self.refused]
        lines += [f"skipped   {text}: already there" for text in self.skipped]
        changed = f"{plural(len(self.changed), 'criterion', 'criteria')} changed, " if self.changed else ""
        lines += ["", f"{changed}{plural(len(self.criteria), 'draft criterion', 'draft criteria')}, "
                      f"{plural(len(self.questions), 'question')}, {len(self.refused)} refused. "
                      "Next: qa-agent review export: a person approves the criteria and answers the questions."]
        return "\n".join(lines)


@dataclass
class Requirement:
    text: str
    name: str          # what the criteria point back to: the ref (PROJ-123), else the file's path
    short: str         # for the model call's name: the ref, else the file's name without .md


def read_requirement(project: TeamProject, where: str, ref: str = "", stdin=None) -> Requirement:
    """where is a file, or - for stdin (which needs a ref: there is no other name to point back to)."""
    ref = ref.strip()
    if where == "-":
        if not ref:
            raise SetupError("reading from stdin needs --ref (the ticket or page it came from, e.g. --ref PROJ-123): "
                             "the criteria point back to it")
        text = (stdin or sys.stdin).read()
    else:
        path = Path(where)
        if not path.is_file():
            raise SetupError(f"no requirement at {where}")
        text = path.read_text(encoding="utf-8")
    if not text.strip():
        raise SetupError(f"the requirement {ref or where} is empty")
    if ref:
        return Requirement(text, ref, ref)
    return Requirement(text, project.relative(Path(where)), Path(where).stem)


def draft_criteria(project: TeamProject, session: AiSession, source: Requirement) -> CriteriaDraftReport:
    requirement, name = source.text, source.name
    drafts = CriteriaDrafts.load(project)
    report = CriteriaDraftReport()
    changed = changed_criteria(drafts, source)                                             # C5: code, no model
    for entry in changed:
        quote, before = entry["source"]["quote"], entry.get("review") or {}
        was = f" (it was approved by {before['by']}, {before.get('date', '')})" \
            if entry.get("status") == "approved" and before.get("by") else ""
        entry["status"] = "changes_needed"
        entry["review"] = {"by": "qa-agent", "date": datetime.date.today().isoformat(),
                           "comment": f"the requirement changed: '{quote}' is no longer in {name}{was}. "
                                      "See the new drafts from it, then approve, change or reject this one"}
        report.changed.append((entry["id"], quote))
    changed_ids = {entry["id"] for entry in changed}
    existing = {key: c for key, c in project.read_all_criteria().items() if key not in changed_ids}
    reply = session.ask(f"draft criteria {source.short}", DRAFT_CRITERIA_SYSTEM,
                        draft_criteria_user(name, requirement, existing, [(e["id"], e["text"]) for e in changed]),
                        max_tokens=3000)
    items = _read_reply(reply)
    if isinstance(items, str):
        report.refused.append(("the reply", items))
        if report.changed:
            drafts.save()
        return report
    known_texts = {_plain(criterion.text) for criterion in existing.values()}
    known_texts |= {"quote:" + _plain((entry.get("source") or {}).get("quote", "")) for entry in drafts.criteria}
    known_questions = {_plain(question.get("text", "")) for question in drafts.questions}
    known_questions |= {"quote:" + _plain(question.get("quote", "")) for question in drafts.questions}
    next_criterion = _counter("AC-", list(project.read_all_criteria()))
    next_question = _counter("Q-", [str(question.get("id", "")) for question in drafts.questions])
    model = f"{session.model.provider}:{session.model.model}"
    for raw in items["criteria"]:
        problem = _problem(raw, requirement)
        if problem:
            report.refused.append((_label(raw), problem))
        elif _plain(raw["text"]) in known_texts or "quote:" + _plain(raw["from"]) in known_texts:
            report.skipped.append(raw["text"])
        else:
            key = next_criterion()
            known_texts |= {_plain(raw["text"]), "quote:" + _plain(raw["from"])}
            drafts.criteria.append({"id": key, "text": raw["text"].strip(), "status": "draft",
                                    "source": {"kind": DRAFTED_BY, "model": model, "requirement": name,
                                               "quote": raw["from"].strip()}})
            report.criteria.append((key, raw["text"].strip()))
    for raw in items["questions"]:
        problem = _problem(raw, requirement) or (
            "" if raw.get("kind") in QUESTION_KINDS else f"kind '{raw.get('kind')}' (use {', '.join(QUESTION_KINDS)})")
        if problem:
            report.refused.append((_label(raw), problem))
        elif _plain(raw["text"]) in known_questions or "quote:" + _plain(raw["from"]) in known_questions:
            report.skipped.append(raw["text"])
        else:
            key = next_question()
            known_questions |= {_plain(raw["text"]), "quote:" + _plain(raw["from"])}
            drafts.questions.append({"id": key, "kind": raw["kind"], "text": raw["text"].strip(),
                                     "quote": raw["from"].strip(), "requirement": name, "status": "open",
                                     "answer": "", "answered_by": ""})
            report.questions.append((key, raw["kind"], raw["text"].strip()))
    if report.criteria or report.questions or report.changed:
        drafts.save()
    return report


def changed_criteria(drafts: CriteriaDrafts, source: Requirement) -> list:
    """Drafted criteria from this requirement whose quoted words aren't in it any more.
    Draft and approved ones only: one already sent back or rejected waits for a person anyway."""
    text = _plain(source.text)
    return [entry for entry in drafts.criteria
            if (entry.get("source") or {}).get("requirement") == source.name
            and entry.get("status", "draft") in ("draft", "approved")
            and _plain(entry["source"].get("quote", "")) not in text]


def plan(project: TeamProject, source: Requirement, session: Optional[AiSession] = None) -> str:
    """What a run would do: what changed since the last run, and the call. Nothing sent, nothing written."""
    drafts = CriteriaDrafts.load(project)
    before = [entry["id"] for entry in drafts.criteria
              if (entry.get("source") or {}).get("requirement") == source.name]
    lines = [f"{source.name}: {plural(len(before), 'criterion', 'criteria')} drafted from it before"
             + (f" ({', '.join(before)})" if before else "") + "."]
    changed = changed_criteria(drafts, source)
    lines += [f"  changed   {entry['id']}: '{entry['source']['quote']}' is no longer in it" for entry in changed]
    if before and not changed:
        lines.append("  no criterion's words have changed")
    prompt = draft_criteria_user(source.name, source.text, project.read_all_criteria())
    tokens = int((len(DRAFT_CRITERIA_SYSTEM) + len(prompt)) * TOKENS_PER_CHARACTER)
    estimate = f"1 model call, about {tokens:,} tokens in and {REPLY_TOKENS_ESTIMATE:,} out"
    cost = session.cost(tokens, REPLY_TOKENS_ESTIMATE) if session is not None else None
    if cost is not None:
        estimate += f", about ${cost:.2f}"
    return "\n".join(lines + ["", estimate + ". Nothing was sent or written: run without --plan to draft."])


def _read_reply(reply: str):
    text = re.sub(r"^\s*```(?:ya?ml)?\s*\n|\n```\s*$", "", reply.strip())
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as error:
        return f"not YAML ({str(error).splitlines()[0]})"
    if not isinstance(data, dict) or not isinstance(data.get("criteria", []), list) \
            or not isinstance(data.get("questions", []), list):
        return "no 'criteria:' and 'questions:' lists"
    items = {"criteria": data.get("criteria") or [], "questions": data.get("questions") or []}
    if not items["criteria"] and not items["questions"]:
        return "nothing drafted"
    return items


def _problem(raw, requirement: str) -> str:
    """Why an item can't be taken, or ''."""
    if not isinstance(raw, dict) or not str(raw.get("text") or "").strip():
        return "no text"
    quote = str(raw.get("from") or "")
    if len(_plain(quote).split()) < MIN_QUOTE_WORDS:
        return f"it must quote at least {MIN_QUOTE_WORDS} words of the requirement"
    if _plain(quote) not in _plain(requirement):                                  # C1: grounded
        return f"'{quote.strip()}' is not in the requirement"
    return ""


def _plain(text: str) -> str:
    """Spacing, case and quote marks aside: what grounding and repeats compare."""
    return " ".join(re.sub(r"[\"'“”‘’]", "", str(text)).lower().split())


def _label(raw) -> str:
    text = str(raw.get("text", "")) if isinstance(raw, dict) else str(raw)
    return (text[:60] + "…") if len(text) > 60 else (text or "an item")


def _counter(prefix: str, used: list):
    numbers = [int(match.group(1)) for match in (re.match(rf"^{re.escape(prefix)}(\d+)$", key) for key in used) if match]
    state = {"next": max(numbers, default=0) + 1}

    def next_key() -> str:
        key = f"{prefix}{state['next']}"
        state["next"] += 1
        return key
    return next_key
