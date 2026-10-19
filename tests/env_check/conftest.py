"""env_check tests use a fake network (httpx.MockTransport): no service has to run."""

import httpx
import pytest

ENVIRONMENTS = """
environments:
  mock:
    services: {bookings: "http://bookings.test", notifications: "http://notify.test/"}
"""
DEPENDENCIES = """
team: cancellations
attempts: 3
wait_seconds: 1
checks:
  - service: bookings
  - service: notifications
    critical: false
"""


@pytest.fixture
def files(tmp_path):
    def write(environments=ENVIRONMENTS, dependencies=DEPENDENCIES):
        (tmp_path / "environments.yaml").write_text(environments)
        (tmp_path / "dependencies.yaml").write_text(dependencies)
        return tmp_path / "environments.yaml", tmp_path / "dependencies.yaml"
    return write


@pytest.fixture
def network():
    """A fake network: status codes per host, a list of every request made."""
    class FakeNetwork:
        def __init__(self):
            self.status = {"bookings.test": 200, "notify.test": 200}
            self.requests = []

        def client(self):
            def answer(request):
                self.requests.append(request)
                status = self.status[request.url.host]
                if isinstance(status, Exception):
                    raise status
                return httpx.Response(status, json={"status": "ok"})
            return httpx.Client(transport=httpx.MockTransport(answer))
    return FakeNetwork()
