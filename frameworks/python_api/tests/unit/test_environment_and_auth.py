import httpx
import pytest

from api_test_framework import ClientCredentials, ConfigError, NoAuth, StaticToken, load_environment, token_provider_for

ENVIRONMENTS = """
environments:
  demo:
    default_service: bookings
    services: {notifications: "http://notify.test", bookings: "http://bookings.test/"}
    auth: {type: client_credentials, service: bookings, token_path: /auth/token,
           client_id: demo-client, client_secret: demo-secret}
  staging:
    services: {bookings: "https://staging.test"}
    auth: {type: static_token, token_env: STAGING_TOKEN}
    read_only: true
    timeout_seconds: 3
  open:
    services: {bookings: "http://open.test"}
"""


@pytest.fixture
def config(tmp_path):
    path = tmp_path / "environments.yaml"
    path.write_text(ENVIRONMENTS)
    return path


def test_an_environment_is_read_with_its_settings(config):
    demo, staging = load_environment(config, "demo"), load_environment(config, "staging")
    assert demo.base_url() == "http://bookings.test" and demo.base_url("notifications") == "http://notify.test"
    assert (staging.read_only, staging.timeout_seconds, staging.default_service) == (True, 3.0, "bookings")


@pytest.mark.parametrize("name, text, message", [
    ("nope", None, "unknown environment 'nope'"),
    ("x", "environments: {x: {services: {}}}", "lists no services"),
    ("x", "environments: {x: {services: {a: 'http://a'}, default_service: b}}", "default_service 'b'"),
])
def test_config_mistakes_are_named(tmp_path, config, name, text, message):
    path = config
    if text:
        path = tmp_path / "other.yaml"
        path.write_text(text)
    with pytest.raises(ConfigError, match=message):
        load_environment(path, name)


def test_an_unknown_service_is_named(config):
    with pytest.raises(ConfigError, match="no service 'payments'"):
        load_environment(config, "demo").base_url("payments")


def test_client_credentials_ask_for_a_token_once(config, fake_http):
    fake_http.answer = lambda request: httpx.Response(200, json={"access_token": "t-1"})
    provider = token_provider_for(load_environment(config, "demo"), fake_http.client())
    assert isinstance(provider, ClientCredentials)
    assert provider.headers() == provider.headers() == {"Authorization": "Bearer t-1"}
    assert len(fake_http.requests) == 1 and str(fake_http.requests[0].url) == "http://bookings.test/auth/token"
    assert fake_http.body() == {"client_id": "demo-client", "client_secret": "demo-secret"}


def test_a_refused_token_request_is_a_config_error(config, fake_http):
    fake_http.answer = lambda request: httpx.Response(401, json={"error": {"code": "invalid_credentials"}})
    with pytest.raises(ConfigError, match="token request to http://bookings.test/auth/token failed: 401"):
        token_provider_for(load_environment(config, "demo"), fake_http.client()).headers()


def test_a_static_token_comes_from_an_environment_variable(config, fake_http, monkeypatch):
    with pytest.raises(ConfigError, match="needs the environment variable STAGING_TOKEN"):
        token_provider_for(load_environment(config, "staging"), fake_http.client())
    monkeypatch.setenv("STAGING_TOKEN", "s-1")
    provider = token_provider_for(load_environment(config, "staging"), fake_http.client())
    assert isinstance(provider, StaticToken) and provider.headers() == {"Authorization": "Bearer s-1"}


def test_no_auth_by_default(config, fake_http):
    assert isinstance(token_provider_for(load_environment(config, "open"), fake_http.client()), NoAuth)
