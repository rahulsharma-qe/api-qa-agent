"""`qa-agent check`: the project's cases checked with rules, no model.

Each finding names the file, the case, the step and the fix. Errors stop a case from being
generated; warnings and notes are for the reviewer, and also appear in the review sheet.
"""

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Optional

from qa_agent.api_model import ApiModel, ApiModelError, load_api_model
from qa_agent.cases import Case, CaseFile, CaseFormatError, Step, load_case_file
from qa_agent.criteria_drafts import CriteriaDrafts
from qa_agent.data_files import DataFileError, column_names
from qa_agent.project import TeamProject

ERROR, WARNING, INFO = "error", "warning", "info"
VALUE = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")
METHODS_WITH_A_BODY = ("POST", "PUT", "PATCH")


@dataclass(frozen=True)
class Finding:
    level: str
    file: str
    case_id: str
    message: str
    same_as: str = ""      # a duplicate case: the id of the case it repeats (printed once per group)

    def as_line(self) -> str:
        return f"  {self.level:<8} {self.message}"


@dataclass
class CheckReport:
    team: str
    findings: list = field(default_factory=list)
    case_files: list = field(default_factory=list)     # CaseFile, every file that could be read

    @property
    def cases(self) -> list[Case]:
        return [case for case_file in self.case_files for case in case_file.cases]

    @property
    def has_errors(self) -> bool:
        return any(finding.level == ERROR for finding in self.findings)

    def _duplicate_lines(self) -> dict:
        """One line per group of duplicates: "TC031, TC045: same steps as TC006 (...)"."""
        groups: dict = {}
        for finding in self.findings:
            if finding.same_as:
                groups.setdefault(finding.same_as, []).append(finding)
        return {first: f"  {WARNING:<8} {', '.join(f.case_id for f in found)}{found[0].message[len(found[0].case_id):]}"
                for first, found in groups.items()}

    def for_case(self, case_id: str) -> list[Finding]:
        return [finding for finding in self.findings if finding.case_id == case_id]

    def as_text(self) -> str:
        lines = [f"qa-agent check: {self.team} · {plural(len(self.cases), 'case')} in "
                 f"{plural(len(self.case_files), 'file')}"]
        by_file: dict[str, list[Finding]] = {}
        for finding in self.findings:
            by_file.setdefault(finding.file, []).append(finding)
        duplicates = self._duplicate_lines()
        for file_name, findings in by_file.items():
            shown = [duplicates.pop(finding.same_as) if finding.same_as else finding.as_line()
                     for finding in findings if not finding.same_as or finding.same_as in duplicates]
            lines += ["", file_name or "the project"] + shown
        counts = Counter(finding.level for finding in self.findings)
        groups = {finding.same_as for finding in self.findings if finding.same_as}
        if groups:
            repeats = sum(1 for finding in self.findings if finding.same_as)
            lines += ["", f"{plural(len(groups), 'group')} of duplicate cases ({plural(repeats, 'case')} "
                          "repeating another case's steps)"]
        lines += ["", " · ".join(plural(counts[level], name)
                                 for level, name in ((ERROR, "error"), (WARNING, "warning"), (INFO, "note")))]
        if not self.findings:
            lines[-1] = "No findings."
        return "\n".join(lines)


def plural(number: int, noun: str, many: str = "") -> str:
    """'1 case', '3 cases', '2 draft criteria' (many, for a noun that isn't plain +s): never '(s)'."""
    return f"{number} {noun if number == 1 else (many or noun + 's')}"


def check_project(project: TeamProject) -> CheckReport:
    """Every rule, over every case file. Raises SetupError when the project itself can't be read."""
    report = CheckReport(project.team)
    criteria = project.read_all_criteria()
    if not project.has_criteria():
        report.findings.append(Finding(INFO, "", "", "No acceptance-criteria.yaml: the criteria rules are skipped"))
    for question in CriteriaDrafts.load(project).open_questions():
        report.findings.append(Finding(INFO, project.relative(project.criteria_drafts_path), "",
                                       f"{question.get('id')} ({question.get('kind')}) is open: {question.get('text')} "
                                       "Answer it in the review sheet's Questions tab"))
    api = _api_model(project, report)
    for path in project.case_files():
        file_name = project.relative(path)
        try:
            report.case_files.append(load_case_file(path))
        except CaseFormatError as error:
            report.findings += [Finding(ERROR, file_name, "", problem) for problem in error.problems]
    _duplicate_ids(project, report)
    _duplicate_cases(project, report)
    for case_file in report.case_files:
        file_name = project.relative(case_file.path)
        for case in case_file.cases:
            for level, message in _case_findings(case, case_file, project, api, criteria):
                report.findings.append(Finding(level, file_name, case.id, f"{case.id}{message}"))
    return report


