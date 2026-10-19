"""Unit tests for the framework itself: a fake network (httpx.MockTransport), no service running."""

import json

import httpx
import pytest

pytest_plugins = ["pytester"]


@pytest.fixture
def fake_http():
    """An httpx client whose answers are set per test: fake_http.answer = lambda request: httpx.Response(...)."""
    class FakeHttp:
        def __init__(self):
            self.requests = []
            self.answer = lambda request: httpx.Response(200, json={"ok": True})

        def client(self):
            def handle(request):
                self.requests.append(request)
                return self.answer(request)
            return httpx.Client(transport=httpx.MockTransport(handle))

        def body(self, index=-1):
            return json.loads(self.requests[index].content or b"null")
    return FakeHttp()
