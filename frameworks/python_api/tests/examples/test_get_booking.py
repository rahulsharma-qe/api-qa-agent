"""GET: a booking that exists, one that doesn't, and a call without a token."""

import pytest

from api_test_framework import Expect, new_passenger


@pytest.mark.regression
@pytest.mark.writes
@pytest.mark.case("EX-GET-01")
def test_get_returns_the_booking_that_was_made(api, context):
    created = api.post("/bookings", json={**new_passenger(), "amount": 120})
    Expect(created).status_is(201)
    pnr = context.remember("pnr", created.value("pnr"))

    found = api.get(f"/bookings/{pnr}")
    Expect(found).status_is(200).field_equals("pnr", pnr).field_equals("status", "active") \
        .field_equals("amount", 120).field_is_type("booked_at", "string")


@pytest.mark.regression
@pytest.mark.case("EX-GET-02")
def test_an_unknown_pnr_is_404(api):
    Expect(api.get("/bookings/NOPE00")).status_is(404).field_equals("error.code", "booking_not_found")


@pytest.mark.regression
@pytest.mark.case("EX-GET-03")
def test_without_a_token_the_answer_is_401(api):
    Expect(api.without_auth().get("/bookings/NOPE00")).status_is(401).field_equals("error.code", "unauthorized")
