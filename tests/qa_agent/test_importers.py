"""API descriptions in: OpenAPI 3 (JSON and YAML, with $ref) and curl with a sample response."""

import json

import pytest

from qa_agent.importers.curl import CurlError, read_curl
from qa_agent.importers.openapi import OpenApiError, read_openapi

OPENAPI = {
    "openapi": "3.1.0", "info": {"title": "t", "version": "1"},
    "paths": {"/bookings": {"post": {"summary": "Create", "requestBody": {"content": {"application/json": {
                  "schema": {"$ref": "#/components/schemas/NewBooking"}}}},
                  "responses": {"201": {}, "422": {}, "default": {}}}},
              "/bookings/{pnr}": {"get": {"responses": {"200": {}, "404": {}}}, "parameters": []}},
    "components": {"schemas": {"NewBooking": {"type": "object", "required": ["passenger_name", "amount"]}}}}


def test_openapi_gives_methods_paths_required_fields_and_response_codes(tmp_path):
    path = tmp_path / "openapi.json"
    path.write_text(json.dumps(OPENAPI))
    operations = {(op.method, op.path): op for op in read_openapi(path)}
    create = operations[("POST", "/bookings")]
    assert (create.summary, create.body_required, create.responses) == ("Create", ["passenger_name", "amount"], [201, 422])
    assert operations[("GET", "/bookings/{pnr}")].responses == [200, 404]
    assert len(operations) == 2                                   # 'parameters' is not a method


def test_openapi_in_yaml_reads_the_same(tmp_path):
    import yaml
    path = tmp_path / "openapi.yaml"
    path.write_text(yaml.safe_dump(OPENAPI))
    assert len(read_openapi(path)) == 2


def test_a_file_that_is_not_openapi_3_is_refused(tmp_path):
    path = tmp_path / "swagger.json"
    path.write_text(json.dumps({"swagger": "2.0"}))
    with pytest.raises(OpenApiError, match="not an OpenAPI 3"):
        read_openapi(path)


def test_curl_gives_the_method_the_path_with_parameters_and_the_status(tmp_path):
    path = tmp_path / "cancel.curl"
    path.write_text('curl -X POST https://qa1.example.com/bookings/AB12CD/cancel \\\n'
                    '  -H "Authorization: Bearer secret-token" \\\n'
                    "  -d '{\"cancelled_at\": \"2026-10-21T10:00:00Z\"}'\n\n"
                    "### response\nHTTP/1.1 200 OK\n{\"refund_amount\": 250}\n")
    imported = read_curl(path)
    assert (imported.operation.method, imported.operation.path, imported.operation.responses) == \
        ("POST", "/bookings/{id}/cancel", [200])
    assert imported.parameters_found == ["AB12CD -> {id}"]
    assert "secret-token" not in repr(imported)                   # headers are never kept


def test_curl_with_data_and_no_method_is_a_post_and_without_data_a_get(tmp_path):
    post, get = tmp_path / "a.curl", tmp_path / "b.curl"
    post.write_text("curl https://h/bookings --data-raw '{}'\n### response\n201\n")
    get.write_text("curl 'https://h/bookings/1042?x=1'\n")
    assert (read_curl(post).operation.method, read_curl(post).operation.responses) == ("POST", [201])
    assert (read_curl(get).operation.method, read_curl(get).operation.path, read_curl(get).operation.responses) == \
        ("GET", "/bookings/{id}", [])


def test_a_file_that_is_not_a_curl_command_is_refused(tmp_path):
    path = tmp_path / "x.curl"
    path.write_text("wget https://h/bookings\n")
    with pytest.raises(CurlError, match="starting with 'curl'"):
        read_curl(path)
