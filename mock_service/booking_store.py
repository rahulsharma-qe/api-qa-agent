"""Bookings in memory. Safe for the few threads a test server uses; `reset()` empties it."""

import secrets
import string
import threading
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Optional

from mock_service.errors import ApiError
from mock_service.models import Booking, RefundStatus
from mock_service.refund_rules import CancelledBeforeBooked, RefundDecision, decide_refund

PNR_ALPHABET = string.ascii_uppercase + string.digits
PNR_LENGTH = 6


@dataclass(frozen=True)
class StoredBooking:
    booking: Booking
    refund: Optional[RefundDecision] = None     # set when the booking is cancelled


class BookingStore:
    def __init__(self, bug: str = ""):
        self._bookings: dict[str, StoredBooking] = {}
        self._lock = threading.Lock()
        self._bug = bug                          # a planted bug (planted_bugs.py), or ""

    def create(self, passenger_name: str, email: str, amount: float, booked_at: Optional[datetime]) -> Booking:
        with self._lock:
            booking = Booking(pnr=self._new_pnr(), passenger_name=passenger_name, email=email, amount=amount,
                              status="active", booked_at=booked_at or _now())
            self._bookings[booking.pnr] = StoredBooking(booking)
            return booking

    def get(self, pnr: str) -> Booking:
        return self._stored(pnr).booking

    def list(self, status: Optional[str] = None, limit: int = 20) -> list[Booking]:
        with self._lock:
            bookings = [stored.booking for stored in self._bookings.values()]
        if self._bug == "status-filter-ignored":
            status = None
        return [b for b in bookings if status is None or b.status == status][:limit]

    def update(self, pnr: str, passenger_name: str, email: str, amount: Optional[float] = None) -> Booking:
        with self._lock:
            stored = self._stored(pnr)
            changes = {"passenger_name": passenger_name, "email": email}
            if amount is not None:                   # only with the planted bug 'amount-changeable'
                changes["amount"] = amount
            booking = stored.booking.model_copy(update=changes)
            self._bookings[pnr] = replace(stored, booking=booking)
            return booking

    def delete(self, pnr: str) -> None:
        with self._lock:
            self._stored(pnr)
            if self._bug != "deleted-still-readable":
                del self._bookings[pnr]

    def cancel(self, pnr: str, cancelled_at: Optional[datetime]) -> RefundDecision:
        with self._lock:
            stored = self._stored(pnr)
            if stored.booking.status == "cancelled" and self._bug != "second-cancel-allowed":
                raise ApiError(409, "already_cancelled", f"Booking {pnr} is already cancelled")
            cancelled_at = cancelled_at or _now()
            try:
                decision = decide_refund(stored.booking.booked_at, cancelled_at, stored.booking.amount,
                                         exactly_24_hours_counts=self._bug != "refund-boundary")
            except CancelledBeforeBooked as error:
                raise ApiError(422, "invalid_request", f"cancelled_at: {error}") from error
            if self._bug == "wrong-refund-amount":
                decision = replace(decision, amount=decision.amount / 2)
            booking = stored.booking.model_copy(update={"status": "cancelled", "cancelled_at": cancelled_at})
            self._bookings[pnr] = StoredBooking(booking, decision)
            return decision

    def refund_status(self, pnr: str) -> RefundStatus:
        stored = self._stored(pnr)
        if stored.refund is None:
            return RefundStatus(pnr=pnr, refund_status="not_cancelled", refund_amount=0.0)
        status = "refunded" if stored.refund.allowed else "no_refund"
        return RefundStatus(pnr=pnr, refund_status=status, refund_amount=stored.refund.amount)

    def reset(self) -> None:
        with self._lock:
            self._bookings.clear()

    def _stored(self, pnr: str) -> StoredBooking:
        stored = self._bookings.get(pnr)
        if stored is None:
            raise ApiError(404, "booking_not_found", f"No booking with PNR {pnr}")
        return stored

    def _new_pnr(self) -> str:
        while True:
            pnr = "".join(secrets.choice(PNR_ALPHABET) for _ in range(PNR_LENGTH))
            if pnr not in self._bookings:
                return pnr


def _now() -> datetime:
    return datetime.now(timezone.utc)
