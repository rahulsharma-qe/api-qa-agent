"""A team's project: where each of its files lives. Every command starts here.

    qa-agent.yaml       team: bookings · service: bookings · stacks: [python] · case_id_prefix: TC (optional)
    api/api.yaml        the API model          criteria.yaml   the acceptance criteria
    cases/*.yaml        the cases, one file per feature
"""

from dataclasses import dataclass
from pathlib import Path

from qa_agent.yaml_files import FileFormatError, read_yaml

CONFIG_FILE = "qa-agent.yaml"
STACKS = ("python", "restassured")


class SetupError(Exception):
    """The project can't be read: a missing or malformed qa-agent.yaml or criteria.yaml."""


@dataclass(frozen=True)
class Criterion:
    id: str
    text: str


@dataclass(frozen=True)
class TeamProject:
    root: Path
    team: str
    main_service: str
    stacks: tuple[str, ...]
    case_id_prefix: str = "TC"          # an imported case with no id gets the next free one: TC042

    @classmethod
    def load(cls, root: Path) -> "TeamProject":
        config_path = Path(root) / CONFIG_FILE
        if not config_path.is_file():
            raise SetupError(f"no {CONFIG_FILE} in {Path(root).resolve()}: run qa-agent in a team's project "
                             f"(or pass --project), or create one with qa-agent init")
        config = _read(config_path)
        problems = [f"'{key}' is missing" for key in ("team", "service", "stacks") if not config.get(key)]
        stacks = config.get("stacks") or []
        if isinstance(stacks, str):
            stacks = [stacks]
        problems += [f"unknown stack '{stack}' (use {' or '.join(STACKS)})" for stack in stacks if stack not in STACKS]
        if problems:
            raise SetupError(f"{config_path}: " + "; ".join(problems))
        return cls(Path(root), str(config["team"]), str(config["service"]), tuple(stacks),
                   str(config.get("case_id_prefix") or "TC"))

    @property
    def api_model_path(self) -> Path:
        return self.root / "api" / "api.yaml"

    @property
    def criteria_path(self) -> Path:
        return self.root / "criteria.yaml"

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

    def read_criteria(self) -> dict[str, Criterion]:
        """Every criterion by id. Empty when the project has no criteria.yaml."""
        if not self.criteria_path.is_file():
            return {}
        data = _read(self.criteria_path) or {}
        entries = data.get("criteria") if isinstance(data, dict) else None
        if not isinstance(entries, list) or not all(isinstance(entry, dict) and entry.get("id") for entry in entries):
            raise SetupError(f"{self.criteria_path}: expected 'criteria:' with a list of {{id, text}}")
        return {str(entry["id"]): Criterion(str(entry["id"]), str(entry.get("text", ""))) for entry in entries}


def _read(path: Path):
    try:
        return read_yaml(path)
    except FileFormatError as error:
        raise SetupError(str(error)) from error
