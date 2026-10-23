"""A Postman collection (v2.1 or v2.0) -> cases.

A folder of requests is one case: its requests are the steps, in order. A request outside a folder
is a case of its own. These test-script lines become expectations and captured values:

    pm.response.to.have.status(201)                         -> status
    pm.expect(pm.response.code).to.eql(201)                 -> status
    pm.expect(json.refund_amount).to.eql(250)               -> fields (also .equal, .to.be.eql)
    pm.expect(json.email).to.include("@")                   -> contains
    pm.expect(pm.response.responseTime).to.be.below(500)    -> max_response_ms
    pm.environment.set("pnr", json.pnr)                     -> capture (also collectionVariables, globals, variables)

Any other line is kept in the case's notes and reported, to be checked by hand. The host
({{baseUrl}}/...) is dropped from paths; Authorization and Cookie headers are never kept. Postman's
dynamic values ({{$guid}}, {{$randomInt}}, ...) become {{unique}}.
"""

import json
import re
from pathlib import Path

from qa_agent.importers.common import CaseImportError, ImportedFeature, ImportResult, leading_id

RESPONSE_JSON = re.compile(r"^(?:var|let|const)\s+(\w+)\s*=\s*pm\.response\.json\(\)\s*;?$")
STATUS = [re.compile(r"^pm\.response\.to\.have\.status\((\d{3})\)"),
          re.compile(r"^pm\.expect\(pm\.response\.code\)\.to\.(?:be\.)?(?:eql|equal)\((\d{3})\)")]
FIELD_EQUALS = re.compile(r"^pm\.expect\((\w+(?:\.\w+|\[\d+\])*)\)\.to\.(?:be\.)?(?:eql|equal)\((.+)\)\s*;?$")
FIELD_CONTAINS = re.compile(r"^pm\.expect\((\w+(?:\.\w+|\[\d+\])*)\)\.to\.(?:include|contain)\((.+)\)\s*;?$")
WITHIN = re.compile(r"^pm\.expect\(pm\.response\.responseTime\)\.to\.be\.below\((\d+)\)")
SET_VARIABLE = re.compile(r"^pm\.(?:environment|collectionVariables|globals|variables)\.set\(\s*[\"'](\w+)[\"']\s*,"
                          r"\s*(\w+(?:\.\w+|\[\d+\])*)\s*\)")
STRUCTURE = re.compile(r"^(?:pm\.test\(.*function\s*\(\)\s*\{|pm\.test\(.*=>\s*\{|\}\);?|\{|\}|//.*)$")
DROPPED_HEADERS = ("authorization", "cookie")
DYNAMIC = re.compile(r"\{\{\$\w+\}\}")                              # {{$guid}}, {{$randomInt}}


def read_postman_collection(path: Path, source_name: str) -> ImportResult:
    collection = _load(path)
    name = str(collection.get("info", {}).get("name") or path.stem)
    feature = ImportedFeature(name)
    result = ImportResult([feature])
    _walk(collection.get("item") or [], feature, result, source_name)
    return result


def _load(path: Path) -> dict:
    try:
        collection = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise CaseImportError(f"{path}: not valid JSON ({error})") from error
    schema = str(collection.get("info", {}).get("schema", "")) if isinstance(collection, dict) else ""
    if "collection/v2" not in schema:
        raise CaseImportError(f"{path}: not a Postman collection v2.0 or v2.1 (export it again as v2.1)")
    return collection


def _walk(items: list, feature: ImportedFeature, result: ImportResult, source: str) -> None:
    loose = []
    for item in items:
        if "item" in item:
            requests = [child for child in item["item"] if "request" in child]
            if requests:
                feature.cases.append(_case(item.get("name", ""), requests, result, source))
            _walk([child for child in item["item"] if "item" in child], feature, result, source)
        elif "request" in item:
            loose.append(item)
    for item in loose:
        feature.cases.append(_case(item.get("name", ""), [item], result, source))


def _case(name: str, requests: list, result: ImportResult, source: str) -> dict:
    case_id, title = leading_id(name)            # "TC030 Create and read"; None: the next free id on import
    notes, steps = [], []
    for number, item in enumerate(requests, start=1):
        step, unread = _step(item)
        steps.append(step)
        notes += [f"step {number}: {line}" for line in unread]
    for note in notes:
        result.notes.append(f"{source}, '{title}' {note}")
    case = {"id": case_id, "title": title or name, "criteria": [], "priority": "P2", "suite": "functional",
            "source": {"format": "postman", "file": source, "item": name}, "steps": steps}
    if notes:
        case["notes"] = "Not converted, check by hand: " + " | ".join(notes)
    return case


