"""A chain across four endpoints: ask for a token, make a booking with it, cancel it, read the refund.

The other examples get their token from the environment's auth settings automatically; this one
does it by hand to show a value (the token) carried from one call into the headers of the next.
"""

import pytest

from api_test_framework import Expect, new_passenger


@pytest.mark.regression
@pytest.mark.writes
@pytest.mark.case("EX-CHAIN-01")
def test_token_then_booking_then_cancel_then_refund_status(api, context, environment):
    if "client_id" not in environment.auth:
        pytest.skip("this example reads plain credentials, which only the mock environment has")
    anonymous = api.without_auth()

    token = anonymous.post("/auth/token", json={"client_id": environment.auth["client_id"],
                                                "client_secret": environment.auth["client_secret"]})
    Expect(token).status_is(200).field_equals("token_type", "Bearer")
    bearer = {"Authorization": f"Bearer {context.remember('token', token.value('access_token'))}"}

    created = anonymous.post("/bookings", headers=bearer,
                             json={**new_passenger(), "amount": 300, "booked_at": "2026-01-15T10:00:00Z"})
    Expect(created).status_is(201)
    pnr = context.remember("pnr", created.value("pnr"))

    cancelled = anonymous.post(f"/bookings/{pnr}/cancel", headers=bearer, json={"cancelled_at": "2026-01-15T18:00:00Z"})
    Expect(cancelled).status_is(200).field_equals("refund_allowed", True)

    Expect(anonymous.get(f"/bookings/{pnr}/refund", headers=bearer)).status_is(200) \
        .field_equals("refund_status", "refunded").field_equals("refund_amount", 300)
