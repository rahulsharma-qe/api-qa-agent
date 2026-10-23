"""One environment from environments.yaml: where each service lives, how to authenticate, and
whether tests may change data there.

    environments:
      demo:
        default_service: bookings
        services: {bookings: "http://localhost:8000", notifications: "http://localhost:8001"}
        auth: {type: client_credentials, service: bookings, token_path: /auth/token,
               client_id: demo-client, client_secret: demo-secret}     # plain values: demo only
        timeout_seconds: 10
        read_only: false
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

DEFAULT_ENVIRONMENT = "demo"
DEFAULT_TIMEOUT_SECONDS = 10.0


class ConfigError(Exception):
    """environments.yaml is missing, malformed, or doesn't have what a test asked for."""


@dataclass(frozen=True)
class EnvironmentConfig:
    name: str
    services: dict
    default_service: str
    auth: dict = field(default_factory=dict)
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS
    read_only: bool = False
    data_dir: Optional[str] = None

    def base_url(self, service: Optional[str] = None) -> str:
        service = service or self.default_service
        if service not in self.services:
            raise ConfigError(f"environment '{self.name}' has no service '{service}' "
                              f"(it has: {', '.join(sorted(self.services))})")
        return str(self.services[service]).rstrip("/")


def load_environment(path, name: str = DEFAULT_ENVIRONMENT) -> EnvironmentConfig:
    path = Path(path)
    if not path.is_file():
        raise ConfigError(f"environments file not found: {path}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as error:
        raise ConfigError(f"{path}: not valid YAML ({error})") from error
    environments = data.get("environments") or {}
    if name not in environments:
        raise ConfigError(f"unknown environment '{name}' in {path} (known: {', '.join(sorted(environments)) or 'none'})")
    settings = environments[name] or {}
    services = settings.get("services") or {}
    if not services:
        raise ConfigError(f"environment '{name}' lists no services")
    default_service = settings.get("default_service") or next(iter(services))
    if default_service not in services:
        raise ConfigError(f"environment '{name}': default_service '{default_service}' is not one of its services")
    return EnvironmentConfig(name=name, services=dict(services), default_service=default_service,
                             auth=dict(settings.get("auth") or {}),
                             timeout_seconds=float(settings.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS)),
                             read_only=bool(settings.get("read_only", False)), data_dir=settings.get("data_dir"))
