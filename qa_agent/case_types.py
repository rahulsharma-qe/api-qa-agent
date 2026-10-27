"""The type of a case, read from what the case already says: no new field to fill in.

    positive   every step expects a 2xx or 3xx: the call works
    negative   a step expects a 4xx or 5xx (other than 401 and 403): wrong input is refused
    auth       a step expects 401 or 403: no token, or not allowed
    edge       the case is tagged edge or boundary: a limit, such as exactly 24 hours

A case that is refused and then reads the booking back to see nothing changed (422, then 200) is
negative: the steps that succeed set up or confirm. A data-driven case whose status comes from its
data file ({{row.expected_status}}) has the type of every row: a file with a 200 row and a 404 row is
positive and negative. Edge comes on top of the others: a refund at exactly 24 hours is positive and
edge. A case in words (no steps) or with a status still TBD has no type yet.
"""

import re

from qa_agent.cases import Case
from qa_agent.data_files import DataFileError, rows

TYPES = ("positive", "negative", "auth", "edge")
EDGE_TAGS = ("edge", "boundary")
NOT_HAPPY = ("negative", "auth", "edge")


def case_types(case: Case, project) -> set:
    fixed, from_rows, row_steps = set(), set(), 0
    for step in case.steps:
        status = step.expect.get("status")
        if isinstance(status, int):
            fixed.add(status)
        else:
            row_steps += 1
            from_rows |= expected_statuses(status, case, project)
    found = set()
    for status in fixed | from_rows:
        if status in (401, 403):
            found.add("auth")
        elif status >= 400:
            found.add("negative")
    if fixed | from_rows and all(status < 400 for status in fixed) and (
            not row_steps or any(status < 400 for status in from_rows)):
        found.add("positive")
    if found and {tag.lower() for tag in case.tags} & set(EDGE_TAGS):
        found.add("edge")
    return found


def label(types: set) -> str:
    return ", ".join(kind for kind in TYPES if kind in types) or "-"


def expected_statuses(status, case: Case, project) -> set:
    """The status a step expects; for {{row.x}}, every value of column x in the case's data file."""
    if isinstance(status, int):
        return {status}
    match = re.match(r"^\{\{\s*row\.(\w+)\s*\}\}$", str(status or ""))
    if not match or not case.data_file:
        return set()
    try:
        values = [row.get(match.group(1)) for row in rows(project.root / case.data_file)]
    except DataFileError:
        return set()
    return {int(float(value)) for value in values if str(value).strip().replace(".0", "").isdigit()}
