"""Fixtures for the demo API's own tests: an app per test, a token, and a booking factory."""

import pytest
from fastapi.testclient import TestClient

from demo_api import DemoApiSettings, create_bookings_app

BOOKED_AT = "2026-10-20T10:00:00Z"


@pytest.fixture
def client():
    return TestClient(create_bookings_app(DemoApiSettings()))


@pytest.fixture
def auth(client):
    token = client.post("/auth/token", json={"client_id": "demo-client", "client_secret": "demo-secret"})
    return {"Authorization": f"Bearer {token.json()['access_token']}"}


@pytest.fixture
def make_booking(client, auth):
    def make(**fields):
        body = {"passenger_name": "Asha Rao", "email": "asha@testdata.example", "amount": 250,
                "booked_at": BOOKED_AT, **fields}
        response = client.post("/bookings", json=body, headers=auth)
        assert response.status_code == 201, response.json()
        return response.json()
    return make
