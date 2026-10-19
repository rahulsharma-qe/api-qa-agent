"""Checks on a response, chained. Each failure says what was expected, what came back, and the
request that produced it:

    Expect(response).status_is(200).field_equals("refund_allowed", True).field_equals("refund_amount", 250)
"""

from typing import Any

from api_test_framework.api_response import MISSING, ApiResponse, describe, read_path

TYPES = {"string": (str,), "number": (int, float), "integer": (int,), "boolean": (bool,), "list": (list,),
         "object": (dict,), "null": (type(None),)}


class ExpectationFailed(AssertionError):
    """An expectation that didn't hold."""


class Expect:
    def __init__(self, response: ApiResponse):
        self.response = response

    def status_is(self, expected: int) -> "Expect":
        if self.response.status_code != expected:
            self._fail(f"expected status {expected}, got {self.response.status_code}")
        return self

    def field_equals(self, path: str, expected: Any) -> "Expect":
        actual = self._field(path)
        if not _same(actual, expected):
            self._fail(f"field '{path}': expected {expected!r}, got {actual!r}")
        return self

    def field_exists(self, path: str) -> "Expect":
        self._field(path)
        return self

    def field_is_type(self, path: str, type_name: str) -> "Expect":
        if type_name not in TYPES:
            raise ValueError(f"unknown type '{type_name}' (use one of: {', '.join(TYPES)})")
        actual = self._field(path)
        is_type = isinstance(actual, TYPES[type_name]) and not (isinstance(actual, bool) and type_name in ("number", "integer"))
        if not is_type:
            article = "an" if type_name[0] in "aeiou" else "a"
            self._fail(f"field '{path}': expected {article} {type_name}, got {type(actual).__name__} {actual!r}")
        return self

    def field_contains(self, path: str, text: str) -> "Expect":
        actual = self._field(path)
        if text not in str(actual):
            self._fail(f"field '{path}': expected it to contain {text!r}, got {actual!r}")
        return self

    def list_length(self, path: str, expected: int) -> "Expect":
        actual = self._field(path)
        if not isinstance(actual, list) or len(actual) != expected:
            got = len(actual) if isinstance(actual, list) else f"not a list ({type(actual).__name__})"
            self._fail(f"field '{path}': expected {expected} item(s), got {got}")
        return self

    def list_contains(self, path: str, **match) -> "Expect":
        """At least one item in the list has every given field: list_contains("items", pnr="AB12CD")."""
        items = self._field(path)
        if not isinstance(items, list) or not any(
                isinstance(item, dict) and all(_same(item.get(k), v) for k, v in match.items()) for item in items):
            self._fail(f"field '{path}': no item with {match}")
        return self

    def list_excludes(self, path: str, **match) -> "Expect":
        """No item in the list has every given field."""
        items = self._field(path)
        if isinstance(items, list) and any(
                isinstance(item, dict) and all(_same(item.get(k), v) for k, v in match.items()) for item in items):
            self._fail(f"field '{path}': expected no item with {match}, found one")
        return self

    def header_equals(self, name: str, expected: str) -> "Expect":
        headers = {key.lower(): value for key, value in self.response.headers.items()}
        actual = headers.get(name.lower())
        if actual != expected:
            self._fail(f"header '{name}': expected {expected!r}, got {actual!r}")
        return self

    def responded_within(self, milliseconds: int) -> "Expect":
        if self.response.elapsed_ms > milliseconds:
            self._fail(f"expected an answer within {milliseconds} ms, took {self.response.elapsed_ms} ms")
        return self

    def _field(self, path: str) -> Any:
        found = read_path(self.response.json, path)
        if found is MISSING:
            self._fail(f"field '{path}' is not in the response")
        return found

    def _fail(self, message: str) -> None:
        raise ExpectationFailed(f"{message}\n{describe(self.response)}")


def _same(actual: Any, expected: Any) -> bool:
    """Equal, treating 250 and 250.0 as the same number but never True as 1."""
    if isinstance(actual, bool) or isinstance(expected, bool):
        return type(actual) is type(expected) and actual == expected
    return actual == expected
