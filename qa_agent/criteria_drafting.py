"""`qa-agent draft criteria <requirement>`: acceptance criteria and questions, drafted from plain words.

    qa-agent draft criteria requirements/cancellation.md

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

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from qa_agent.ai.prompts import DRAFT_CRITERIA_SYSTEM, draft_criteria_user
from qa_agent.ai.session import AiSession
from qa_agent.criteria_drafts import QUESTION_KINDS, CriteriaDrafts
from qa_agent.checks import plural
from qa_agent.project import SetupError, TeamProject

DRAFTED_BY = "ai-draft"
MIN_QUOTE_WORDS = 3            # a word or two ("the", "refund") is in almost any requirement: no proof


@dataclass
class CriteriaDraftReport:
    criteria: list = field(default_factory=list)        # (id, text)
    questions: list = field(default_factory=list)       # (id, kind, text)
    refused: list = field(default_factory=list)         # (what, reason)
    skipped: list = field(default_factory=list)         # text already there

    def as_text(self) -> str:
        lines = [f"drafted   {key}: {text}" for key, text in self.criteria]
        lines += [f"question  {key} ({kind}): {text}" for key, kind, text in self.questions]
        lines += [f"refused   {what}: {reason}" for what, reason in self.refused]
        lines += [f"skipped   {text}: already there" for text in self.skipped]
        lines += ["", f"{plural(len(self.criteria), 'draft criterion', 'draft criteria')}, "
                      f"{plural(len(self.questions), 'question')}, {len(self.refused)} refused. "
                      "Next: qa-agent review export: a person approves the criteria and answers the questions."]
        return "\n".join(lines)


def draft_criteria(project: TeamProject, session: AiSession, requirement_path: Path) -> CriteriaDraftReport:
    if not requirement_path.is_file():
        raise SetupError(f"no requirement at {requirement_path}")
    requirement = requirement_path.read_text(encoding="utf-8")
    name = project.relative(requirement_path)
    reply = session.ask(f"draft criteria {requirement_path.stem}", DRAFT_CRITERIA_SYSTEM,
                        draft_criteria_user(name, requirement, project.read_all_criteria()), max_tokens=3000)
    report = CriteriaDraftReport()
    items = _read_reply(reply)
    if isinstance(items, str):
        report.refused.append(("the reply", items))
        return report
    drafts = CriteriaDrafts.load(project)
    known_texts = {_plain(criterion.text) for criterion in project.read_all_criteria().values()}
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
    if report.criteria or report.questions:
        drafts.save()
    return report


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
