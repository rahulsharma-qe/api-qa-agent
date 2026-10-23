"""Gherkin (.feature) -> cases. One scenario is one case.

Tags: @TC040 is the case id, @AC-2 a criterion, @P0 to @P3 the priority, any other tag a tag.
A scenario with no id tag gets the project's next free id on import.

A scenario whose every step uses the fixed phrasing below becomes runnable steps; phase 3c
generates feature files in the same phrasing, so a feature file can go both ways:

    When I POST "/bookings" with            (a doc string body follows; "with" is optional)
    Then the status is 201
    And "refund_amount" is 250              (a JSON value: 250, true, "text")
    And I remember "pnr" as "pnr"           (a name, then a path in the response)

Any other scenario is kept in words (manual_steps): traced, "needs steps". A Scenario Outline's
Examples become the case's data file, and <column> becomes {{row.column}}.
"""

import json
import re
from pathlib import Path

from qa_agent.importers.common import CaseImportError, ImportedFeature, ImportResult

KEYWORD = re.compile(r"^(Given|When|Then|And|But|\*)\s+(.*)$")
REQUEST = re.compile(r'^I (GET|POST|PUT|PATCH|DELETE) "([^"]+)"(?: with)?$')
STATUS = re.compile(r"^the status is (\d{3}|\{\{row\.\w+\}\})$")
FIELD = re.compile(r'^"([^"]+)" is (.+)$')
REMEMBER = re.compile(r'^I remember "(\w+)" as "([^"]+)"$')
CASE_ID_TAG = re.compile(r"^@(TC-?\d+)$", re.IGNORECASE)
OUTLINE_VALUE = re.compile(r"<(\w+)>")


def read_feature_file(path: Path, source_name: str) -> ImportResult:
    lines = path.read_text(encoding="utf-8").splitlines()
    feature_name = next((line.split(":", 1)[1].strip() for line in lines if line.strip().startswith("Feature:")), None)
    if not feature_name:
        raise CaseImportError(f"{path}: no 'Feature:' line")
    feature = ImportedFeature(feature_name)
    result = ImportResult([feature])
    background, scenarios = _scenarios(lines)
    for scenario in scenarios:
        feature.cases.append(_case(scenario, background, source_name, result))
    return result


def _scenarios(lines: list[str]) -> tuple[list, list]:
    """Background steps, and each scenario: its tags, name, steps (with doc strings) and examples."""
    background, scenarios, current, tags, in_doc, section = [], [], None, [], False, None
    feature_tags: list[str] = []          # tags above Feature: apply to every scenario
    for raw in lines:
        line = raw.strip()
        if line.startswith('"""'):
            in_doc = not in_doc
            if in_doc:
                _target(current, background, section)[-1]["doc"] = []
            continue
        if in_doc:
            _target(current, background, section)[-1]["doc"].append(raw.strip())
            continue
        if not line or line.startswith("#"):
            continue
        if line.startswith("@"):
            tags += line.split()
        elif line.startswith("Feature:"):
            feature_tags, tags = tags, []
        elif line.startswith("Background:"):
            section = "background"
        elif line.startswith(("Scenario:", "Scenario Outline:", "Scenario Template:")):
            current = {"tags": feature_tags + tags, "name": line.split(":", 1)[1].strip(), "steps": [], "examples": [],
                       "outline": "Outline" in line or "Template" in line}
            scenarios.append(current)
            tags, section = [], "scenario"
        elif line.startswith(("Examples:", "Scenarios:")):
            section = "examples"
        elif line.startswith("|") and section == "examples" and current is not None:
            current["examples"].append([cell.strip() for cell in line.strip("|").split("|")])
        elif KEYWORD.match(line):
            keyword, text = KEYWORD.match(line).groups()
            _target(current, background, section).append({"keyword": keyword, "text": text})
    return background, scenarios


def _target(current, background, section):
    return background if section == "background" or current is None else current["steps"]


def _case(scenario: dict, background: list, source: str, result: ImportResult) -> dict:
    case_id, criteria, priority, tags = None, [], "P2", []
    for tag in scenario["tags"]:
        if CASE_ID_TAG.match(tag):
            case_id = CASE_ID_TAG.match(tag).group(1).upper()
        elif tag.upper().startswith("@AC-"):
            criteria.append(tag[1:].upper())
        elif tag.upper() in ("@P0", "@P1", "@P2", "@P3"):
            priority = tag[1:].upper()
        else:
            tags.append(tag[1:])
    case = {"id": case_id, "title": scenario["name"], "criteria": criteria, "priority": priority,
            "track": "functional"}
    if tags:
        case["tags"] = tags
    case["source"] = {"format": "gherkin", "file": source, "scenario": scenario["name"]}
    all_steps = background + scenario["steps"]
    steps = _runnable_steps(all_steps, scenario["outline"])
    if steps is None:
        case["manual_steps"] = [f"{step['keyword']} {step['text']}" for step in all_steps]
        result.notes.append(f"{source}, '{scenario['name']}': not in the fixed phrasing; kept in words (needs steps)")
        return case
    case["steps"] = steps
    if scenario["outline"] and len(scenario["examples"]) > 1:
        header, *rows = scenario["examples"]
        case["_data_rows"] = [dict(zip(header, row)) for row in rows]      # written to data/ on import
    return case


def _runnable_steps(steps: list, outline: bool):
    """The steps in the case format, or None when any step is not in the fixed phrasing."""
    runnable = []
    for step in steps:
        text = OUTLINE_VALUE.sub(r"{{row.\1}}", step["text"]) if outline else step["text"]
        request = REQUEST.match(text)
        if request:
            new = {"request": {"method": request.group(1), "path": request.group(2)}, "expect": {}}
            if step.get("doc"):
                body = OUTLINE_VALUE.sub(r"{{row.\1}}", "\n".join(step["doc"])) if outline else "\n".join(step["doc"])
                try:
                    new["request"]["body"] = json.loads(body)
                except json.JSONDecodeError:
                    return None
            runnable.append(new)
            continue
        if not runnable:
            return None
        last = runnable[-1]
        status, field, remember = STATUS.match(text), FIELD.match(text), REMEMBER.match(text)
        if status:
            value = status.group(1)
            last["expect"]["status"] = int(value) if value.isdigit() else value
        elif field:
            last["expect"].setdefault("fields", {})[field.group(1)] = _value(field.group(2))
        elif remember:
            last.setdefault("capture", {})[remember.group(1)] = remember.group(2)
        else:
            return None
    return runnable or None


def _value(text: str):
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text.strip()
