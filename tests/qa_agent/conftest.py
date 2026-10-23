"""A small team project in a temporary folder, written by each test as it needs."""

import textwrap
from pathlib import Path

import pytest


@pytest.fixture
def make_project(tmp_path):
    def make(files: dict[str, str], config: str = "team: t\nservice: bookings\nframeworks: [pytest]\n") -> Path:
        (tmp_path / "qa-agent.yaml").write_text(config, encoding="utf-8")
        for name, text in files.items():
            path = tmp_path / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(textwrap.dedent(text).lstrip(), encoding="utf-8")
        return tmp_path
    return make


API = """
services:
  bookings:
    operations:
      - {method: POST, path: /bookings, body_required: [passenger_name, email], responses: [201, 422]}
      - {method: GET, path: "/bookings/{pnr}", responses: [200, 404]}
      - {method: GET, path: /bookings/search, responses: [200]}
      - {method: POST, path: "/bookings/{pnr}/cancel", responses: [200, 404, 409]}
"""

CRITERIA = """
criteria:
  - {id: AC-1, text: A booking can be made}
  - {id: AC-2, text: A booking can be cancelled}
"""
