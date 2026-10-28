"""`qa-agent init`: a team's project that works on day one, in the framework the team chose.

    qa-agent init bookings-team --framework pytest        (or --framework restassured)

It writes the project's files from qa_agent/project_templates (common, then the framework's own), an
empty Excel sheet in the API layout, and one starter case. The starter case is approved by
'qa-agent init', said so in its review, so the first run has a test; the team replaces it with its
own cases. Then it runs generate.
"""

import datetime
import re
import stat
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path

from jinja2 import Environment, StrictUndefined

from qa_agent import __version__
from qa_agent.cases import load_case_file, save_case_file
from qa_agent.generate import generate
from qa_agent.project import FRAMEWORKS, SetupError, TeamProject

API_LAYOUT = ["Case ID", "Title", "Criteria", "Priority", "Tags", "Step", "Method", "Path", "Body",
              "Expected Status", "Expected Fields", "Capture"]
HOW_TO_FILL = [
    "How to fill the API layout (one row per step)",
    "",
    "Case ID: on a case's first row only; later rows of the same case leave it empty.",
    "Method and Path: GET /bookings/{{pnr}}. {{pnr}} is a value captured in an earlier step.",
    'Body: JSON, for example {"passenger_name": "Asha {{unique}}", "amount": 250}. {{unique}} is new in each test.',
    "Expected Status: 201. Expected Fields: status=active; amount=250.",
    "Capture: pnr=pnr (a name = a path in the response).",
    "Criteria: AC-1, AC-2. Priority: P0 to P3 (or Critical, High, Medium, Low). Tags: smoke, crud.",
    "",
    "Then: qa-agent import cases existing/api_cases_template.xlsx",
]
STARTER_REVIEW = "The starter case, approved by qa-agent init so the project runs on day one"


@dataclass
class InitResult:
    root: Path
    files: list = field(default_factory=list)

    def as_text(self, framework: str) -> str:
        test_folder = "tests/generated" if framework == "pytest" else "src/test/java/generated"
        run = "pytest" if framework == "pytest" else "./mvnw test"
        return "\n".join([f"created {self.root}: {len(self.files)} files, one starter case and its test in "
                          f"{test_folder}", "", "Next:", f"  cd {self.root}",
                          "  python -m demo_api &              # the reference API",
                          "  python -m env_check --env demo",
                          f"  {run}", "", "Then bring your own API and cases: see README.md"])


def init_project(root: Path, framework: str, team: str = "", service: str = "bookings") -> InitResult:
    if framework not in FRAMEWORKS:
        raise SetupError(f"unknown framework '{framework}' (use {' or '.join(FRAMEWORKS)})")
    root = Path(root)
    if root.exists() and any(root.iterdir()):
        raise SetupError(f"{root} is not empty: qa-agent init makes a new project in an empty folder")
    team = team or root.resolve().name
    artifact = re.sub(r"[^a-z0-9]+", "-", team.lower()).strip("-") or "team"
    values = {"team": team, "service": service, "framework": framework, "artifact": artifact, "release": f"v{__version__}",
              "package": artifact.replace("-", "")}
    result = InitResult(root)
    for part in ("common", framework):
        _copy(resources.files("qa_agent") / "project_templates" / part, root, values, result)
    _api_layout_sheet(root / "existing" / "api_cases_template.xlsx")
    result.files.append("existing/api_cases_template.xlsx")
    _approve_starter(root / "cases" / "bookings.yaml")
    generate(TeamProject.load(root))
    return result


def _copy(source, target: Path, values: dict, result: InitResult, relative: str = "") -> None:
    templates = Environment(undefined=StrictUndefined, keep_trailing_newline=True, trim_blocks=True,
                            lstrip_blocks=True)
    for item in sorted(source.iterdir(), key=lambda entry: entry.name):
        name = item.name.replace("dot-", ".", 1) if item.name.startswith("dot-") else item.name
        name = ".gitignore" if name == "gitignore" else name
        if item.is_dir():
            _copy(item, target, values, result, f"{relative}{name}/")
            continue
        if item.name == "__init__.py" or item.name.endswith(".pyc"):
            continue
        destination = target / relative / name.removesuffix(".j2")
        destination.parent.mkdir(parents=True, exist_ok=True)
        if item.name.endswith(".j2"):
            destination.write_text(templates.from_string(item.read_text(encoding="utf-8")).render(**values),
                                   encoding="utf-8")
        else:
            destination.write_bytes(item.read_bytes())
        if destination.name == "mvnw":
            destination.chmod(destination.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        result.files.append(f"{relative}{destination.name}")


def _api_layout_sheet(path: Path) -> None:
    from openpyxl import Workbook
    from openpyxl.styles import Font
    book = Workbook()
    sheet = book.active
    sheet.title = "Bookings"
    sheet.append(API_LAYOUT)
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    for letter, width in zip("ABCDEFGHIJKL", (10, 36, 10, 9, 12, 6, 8, 26, 60, 10, 30, 14)):
        sheet.column_dimensions[letter].width = width
    guide = book.create_sheet("How to fill")
    for line in HOW_TO_FILL:
        guide.append([line])
    guide["A1"].font = Font(bold=True, size=13)
    guide.column_dimensions["A"].width = 110
    path.parent.mkdir(parents=True, exist_ok=True)
    book.save(path)


def _approve_starter(path: Path) -> None:
    case_file = load_case_file(path)
    for case in case_file.cases:
        case.review.status, case.review.by = "approved", "qa-agent init"
        case.review.date, case.review.comment = datetime.date.today().isoformat(), STARTER_REVIEW
        case.review.fingerprint = case.fingerprint()
    save_case_file(case_file)
