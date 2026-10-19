"""The bookings service: a token endpoint, bookings (create, read, update, delete, list), cancel with
the refund rule, refund status, a health check, and a reset for tests.

Every /bookings route needs `Authorization: Bearer <token>` from POST /auth/token.
"""

import secrets
from typing import Optional

from fastapi import Depends, FastAPI, Header, Query, Response

from mock_service.booking_store import BookingStore
from mock_service.errors import ApiError, add_error_handlers
from mock_service.models import (Booking, BookingList, BookingStatus, BookingUpdate, CancelRequest, CancelResult,
                                 Health, NewBooking, RefundStatus, TokenRequest, TokenResponse)
from mock_service.settings import MockSettings

SERVICE_NAME = "bookings"
SERVICE_VERSION = "1.0.0"


def create_bookings_app(settings: Optional[MockSettings] = None) -> FastAPI:
    settings = settings or MockSettings.from_environment()
    app = FastAPI(title="AeroAssist bookings (reference API)", version=SERVICE_VERSION,
                  description="A small bookings API that api-qa-agent's frameworks and examples run against.")
    add_error_handlers(app)
    store = BookingStore()
    issued_tokens: set[str] = set()
    app.state.store = store

    def require_token(authorization: Optional[str] = Header(default=None)) -> None:
        scheme, _, token = (authorization or "").partition(" ")
        if scheme.lower() != "bearer" or token not in issued_tokens:
            raise ApiError(401, "unauthorized", "A valid bearer token is required: POST /auth/token first")

    @app.post("/auth/token", response_model=TokenResponse, tags=["auth"])
    def issue_token(request: TokenRequest) -> TokenResponse:
        if (request.client_id, request.client_secret) != (settings.client_id, settings.client_secret):
            raise ApiError(401, "invalid_credentials", "Unknown client_id or wrong client_secret")
        token = secrets.token_urlsafe(24)
        issued_tokens.add(token)
        return TokenResponse(access_token=token)

    @app.post("/bookings", response_model=Booking, status_code=201, tags=["bookings"],
              dependencies=[Depends(require_token)])
    def create_booking(request: NewBooking) -> Booking:
        return store.create(request.passenger_name, request.email, request.amount, request.booked_at)

    @app.get("/bookings", response_model=BookingList, tags=["bookings"], dependencies=[Depends(require_token)])
    def list_bookings(status: Optional[BookingStatus] = None, limit: int = Query(default=20, ge=1, le=100)) -> BookingList:
        items = store.list(status, limit)
        return BookingList(items=items, count=len(items))

    @app.get("/bookings/{pnr}", response_model=Booking, tags=["bookings"], dependencies=[Depends(require_token)])
    def get_booking(pnr: str) -> Booking:
        return store.get(pnr)

    @app.put("/bookings/{pnr}", response_model=Booking, tags=["bookings"], dependencies=[Depends(require_token)])
    def update_booking(pnr: str, request: BookingUpdate) -> Booking:
        return store.update(pnr, request.passenger_name, request.email)

    @app.delete("/bookings/{pnr}", status_code=204, tags=["bookings"], dependencies=[Depends(require_token)])
    def delete_booking(pnr: str) -> Response:
        store.delete(pnr)
        return Response(status_code=204)

    @app.post("/bookings/{pnr}/cancel", response_model=CancelResult, tags=["refunds"],
              dependencies=[Depends(require_token)])
    def cancel_booking(pnr: str, request: Optional[CancelRequest] = None) -> CancelResult:
        decision = store.cancel(pnr, request.cancelled_at if request else None)
        return CancelResult(pnr=pnr, refund_allowed=decision.allowed, refund_amount=decision.amount,
                            reason=decision.reason)

    @app.get("/bookings/{pnr}/refund", response_model=RefundStatus, tags=["refunds"],
             dependencies=[Depends(require_token)])
    def refund_status(pnr: str) -> RefundStatus:
        return store.refund_status(pnr)

    @app.get("/health-check", response_model=Health, tags=["health"])
    def health_check() -> Health:
        return Health(status="ok", service=SERVICE_NAME)

    if settings.test_mode:
        @app.post("/test/reset", status_code=204, tags=["test"])
        def reset() -> Response:
            store.reset()
            return Response(status_code=204)

    return app
