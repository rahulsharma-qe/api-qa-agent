"""`qa-agent trace`: criteria -> cases -> tests -> results, and how much is covered.

    qa-agent trace --results reports/junit.xml target/surefire-reports

Only approved cases count towards coverage; a case in words or a draft is listed, not counted.
Coverage is measured and reported, never decided here: drafting cases for the gaps is the AI
layer's job. `--check` fails only when an approved case has no test.

    Criteria        each criterion has at least one approved case
    Operations      each operation in api/api.yaml has one (not_tested: <reason> leaves it out)
    Response codes  each documented code of each operation is expected by an approved step;
                    401 counts once per service, 422 only where the operation takes a body
    Cases -> tests  each approved case has its test in every framework
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from qa_agent.api_model import ApiModel, ApiModelError, load_api_model
from qa_agent.cases import Case, load_case_file
from qa_agent.data_files import DataFileError, rows
from qa_agent.project import TeamProject
from qa_agent.renderers import RENDERERS
from qa_agent.results import read_results
from qa_agent.review_sheet import natural_order

TAKES_A_BODY = ("POST", "PUT", "PATCH")
FLOORED = ("Criteria", "Operations")
TEST_NAME = {"pytest": re.compile(r"^def (test_\w+)\(", re.MULTILINE),
             "restassured": re.compile(r"^\s+public void (\w+)\(", re.MULTILINE)}


@dataclass
class Coverage:
    name: str
    covered: int
    total: int
    missing: list = field(default_factory=list)
    note: str = ""

    @property
    def percent(self) -> float:
        return 100.0 * self.covered / self.total if self.total else 100.0

    def as_line(self) -> str:
        if self.note:
            return f"{self.name:<15} {self.note}"
        line = f"{self.name:<15} {self.covered} of {self.total}"
        return line + (f"   missing: {', '.join(self.missing)}" if self.missing else "")


@dataclass
class TraceRow:
    criterion: str
    case_id: str
    title: str
    review: str
    suite: str
    tests: list
    result: str


@dataclass
class TraceReport:
    team: str
    rows: list = field(default_factory=list)
    coverage: list = field(default_factory=list)
    not_tested: list = field(default_factory=list)        # "POST /test/reset: a test-only route"
    missing_tests: list = field(default_factory=list)     # "TC001 (restassured)"
    below_floor: list = field(default_factory=list)       # "Operations 62% (floor 80%)", with --min-coverage
    orphan_tests: list = field(default_factory=list)
    results_read: dict = field(default_factory=dict)      # framework -> {"passed": n, ...}

    def as_text(self) -> str:
        lines = [f"qa-agent trace: {self.team}", ""] + [item.as_line() for item in self.coverage]
        if self.not_tested:
            lines.append(f"{'Not tested':<15} on purpose: " + "; ".join(self.not_tested))
        lines.append(f"{'Results':<15} " + (" · ".join(f"{framework} " + ", ".join(f"{n} {kind}" for kind, n in counts.items())
                                                     for framework, counts in self.results_read.items())
                                            or "none given (--results reports/junit.xml target/surefire-reports)"))
        if self.missing_tests:
            lines.append(f"{'No test':<15} " + ", ".join(self.missing_tests) + ": run qa-agent generate")
        if self.orphan_tests:
            lines.append(f"{'No case':<15} " + ", ".join(self.orphan_tests))
        if self.below_floor:
            lines.append(f"{'Below floor':<15} " + ", ".join(self.below_floor))
        return "\n".join(lines)

    def apply_floor(self, minimum: float) -> None:
        """--min-coverage: criteria and operations coverage must reach it (response codes are reported only)."""
        for item in self.coverage:
            if item.name in FLOORED and not item.note and item.percent < minimum:
                self.below_floor.append(f"{item.name} {item.percent:.0f}% (floor {minimum:.0f}%)")

    def as_markdown(self) -> str:
        lines = [f"# Trace: {self.team}", "", "| Coverage | Covered | Missing |", "|---|---|---|"]
        for item in self.coverage:
            lines.append(f"| {item.name} | {item.note or f'{item.covered} of {item.total}'} | "
                         f"{', '.join(item.missing) or '-'} |")
        if self.not_tested:
            lines += ["", "Not tested, on purpose: " + "; ".join(self.not_tested)]
        lines += ["", "| Criterion | Case | Title | Review | Suite | Tests | Latest result |",
                  "|---|---|---|---|---|---|---|"]
        for row in self.rows:
            lines.append(f"| {row.criterion} | {row.case_id or '-'} | {row.title} | {row.review} | {row.suite} | "
                         f"{'<br>'.join(f'`{test}`' for test in row.tests) or '-'} | {row.result} |")
        return "\n".join(lines) + "\n"

    def write_excel(self, path: Path) -> None:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font
        book = Workbook()
        matrix = book.active
        matrix.title = "Trace"
        matrix.append(["Criterion", "Case", "Title", "Review", "Suite", "Tests", "Latest result"])
        for row in self.rows:
            matrix.append([row.criterion, row.case_id, row.title, row.review, row.suite, "\n".join(row.tests),
                           row.result])
        coverage = book.create_sheet("Coverage")
        coverage.append(["Coverage", "Covered", "Of", "Missing"])
        for item in self.coverage:
            coverage.append([item.name, item.covered, item.total, item.note or "\n".join(item.missing)])
        for sheet, widths in ((matrix, (11, 10, 44, 18, 12, 60, 14)), (coverage, (16, 9, 6, 70))):
            for index, width in enumerate(widths):
                sheet.column_dimensions[chr(65 + index)].width = width
            for cell in sheet[1]:
                cell.font = Font(bold=True)
            for line in sheet.iter_rows(min_row=2):
                for cell in line:
                    cell.alignment = Alignment(wrap_text=True, vertical="top")
        path.parent.mkdir(parents=True, exist_ok=True)
        book.save(path)


def build_trace(project: TeamProject, result_paths: Optional[list] = None) -> TraceReport:
    report = TraceReport(project.team)
    criteria = project.read_criteria()
    cases = sorted((case for path in project.case_files() for case in load_case_file(path).cases),
                   key=lambda case: natural_order(case.id))
    approved = [case for case in cases if case.is_approved]
    written = {framework: _written_tests(project, framework) for framework in project.frameworks}
    results = read_results(result_paths or [])
    report.results_read = results.counts
    outcomes = results.outcomes
    expected_names = set()
    tests_by_case = {}
    for case in approved:
        tests_by_case[case.id] = []
        for framework in project.frameworks:
            for name in RENDERERS[framework].test_names(case):
                expected_names.add(name)
                if name in written[framework]:
                    tests_by_case[case.id].append(f"{framework}: {written[framework][name]}")
                else:
                    report.missing_tests.append(f"{case.id} ({framework})")
    report.orphan_tests = sorted(f"{framework}: {label}" for framework in project.frameworks
                                 for name, label in written[framework].items() if name not in expected_names)
    report.rows = _rows(cases, criteria, tests_by_case, outcomes, project)
    report.coverage = [_criteria_coverage(criteria, cases)]
    api = _api(project)
    if api is None:
        report.coverage.append(Coverage("Operations", 0, 0, note="no api/api.yaml: qa-agent import api <file>"))
    else:
        report.coverage += _api_coverage(api, approved, project, report)
    with_tests = sum(1 for case in approved if not any(item.startswith(case.id + " ") for item in report.missing_tests))
    report.coverage.append(Coverage("Cases to tests", with_tests, len(approved),
                                    [item for item in report.missing_tests]))
    return report


def _written_tests(project: TeamProject, framework: str) -> dict:
    """Test name -> 'file::name', for every test in the framework's generated folder."""
    renderer = RENDERERS[framework]
    folder = project.root / renderer.output_dir
    found = {}
    for path in sorted(folder.glob("*.py" if framework == "pytest" else "*.java")) if folder.is_dir() else []:
        text = path.read_text(encoding="utf-8")
        if not text.startswith(renderer.header_mark):
            continue
        for name in TEST_NAME[framework].findall(text):        # data providers return Object[][], not void
            found[name] = f"{path.name}::{name}"
    return found


