"""A stand-in for a service the bookings team depends on. It does nothing but answer its health
check, and it can be switched down, so env_check has a dependency to report on:

    POST /test/state {"down": true}     or start it with NOTIFICATIONS_DOWN=1
"""

from typing import Optional

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from demo_api.errors import add_error_handlers
from demo_api.models import Health, NotificationsState
from demo_api.settings import DemoApiSettings

SERVICE_NAME = "notifications"


def create_notifications_app(settings: Optional[DemoApiSettings] = None) -> FastAPI:
    settings = settings or DemoApiSettings.from_environment()
    app = FastAPI(title="Notifications (stand-in)", version="1.0.0")
    add_error_handlers(app)
    app.state.down = settings.notifications_down

    @app.get("/health-check", response_model=Health, responses={503: {"model": Health}}, tags=["health"])
    def health_check():
        if app.state.down:
            return JSONResponse(Health(status="down", service=SERVICE_NAME).model_dump(), status_code=503)
        return Health(status="ok", service=SERVICE_NAME)

    if settings.test_mode:
        @app.post("/test/state", response_model=NotificationsState, tags=["test"])
        def set_state(state: NotificationsState) -> NotificationsState:
            app.state.down = state.down
            return state

    return app
