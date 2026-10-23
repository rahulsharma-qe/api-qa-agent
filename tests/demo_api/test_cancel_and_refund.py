import pytest


@pytest.mark.parametrize("cancelled_at, allowed, amount", [
    ("2026-10-20T10:00:00Z", True, 250),       # at once
    ("2026-10-21T09:59:00Z", True, 250),       # 23:59 later
    ("2026-10-21T10:00:00Z", True, 250),       # exactly 24 hours: still refunded
    ("2026-10-21T10:00:01Z", False, 0),        # one second past
    ("2026-10-21T15:30:00+05:30", True, 250),  # exactly 24 hours, written in another time zone
])
def test_the_24_hour_boundary(client, auth, make_booking, cancelled_at, allowed, amount):
    pnr = make_booking()["pnr"]
    result = client.post(f"/bookings/{pnr}/cancel", json={"cancelled_at": cancelled_at}, headers=auth)
    assert result.status_code == 200
    assert (result.json()["refund_allowed"], result.json()["refund_amount"]) == (allowed, amount)


def test_cancelling_before_booking_is_refused(client, auth, make_booking):
    pnr = make_booking()["pnr"]
    result = client.post(f"/bookings/{pnr}/cancel", json={"cancelled_at": "2026-10-20T09:00:00Z"}, headers=auth)
    assert result.status_code == 422
    assert client.get(f"/bookings/{pnr}", headers=auth).json()["status"] == "active"


def test_a_second_cancel_is_a_conflict_and_changes_nothing(client, auth, make_booking):
    pnr = make_booking()["pnr"]
    client.post(f"/bookings/{pnr}/cancel", json={"cancelled_at": "2026-10-20T11:00:00Z"}, headers=auth)
    again = client.post(f"/bookings/{pnr}/cancel", json={"cancelled_at": "2026-10-25T11:00:00Z"}, headers=auth)
    assert again.status_code == 409 and again.json()["error"]["code"] == "already_cancelled"
    assert client.get(f"/bookings/{pnr}/refund", headers=auth).json()["refund_status"] == "refunded"


def test_cancel_without_a_body_uses_now(client, auth):
    created = client.post("/bookings", json={"passenger_name": "A", "email": "a@testdata.example", "amount": 9},
                          headers=auth).json()
    result = client.post(f"/bookings/{created['pnr']}/cancel", headers=auth)
    assert result.status_code == 200 and result.json()["refund_allowed"] is True


def test_refund_status_through_the_booking_life(client, auth, make_booking):
    refunded, not_refunded = make_booking()["pnr"], make_booking()["pnr"]
    assert client.get(f"/bookings/{refunded}/refund", headers=auth).json()["refund_status"] == "not_cancelled"
    client.post(f"/bookings/{refunded}/cancel", json={"cancelled_at": "2026-10-20T12:00:00Z"}, headers=auth)
    client.post(f"/bookings/{not_refunded}/cancel", json={"cancelled_at": "2026-10-23T12:00:00Z"}, headers=auth)
    assert client.get(f"/bookings/{refunded}/refund", headers=auth).json() == \
        {"pnr": refunded, "refund_status": "refunded", "refund_amount": 250}
    assert client.get(f"/bookings/{not_refunded}/refund", headers=auth).json()["refund_status"] == "no_refund"
    assert client.get("/bookings/NOPE00/refund", headers=auth).status_code == 404
