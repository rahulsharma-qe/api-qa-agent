"""The case format: test cases as data, one file per feature.

    feature: Cancellation and refund
    cases:
      - id: TC003
        title: Cancel exactly at 24 hours gets a full refund
        criteria: [AC-2]
        priority: P1
        steps:
          - request: {method: POST, path: /bookings, body: {...}}
            expect: {status: 201}
            capture: {pnr: pnr}
          - request: {method: POST, path: "/bookings/{{pnr}}/cancel", body: {...}}
            expect: {status: 200, fields: {refund_amount: 250}}

Loading checks the shape and reports every problem at once; `checks.py` then checks the meaning
(paths against the API, values captured before use, criteria).
"""

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from qa_agent.yaml_files import FileFormatError, read_yaml, write_yaml

METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE")
PRIORITIES = ("P0", "P1", "P2", "P3")
SUITES = ("functional", "regression")
REVIEW_STATUSES = ("draft", "approved", "changes_needed", "rejected")
TYPE_NAMES = ("string", "number", "integer", "boolean", "list", "object", "null")
EXPECTATIONS = ("status", "fields", "exists", "types", "contains", "list_length", "list_contains",
                "list_excludes", "headers", "max_response_ms")
NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
ROW_VALUE = re.compile(r"^\{\{\s*row\.[^{}]+\}\}$")       # {{row.expected_status}}: a value from the data file
RESERVED_NAMES = ("unique", "row")

CASE_KEYS = ("id", "title", "criteria", "priority", "suite", "tags", "data_file", "source", "steps", "manual_steps",
             "notes", "review")
STEP_KEYS = ("name", "request", "expect", "capture")
REQUEST_KEYS = ("method", "path", "query", "headers", "body", "service", "auth")
REVIEW_KEYS = ("status", "by", "date", "comment", "fingerprint")


class CaseFormatError(Exception):
    """A case file doesn't have the shape of the case format. Holds every problem found."""

    def __init__(self, path: Path, problems: list[str]):
        super().__init__(f"{path}: " + "; ".join(problems))
        self.path, self.problems = path, problems


@dataclass
class Request:
    method: str
    path: str
    query: dict = field(default_factory=dict)
    headers: dict = field(default_factory=dict)
    body: Any = None
    service: Optional[str] = None       # None: the project's main service
    auth: Optional[str] = None          # "none": a call without a token

    def to_dict(self) -> dict:
        data = {"method": self.method, "path": self.path}
        for key in ("query", "headers", "body", "service", "auth"):
            value = getattr(self, key)
            if value not in (None, {}, []):
                data[key] = value
        return data


@dataclass
class Step:
    request: Request
    expect: dict = field(default_factory=dict)
    capture: dict = field(default_factory=dict)
    name: Optional[str] = None

    def to_dict(self) -> dict:
        data = {"name": self.name} if self.name else {}
        data["request"] = self.request.to_dict()
        if self.expect:
            data["expect"] = self.expect
        if self.capture:
            data["capture"] = self.capture
        return data


@dataclass
class Review:
    status: str = "draft"
    by: str = ""
    date: str = ""
    comment: str = ""
    fingerprint: str = ""

    def to_dict(self) -> dict:
        return {key: getattr(self, key) for key in REVIEW_KEYS if getattr(self, key) or key == "status"}


@dataclass
class Case:
    id: str
    title: str
    criteria: list = field(default_factory=list)
    priority: str = "P2"
    suite: str = "functional"
    tags: list = field(default_factory=list)
    data_file: Optional[str] = None
    source: dict = field(default_factory=dict)
    steps: list = field(default_factory=list)
    manual_steps: list = field(default_factory=list)
    notes: str = ""
    review: Review = field(default_factory=Review)

    def fingerprint(self) -> str:
        """A hash of what the test does (id, steps, data file). Editing any of it after approval shows up."""
        # The names inside are the ones the format had when approvals began (data, steps_text, within_ms):
        # renaming a field in the file must not change the fingerprint of a case already approved.
        steps = [_with_names_at_approval(step.to_dict()) for step in self.steps]
        content = {"id": self.id, "steps": steps, "data": self.data_file, "steps_text": self.manual_steps}
        return hashlib.sha256(json.dumps(content, sort_keys=True, default=str).encode()).hexdigest()[:12]

    @property
    def needs_steps(self) -> bool:
        return not self.steps and bool(self.manual_steps)

    @property
    def is_approved(self) -> bool:
        """Approved, and unchanged since: the only cases that become code."""
        return self.review.status == "approved" and self.review.fingerprint == self.fingerprint()

    @property
    def changed_after_approval(self) -> bool:
        return self.review.status == "approved" and self.review.fingerprint != self.fingerprint()

    def to_dict(self) -> dict:
        data = {"id": self.id, "title": self.title, "criteria": self.criteria, "priority": self.priority,
                "suite": self.suite}
        for key in ("tags", "data_file", "source", "notes"):
            if getattr(self, key):
                data[key] = getattr(self, key)
        if self.steps:
            data["steps"] = [step.to_dict() for step in self.steps]
        if self.manual_steps:
            data["manual_steps"] = self.manual_steps
        data["review"] = self.review.to_dict()
        return data


