"""One service's HTTP calls. Every request and response is recorded in the scenario context, and
the token is masked wherever a request is shown.

    api.post("/bookings", json={...})        -> ApiResponse
    api.without_auth().get("/bookings/X")    the same client with no token, for 401 tests
"""

import time
from typing import Any, Optional

import httpx

from api_test_framework.api_response import ApiRequest, ApiResponse
from api_test_framework.auth import NoAuth, TokenProvider
from api_test_framework.scenario_context import ScenarioContext

MASKED = "***"
SECRET_HEADERS = {"authorization", "x-api-key", "cookie"}


class ApiClient:
    def __init__(self, base_url: str, http: httpx.Client, auth: Optional[TokenProvider] = None,
                 context: Optional[ScenarioContext] = None, timeout_seconds: float = 10.0):
        self.base_url = base_url.rstrip("/")
        self._http, self._auth = http, auth or NoAuth()
        self.context = context if context is not None else ScenarioContext()
        self._timeout = timeout_seconds

    def get(self, path: str, params: Optional[dict] = None, headers: Optional[dict] = None) -> ApiResponse:
        return self.request("GET", path, params=params, headers=headers)

    def post(self, path: str, json: Any = None, params: Optional[dict] = None, headers: Optional[dict] = None) -> ApiResponse:
        return self.request("POST", path, json=json, params=params, headers=headers)

    def put(self, path: str, json: Any = None, headers: Optional[dict] = None) -> ApiResponse:
        return self.request("PUT", path, json=json, headers=headers)

    def patch(self, path: str, json: Any = None, headers: Optional[dict] = None) -> ApiResponse:
        return self.request("PATCH", path, json=json, headers=headers)

    def delete(self, path: str, headers: Optional[dict] = None) -> ApiResponse:
        return self.request("DELETE", path, headers=headers)

    def without_auth(self) -> "ApiClient":
        return ApiClient(self.base_url, self._http, NoAuth(), self.context, self._timeout)

    def request(self, method: str, path: str, json: Any = None, params: Optional[dict] = None,
                headers: Optional[dict] = None) -> ApiResponse:
        url = self.base_url + "/" + path.lstrip("/")
        all_headers = {**self._auth.headers(), **(headers or {})}
        started = time.perf_counter()
        raw = self._http.request(method, url, json=json, params=params, headers=all_headers, timeout=self._timeout)
        elapsed = int((time.perf_counter() - started) * 1000)
        request = ApiRequest(method, str(raw.request.url), json, _masked(all_headers))
        response = ApiResponse(raw.status_code, raw.text, dict(raw.headers), elapsed, request)
        self.context.record(response)
        return response


def _masked(headers: dict) -> dict:
    return {name: (MASKED if name.lower() in SECRET_HEADERS else value) for name, value in headers.items()}
