"""acceptance-criteria-drafts.yaml: criteria and questions drafted from a requirement.

Written only by code (qa-agent draft criteria, qa-agent review apply), never by hand, so it can be
rewritten freely; a person's acceptance-criteria.yaml is never touched.

    criteria:
      - id: AC-7
        text: A booking cancelled within 24 hours of being made gets a full refund.
        status: draft                     # draft, approved, changes_needed or rejected
        source: {kind: ai-draft, model: anthropic:<model>, requirement: requirements/cancel.md,
                 quote: "Cancel within a day and get all your money back."}
        review: {by: qa-lead, date: 2026-10-24, comment: ""}
    questions:
      - id: Q-1
        kind: contradiction               # ambiguity, omission, contradiction or dependency
        text: Line 3 says 24 hours, line 9 says one working day. Which is it?
        quote: "within one working day"
        status: open                      # open or answered
        answer: ""
        answered_by: ""
"""

from dataclasses import dataclass, field
from pathlib import Path

from qa_agent.project import TeamProject
from qa_agent.yaml_files import read_yaml, write_yaml

QUESTION_KINDS = ("ambiguity", "omission", "contradiction", "dependency")
HEADER = "# Drafted by qa-agent draft criteria. A person approves each criterion, and answers each\n" \
         "# question, in the review sheet (qa-agent review export, then review apply). Written by code only.\n"


@dataclass
class CriteriaDrafts:
    path: Path
    criteria: list = field(default_factory=list)       # dicts, as in the file
    questions: list = field(default_factory=list)

    @classmethod
    def load(cls, project: TeamProject) -> "CriteriaDrafts":
        path = project.criteria_drafts_path
        data = (read_yaml(path) or {}) if path.is_file() else {}
        return cls(path, list(data.get("criteria") or []), list(data.get("questions") or []))

    def save(self) -> None:
        write_yaml(self.path, {"criteria": self.criteria, "questions": self.questions})
        self.path.write_text(HEADER + self.path.read_text(encoding="utf-8"), encoding="utf-8")

    def open_questions(self) -> list:
        return [question for question in self.questions if question.get("status", "open") == "open"]
