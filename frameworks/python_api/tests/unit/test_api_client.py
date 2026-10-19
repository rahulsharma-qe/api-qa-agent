import httpx

from api_test_framework import ApiClient, ScenarioContext, StaticToken


def test_requests_go_to_the_base_url_with_the_token(fake_http):
    api = ApiClient("http://svc.test/", fake_http.client(), StaticToken("secret-token"))
    api.post("/bookings", json={"amount": 1})
    api.get("bookings", params={"status": "active"})
    first, second = fake_http.requests
    assert str(first.url) == "http://svc.test/bookings" and fake_http.body(0) == {"amount": 1}
    assert first.headers["Authorization"] == "Bearer secret-token"
    assert str(second.url) == "http://svc.test/bookings?status=active"


def test_the_token_is_masked_wherever_a_request_is_shown(fake_http):
    api = ApiClient("http://svc.test", fake_http.client(), StaticToken("secret-token"))
    response = api.get("/bookings/X", headers={"X-Request-Id": "r1"})
    assert response.request.headers == {"Authorization": "***", "X-Request-Id": "r1"}
    assert "secret-token" not in api.context.history()


def test_every_step_is_recorded_in_the_context(fake_http):
    fake_http.answer = lambda request: httpx.Response(201 if request.method == "POST" else 200, json={"pnr": "AB12CD"})
    context = ScenarioContext()
    api = ApiClient("http://svc.test", fake_http.client(), context=context)
    created = api.post("/bookings", json={})
    context.remember("pnr", created.value("pnr"))
    api.get(f"/bookings/{context.get('pnr')}")
    assert [step.response.status_code for step in context.steps] == [201, 200]
    assert "step 2\n  GET http://svc.test/bookings/AB12CD" in context.history()


def test_without_auth_sends_no_token_and_shares_the_context(fake_http):
    api = ApiClient("http://svc.test", fake_http.client(), StaticToken("secret-token"))
    api.without_auth().get("/bookings/X")
    assert "Authorization" not in fake_http.requests[0].headers
    assert len(api.context.steps) == 1


def test_a_missing_remembered_value_names_what_is_known():
    context = ScenarioContext()
    context.remember("pnr", "AB12CD")
    try:
        context.get("token")
    except KeyError as error:
        assert "'token' was never remembered (remembered: pnr)" in str(error)
