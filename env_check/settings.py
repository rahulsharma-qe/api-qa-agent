"""Read environments.yaml (where each service lives) and dependencies.yaml (what a team needs).

Only the parts env_check uses are read here: the service addresses. The test frameworks read the
same environments.yaml for everything else (authentication, timeouts, read-only)."""

from dataclasses import dataclass, field
from pathlib import Path

import yaml

DEFAULT_PATH = "/health-check"


class SetupError(Exception):
    """A file or a setting is wrong. Reported with exit code 2, never as 'not ready'."""


@dataclass(frozen=True)
class Dependency:
    service: str
    url: str
    critical: bool = True
    expect_status: int = 200
    timeout_seconds: float = 5.0


@dataclass(frozen=True)
class ReadinessSettings:
    environment: str
    team: str
    dependencies: list = field(default_factory=list)   # [Dependency]
    attempts: int = 3
    wait_seconds: float = 2.0


def load_settings(environment: str, environments_path, dependencies_path) -> ReadinessSettings:
    services = _services(environment, _read_yaml(environments_path))
    plan = _read_yaml(dependencies_path)
    checks = plan.get("checks")
    if not isinstance(checks, list) or not checks:
        raise SetupError(f"{dependencies_path}: 'checks' must list at least one service")
    dependencies = [_dependency(check, services, environment, dependencies_path) for check in checks]
    attempts, wait = plan.get("attempts", 3), plan.get("wait_seconds", 2.0)
    if not isinstance(attempts, int) or attempts < 1:
        raise SetupError(f"{dependencies_path}: 'attempts' must be a whole number, 1 or more")
    return ReadinessSettings(environment, str(plan.get("team", "")), dependencies, attempts, float(wait))


def _read_yaml(path) -> dict:
    path = Path(path)
    if not path.is_file():
        raise SetupError(f"file not found: {path}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as error:
        raise SetupError(f"{path}: not valid YAML ({error})") from error
    if not isinstance(data, dict):
        raise SetupError(f"{path}: expected a mapping at the top")
    return data


def _services(environment: str, data: dict) -> dict:
    environments = data.get("environments") or {}
    if environment not in environments:
        known = ", ".join(sorted(environments)) or "none"
        raise SetupError(f"unknown environment '{environment}' (known: {known})")
    services = (environments[environment] or {}).get("services") or {}
    if not services:
        raise SetupError(f"environment '{environment}' lists no services")
    return services


def _dependency(check, services: dict, environment: str, source) -> Dependency:
    if not isinstance(check, dict) or "service" not in check:
        raise SetupError(f"{source}: every check needs a 'service'")
    name = check["service"]
    if name not in services:
        raise SetupError(f"{source}: service '{name}' is not in environment '{environment}'")
    unknown = set(check) - {"service", "path", "critical", "expect_status", "timeout_seconds"}
    if unknown:
        raise SetupError(f"{source}: unknown setting(s) for '{name}': {', '.join(sorted(unknown))}")
    url = str(services[name]).rstrip("/") + "/" + str(check.get("path", DEFAULT_PATH)).lstrip("/")
    return Dependency(service=name, url=url, critical=bool(check.get("critical", True)),
                      expect_status=int(check.get("expect_status", 200)),
                      timeout_seconds=float(check.get("timeout_seconds", 5.0)))
