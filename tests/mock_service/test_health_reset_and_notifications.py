from fastapi.testclient import TestClient

from mock_service import MockSettings, create_bookings_app, create_notifications_app


def test_reset_empties_the_store(client, auth, make_booking):
    pnr = make_booking()["pnr"]
    assert client.post("/test/reset").status_code == 204
    assert client.get(f"/bookings/{pnr}", headers=auth).status_code == 404


def test_test_routes_are_off_outside_test_mode():
    client = TestClient(create_bookings_app(MockSettings(test_mode=False)))
    assert client.post("/test/reset").status_code == 404


def test_notifications_can_be_switched_down_and_up():
    client = TestClient(create_notifications_app(MockSettings()))
    assert client.get("/health-check").json() == {"status": "ok", "service": "notifications"}
    client.post("/test/state", json={"down": True})
    down = client.get("/health-check")
    assert down.status_code == 503 and down.json()["status"] == "down"
    client.post("/test/state", json={"down": False})
    assert client.get("/health-check").status_code == 200


def test_notifications_can_start_down():
    client = TestClient(create_notifications_app(MockSettings(notifications_down=True)))
    assert client.get("/health-check").status_code == 503


def test_settings_come_from_the_environment(monkeypatch):
    monkeypatch.setenv("MOCK_CLIENT_ID", "team-a")
    monkeypatch.setenv("MOCK_TEST_MODE", "off")
    monkeypatch.setenv("NOTIFICATIONS_DOWN", "1")
    settings = MockSettings.from_environment()
    assert (settings.client_id, settings.test_mode, settings.notifications_down) == ("team-a", False, True)
