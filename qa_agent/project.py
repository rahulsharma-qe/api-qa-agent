"""A team's project: where each of its files lives. Every command starts here.

    qa-agent.yaml               team: bookings · service: bookings · frameworks: [pytest] · case_id_prefix: TC (optional)
    api/api.yaml                the API model
    acceptance-criteria.yaml    the acceptance criteria a person wrote (approved by being written)
    acceptance-criteria-drafts.yaml   criteria and questions drafted from a requirement (qa-agent draft
                                criteria), each approved by a person in the review sheet before it counts
    cases/*.yaml                the cases, one file per feature
"""

from dataclasses import dataclass, field
from pathlib import Path

from qa_agent.cases import PRIORITIES
from qa_agent.yaml_files import FileFormatError, read_yaml

CONFIG_FILE = "qa-agent.yaml"
CRITERIA_DRAFTS_FILE = "acceptance-criteria-drafts.yaml"
CRITERION_STATUSES = ("draft", "approved", "changes_needed", "rejected")
FRAMEWORKS = ("pytest", "restassured")


class SetupError(Exception):
    """The project can't be read: a missing or malformed qa-agent.yaml or acceptance-criteria.yaml."""


@dataclass(frozen=True)
class Criterion:
    id: str
    text: str
    status: str = "approved"            # a person's own criteria are approved; drafted ones start as draft
    source: dict = field(default_factory=dict, compare=False, hash=False)    # where a drafted one came from

    @property
    def is_approved(self) -> bool:
        return self.status == "approved"


@dataclass(frozen=True)
class TeamProject:
    root: Path
    team: str
    main_service: str
    frameworks: tuple[str, ...]
    case_id_prefix: str = "TC"          # an imported case with no id gets the next free one: TC042
    ai: dict = field(default_factory=dict, compare=False, hash=False)   # the AI layer's settings (qa_agent/ai)
    regression_priorities: tuple = ()   # what promote moves to regression by default; empty: every priority

    @classmethod
    def load(cls, root: Path) -> "TeamProject":
        config_path = Path(root) / CONFIG_FILE
        if not config_path.is_file():
            raise SetupError(f"no {CONFIG_FILE} in {Path(root).resolve()}: run qa-agent in a team's project "
                             f"(or pass --project), or create one with qa-agent init")
        config = _read(config_path)
        problems = [f"'{key}' is missing" for key in ("team", "service", "frameworks") if not config.get(key)]
        frameworks = config.get("frameworks") or []
        if isinstance(frameworks, str):
            frameworks = [frameworks]
        problems += [f"unknown framework '{framework}' (use {' or '.join(FRAMEWORKS)})" for framework in frameworks if framework not in FRAMEWORKS]
        if problems:
            raise SetupError(f"{config_path}: " + "; ".join(problems))
        ai = config.get("ai") or {}
        if not isinstance(ai, dict):
            raise SetupError(f"{config_path}: 'ai' should be a mapping (provider, model or recorded)")
        return cls(Path(root), str(config["team"]), str(config["service"]), tuple(frameworks),
                   str(config.get("case_id_prefix") or "TC"), dict(ai), _regression_priorities(config, config_path))

    @property
    def api_model_path(self) -> Path:
        return self.root / "api" / "api.yaml"

    @property
    def criteria_path(self) -> Path:
        return self.root / "acceptance-criteria.yaml"

    @property
    def cases_dir(self) -> Path:
        return self.root / "cases"

    def case_files(self) -> list[Path]:
        return sorted(self.cases_dir.glob("*.yaml")) if self.cases_dir.is_dir() else []

    def relative(self, path: Path) -> str:
        """A path as people see it in the project: cases/cancellation.yaml."""
        try:
            return Path(path).resolve().relative_to(self.root.resolve()).as_posix()
        except ValueError:
            return str(path)

    @property
    def criteria_drafts_path(self) -> Path:
        return self.root / CRITERIA_DRAFTS_FILE

    def has_criteria(self) -> bool:
        return self.criteria_path.is_file() or self.criteria_drafts_path.is_file()

    def read_criteria(self) -> dict[str, Criterion]:
        """The approved criteria by id: what coverage, gaps and drafting count. Empty with no criteria files."""
        return {key: criterion for key, criterion in self.read_all_criteria().items() if criterion.is_approved}

    def read_all_criteria(self) -> dict[str, Criterion]:
        """Every criterion by id, drafts included: a person's file first, then the drafted ones."""
        found: dict[str, Criterion] = {}
        for path, drafted in ((self.criteria_path, False), (self.criteria_drafts_path, True)):
            if not path.is_file():
                continue
            data = _read(path) or {}
            entries = data.get("criteria", []) if isinstance(data, dict) else None
            if not isinstance(entries, list) or not all(isinstance(entry, dict) and entry.get("id") for entry in entries):
                raise SetupError(f"{path}: expected 'criteria:' with a list of {{id, text}}")
            for entry in entries:
                key = str(entry["id"])
                if key in found:
                    raise SetupError(f"{path}: criterion {key} is also in {self.relative(self.criteria_path)}")
                status = str(entry.get("status") or ("draft" if drafted else "approved"))
                if status not in CRITERION_STATUSES:
                    raise SetupError(f"{path}: {key}: status '{status}' (use {', '.join(CRITERION_STATUSES)})")
                source = entry.get("source") if isinstance(entry.get("source"), dict) else {}
                found[key] = Criterion(key, str(entry.get("text", "")), status, source)
        return found


def _read(path: Path):
    try:
        return read_yaml(path)
    except FileFormatError as error:
        raise SetupError(str(error)) from error


def _regression_priorities(config: dict, config_path: Path) -> tuple:
    """regression: {priorities: [P0, P1]}: the priorities promote moves by default."""
    regression = config.get("regression") or {}
    priorities = regression.get("priorities") if isinstance(regression, dict) else None
    if regression and (not isinstance(priorities, list) or not priorities
                       or any(str(item) not in PRIORITIES for item in priorities)):
        raise SetupError(f"{config_path}: regression: priorities should be a list of {', '.join(PRIORITIES)}, "
                         "e.g. regression: {priorities: [P0, P1]}")
    return tuple(str(item) for item in priorities or ())