FIELD_NAMES_AT_APPROVAL = {"max_response_ms": "within_ms"}       # the expectation's name now -> in fingerprints


def _with_names_at_approval(step: dict) -> dict:
    expect = {FIELD_NAMES_AT_APPROVAL.get(key, key): value for key, value in step.get("expect", {}).items()}
    return {**step, "expect": expect} if "expect" in step else step


@dataclass
class CaseFile:
    path: Path
    feature: str
    cases: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"feature": self.feature, "cases": [case.to_dict() for case in self.cases]}


def load_case_file(path: Path) -> CaseFile:
    try:
        data = read_yaml(path)
    except FileFormatError as error:
        raise CaseFormatError(path, [str(error)]) from error
    return parse_case_file(data, path)


def save_case_file(case_file: CaseFile) -> None:
    write_yaml(case_file.path, case_file.to_dict())


def parse_case_file(data: Any, path: Path) -> CaseFile:
    problems: list[str] = []
    if not isinstance(data, dict) or not isinstance(data.get("cases"), list):
        raise CaseFormatError(path, ["expected 'feature:' and 'cases:' with a list of cases"])
    _unknown_keys(data, ("feature", "cases"), "the file", problems)
    cases, seen = [], set()
    for number, entry in enumerate(data["cases"], start=1):
        case = _parse_case(entry, number, problems)
        if case is None:
            continue
        if case.id in seen:
            problems.append(f"{case.id}: the id is used twice in this file")
        seen.add(case.id)
        cases.append(case)
    if problems:
        raise CaseFormatError(path, problems)
    return CaseFile(path, str(data.get("feature") or path.stem), cases)


def _parse_case(entry: Any, number: int, problems: list[str]) -> Optional[Case]:
    if not isinstance(entry, dict) or not entry.get("id"):
        problems.append(f"case {number}: needs an 'id'")
        return None
    case_id = str(entry["id"])
    _unknown_keys(entry, CASE_KEYS, case_id, problems)
    if not entry.get("title"):
        problems.append(f"{case_id}: needs a 'title'")
    priority = str(entry.get("priority", "P2"))
    if priority not in PRIORITIES:
        problems.append(f"{case_id}: priority '{priority}' (use {', '.join(PRIORITIES)})")
    suite = str(entry.get("suite", "functional"))
    if suite not in SUITES:
        problems.append(f"{case_id}: suite '{suite}' (use {' or '.join(SUITES)})")
    steps = [_parse_step(raw, f"{case_id} step {index}", problems)
             for index, raw in enumerate(_as_list(entry.get("steps"), f"{case_id}: 'steps'", problems), start=1)]
    manual_steps = entry.get("manual_steps") or []
    return Case(
        id=case_id, title=str(entry.get("title", "")),
        criteria=[str(item) for item in _as_list(entry.get("criteria"), f"{case_id}: 'criteria'", problems)],
        priority=priority, suite=suite,
        tags=[str(item) for item in _as_list(entry.get("tags"), f"{case_id}: 'tags'", problems)],
        data_file=str(entry["data_file"]) if entry.get("data_file") else None,
        source=entry.get("source") if isinstance(entry.get("source"), dict) else {},
        steps=[step for step in steps if step is not None],
        manual_steps=[manual_steps] if isinstance(manual_steps, str) else [str(line) for line in manual_steps],
        notes=str(entry.get("notes") or ""),
        review=_parse_review(entry.get("review"), case_id, problems))


