"""Test results from JUnit XML: pytest's --junitxml and Maven Surefire both write it.

A path may be a file or a folder of files (target/surefire-reports); other XML in a folder
(testng-results.xml) is skipped. A test's name loses its data-row suffix (test_x[row1], tcX[0](...)),
so a data-driven test gives one outcome per row under one name.
"""

import re
import xml.etree.ElementTree as ElementTree
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Results:
    outcomes: dict = field(default_factory=dict)      # test name -> ["passed", "failed", ...]
    counts: dict = field(default_factory=dict)        # framework -> {"passed": n, ...}

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
            continue
        if root.tag not in ("testsuite", "testsuites"):
            continue
        for case in root.iter("testcase"):
            name = re.split(r"[\[(]", case.get("name", ""), maxsplit=1)[0].strip()
            if case.find("failure") is not None or case.find("error") is not None:
                outcome = "failed"
            elif case.find("skipped") is not None:
                outcome = "skipped"
            else:
                outcome = "passed"
            results.outcomes.setdefault(name, []).append(outcome)
            framework = "pytest" if name.startswith("test_") else "restassured"
            counts = results.counts.setdefault(framework, {})
            counts[outcome] = counts.get(outcome, 0) + 1
    return results
