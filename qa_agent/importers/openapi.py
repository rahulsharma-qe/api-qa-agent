"""OpenAPI 3 (JSON or YAML) -> the API model: paths, methods, summaries, required body fields and
documented response codes."""

import json
from pathlib import Path

import yaml

from qa_agent.api_model import Operation

METHODS = ("get", "post", "put", "patch", "delete")


class OpenApiError(Exception):
    """The file is not an OpenAPI 3 description qa-agent can read."""


def read_openapi(path: Path) -> list[Operation]:
    document = _load(path)
    if not isinstance(document, dict) or not str(document.get("openapi", "")).startswith("3"):
        raise OpenApiError(f"{path}: not an OpenAPI 3 description (no 'openapi: 3.x' at the top)")
    operations = []
    for route, methods in (document.get("paths") or {}).items():
        for method, operation in (methods or {}).items():
            if method not in METHODS or not isinstance(operation, dict):
                continue
            operations.append(Operation(
                method=method.upper(), path=route, summary=str(operation.get("summary") or ""),
                body_required=_required_body_fields(document, operation),
                responses=sorted(int(code) for code in (operation.get("responses") or {}) if str(code).isdigit())))
    return operations


def _load(path: Path):
    text = path.read_text(encoding="utf-8")
    try:
        return json.loads(text) if path.suffix == ".json" else yaml.safe_load(text)
    except (json.JSONDecodeError, yaml.YAMLError) as error:
        raise OpenApiError(f"{path}: can't be read ({error})") from error


def _required_body_fields(document: dict, operation: dict) -> list[str]:
    body = _resolve(document, operation.get("requestBody") or {})
    schema = _resolve(document, ((body.get("content") or {}).get("application/json") or {}).get("schema") or {})
    return [str(name) for name in schema.get("required") or []]


def _resolve(document: dict, node: dict, depth: int = 0) -> dict:
    """Follows a local $ref (#/components/schemas/NewBooking) to what it points at."""
    reference = node.get("$ref") if isinstance(node, dict) else None
    if not reference or depth > 10:
        return node if isinstance(node, dict) else {}
    target = document
    for part in reference.lstrip("#/").split("/"):
        target = target.get(part, {}) if isinstance(target, dict) else {}
    return _resolve(document, target, depth + 1)
