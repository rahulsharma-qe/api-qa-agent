"""The pytest side of the framework, switched on when the package is installed.

    pytest --env qa2                      the environment (or API_ENV=qa2); default: demo
    pytest --api-config path.yaml         the environments file (or API_CONFIG); default: config/environments.yaml
    pytest -m regression                  only regression tests (or -m smoke)
    pytest -m p0                          only the P0 tests: a test with priority("P0") is also marked p0
    pytest --evidence reports/evidence    every test's requests and responses, pass or fail, one file each
    pytest --reruns 1                     retry a failure once; a pass on retry is listed separately
    pytest --alluredir reports/allure-results   the Allure report (allure generate reports/allure-results)

Fixtures:  environment · api (the default service) · api_for("notifications") · context
Markers:   smoke · regression · functional · writes (skipped on a read-only environment) · case("TC003")
           · priority("P0") (P0 to P3)
On a failure, the report shows every request and response of the test, in order.
"""

import os
from pathlib import Path
from typing import Optional

import httpx
import pytest

from api_test_framework.api_client import ApiClient
from api_test_framework.auth import token_provider_for
from api_test_framework.environment import DEFAULT_ENVIRONMENT, ConfigError, EnvironmentConfig, load_environment
from api_test_framework.reporting import (PRIORITIES, allure_is_on, attach_step_to_allure, label_allure_test,
                                         write_evidence)
from api_test_framework.scenario_context import ScenarioContext

DEFAULT_CONFIG = "config/environments.yaml"
SETUP_PROBLEM_EXIT_CODE = 2
MARKERS = {
    "smoke": "the few checks that say the service is up and usable",
    "regression": "runs on every build",
    "functional": "new behaviour; runs on demand until promoted to regression",
    "writes": "changes data: skipped on an environment marked read_only",
    "case(case_id)": "the test case this test was generated from; written into the JUnit report",
    "priority(level)": "P0 (highest) to P3; written into the JUnit report, and the severity in Allure",
    **{level.lower(): f"priority {level}: added from priority(\"{level}\"), so -m {level.lower()} picks them"
       for level in PRIORITIES},
}
ENVIRONMENT_KEY = pytest.StashKey[EnvironmentConfig]()
CONTEXT_KEY = pytest.StashKey[ScenarioContext]()
PASSED_ON_RETRY_KEY = pytest.StashKey[list]()


def pytest_addoption(parser):
    group = parser.getgroup("api_test_framework", "API tests")
    group.addoption("--env", default=None, help="environment name in environments.yaml (default: API_ENV, else demo)")
    group.addoption("--api-config", default=None,
                    help=f"environments file (default: API_CONFIG, else {DEFAULT_CONFIG} under the test root)")
    group.addoption("--evidence", default=None, metavar="FOLDER",
                    help="write every test's requests and responses, pass or fail, one file per test")


def pytest_configure(config):
    for marker, description in MARKERS.items():
        config.addinivalue_line("markers", f"{marker}: {description}")
    config.stash[PASSED_ON_RETRY_KEY] = []


@pytest.hookimpl(tryfirst=True)              # before -m deselects, so -m p0 sees the p0 marker
def pytest_collection_modifyitems(config, items):
    for item in items:
        level = _priority(item)    # a wrong priority stops the run before anything is sent
        if level and not item.get_closest_marker(level.lower()):
            item.add_marker(level.lower())
    writing = [item for item in items if item.get_closest_marker("writes")]
    environment = _environment(config) if writing else None
    if environment is not None and environment.read_only:
        skip = pytest.mark.skip(reason=f"changes data; environment '{environment.name}' is read-only")
        for item in writing:
            item.add_marker(skip)


