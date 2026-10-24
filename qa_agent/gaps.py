"""The coverage gaps, as code finds them: what `qa-agent draft cases` drafts for, and nothing else.

The same counting as the trace, kept as a list instead of a line:

    criterion   an acceptance criterion with no case
    operation   an operation, with the response codes no case expects
    401         a call without a valid token, once per service

A case waiting for review (a draft, changes needed, steps still in words) already covers what it
tests: it is reviewed, not drafted again. A rejected case covers nothing. The model never decides what
to test; it is given one gap at a time.
"""

from dataclasses import dataclass, field
from typing import Optional

from qa_agent.api_model import Operation
from qa_agent.cases import load_case_file
from qa_agent.project import Criterion, TeamProject
from qa_agent.trace import api_items, read_api


@dataclass
class Gap:
    key: str                                # "AC-6", "GET /bookings", "401 (bookings)": the draft's source.gap
    kind: str                               # criterion, operation or 401
    criterion: Optional[Criterion] = None
    service: str = ""
    operation: Optional[Operation] = None
    codes: list = field(default_factory=list)

    def short(self) -> str:
        """For a list next to the key: what is missing."""
        if self.kind == "criterion":
            return f"no case: {self.criterion.text}"
        if self.kind == "401":
            return "no call without a valid token"
        return "no case expects " + ", ".join(str(code) for code in self.codes)

    def describe(self) -> str:
        """For the model: the gap in a sentence."""
        if self.kind == "criterion":
            return f"Acceptance criterion {self.criterion.id} has no case: {self.criterion.text}"
        if self.kind == "401":
            return f"No case calls the {self.service} service without a valid token (expect 401)"
        codes = ", ".join(str(code) for code in self.codes)
        return f"{self.key}: no case expects {codes}"


def find_gaps(project: TeamProject, leave_out: frozenset = frozenset()) -> list[Gap]:
    """What no case covers. Cases in leave_out are counted as not there (a redo asks: without this case?)."""
    cases = [case for path in project.case_files() for case in load_case_file(path).cases
             if case.review.status != "rejected" and case.id not in leave_out]
    gaps = [Gap(criterion.id, "criterion", criterion=criterion)
            for criterion in project.read_criteria().values()
            if not any(criterion.id in case.criteria for case in cases)]
    api = read_api(project)
    if api is None:
        return gaps
    _, codes, _ = api_items(api, cases, project)
    by_operation: dict = {}
    for item in codes:
        if item.covered:
            continue
        if item.operation is None:
            gaps.append(Gap(f"401 ({item.service})", "401", service=item.service, codes=[401]))
            continue
        label = item.label.rsplit(" ", 1)[0]
        if label not in by_operation:
            by_operation[label] = Gap(label, "operation", service=item.service, operation=item.operation)
            gaps.append(by_operation[label])
        by_operation[label].codes.append(item.code)
    return gaps
