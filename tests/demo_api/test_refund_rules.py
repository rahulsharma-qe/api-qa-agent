from datetime import datetime, timedelta, timezone

import pytest

from demo_api.refund_rules import CancelledBeforeBooked, decide_refund

BOOKED = datetime(2026, 10, 20, 10, 0, tzinfo=timezone.utc)


def test_exactly_24_hours_is_inside_the_window():
    assert decide_refund(BOOKED, BOOKED + timedelta(hours=24), 100).allowed


def test_past_24_hours_gets_nothing():
    decision = decide_refund(BOOKED, BOOKED + timedelta(hours=24, seconds=1), 100)
    assert (decision.allowed, decision.amount) == (False, 0.0)


def test_before_booking_is_an_error():
    with pytest.raises(CancelledBeforeBooked):
        decide_refund(BOOKED, BOOKED - timedelta(seconds=1), 100)
