"""Settings, read from environment variables so a CI job or a laptop can change them."""

import os
from dataclasses import dataclass

TRUE_WORDS = ("1", "true", "yes", "on")


@dataclass(frozen=True)
class DemoApiSettings:
    client_id: str = "demo-client"
    client_secret: str = "demo-secret"
    test_mode: bool = True              # turns /test/* routes on
    notifications_down: bool = False    # start the notifications stand-in switched down
    bug: str = ""                       # one seeded bug switched on (seeded_bugs.py); none by default

    @classmethod
    def from_environment(cls) -> "DemoApiSettings":
        return cls(
            client_id=os.getenv("DEMO_CLIENT_ID", cls.client_id),
            client_secret=os.getenv("DEMO_CLIENT_SECRET", cls.client_secret),
            test_mode=_flag("DEMO_TEST_MODE", default=True),
            notifications_down=_flag("NOTIFICATIONS_DOWN", default=False),
            bug=os.getenv("DEMO_BUG", ""),
        )


def _flag(name: str, default: bool) -> bool:
    value = os.getenv(name)
    return default if value is None else value.strip().lower() in TRUE_WORDS