def _step(item: dict) -> tuple[dict, list[str]]:
    request = item["request"] if isinstance(item["request"], dict) else {"url": item["request"], "method": "GET"}
    request = json.loads(DYNAMIC.sub("{{unique}}", json.dumps(request)))
    path, query = _path_and_query(request.get("url"))
    step_request = {"method": str(request.get("method") or "GET").upper(), "path": path}
    if query:
        step_request["query"] = query
    headers = {h["key"]: h.get("value", "") for h in request.get("header") or []
               if not h.get("disabled") and h.get("key", "").lower() not in DROPPED_HEADERS + ("content-type", "accept")}
    if headers:
        step_request["headers"] = headers
    body = _body(request.get("body") or {})
    if body is not None:
        step_request["body"] = body
    if (request.get("auth") or {}).get("type") == "noauth":
        step_request["auth"] = "none"
    expect, capture, unread = _read_tests(item)
    step = {"name": item.get("name", "")} if item.get("name") else {}
    step["request"] = step_request
    step["expect"] = expect
    if capture:
        step["capture"] = capture
    return step, unread


def _path_and_query(url) -> tuple[str, dict]:
    if isinstance(url, dict):
        raw = url.get("raw") or ""
        query = {q["key"]: q.get("value", "") for q in url.get("query") or [] if not q.get("disabled")}
    else:
        raw, query = str(url or ""), {}
    raw, _, raw_query = raw.partition("?")
    if raw_query and not query:
        query = {name: value for name, _, value in (part.partition("=") for part in raw_query.split("&"))}
    raw = re.sub(r"^\{\{[^{}]+\}\}", "", raw)                          # {{baseUrl}}/bookings
    raw = re.sub(r"^[a-z]+://[^/]+", "", raw)                          # https://host/bookings
    path = "/" + raw.lstrip("/")
    path = re.sub(r"/:(\w+)", r"/{{\1}}", path)                        # /bookings/:pnr -> /bookings/{{pnr}}
    return path.rstrip("/") or "/", query


def _body(body: dict):
    if body.get("mode") != "raw" or not body.get("raw"):
        return None
    raw = body["raw"]
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        quoted = re.sub(r'(?<!")(\{\{[^{}]+\}\})(?!")', r'"\1"', raw)    # {"amount": {{amount}}} -> "{{amount}}"
        try:
            return json.loads(quoted)
        except json.JSONDecodeError:
            return raw


def _read_tests(item: dict) -> tuple[dict, dict, list[str]]:
    lines = [line.strip() for event in item.get("event") or [] if event.get("listen") == "test"
             for line in (event.get("script") or {}).get("exec") or [] if line.strip()]
    expect, capture, unread, names = {}, {}, [], {"__body__"}
    for line in lines:
        alias = RESPONSE_JSON.match(line)
        if alias:
            names.add(alias.group(1))
            continue
        if STRUCTURE.match(line):
            continue
        if not _read_line(_unwrap(line).replace("pm.response.json()", "__body__"), names, expect, capture):
            unread.append(line)
    return expect, capture, unread


def _unwrap(line: str) -> str:
    """pm.test("ok", () => pm.response.to.have.status(200)); -> pm.response.to.have.status(200)"""
    match = re.match(r"^pm\.test\(.*?(?:function\s*\(\)\s*\{|=>\s*\{?)\s*(pm\..*?);?\s*\}?\s*\)?;?$", line)
    return match.group(1) if match else line.rstrip(";")


def _read_line(line: str, names: set, expect: dict, capture: dict) -> bool:
    for pattern in STATUS:
        match = pattern.match(line)
        if match:
            expect["status"] = int(match.group(1))
            return True
    match = WITHIN.match(line)
    if match:
        expect["max_response_ms"] = int(match.group(1))
        return True
    for pattern, key in ((FIELD_EQUALS, "fields"), (FIELD_CONTAINS, "contains")):
        match = pattern.match(line)
        field_path = _field_path(match.group(1), names) if match else None
        if field_path:
            value = _value(match.group(2))
            if key == "contains" and not isinstance(value, str):
                return False
            expect.setdefault(key, {})[field_path] = value
            return True
    match = SET_VARIABLE.match(line)
    field_path = _field_path(match.group(2), names) if match else None
    if field_path:
        capture[match.group(1)] = field_path
        return True
    return False


def _field_path(expression: str, names: set) -> str:
    """json.items[0].pnr -> items[0].pnr, when json is the response body."""
    for name in names:
        if expression.startswith(name + "."):
            return expression[len(name) + 1:]
    return ""


def _value(text: str):
    text = text.strip()
    try:
        return json.loads(text.replace("'", '"') if text.startswith("'") else text)
    except json.JSONDecodeError:
        return text
