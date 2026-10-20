"""Postman collections: folders become cases, test scripts become expectations and captures."""

import json

import pytest

from qa_agent.importers.common import CaseImportError
from qa_agent.importers.postman import read_postman_collection

SCHEMA = "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"


def script(*lines):
    return [{"listen": "test", "script": {"exec": list(lines)}}]


def collection(tmp_path, items, name="Bookings smoke"):
    path = tmp_path / "c.postman_collection.json"
    path.write_text(json.dumps({"info": {"name": name, "schema": SCHEMA}, "item": items}))
    return path


def test_a_folder_is_one_case_and_its_scripts_become_expectations(tmp_path):
    path = collection(tmp_path, [{"name": "TC030 Create and read", "item": [
        {"name": "Create", "request": {"method": "POST", "url": {"raw": "{{baseUrl}}/bookings"},
                                       "header": [{"key": "Authorization", "value": "Bearer {{token}}"},
                                                  {"key": "X-Channel", "value": "app"}],
                                       "body": {"mode": "raw", "raw": '{"name": "M {{$randomInt}}", "amount": {{amount}}}'}},
         "event": script('pm.test("created", function () {', "pm.response.to.have.status(201);", "});",
                        "var jsonData = pm.response.json();", 'pm.environment.set("pnr", jsonData.pnr);',
                        'pm.expect(jsonData.status).to.eql("active");')},
        {"name": "Read", "request": {"method": "GET", "url": "https://qa1.example.com/bookings/:pnr?full=1"},
         "event": script('pm.test("ok", () => pm.response.to.have.status(200));',
                        "pm.expect(pm.response.json().amount).to.eql(120);",
                        'pm.expect(pm.response.json().email).to.include("@");',
                        "pm.expect(pm.response.responseTime).to.be.below(500);",
                        "pm.expect(pm.response.json().name).to.match(/M/);")}]}])
    result = read_postman_collection(path, "existing/c.json")
    case = result.features[0].cases[0]
    create, read = case["steps"]
    assert (case["id"], case["title"]) == ("TC030", "Create and read")
    assert create["request"] == {"method": "POST", "path": "/bookings", "headers": {"X-Channel": "app"},
                                 "body": {"name": "M {{unique}}", "amount": "{{amount}}"}}
    assert create["expect"] == {"status": 201, "fields": {"status": "active"}}
    assert create["capture"] == {"pnr": "pnr"}
    assert read["request"] == {"method": "GET", "path": "/bookings/{{pnr}}", "query": {"full": "1"}}
    assert read["expect"] == {"status": 200, "fields": {"amount": 120}, "contains": {"email": "@"}, "within_ms": 500}
    assert "to.match(/M/)" in case["notes"] and "to.match(/M/)" in result.notes[0]


def test_a_request_outside_a_folder_is_a_case_whose_id_comes_on_import(tmp_path):
    path = collection(tmp_path, [{"name": "Health", "request": {"auth": {"type": "noauth"}, "method": "GET",
                                                                "url": {"raw": "{{baseUrl}}/health-check"}}}])
    case = read_postman_collection(path, "c.json").features[0].cases[0]
    assert (case["id"], case["title"]) == (None, "Health")
    assert case["steps"][0]["request"] == {"method": "GET", "path": "/health-check", "auth": "none"}


def test_a_file_that_is_not_a_v2_collection_is_refused(tmp_path):
    path = tmp_path / "x.json"
    path.write_text(json.dumps({"info": {"name": "x", "schema": "v1"}}))
    with pytest.raises(CaseImportError, match="not a Postman collection"):
        read_postman_collection(path, "x.json")