def pytest_runtest_setup(item):
    case_id, priority = _case_id(item), _priority(item)
    if case_id and ("case_id", case_id) not in item.user_properties:
        item.user_properties.append(("case_id", case_id))
    if priority and ("priority", priority) not in item.user_properties:
        item.user_properties.append(("priority", priority))


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):
    if allure_is_on(item.config):
        label_allure_test(_case_id(item), _priority(item))
    yield


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    context = item.stash.get(CONTEXT_KEY, None)
    if report.when == "call" and report.failed and context is not None and context.steps:
        report.sections.append(("API steps, in order", context.history()))
    attempt = getattr(item, "execution_count", 1)          # set by pytest-rerunfailures
    if report.when == "call" and report.passed and attempt > 1:
        item.user_properties.append(("passed_on_retry", "true"))      # the JUnit report reads them at teardown
        item.config.stash[PASSED_ON_RETRY_KEY].append(item.nodeid)
    folder = item.config.getoption("--evidence")
    if folder and (report.when == "call" or (report.when == "setup" and not report.passed)):
        outcome = "passed on retry" if report.passed and attempt > 1 else report.outcome
        write_evidence(folder, item.nodeid, outcome, _case_id(item), attempt, context,
                       report.longreprtext if report.failed else "")


def pytest_sessionfinish(session, exitstatus):
    """Allure's 'Environment' panel: which environment and which hosts this run used."""
    config = session.config
    environment = _environment(config) if allure_is_on(config) else None
    if environment is not None:
        lines = [f"Environment={environment.name}", f"Read-only={str(environment.read_only).lower()}"]
        lines += [f"{service}={url}" for service, url in sorted(environment.services.items())]
        folder = Path(config.option.allure_report_dir)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "environment.properties").write_text("\n".join(lines) + "\n", encoding="utf-8")


def pytest_terminal_summary(terminalreporter, config):
    passed_on_retry = config.stash.get(PASSED_ON_RETRY_KEY, [])
    if passed_on_retry:
        terminalreporter.section("Passed on retry: look at these, they may be flaky")
        for nodeid in passed_on_retry:
            terminalreporter.line(f"  {nodeid}")


@pytest.fixture(scope="session")
def environment(pytestconfig) -> EnvironmentConfig:
    try:
        return _load(pytestconfig)
    except ConfigError as error:
        pytest.exit(f"SETUP PROBLEM: {error}", returncode=SETUP_PROBLEM_EXIT_CODE)


@pytest.fixture(scope="session")
def http_session():
    with httpx.Client() as client:
        yield client


@pytest.fixture(scope="session")
def token_provider(environment, http_session):
    try:
        return token_provider_for(environment, http_session)
    except ConfigError as error:
        pytest.exit(f"SETUP PROBLEM: {error}", returncode=SETUP_PROBLEM_EXIT_CODE)


@pytest.fixture
def context(request) -> ScenarioContext:
    scenario = ScenarioContext(on_step=attach_step_to_allure if allure_is_on(request.config) else None)
    request.node.stash[CONTEXT_KEY] = scenario
    return scenario


@pytest.fixture
def api(environment, http_session, token_provider, context) -> ApiClient:
    return ApiClient(environment.base_url(), http_session, token_provider, context, environment.timeout_seconds)


@pytest.fixture
def api_for(environment, http_session, token_provider, context):
    def client_for(service: str) -> ApiClient:
        return ApiClient(environment.base_url(service), http_session, token_provider, context,
                         environment.timeout_seconds)
    return client_for


def _case_id(item) -> Optional[str]:
    marker = item.get_closest_marker("case")
    return str(marker.args[0]) if marker and marker.args else None


def _priority(item) -> Optional[str]:
    marker = item.get_closest_marker("priority")
    if not marker or not marker.args:
        return None
    level = str(marker.args[0]).upper()
    if level not in PRIORITIES:
        raise pytest.UsageError(f"{item.nodeid}: priority must be one of {', '.join(PRIORITIES)}, not '{marker.args[0]}'")
    return level


def _environment(config) -> Optional[EnvironmentConfig]:
    try:
        return _load(config)
    except ConfigError:
        return None          # reported by the environment fixture when a test needs it


def _load(config) -> EnvironmentConfig:
    if ENVIRONMENT_KEY not in config.stash:
        name = config.getoption("--env") or os.getenv("API_ENV") or DEFAULT_ENVIRONMENT
        path = config.getoption("--api-config") or os.getenv("API_CONFIG") or Path(config.rootpath) / DEFAULT_CONFIG
        config.stash[ENVIRONMENT_KEY] = load_environment(path, name)
    return config.stash[ENVIRONMENT_KEY]