def _result(case: Case, project: TeamProject, outcomes: dict) -> str:
    """Per framework: 'pytest passed 3/3 · restassured not run'. A data-driven case has a run per row."""
    labels = []
    for framework in project.frameworks:
        seen = [outcome for name in RENDERERS[framework].test_names(case) for outcome in outcomes.get(name, [])]
        if not seen:
            label = "not run"
        elif "failed" in seen:
            label = f"failed {seen.count('failed')}/{len(seen)}"
        elif all(outcome == "skipped" for outcome in seen):
            label = "skipped"
        else:
            label = f"passed {seen.count('passed')}/{len(seen)}"
        labels.append(f"{framework} {label}" if len(project.frameworks) > 1 else label)
    return " · ".join(labels)


def _review_label(case: Case) -> str:
    if case.changed_after_approval:
        return "changed after approval"
    if case.needs_steps:
        return f"{case.review.status.replace('_', ' ')} (needs steps)"
    return case.review.status.replace("_", " ")


def _rows(cases: list, criteria: dict, tests_by_case: dict, outcomes: dict, project: TeamProject) -> list:
    found = []
    for criterion in list(criteria) + ["(no criterion)"]:
        linked = [case for case in cases if criterion in case.criteria
                  or (criterion == "(no criterion)" and not set(case.criteria) & set(criteria))]
        if not linked and criterion != "(no criterion)":
            found.append(TraceRow(criterion, "", "no case", "-", "-", [], "-"))
        for case in linked:
            tests = tests_by_case.get(case.id, [])
            result = _result(case, project, outcomes) if case.is_approved else "-"
            found.append(TraceRow(criterion, case.id, case.title, _review_label(case), case.suite, tests, result))
    return found