def _api_model(project: TeamProject, report: CheckReport) -> Optional[ApiModel]:
    if not project.api_model_path.is_file():
        report.findings.append(Finding(INFO, "", "", "No api/api.yaml: the rules that need the API are skipped "
                                                      "(qa-agent import api <file> creates it)"))
        return None
    try:
        return load_api_model(project.api_model_path)
    except ApiModelError as error:
        report.findings.append(Finding(ERROR, "api/api.yaml", "", f"{error}; the rules that need the API are skipped"))
        return None


def _duplicate_ids(project: TeamProject, report: CheckReport) -> None:
    places: dict[str, list[str]] = {}
    for case_file in report.case_files:
        for case in case_file.cases:
            places.setdefault(case.id, []).append(project.relative(case_file.path))
    for case_id, files in places.items():
        if len(set(files)) > 1:
            report.findings.append(Finding(ERROR, files[-1], case_id,
                                           f"{case_id}: the id is also used in {files[0]}. Fix: give each case its own id"))


def _duplicate_cases(project: TeamProject, report: CheckReport) -> None:
    """Cases with different ids and the same steps (requests, expectations, captures, data file), or the
    same manual steps (case and spacing aside). Rejected cases and cases with no steps are left out. The
    case with the lowest id is the one kept; each repeat gets a warning naming it."""
    by_steps: dict[str, list] = {}
    for case_file in report.case_files:
        for case in case_file.cases:
            if case.review.status != "rejected" and (case.steps or case.manual_steps):
                by_steps.setdefault(_steps_key(case), []).append((case, project.relative(case_file.path)))
    for found in by_steps.values():
        if len(found) < 2:
            continue
        found.sort(key=lambda pair: _id_order(pair[0].id))
        (first, first_file), repeats = found[0], found[1:]
        for case, file_name in repeats:
            report.findings.append(Finding(
                WARNING, file_name, case.id, f"{case.id}: same steps as {first.id} ({first_file}). "
                "Fix: reject one in the review sheet, or remove it", same_as=first.id))


def _steps_key(case: Case) -> str:
    steps = [{key: value for key, value in step.to_dict().items() if key != "name"} for step in case.steps]
    manual = [" ".join(line.lower().split()) for line in case.manual_steps]
    return json.dumps({"steps": steps, "data": case.data_file, "manual": manual}, sort_keys=True, default=str)


def _id_order(case_id: str) -> tuple:
    """TC2 before TC10: the number in the id, then the id."""
    number = re.search(r"\d+", case_id)
    return (int(number.group()) if number else 0, case_id)


def _case_findings(case: Case, case_file: CaseFile, project: TeamProject, api: Optional[ApiModel],
                   criteria: dict) -> list[tuple[str, str]]:
    """(level, message) pairs; each message starts after the case id. A rejected case is left alone."""
    if case.review.status == "rejected":
        return []
    found: list[tuple[str, str]] = []
    if not case.steps and not case.manual_steps:
        found.append((ERROR, ": has no steps. Fix: add steps (or manual_steps for steps still written in words)"))
    if case.needs_steps:
        found.append((INFO, ": needs steps (it has manual steps only). It is kept and traced, and can't be "
                            "generated until it has steps"))
    if case.changed_after_approval:
        found.append((WARNING, ": changed after it was approved. Review it again; until then it is not generated"))
    found += _criteria_findings(case, criteria)
    columns = _data_columns(case, project, found)
    captured: set[str] = set()
    for number, step in enumerate(case.steps, start=1):
        where = f" step {number}"
        if not step.expect:
            found.append((ERROR, f"{where}: checks nothing. Fix: add expect (at least a status)"))
        if _has_tbd([step.request.path, step.request.query, step.request.headers, step.request.body, step.expect]):
            found.append((ERROR, f"{where}: has TBD, a value still to confirm. Fix: replace TBD with the value "
                                 "the API should give (see the case's notes)"))
        found += _value_findings(step, where, captured, columns, case.data_file)
        if api is not None:
            found += _api_findings(step, where, api, step.request.service or project.main_service)
        captured |= set(step.capture)
    if _is_hollow(case.steps):
        found.append((WARNING, ": checks only status codes and ends in success: it passes even when the response "
                               "is wrong (a wrong amount, a missing field). Fix: add fields, exists or types to "
                               "the step that matters"))
    return found


