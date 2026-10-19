"""Lists check the test's own items, never totals: other tests (or teams) may be using the service."""

import pytest

from api_test_framework import Expect, new_passenger


@pytest.mark.functional
@pytest.mark.writes
@pytest.mark.case("EX-LIST-01")
def test_the_status_filter(api, context):
    active = api.post("/bookings", json={**new_passenger(), "amount": 10}).value("pnr")
    cancelled = api.post("/bookings", json={**new_passenger(), "amount": 20, "booked_at": "2026-01-15T10:00:00Z"}).value("pnr")
    api.post(f"/bookings/{cancelled}/cancel", json={"cancelled_at": "2026-01-15T11:00:00Z"})

    listed = api.get("/bookings", params={"status": "cancelled", "limit": 100})
    Expect(listed).status_is(200).field_is_type("items", "list") \
        .list_contains("items", pnr=cancelled, status="cancelled").list_excludes("items", pnr=active)


@pytest.mark.functional
@pytest.mark.case("EX-LIST-02")
def test_limit_and_a_bad_filter(api):
    Expect(api.get("/bookings", params={"limit": 1})).status_is(200).field_is_type("count", "integer")
    Expect(api.get("/bookings", params={"status": "unknown"})).status_is(422).field_equals("error.code", "invalid_request")
