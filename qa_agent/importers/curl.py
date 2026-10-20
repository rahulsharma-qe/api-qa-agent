"""A curl command with a sample response -> one operation of the API model.

    curl -X POST https://qa1.example.com/bookings/AB12CD/cancel \\
      -H "Authorization: Bearer ..." -d '{"cancelled_at": "2026-10-21T10:00:00Z"}'
    ### response
    HTTP/1.1 200 OK
    {"pnr": "AB12CD", "refund_allowed": true, "refund_amount": 250}

Headers are not kept, so a token in the command never reaches the repository. A path part that
looks like a value (AB12CD, 1042, a UUID) becomes a parameter: /bookings/{id}/cancel.
"""

import re
import shlex
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from qa_agent.api_model import Operation

RESPONSE_MARKER = "### response"
STATUS_LINE = re.compile(r"^(?:HTTP/[\d.]+\s+)?(\d{3})\b")
UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
DATA_OPTIONS = ("-d", "--data", "--data-raw", "--data-binary", "--json")
OPTIONS_WITH_A_VALUE = ("-H", "--header", "-u", "--user", "-o", "--output", "-A", "--user-agent", "-b", "--cookie",
                        "-e", "--referer", "--connect-timeout", "-m", "--max-time")


class CurlError(Exception):
    """The file is not a curl command qa-agent can read."""


@dataclass
class CurlImport:
    operation: Operation
    parameters_found: list          # ["AB12CD -> {id}"], shown to the person so they can rename them


def read_curl(path: Path) -> CurlImport:
    text = path.read_text(encoding="utf-8")
    command, _, response = text.partition(RESPONSE_MARKER)
    tokens = _tokens(command, path)
    method, url, has_body = None, None, False
    index = 1
    while index < len(tokens):
        token = tokens[index]
        if token in ("-X", "--request") and index + 1 < len(tokens):
            method, index = tokens[index + 1].upper(), index + 2
        elif token in DATA_OPTIONS or token.startswith("--data"):
            has_body, index = True, index + 2
        elif token in OPTIONS_WITH_A_VALUE:
            index += 2
        elif token.startswith("-"):
            index += 1
        else:
            url, index = url or token, index + 1
    if not url:
        raise CurlError(f"{path}: no URL in the curl command")
    route, found = _with_parameters(urlparse(url if "://" in url else "http://host" + url).path or "/")
    status = _status(response)
    operation = Operation(method=method or ("POST" if has_body else "GET"), path=route,
                          responses=[status] if status else [])
    return CurlImport(operation, found)


def _tokens(command: str, path: Path) -> list[str]:
    try:
        tokens = shlex.split(command.replace("\\\n", " "))
    except ValueError as error:
        raise CurlError(f"{path}: the curl command can't be read ({error})") from error
    if not tokens or tokens[0] != "curl":
        raise CurlError(f"{path}: expected a command starting with 'curl'")
    return tokens


def _with_parameters(route: str) -> tuple[str, list[str]]:
    parts, found = [], []
    for part in route.rstrip("/").split("/"):
        if _looks_like_a_value(part):
            found.append(f"{part} -> {{id}}")
            part = "{id}"
        parts.append(part)
    return "/".join(parts) or "/", found


def _looks_like_a_value(part: str) -> bool:
    if part.isdigit() or UUID.match(part):
        return True
    return len(part) >= 5 and any(c.isdigit() for c in part) and any(c.isalpha() for c in part) \
        and part.isalnum()


def _status(response: str) -> int:
    for line in response.strip().splitlines():
        match = STATUS_LINE.match(line.strip())
        return int(match.group(1)) if match else 0
    return 0
