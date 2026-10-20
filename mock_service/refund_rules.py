"""The refund rule, in one place: a booking cancelled within 24 hours of being made gets a full
refund; exactly 24 hours still counts. Tests never import this module: their expected results
come from the case or its data, so a mistake here is caught instead of copied.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

REFUND_WINDOW = timedelta(hours=24)


@dataclass(frozen=True)
class RefundDecision:
    allowed: bool
    amount: float
    reason: str


class CancelledBeforeBooked(ValueError):
    """The cancellation time is earlier than the booking time."""


def decide_refund(booked_at: datetime, cancelled_at: datetime, amount: float,
                  exactly_24_hours_counts: bool = True) -> RefundDecision:
    """exactly_24_hours_counts=False is the planted bug 'refund-boundary' (< instead of <=)."""
    elapsed = cancelled_at - booked_at
    if elapsed < timedelta(0):
        raise CancelledBeforeBooked("is earlier than booked_at")
    if elapsed < REFUND_WINDOW or (exactly_24_hours_counts and elapsed == REFUND_WINDOW):
        return RefundDecision(True, amount, "cancelled within 24 hours of booking")
    return RefundDecision(False, 0.0, "cancelled more than 24 hours after booking")
