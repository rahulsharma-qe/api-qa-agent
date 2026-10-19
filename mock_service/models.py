"""Request and response shapes. They are also what the OpenAPI description is generated from."""

import re
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
BookingStatus = Literal["active", "cancelled"]
RefundStatusValue = Literal["refunded", "no_refund", "not_cancelled"]


def _with_time_zone(value: Optional[datetime]) -> Optional[datetime]:
    if value is not None and value.tzinfo is None:
        raise ValueError("must include a time zone, for example 2026-10-20T10:00:00Z")
    return value


def _valid_email(value: str) -> str:
    if not EMAIL.match(value):
        raise ValueError("not a valid email address")
    return value


class TokenRequest(BaseModel):
    client_id: str
    client_secret: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in: int = 3600


class NewBooking(BaseModel):
    passenger_name: str = Field(min_length=1, max_length=100)
    email: str
    amount: float = Field(ge=0)
    booked_at: Optional[datetime] = Field(default=None, description="Defaults to now; set it to test time boundaries")

    _email = field_validator("email")(_valid_email)
    _booked_at = field_validator("booked_at")(_with_time_zone)


class BookingUpdate(BaseModel):
    passenger_name: str = Field(min_length=1, max_length=100)
    email: str

    _email = field_validator("email")(_valid_email)

    @model_validator(mode="before")
    @classmethod
    def amount_is_fixed(cls, data):
        if isinstance(data, dict) and "amount" in data:
            raise ValueError("amount cannot be changed after a booking is made")
        return data


class Booking(BaseModel):
    pnr: str
    passenger_name: str
    email: str
    amount: float
    status: BookingStatus
    booked_at: datetime
    cancelled_at: Optional[datetime] = None


class BookingList(BaseModel):
    items: list[Booking]
    count: int


class CancelRequest(BaseModel):
    cancelled_at: Optional[datetime] = Field(default=None, description="Defaults to now")

    _cancelled_at = field_validator("cancelled_at")(_with_time_zone)


class CancelResult(BaseModel):
    pnr: str
    refund_allowed: bool
    refund_amount: float
    reason: str


class RefundStatus(BaseModel):
    pnr: str
    refund_status: RefundStatusValue
    refund_amount: float


class Health(BaseModel):
    status: Literal["ok", "down"]
    service: str


class NotificationsState(BaseModel):
    down: bool
