import pytest

from api_test_framework import Expect, ExpectationFailed
from api_test_framework.api_response import ApiRequest, ApiResponse

BODY = '{"pnr": "AB12CD", "amount": 250.0, "refund_allowed": true, "count": 1, "items": [{"pnr": "AB12CD", "status": "cancelled"}]}'


def expect(body=BODY, status=200, headers=None, elapsed=40):
    return Expect(ApiResponse(status, body, headers or {"Content-Type": "application/json"}, elapsed,
                              ApiRequest("POST", "http://svc.test/bookings", {"amount": 250})))


def test_passing_checks_chain():
    (expect().status_is(200).field_equals("amount", 250).field_equals("refund_allowed", True)
     .field_exists("pnr").field_is_type("amount", "number").field_is_type("items", "list")
     .field_contains("pnr", "AB").list_length("items", 1).list_contains("items", pnr="AB12CD", status="cancelled")
     .list_excludes("items", pnr="ZZ0000").header_equals("content-type", "application/json").responded_within(100))


@pytest.mark.parametrize("check, message", [
    (lambda e: e.status_is(201), "expected status 201, got 200"),
    (lambda e: e.field_equals("amount", 99), "field 'amount': expected 99, got 250.0"),
    (lambda e: e.field_equals("count", True), "field 'count': expected True, got 1"),       # 1 is not True
    (lambda e: e.field_exists("missing"), "field 'missing' is not in the response"),
    (lambda e: e.field_is_type("refund_allowed", "integer"), "expected an integer, got bool"),
    (lambda e: e.field_contains("pnr", "ZZ"), "expected it to contain 'ZZ'"),
    (lambda e: e.list_length("items", 2), "expected 2 item(s), got 1"),
    (lambda e: e.list_contains("items", pnr="ZZ0000"), "no item with {'pnr': 'ZZ0000'}"),
    (lambda e: e.list_excludes("items", pnr="AB12CD"), "expected no item with {'pnr': 'AB12CD'}"),
    (lambda e: e.header_equals("X-Trace", "1"), "header 'X-Trace': expected '1', got None"),
    (lambda e: e.responded_within(10), "expected an answer within 10 ms, took 40 ms"),
])
def test_each_failure_says_what_and_shows_the_request(check, message):
    with pytest.raises(ExpectationFailed) as failure:
        check(expect())
    text = str(failure.value)
    assert message in text
    assert 'POST http://svc.test/bookings  {"amount": 250}' in text and "-> 200" in text


def test_an_unknown_type_name_is_a_mistake_in_the_test():
    with pytest.raises(ValueError, match="unknown type 'text'"):
        expect().field_is_type("pnr", "text")
