"""Data-driven: the 24-hour refund boundary, one test run per row of data/cancellation_boundaries.csv."""

from pathlib import Path

import pytest

from api_test_framework import Expect, load_rows, new_passenger

ROWS = load_rows(Path(__file__).resolve().parents[2] / "data" / "cancellation_boundaries.csv")


@pytest.mark.regression
@pytest.mark.writes
@pytest.mark.case("EX-REFUND-01")
@pytest.mark.priority("P0")
@pytest.mark.parametrize("row", ROWS, ids=[row["case"] for row in ROWS])
def test_refund_at_the_24_hour_boundary(api, context, row):
    created = api.post("/bookings", json={**new_passenger(), "amount": 250, "booked_at": row["booked_at"]})
    pnr = context.remember("pnr", created.value("pnr"))

    cancelled = api.post(f"/bookings/{pnr}/cancel", json={"cancelled_at": row["cancelled_at"]})
    expect = Expect(cancelled).status_is(row["expected_status"])
    if row["expected_status"] == 200:
        expect.field_equals("refund_allowed", row["refund_allowed"]).field_equals("refund_amount", row["refund_amount"])


@pytest.mark.regression
@pytest.mark.writes
@pytest.mark.case("EX-REFUND-02")
@pytest.mark.priority("P1")
def test_a_second_cancel_is_refused_and_changes_nothing(api, context):
    pnr = context.remember("pnr", api.post("/bookings", json={**new_passenger(), "amount": 250,
                                                               "booked_at": "2026-01-15T10:00:00Z"}).value("pnr"))
    Expect(api.post(f"/bookings/{pnr}/cancel", json={"cancelled_at": "2026-01-15T11:00:00Z"})).status_is(200)
    Expect(api.post(f"/bookings/{pnr}/cancel", json={"cancelled_at": "2026-01-20T11:00:00Z"})) \
        .status_is(409).field_equals("error.code", "already_cancelled")
    Expect(api.get(f"/bookings/{pnr}/refund")).field_equals("refund_status", "refunded")
