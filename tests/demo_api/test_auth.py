import pytest


def test_right_credentials_get_a_bearer_token(client):
    response = client.post("/auth/token", json={"client_id": "demo-client", "client_secret": "demo-secret"})
    assert response.status_code == 200
    assert response.json()["token_type"] == "Bearer" and response.json()["access_token"]


def test_wrong_credentials_are_refused(client):
    response = client.post("/auth/token", json={"client_id": "demo-client", "client_secret": "wrong"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_credentials"


@pytest.mark.parametrize("header", [None, "Bearer not-a-real-token", "Basic abc"])
def test_bookings_need_an_issued_bearer_token(client, header):
    headers = {"Authorization": header} if header else {}
    response = client.get("/bookings/ABC123", headers=headers)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_health_check_needs_no_token(client):
    assert client.get("/health-check").status_code == 200