def _parse_step(raw: Any, where: str, problems: list[str]) -> Optional[Step]:
    if not isinstance(raw, dict) or not isinstance(raw.get("request"), dict):
        problems.append(f"{where}: needs a 'request' with a method and a path")
        return None
    _unknown_keys(raw, STEP_KEYS, where, problems)
    request = raw["request"]
    _unknown_keys(request, REQUEST_KEYS, f"{where} request", problems)
    method = str(request.get("method", "")).upper()
    if method not in METHODS:
        problems.append(f"{where}: method '{request.get('method')}' (use {', '.join(METHODS)})")
    path = str(request.get("path", ""))
    if not path.startswith("/"):
        problems.append(f"{where}: path '{path}' must start with /")
    if request.get("auth") not in (None, "none"):
        problems.append(f"{where}: auth '{request.get('auth')}' (only 'none' is allowed: a call without a token)")
    for key in ("query", "headers"):
        if not isinstance(request.get(key, {}), dict):
            problems.append(f"{where}: '{key}' must be a mapping of names to values")
    expect = raw.get("expect") or {}
    capture = raw.get("capture") or {}
    _check_expect(expect, where, problems)
    if not isinstance(capture, dict):
        problems.append(f"{where}: 'capture' must map a name to a path in the response")
        capture = {}
    for name in capture:
        if not NAME.match(str(name)) or str(name) in RESERVED_NAMES:
            problems.append(f"{where}: capture name '{name}' (letters, digits and _; not 'unique' or 'row')")
    return Step(Request(method, path, dict(request.get("query") or {}), dict(request.get("headers") or {}),
                        request.get("body"), request.get("service"), request.get("auth")),
                dict(expect) if isinstance(expect, dict) else {}, {str(k): str(v) for k, v in capture.items()},
                raw.get("name"))


def _check_expect(expect: Any, where: str, problems: list[str]) -> None:
    if not isinstance(expect, dict):
        problems.append(f"{where}: 'expect' must be a mapping")
        return
    _unknown_keys(expect, EXPECTATIONS, f"{where} expect", problems)
    shapes = {
        "status": lambda v: (isinstance(v, int) and not isinstance(v, bool) and 100 <= v <= 599)
        or (isinstance(v, str) and bool(ROW_VALUE.match(v))),
        "max_response_ms": lambda v: isinstance(v, int) and not isinstance(v, bool) and v > 0,
        "exists": lambda v: isinstance(v, list) and all(isinstance(item, str) for item in v),
        "fields": lambda v: isinstance(v, dict),
        "types": lambda v: isinstance(v, dict) and all(item in TYPE_NAMES for item in v.values()),
        "contains": lambda v: isinstance(v, dict) and all(isinstance(item, str) for item in v.values()),
        "list_length": lambda v: isinstance(v, dict) and all(isinstance(item, int) for item in v.values()),
        "list_contains": lambda v: isinstance(v, dict) and all(isinstance(item, dict) for item in v.values()),
        "list_excludes": lambda v: isinstance(v, dict) and all(isinstance(item, dict) for item in v.values()),
        "headers": lambda v: isinstance(v, dict),
    }
    hints = {"status": "a status code such as 201, or {{row.column}} in a data-driven case", "max_response_ms": "milliseconds, a whole number",
             "exists": "a list of paths", "fields": "path: expected value",
             "types": f"path: one of {', '.join(TYPE_NAMES)}", "contains": "path: text",
             "list_length": "path: a whole number", "list_contains": "path: {field: value}",
             "list_excludes": "path: {field: value}", "headers": "name: value"}
    for key, value in expect.items():
        if key in shapes and not shapes[key](value):
            problems.append(f"{where}: expect '{key}' should be {hints[key]}")


def _parse_review(raw: Any, case_id: str, problems: list[str]) -> Review:
    if raw is None:
        return Review()
    if not isinstance(raw, dict):
        problems.append(f"{case_id}: 'review' must be a mapping")
        return Review()
    _unknown_keys(raw, REVIEW_KEYS, f"{case_id} review", problems)
    review = Review(**{key: str(raw.get(key) or "") for key in REVIEW_KEYS})
    review.status = review.status or "draft"
    if review.status not in REVIEW_STATUSES:
        problems.append(f"{case_id}: review status '{review.status}' (use {', '.join(REVIEW_STATUSES)})")
    return review


def _as_list(value: Any, where: str, problems: list[str]) -> list:
    if value is None:
        return []
    if not isinstance(value, list):
        problems.append(f"{where} must be a list")
        return []
    return value


def _unknown_keys(mapping: dict, allowed: tuple, where: str, problems: list[str]) -> None:
    for key in mapping:
        if key not in allowed:
            problems.append(f"{where}: unknown key '{key}' (allowed: {', '.join(allowed)})")
