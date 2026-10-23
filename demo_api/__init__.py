"""The reference API the utility is tested against: a small bookings service, plus a stand-in
notifications service that env_check reports on.

    python -m demo_api                      bookings on :8000, notifications on :8001
    python -m demo_api --export-openapi demo_api/openapi.json

It is a test double, not a product: data lives in memory and `/test/*` routes reset it.
"""

from demo_api.bookings_app import create_bookings_app
from demo_api.notifications_app import create_notifications_app
from demo_api.settings import DemoApiSettings

__all__ = ["DemoApiSettings", "create_bookings_app", "create_notifications_app"]
