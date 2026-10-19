"""Where the Authorization header comes from. Chosen by the environment's `auth.type`:

    none                 no header
    static_token         a token from an environment variable:   {type: static_token, token_env: STAGING_TOKEN}
    client_credentials   asked from a token endpoint once per run: {type: client_credentials, service: bookings,
                         token_path: /auth/token, client_id_env: QA1_CLIENT_ID, client_secret_env: QA1_CLIENT_SECRET}
                         (client_id / client_secret as plain values are for a mock only)
"""

import os
from typing import Optional

import httpx

from api_test_framework.environment import ConfigError, EnvironmentConfig


class TokenProvider:
    def headers(self) -> dict:
        raise NotImplementedError


class NoAuth(TokenProvider):
    def headers(self) -> dict:
        return {}


class StaticToken(TokenProvider):
    def __init__(self, token: str):
        self._token = token

    def headers(self) -> dict:
        return {"Authorization": f"Bearer {self._token}"}


class ClientCredentials(TokenProvider):
    """POSTs the client id and secret to the token endpoint the first time a header is needed."""

    def __init__(self, token_url: str, client_id: str, client_secret: str, http: httpx.Client):
        self._token_url, self._client_id, self._client_secret, self._http = token_url, client_id, client_secret, http
        self._token: Optional[str] = None

    def headers(self) -> dict:
        if self._token is None:
            response = self._http.post(self._token_url, json={"client_id": self._client_id,
                                                              "client_secret": self._client_secret})
            if response.status_code != 200:
                raise ConfigError(f"token request to {self._token_url} failed: {response.status_code} {response.text[:200]}")
            self._token = response.json()["access_token"]
        return {"Authorization": f"Bearer {self._token}"}


def token_provider_for(environment: EnvironmentConfig, http: httpx.Client) -> TokenProvider:
    auth = environment.auth
    kind = auth.get("type", "none")
    if kind == "none":
        return NoAuth()
    if kind == "static_token":
        return StaticToken(_secret(auth, "token", environment.name))
    if kind == "client_credentials":
        token_url = environment.base_url(auth.get("service")) + "/" + str(auth.get("token_path", "/auth/token")).lstrip("/")
        return ClientCredentials(token_url, _secret(auth, "client_id", environment.name),
                                 _secret(auth, "client_secret", environment.name), http)
    raise ConfigError(f"environment '{environment.name}': unknown auth type '{kind}' "
                      "(use none, static_token or client_credentials)")


def _secret(auth: dict, name: str, environment: str) -> str:
    """A value from `<name>_env` (an environment variable), or a plain `<name>` (for a mock only)."""
    variable = auth.get(f"{name}_env")
    if variable:
        value = os.getenv(variable)
        if not value:
            raise ConfigError(f"environment '{environment}' needs the environment variable {variable}")
        return value
    if name in auth:
        return str(auth[name])
    raise ConfigError(f"environment '{environment}': auth needs '{name}_env' (or '{name}' for a mock)")
