"""What every importer of existing cases shares: the result it returns, and the small readers of the
values teams write in their sheets (ids, priorities, lists, `name=value` pairs)."""

import re
from dataclasses import dataclass, field
from typing import Any, Optional

import yaml

PRIORITY_WORDS = {"blocker": "P0", "critical": "P0", "highest": "P0", "high": "P1", "major": "P1",
                  "medium": "P2", "normal": "P2", "low": "P3", "minor": "P3", "lowest": "P3", "trivial": "P3"}
LEADING_ID = re.compile(r"^\s*([A-Za-z]{1,10}-?\d{1,6})\b[\s:.\-–]*(.*)$")


class CaseImportError(Exception):
    """The file can't be read as cases at all (wrong format, no header qa-agent knows)."""


@dataclass
class ImportedFeature:
    """Cases for one feature file, as case dicts in the case format. A case with no id in its source
    has "id": None and gets the project's next free id on import; a case whose data came with it
    (a Gherkin outline's Examples) carries the rows under "_data_rows"."""
    feature: str
    cases: list = field(default_factory=list)


@dataclass
class ImportResult:
    features: list = field(default_factory=list)
    notes: list = field(default_factory=list)          # rows skipped, lines to check by hand


def slug(text: str) -> str:
    """'Bookings API' -> 'bookings-api': a file name."""
    return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-") or "cases"


def leading_id(name: str) -> tuple[Optional[str], str]:
    """'TC030 Create and read' -> ('TC030', 'Create and read'); 'Create and read' -> (None, ...)."""
    match = LEADING_ID.match(name or "")
    if match and any(c.isdigit() for c in match.group(1)) and match.group(2):
        return match.group(1).upper(), match.group(2).strip()
    return None, (name or "").strip()


def priority_from(value: Any) -> tuple[str, Optional[str]]:
    """P0-P3, or the words teams use (Critical, High, Medium, Low). Unknown -> P2, with a note."""
    text = str(value or "").strip()
    if not text:
        return "P2", None
    if text.upper() in ("P0", "P1", "P2", "P3"):
        return text.upper(), None
    if text.lower() in PRIORITY_WORDS:
        return PRIORITY_WORDS[text.lower()], None
    return "P2", f"priority '{text}' is not one qa-agent knows; set to P2"


def split_list(value: Any) -> list[str]:
    """'AC-1, AC-2' or 'AC-1; AC-2' or 'AC-1 AC-2' -> ['AC-1', 'AC-2']."""
    return [item for item in re.split(r"[,;\s]+", str(value or "").strip()) if item]


def parse_pairs(value: Any) -> dict:
    """'refund_allowed=true; refund_amount=250' -> {'refund_allowed': True, 'refund_amount': 250}."""
    pairs = {}
    for part in re.split(r"[;\n]+", str(value or "")):
        if "=" not in part:
            continue
        name, _, raw = part.partition("=")
        pairs[name.strip()] = scalar(raw.strip())
    return pairs


def scalar(text: str) -> Any:
    """A cell's text as the value it means: 250, true, null, or the text itself."""
    if text == "":
        return ""
    try:
        value = yaml.safe_load(text)
    except yaml.YAMLError:
        return text
    return value if isinstance(value, (str, int, float, bool)) or value is None else text
