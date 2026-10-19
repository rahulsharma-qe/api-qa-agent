"""Check each dependency with a safe GET, retrying a failed attempt, and decide: ready or not."""

import time
from dataclasses import dataclass, field
from typing import Callable, Optional

import httpx

from env_check.settings import Dependency, ReadinessSettings, load_settings

EXIT_READY, EXIT_SETUP_PROBLEM, EXIT_NOT_READY = 0, 2, 3


@dataclass
class CheckResult:
    dependency: Dependency
    ok: bool
    status_code: Optional[int] = None
    elapsed_ms: Optional[int] = None
    error: str = ""
    attempts: int = 1

    def as_dict(self) -> dict:
        return {"service": self.dependency.service, "url": self.dependency.url, "critical": self.dependency.critical,
                "ok": self.ok, "status_code": self.status_code, "elapsed_ms": self.elapsed_ms,
                "error": self.error, "attempts": self.attempts}


@dataclass
class ReadinessReport:
    environment: str
    team: str
    results: list = field(default_factory=list)    # [CheckResult]

    @property
    def ready(self) -> bool:
        return all(result.ok for result in self.results if result.dependency.critical)

    @property
    def exit_code(self) -> int:
        return EXIT_READY if self.ready else EXIT_NOT_READY

    def as_dict(self) -> dict:
        return {"environment": self.environment, "team": self.team, "ready": self.ready,
                "results": [result.as_dict() for result in self.results]}

    def as_text(self) -> str:
        lines = [f"{self.environment}" + (f" · {self.team}" if self.team else "")]
        for result in self.results:
            status = str(result.status_code) if result.status_code is not None else "-"
            took = f"{result.elapsed_ms} ms" if result.elapsed_ms is not None else "-"
            if result.ok:
                verdict = "ok"
            elif result.dependency.critical:
                verdict = f"DOWN ({result.error})"
            else:
                verdict = f"DOWN, not critical: tests still run ({result.error})"
            lines.append(f"  {result.dependency.service:<16}{status:<6}{took:<10}{verdict}")
        down = [r.dependency.service for r in self.results if not r.ok and r.dependency.critical]
        lines.append(f"READY (exit {EXIT_READY})" if self.ready
                     else f"NOT READY (exit {EXIT_NOT_READY}): {', '.join(down)} down. An environment problem, not a test failure.")
        return "\n".join(lines)


def check_environment(environment: str, environments_path, dependencies_path, http: Optional[httpx.Client] = None,
                      sleep: Callable[[float], None] = time.sleep) -> ReadinessReport:
    settings = load_settings(environment, environments_path, dependencies_path)
    return check_dependencies(settings, http=http, sleep=sleep)


def check_dependencies(settings: ReadinessSettings, http: Optional[httpx.Client] = None,
                       sleep: Callable[[float], None] = time.sleep) -> ReadinessReport:
    client = http or httpx.Client()
    try:
        results = [_check(client, dependency, settings, sleep) for dependency in settings.dependencies]
    finally:
        if http is None:
            client.close()
    return ReadinessReport(settings.environment, settings.team, results)


def _check(client: httpx.Client, dependency: Dependency, settings: ReadinessSettings, sleep) -> CheckResult:
    wait = settings.wait_seconds
    result = None
    for attempt in range(1, settings.attempts + 1):
        result = _attempt(client, dependency)
        result.attempts = attempt
        if result.ok:
            return result
        if attempt < settings.attempts:
            sleep(wait)
            wait *= 2
    return result


def _attempt(client: httpx.Client, dependency: Dependency) -> CheckResult:
    started = time.perf_counter()
    try:
        response = client.get(dependency.url, timeout=dependency.timeout_seconds)    # GET only: never changes data
    except httpx.TimeoutException:
        return CheckResult(dependency, False, error=f"no answer within {dependency.timeout_seconds:g} s")
    except httpx.HTTPError as error:
        return CheckResult(dependency, False, error=f"cannot connect: {type(error).__name__}")
    elapsed = int((time.perf_counter() - started) * 1000)
    ok = response.status_code == dependency.expect_status
    error = "" if ok else f"expected {dependency.expect_status}, got {response.status_code}"
    return CheckResult(dependency, ok, response.status_code, elapsed, error)