def _criteria_coverage(criteria: dict, cases: list) -> Coverage:
    if not criteria:
        return Coverage("Criteria", 0, 0, note="no acceptance-criteria.yaml")
    missing = []
    for criterion in criteria:
        linked = [case for case in cases if criterion in case.criteria]
        if any(case.is_approved for case in linked):
            continue
        if not linked:
            missing.append(f"{criterion} (no case)")
        else:
            missing.append(f"{criterion} (not approved: {', '.join(case.id for case in linked)})")
    return Coverage("Criteria", len(criteria) - len(missing), len(criteria), missing)


def _api(project: TeamProject) -> Optional[ApiModel]:
    if not project.api_model_path.is_file():
        return None
    try:
        return load_api_model(project.api_model_path)
    except ApiModelError:
        return None


def _api_coverage(api: ApiModel, approved: list, project: TeamProject, report: TraceReport) -> list:
    called: dict = {}          # (service, method, path) -> statuses expected by approved steps
    for case in approved:
        for step in case.steps:
            service = step.request.service or project.main_service
            operation = api.find(service, step.request.method, step.request.path)
            if operation is not None:
                called.setdefault((service, operation.method, operation.path), set()).update(
                    _statuses(step.expect.get("status"), case, project))
    operations, codes, services_with_401 = [], [], {}
    for service, service_operations in sorted(api.services.items()):
        for operation in service_operations:
            label = f"{operation.method} {operation.path}" + ("" if service == project.main_service else f" ({service})")
            if operation.not_tested:
                report.not_tested.append(f"{label}: {operation.not_tested}")
                continue
            statuses = called.get((service, operation.method, operation.path))
            operations.append((label, statuses is not None))
            for code in operation.responses:
                if code == 401:
                    services_with_401.setdefault(service, False)
                    services_with_401[service] |= 401 in (statuses or set())
                elif code != 422 or operation.method in TAKES_A_BODY:
                    codes.append((f"{label} {code}", code in (statuses or set())))
    for service, seen in services_with_401.items():
        codes.append((f"401 ({service}, any operation)", seen))
    return [_coverage("Operations", operations), _coverage("Response codes", codes)]


def _coverage(name: str, items: list) -> Coverage:
    return Coverage(name, sum(1 for _, seen in items if seen), len(items), [label for label, seen in items if not seen])


def _statuses(status, case: Case, project: TeamProject) -> set:
    """The status a step expects; for {{row.x}}, every value of column x in the case's data file."""
    if isinstance(status, int):
        return {status}
    match = re.match(r"^\{\{\s*row\.(\w+)\s*\}\}$", str(status or ""))
    if not match or not case.data_file:
        return set()
    try:
        values = [row.get(match.group(1)) for row in rows(project.root / case.data_file)]
    except DataFileError:
        return set()
    return {int(float(value)) for value in values if str(value).strip().replace(".0", "").isdigit()}
