"""What QA teams read after a run: the Allure report, the evidence folder, and which tests passed
only on retry.

Allure is used when allure-pytest is installed and the run asks for it (--alluredir); without it,
everything else works the same.
"""

import json
import re
from pathlib import Path
from typing import Optional

from api_test_framework.api_response import describe
from api_test_framework.scenario_context import ScenarioContext, Step

SEVERITY_BY_PRIORITY = {"P0": "blocker", "P1": "critical", "P2": "normal", "P3": "minor"}
PRIORITIES = tuple(SEVERITY_BY_PRIORITY)

try:
    import allure
except ImportError:          # Allure is optional
    allure = None


def allure_is_on(config) -> bool:
    return allure is not None and bool(getattr(config.option, "allure_report_dir", None))


def attach_step_to_allure(step: Step) -> None:
    request, response = step.response.request, step.response
    name = f"step {step.number}: {request.method} {request.url} -> {response.status_code}"
    body = {"request": {"method": request.method, "url": request.url, "headers": request.headers, "body": request.body},
            "response": {"status": response.status_code, "elapsed_ms": response.elapsed_ms,
                         "body": response.json if response.json is not None else response.body_text}}
    allure.attach(json.dumps(body, indent=2, default=str), name=name, attachment_type=allure.attachment_type.JSON)


def label_allure_test(case_id: Optional[str], priority: Optional[str]) -> None:
    if case_id:
        allure.dynamic.label("case_id", case_id)
        allure.dynamic.tag(f"case {case_id}")
    if priority:
        allure.dynamic.severity(SEVERITY_BY_PRIORITY[priority])
        allure.dynamic.tag(priority)


def write_evidence(folder, nodeid: str, outcome: str, case_id: Optional[str], attempt: int,
                   context: Optional[ScenarioContext], failure: str = "") -> Path:
    """One text file per test, pass or fail: what ran, the result, and every request and response."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (re.sub(r"[^A-Za-z0-9_.-]+", "_", nodeid).strip("_") + ".txt")
    lines = [f"test:    {nodeid}", f"case:    {case_id or '-'}", f"result:  {outcome}"
             + (f" (attempt {attempt})" if attempt > 1 else ""), ""]
    lines.append(context.history() if context is not None else "(this test made no API calls)")
    if failure:
        lines += ["", "failure:", failure]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def describe_last_step(context: Optional[ScenarioContext]) -> str:
    if context is None or not context.steps:
        return ""
    return describe(context.steps[-1].response)
