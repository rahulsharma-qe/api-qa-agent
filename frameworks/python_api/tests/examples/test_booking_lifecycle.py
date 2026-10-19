"""Create, read, update, read, delete, read: one booking's whole life, its PNR carried step to step."""

import pytest

from api_test_framework import Expect, new_passenger


@pytest.mark.regression
@pytest.mark.writes
@pytest.mark.case("EX-CRUD-01")
def test_a_booking_from_creation_to_deletion(api, context):
    passenger = new_passenger()
    created = api.post("/bookings", json={**passenger, "amount": 250})
    Expect(created).status_is(201).field_equals("status", "active")
    pnr = context.remember("pnr", created.value("pnr"))

    Expect(api.get(f"/bookings/{pnr}")).status_is(200).field_equals("passenger_name", passenger["passenger_name"])

    renamed = {**new_passenger(), "passenger_name": "Asha Rao"}
    Expect(api.put(f"/bookings/{pnr}", json=renamed)).status_is(200)
    Expect(api.get(f"/bookings/{pnr}")).status_is(200).field_equals("passenger_name", "Asha Rao") \
        .field_equals("email", renamed["email"]).field_equals("amount", 250)

    Expect(api.delete(f"/bookings/{pnr}")).status_is(204)
    Expect(api.get(f"/bookings/{pnr}")).status_is(404)


@pytest.mark.regression
@pytest.mark.writes
@pytest.mark.case("EX-CRUD-02")
def test_the_amount_cannot_be_changed(api, context):
    pnr = context.remember("pnr", api.post("/bookings", json={**new_passenger(), "amount": 250}).value("pnr"))
    refused = api.put(f"/bookings/{pnr}", json={**new_passenger(), "amount": 1})
    Expect(refused).status_is(422).field_contains("error.message", "amount cannot be changed")
    Expect(api.get(f"/bookings/{pnr}")).field_equals("amount", 250)
