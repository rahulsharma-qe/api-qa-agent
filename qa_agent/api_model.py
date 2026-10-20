"""The API model: one small file, api/api.yaml, whatever the team started from.

    services:
      bookings:
        operations:
          - {method: POST, path: /bookings, summary: Create a booking,
             body_required: [passenger_name, amount], responses: [201, 401, 422]}
          - {method: POST, path: "/bookings/{pnr}/cancel", responses: [200, 404, 409]}

Importers (OpenAPI, curl) write it; people may edit it; every other command reads only this.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from qa_agent.yaml_files import FileFormatError, read_yaml, write_yaml

PARAMETER = re.compile(r"^\{[^{}]+\}$")          # {pnr} in the API model
VALUE = re.compile(r"\{\{[^{}]+\}\}")             # {{pnr}} in a case


@dataclass
class Operation:
    method: str
    path: str
    summary: str = ""
    body_required: list = field(default_factory=list)
    responses: list = field(default_factory=list)

    @property
    def key(self) -> tuple[str, str]:
        """The same operation however its parameters are named: /bookings/{pnr} and /bookings/{id}."""
        return self.method, "/".join("{}" if PARAMETER.match(part) else part for part in self.path.split("/"))

    def to_dict(self) -> dict:
        data = {"method": self.method, "path": self.path}
        if self.summary:
            data["summary"] = self.summary
        if self.body_required:
            data["body_required"] = self.body_required
        data["responses"] = sorted(self.responses)
        return data


@dataclass
class ApiModel:
    services: dict = field(default_factory=dict)      # service name -> list of Operation

    def operations(self, service: str) -> list:
        return self.services.get(service, [])

    def find(self, service: str, method: str, path: str) -> Optional[Operation]:
        """The operation a case's request calls. A path may carry values (/bookings/{{pnr}}/cancel or
        /bookings/AB12CD/cancel); when two operations match, the one with more fixed parts wins
        (/bookings/search before /bookings/{pnr})."""
        parts = _parts(path)
        best, best_score = None, -1
        for operation in self.operations(service):
            if operation.method != method.upper():
                continue
            template = _parts(operation.path)
            if len(template) != len(parts):
                continue
            score = 0
            for expected, actual in zip(template, parts):
                if PARAMETER.match(expected):
                    continue
                if VALUE.search(actual) or expected != actual:
                    break
                score += 1
            else:
                if score > best_score:
                    best, best_score = operation, score
        return best

    def add(self, service: str, operation: Operation) -> bool:
        """Adds an operation, or merges its responses and required fields into the one already there.
        True when it was new."""
        existing = {op.key: op for op in self.services.setdefault(service, [])}
        if operation.key in existing:
            known = existing[operation.key]
            known.responses = sorted(set(known.responses) | set(operation.responses))
            known.body_required = known.body_required or operation.body_required
            known.summary = known.summary or operation.summary
            return False
        self.services[service].append(operation)
        return True

    def count(self) -> int:
        return sum(len(operations) for operations in self.services.values())

    def to_dict(self) -> dict:
        return {"services": {name: {"operations": [op.to_dict() for op in sorted(ops, key=_order)]}
                             for name, ops in sorted(self.services.items())}}


class ApiModelError(Exception):
    """api/api.yaml is not the shape of the API model."""


def load_api_model(path: Path) -> ApiModel:
    try:
        data = read_yaml(path)
    except FileFormatError as error:
        raise ApiModelError(str(error)) from error
    if not isinstance(data, dict) or not isinstance(data.get("services"), dict):
        raise ApiModelError(f"{path}: expected 'services:' with each service's 'operations'")
    model = ApiModel()
    for service, content in data["services"].items():
        operations = (content or {}).get("operations") or []
        for number, raw in enumerate(operations, start=1):
            if not isinstance(raw, dict) or not raw.get("method") or not str(raw.get("path", "")).startswith("/"):
                raise ApiModelError(f"{path}: {service} operation {number} needs a method and a path starting with /")
            model.add(str(service), Operation(
                method=str(raw["method"]).upper(), path=str(raw["path"]), summary=str(raw.get("summary") or ""),
                body_required=[str(name) for name in raw.get("body_required") or []],
                responses=[int(code) for code in raw.get("responses") or []]))
    return model


def save_api_model(model: ApiModel, path: Path) -> None:
    write_yaml(path, model.to_dict())


def _parts(path: str) -> list[str]:
    return path.split("?", 1)[0].rstrip("/").split("/")


METHOD_ORDER = ("GET", "POST", "PUT", "PATCH", "DELETE")


def _order(operation: Operation) -> tuple:
    method = METHOD_ORDER.index(operation.method) if operation.method in METHOD_ORDER else len(METHOD_ORDER)
    return operation.path, method
