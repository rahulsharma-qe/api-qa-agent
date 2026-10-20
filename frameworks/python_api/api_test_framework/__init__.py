"""api_test_framework: plain API tests on pytest and httpx.

    from api_test_framework import Expect, new_passenger

    def test_get_booking(api, context):
        created = api.post("/bookings", json={**new_passenger(), "amount": 250})
        Expect(created).status_is(201)

Fixtures (`api`, `api_for`, `context`, `environment`), the `--env` option and the markers come from
the pytest plugin, which is switched on when the package is installed.
"""

from api_test_framework.api_client import ApiClient
from api_test_framework.api_response import ApiResponse, FieldNotFound
from api_test_framework.auth import ClientCredentials, NoAuth, StaticToken, TokenProvider, token_provider_for
from api_test_framework.environment import ConfigError, EnvironmentConfig, load_environment
from api_test_framework.expect import Expect, ExpectationFailed
from api_test_framework.scenario_context import ScenarioContext, Step
from api_test_framework.test_data import load_rows, new_passenger, unique_id

__version__ = "0.1.0"

__all__ = ["ApiClient", "ApiResponse", "ClientCredentials", "ConfigError", "EnvironmentConfig", "Expect",
           "ExpectationFailed", "FieldNotFound", "NoAuth", "ScenarioContext", "StaticToken", "Step", "TokenProvider",
           "load_environment", "load_rows", "new_passenger", "token_provider_for", "unique_id"]
