"""Each seeded bug changes exactly the behaviour it names; with none, the API is correct."""

import pytest
from fastapi.testclient import TestClient

from mock_service.__main__ import main
from mock_service.bookings_app import create_bookings_app
from mock_service.seeded_bugs import BUGS, UnknownBug
from mock_service.settings import MockSettings

BOOKED = "2026-01-15T10:00:00Z"


def client(bug=""):
    app = TestClient(create_bookings_app(MockSettings(bug=bug)))
    token = app.post("/auth/token", json={"client_id": "demo-client", "client_secret": "demo-secret"}).json()
    app.headers["Authorization"] = f"Bearer {token['access_token']}"
    return app


def booking(app, amount=250):
    return app.post("/bookings", json={"passenger_name": "A", "email": "a@testdata.example", "amount": amount,
                                       "booked_at": BOOKED}).json()["pnr"]


def cancel(app, pnr, at="2026-01-16T10:00:00Z"):
    return app.post(f"/bookings/{pnr}/cancel", json={"cancelled_at": at})


@pytest.mark.parametrize("bug, correct, broken", [
    ("refund-boundary", True, False),
    ("wrong-refund-amount", 250, 125),
])
def test_refund_bugs(bug, correct, broken):
    field = "refund_allowed" if bug == "refund-boundary" else "refund_amount"
    good, bad = client(), client(bug)
    assert cancel(good, booking(good)).json()[field] == correct
    assert cancel(bad, booking(bad)).json()[field] == broken


def test_second_cancel_allowed():
    good, bad = client(), client("second-cancel-allowed")
    for app, second in ((good, 409), (bad, 200)):
        pnr = booking(app)
        cancel(app, pnr)
        assert cancel(app, pnr).status_code == second


def test_deleted_still_readable():
    for bug, after in (("", 404), ("deleted-still-readable", 200)):
        app = client(bug)
        pnr = booking(app)
        assert app.delete(f"/bookings/{pnr}").status_code == 204
        assert app.get(f"/bookings/{pnr}").status_code == after


def test_amount_changeable():
    for bug, status, amount in (("", 422, 250), ("amount-changeable", 200, 1)):
        app = client(bug)
        pnr = booking(app)
        update = app.put(f"/bookings/{pnr}", json={"passenger_name": "B", "email": "b@testdata.example", "amount": 1})
        assert update.status_code == status
        assert app.get(f"/bookings/{pnr}").json()["amount"] == amount


def test_token_not_checked():
    for bug, status in (("", 401), ("token-not-checked", 200)):
        app = client(bug)
        del app.headers["Authorization"]
        assert app.get("/bookings").status_code == status


def test_status_filter_ignored():
    for bug, statuses in (("", {"cancelled"}), ("status-filter-ignored", {"active", "cancelled"})):
        app = client(bug)
        booking(app)
        cancel(app, booking(app))
        assert {item["status"] for item in app.get("/bookings", params={"status": "cancelled"}).json()["items"]} == statuses


def test_every_bug_has_a_test_here_and_an_unknown_one_is_refused(capsys):
    assert set(BUGS) == {"refund-boundary", "wrong-refund-amount", "second-cancel-allowed", "deleted-still-readable",
                         "amount-changeable", "token-not-checked", "status-filter-ignored"}
    with pytest.raises(UnknownBug, match="no seeded bug 'typo'"):
        create_bookings_app(MockSettings(bug="typo"))
    assert main(["--bug", "typo"]) == 2
    assert "use one of: refund-boundary" in capsys.readouterr().out


def test_the_openapi_description_is_the_one_without_bugs():
    assert create_bookings_app(MockSettings(bug="amount-changeable")).openapi()["paths"].keys() == \
        create_bookings_app(MockSettings()).openapi()["paths"].keys()
