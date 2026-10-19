"""The pytest side of the framework, switched on when the package is installed.

    pytest --env qa2                      the environment (or API_ENV=qa2); default: mock
    pytest --api-config path.yaml         the environments file (or API_CONFIG); default: config/environments.yaml
    pytest -m regression                  only regression tests

Fixtures:  environment · api (the default service) · api_for("notifications") · context
Markers:   regression · functional · writes (skipped on a read-only environment) · case("TC003")
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
from api_test_framework.scenario_context import ScenarioContext

DEFAULT_CONFIG = "config/environments.yaml"
SETUP_PROBLEM_EXIT_CODE = 2
MARKERS = {
    "regression": "runs on every build",
    "functional": "new behaviour; runs on demand until promoted to regression",
    "writes": "changes data: skipped on an environment marked read_only",
    "case(case_id)": "the test case this test was generated from; written into the JUnit report",
}
ENVIRONMENT_KEY = pytest.StashKey[EnvironmentConfig]()
CONTEXT_KEY = pytest.StashKey[ScenarioContext]()


def pytest_addoption(parser):
    group = parser.getgroup("api_test_framework", "API tests")
    group.addoption("--env", default=None, help="environment name in environments.yaml (default: API_ENV, else mock)")
    group.addoption("--api-config", default=None,
                    help=f"environments file (default: API_CONFIG, else {DEFAULT_CONFIG} under the test root)")


def pytest_configure(config):
    for marker, description in MARKERS.items():
        config.addinivalue_line("markers", f"{marker}: {description}")


def pytest_collection_modifyitems(config, items):
    writing = [item for item in items if item.get_closest_marker("writes")]
    environment = _environment(config) if writing else None
    if environment is not None and environment.read_only:
        skip = pytest.mark.skip(reason=f"changes data; environment '{environment.name}' is read-only")
        for item in writing:
            item.add_marker(skip)


def pytest_runtest_setup(item):
    case = item.get_closest_marker("case")
    if case and case.args:
        item.user_properties.append(("case_id", str(case.args[0])))


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    context = item.stash.get(CONTEXT_KEY, None)
    if report.when == "call" and report.failed and context is not None and context.steps:
        report.sections.append(("API steps, in order", context.history()))


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
    scenario = ScenarioContext()
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
