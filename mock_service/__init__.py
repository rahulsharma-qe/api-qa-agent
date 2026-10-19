"""The reference API the utility is tested against: a small bookings service, plus a stand-in
notifications service that env_check reports on.

    python -m mock_service                      bookings on :8000, notifications on :8001
    python -m mock_service --export-openapi mock_service/openapi.json

It is a test double, not a product: data lives in memory and `/test/*` routes reset it.
"""

from mock_service.bookings_app import create_bookings_app
from mock_service.notifications_app import create_notifications_app
from mock_service.settings import MockSettings

__all__ = ["MockSettings", "create_bookings_app", "create_notifications_app"]
