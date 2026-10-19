"""What came back from one request, and `value()` to read any field by a dotted path:

    response.value("pnr")                 a top-level field
    response.value("items[0].pnr")        a field inside the first item of a list
"""

import json
import re
from dataclasses import dataclass, field
from typing import Any, Optional

_PART = re.compile(r"^([^\[\]]*)((?:\[\d+\])*)$")
_INDEX = re.compile(r"\[(\d+)\]")
MISSING = object()


class FieldNotFound(AssertionError):
    """A path that isn't in the response. Fails the test with the path and the body."""


@dataclass
class ApiRequest:
    method: str
    url: str
    body: Any = None
    headers: dict = field(default_factory=dict)    # the Authorization value is already masked


@dataclass
class ApiResponse:
    status_code: int
    body_text: str
    headers: dict
    elapsed_ms: int
    request: ApiRequest

    @property
    def json(self) -> Any:
        """The body as JSON, or None when it isn't JSON (or is empty)."""
        if not self.body_text:
            return None
        try:
            return json.loads(self.body_text)
        except ValueError:
            return None

    def value(self, path: str) -> Any:
        found = read_path(self.json, path)
        if found is MISSING:
            raise FieldNotFound(f"field '{path}' is not in the response\n{describe(self)}")
        return found

    def has(self, path: str) -> bool:
        return read_path(self.json, path) is not MISSING


def read_path(data: Any, path: str) -> Any:
    """Follow 'a.b[0].c' through dictionaries and lists; MISSING when any step isn't there."""
    current = data
    for part in path.split("."):
        match = _PART.match(part)
        if not match:
            return MISSING
        key, indexes = match.groups()
        if key:
            if not isinstance(current, dict) or key not in current:
                return MISSING
            current = current[key]
        for index in (int(i) for i in _INDEX.findall(indexes)):
            if not isinstance(current, list) or index >= len(current):
                return MISSING
            current = current[index]
    return current


def describe(response: Optional["ApiResponse"], limit: int = 500) -> str:
    """Two lines a person can read: the request, then what came back."""
    if response is None:
        return "  (no response)"
    request = response.request
    sent = f"  {request.method} {request.url}"
    if request.body is not None:
        sent += f"  {_short(json.dumps(request.body, default=str), limit)}"
    return f"{sent}\n  -> {response.status_code} {_short(response.body_text, limit)}  ({response.elapsed_ms} ms)"


def _short(text: str, limit: int) -> str:
    text = text or ""
    return text if len(text) <= limit else text[:limit] + f"... ({len(text) - limit} more characters)"
