import re


def test_create_returns_the_booking_with_a_new_pnr(make_booking):
    booking = make_booking()
    assert re.fullmatch(r"[A-Z0-9]{6}", booking["pnr"])
    assert booking["status"] == "active" and booking["cancelled_at"] is None
    assert booking["booked_at"] == "2026-10-20T10:00:00Z"


def test_booked_at_defaults_to_now(client, auth):
    response = client.post("/bookings", json={"passenger_name": "A", "email": "a@testdata.example", "amount": 1},
                           headers=auth)
    assert response.status_code == 201 and response.json()["booked_at"]


def test_invalid_fields_are_listed_in_one_error(client, auth):
    response = client.post("/bookings", json={"passenger_name": "", "email": "x", "amount": -1}, headers=auth)
    assert response.status_code == 422
    message = response.json()["error"]["message"]
    assert "passenger_name" in message and "email: not a valid email address" in message and "amount" in message


def test_a_time_without_a_time_zone_is_refused(client, auth):
    body = {"passenger_name": "A", "email": "a@testdata.example", "amount": 1, "booked_at": "2026-10-20T10:00:00"}
    response = client.post("/bookings", json=body, headers=auth)
    assert response.status_code == 422 and "time zone" in response.json()["error"]["message"]


def test_get_returns_the_booking_or_404(client, auth, make_booking):
    booking = make_booking()
    assert client.get(f"/bookings/{booking['pnr']}", headers=auth).json() == booking
    missing = client.get("/bookings/NOPE00", headers=auth)
    assert missing.status_code == 404 and missing.json()["error"]["code"] == "booking_not_found"


def test_list_filters_by_status_and_respects_the_limit(client, auth, make_booking):
    active, cancelled = make_booking(), make_booking()
    client.post(f"/bookings/{cancelled['pnr']}/cancel", json={"cancelled_at": "2026-10-20T12:00:00Z"}, headers=auth)
    listed = client.get("/bookings?status=cancelled", headers=auth).json()
    pnrs = [item["pnr"] for item in listed["items"]]
    assert cancelled["pnr"] in pnrs and active["pnr"] not in pnrs and listed["count"] == len(pnrs)
    assert client.get("/bookings?limit=1", headers=auth).json()["count"] == 1
    assert client.get("/bookings?status=unknown", headers=auth).status_code == 422


def test_update_changes_name_and_email_only(client, auth, make_booking):
    pnr = make_booking()["pnr"]
    updated = client.put(f"/bookings/{pnr}", json={"passenger_name": "Asha R", "email": "ar@testdata.example"},
                         headers=auth)
    assert updated.status_code == 200 and updated.json()["passenger_name"] == "Asha R"
    refused = client.put(f"/bookings/{pnr}", json={"passenger_name": "A", "email": "a@testdata.example", "amount": 1},
                         headers=auth)
    assert refused.status_code == 422 and "amount cannot be changed" in refused.json()["error"]["message"]
    assert client.get(f"/bookings/{pnr}", headers=auth).json()["amount"] == 250
    assert client.put("/bookings/NOPE00", json={"passenger_name": "A", "email": "a@testdata.example"},
                      headers=auth).status_code == 404


def test_delete_then_get_is_404(client, auth, make_booking):
    pnr = make_booking()["pnr"]
    assert client.delete(f"/bookings/{pnr}", headers=auth).status_code == 204
    assert client.get(f"/bookings/{pnr}", headers=auth).status_code == 404
    assert client.delete(f"/bookings/{pnr}", headers=auth).status_code == 404


def test_unknown_routes_use_the_same_error_shape(client):
    response = client.get("/no-such-route")
    assert response.status_code == 404 and response.json()["error"]["code"] == "not_found"
