import pytest

from api_test_framework.api_response import ApiRequest, ApiResponse, FieldNotFound

BODY = '{"pnr": "AB12CD", "items": [{"pnr": "X1", "tags": ["a", "b"]}], "nested": {"a": {"b": 0}}}'


def response(body=BODY, status=200):
    return ApiResponse(status, body, {}, 12, ApiRequest("GET", "http://svc.test/bookings"))


@pytest.mark.parametrize("path, expected", [
    ("pnr", "AB12CD"), ("items[0].pnr", "X1"), ("items[0].tags[1]", "b"), ("nested.a.b", 0),
])
def test_value_reads_any_field_by_path(path, expected):
    assert response().value(path) == expected


@pytest.mark.parametrize("path", ["missing", "items[3].pnr", "pnr.inner", "items.pnr", "nested.a.c"])
def test_a_missing_path_fails_with_the_path_and_the_body(path):
    with pytest.raises(FieldNotFound) as failure:
        response().value(path)
    assert f"field '{path}'" in str(failure.value) and "GET http://svc.test/bookings" in str(failure.value)


def test_json_is_none_for_an_empty_or_non_json_body():
    assert response("").json is None and response("<html>").json is None
    assert response().has("items[0].pnr") and not response().has("items[1]")