def _has_tbd(value: Any) -> bool:
    """TBD anywhere in a step: a value a drafter (a person or the AI layer) couldn't confirm."""
    if isinstance(value, str):
        return re.search(r"\bTBD\b", value) is not None
    if isinstance(value, dict):
        return any(_has_tbd(key) or _has_tbd(item) for key, item in value.items())
    if isinstance(value, (list, tuple)):
        return any(_has_tbd(item) for item in value)
    return False


def _is_hollow(steps: list[Step]) -> bool:
    """Every step checks only a status (or a time), and the last one expects success: a wrong answer passes.
    A case that ends in a refusal or a 404 is not hollow: that status is the point of it."""
    if not steps or any(set(step.expect) - {"status", "max_response_ms"} for step in steps):
        return False
    last = steps[-1].expect.get("status")
    return isinstance(last, int) and 200 <= last < 300


def _criteria_findings(case: Case, criteria: dict) -> list[tuple[str, str]]:
    """criteria: every criterion, drafts included."""
    if not criteria:
        return []
    if not case.criteria:
        return [(WARNING, ": linked to no criterion. Fix: add criteria: [AC-…] so it can be traced")]
    found = []
    for item in case.criteria:
        if item not in criteria:
            found.append((ERROR, f": criterion {item} is not in acceptance-criteria.yaml. Fix: correct the id, "
                                 "or add the criterion"))
        elif not criteria[item].is_approved:
            found.append((WARNING, f": criterion {item} is {criteria[item].status.replace('_', ' ')}, not approved: "
                                   "it counts once a person approves it in the review sheet"))
    return found


def _data_columns(case: Case, project: TeamProject, found: list) -> Optional[list[str]]:
    if not case.data_file:
        return None
    try:
        return column_names(project.root / case.data_file)
    except DataFileError as error:
        found.append((ERROR, f": data file {case.data_file}: {str(error).split(': ', 1)[-1]}"))
        return []


def _value_findings(step: Step, where: str, captured: set, columns: Optional[list], data: Optional[str]):
    found = []
    request = step.request
    for name in sorted(set(_values_in([request.path, request.query, request.headers, request.body, step.expect]))):
        if name == "unique":
            continue
        if name.startswith("row."):
            column = name[4:]
            if columns is None:
                found.append((ERROR, f"{where}: {{{{{name}}}}} needs a data file. Fix: add data_file: <file> to the case"))
            elif columns and column not in columns:
                found.append((ERROR, f"{where}: {{{{{name}}}}}: {data} has no column '{column}' "
                                     f"(it has: {', '.join(columns)})"))
        elif name not in captured:
            found.append((ERROR, f"{where}: {{{{{name}}}}} is used before it is captured. "
                                 f"Fix: add capture: {{{name}: <path in the response>}} to an earlier step"))
    return found


def _api_findings(step: Step, where: str, api: ApiModel, service: str):
    request = step.request
    if service not in api.services:
        return [(ERROR, f"{where}: service '{service}' is not in api/api.yaml "
                        f"(it has: {', '.join(sorted(api.services)) or 'none'})")]
    operation = api.find(service, request.method, request.path)
    if operation is None:
        return [(ERROR, f"{where}: {request.method} {request.path} is not in api/api.yaml. "
                        f"Fix: correct the method or path, or import the API description again")]
    found = []
    status = step.expect.get("status")
    if isinstance(status, int) and operation.responses and status not in operation.responses:
        found.append((WARNING, f"{where}: status {status} is not documented for {operation.method} {operation.path} "
                               f"(documented: {', '.join(map(str, operation.responses))}). "
                               f"Fix: check the expected status, or document it in the API"))
    if request.method in METHODS_WITH_A_BODY and operation.body_required and isinstance(request.body, dict):
        missing = [name for name in operation.body_required if name not in request.body]
        if missing:
            found.append((WARNING, f"{where}: the body leaves out required {', '.join(missing)}. "
                                   f"Fine for a negative test; otherwise add them"))
    return found


def _values_in(value: Any):
    """Every {{name}} in a value, however deep."""
    if isinstance(value, str):
        yield from VALUE.findall(value)
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from _values_in(key)
            yield from _values_in(item)
    elif isinstance(value, list):
        for item in value:
            yield from _values_in(item)
