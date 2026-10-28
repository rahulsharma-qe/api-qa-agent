"""Test results from JUnit XML: pytest's --junitxml and Maven Surefire both write it.

A path may be a file or a folder of files (target/surefire-reports); other XML in a folder
(testng-results.xml) is skipped. A test's name loses its data-row suffix (test_x[row1], tcX[0](...)),
so a data-driven test gives one outcome per row under one name. Each run of a test is also kept
whole (`runs`): its full name with the row, the case id pytest records, and the failure message.
"""

import re
import xml.etree.ElementTree as ElementTree
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class TestRun:
    __test__ = False       # not a pytest test class
    name: str              # test_tc002_the_refund
    full_name: str         # test_tc002_the_refund[23 hours]: one data row
    outcome: str           # passed, failed, skipped
    message: str = ""      # the failure's first line
    case_id: str = ""      # from the case_id property, when the test records it


@dataclass
class Results:
    outcomes: dict = field(default_factory=dict)      # test name -> ["passed", "failed", ...]
    counts: dict = field(default_factory=dict)        # framework -> {"passed": n, ...}
    runs: list = field(default_factory=list)          # every TestRun, in file order
    unreadable: list = field(default_factory=list)    # files that aren't valid XML or can't be opened

    def for_names(self, names: list) -> list:
        return [outcome for name in names for outcome in self.outcomes.get(name, [])]

    @property
    def frameworks(self) -> set:
        return set(self.counts)


def read_results(paths: list) -> Results:
    results = Results()
    files = []
    for path in map(Path, paths):
        files += sorted(path.glob("*.xml")) if path.is_dir() else [path]
    for path in files:
        try:
            root = ElementTree.parse(path).getroot()
        except (ElementTree.ParseError, OSError):
            results.unreadable.append(path)
            continue
        if root.tag not in ("testsuite", "testsuites"):
            continue
        for case in root.iter("testcase"):
            full_name = case.get("name", "").strip()
            name = re.split(r"[\[(]", full_name, maxsplit=1)[0].strip()
            problem = case.find("failure") if case.find("failure") is not None else case.find("error")
            if problem is not None:
                outcome = "failed"
            elif case.find("skipped") is not None:
                outcome = "skipped"
            else:
                outcome = "passed"
            results.outcomes.setdefault(name, []).append(outcome)
            results.runs.append(TestRun(name, full_name, outcome, _first_line(problem), _case_id(case)))
            framework = "pytest" if name.startswith("test_") else "restassured"
            counts = results.counts.setdefault(framework, {})
            counts[outcome] = counts.get(outcome, 0) + 1
    return results


def _first_line(problem) -> str:
    if problem is None:
        return ""
    text = (problem.get("message") or problem.text or "").strip()
    if not text:
        return ""
    line = text.splitlines()[0].strip()
    return re.sub(r"^(?:\w+\.)+(\w+: )", r"\1", line)[:160]       # api_test_framework.expect.X: -> X:


def _case_id(case) -> str:
    for item in case.iter("property"):
        if item.get("name") == "case_id":
            return item.get("value", "")
    return ""
