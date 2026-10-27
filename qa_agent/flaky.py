"""`qa-agent flaky`: the tests that passed in some runs and failed in others, on the same code.

    qa-agent flaky --runs reports/run1.xml reports/run2.xml reports/run3.xml

A flaky test costs reruns and teaches a team to ignore red, until the red is a real bug. This names
each one with its case and its last failure, so someone fixes the test, the data or the bug. It
lists and changes nothing: promote already keeps a case that failed in a run out of regression.

Runs are compared test by test, and a data-driven test row by row. Give runs of the same build: a
test that starts failing after a code change is a change, not flakiness. At least two runs, with
tests in common. A test that failed in every run is listed apart: failing, not flaky. A skipped run
counts neither way. Exit 0: it reports, it doesn't gate a build.
"""

from dataclasses import dataclass, field
from pathlib import Path

from qa_agent.cases import CaseFormatError, load_case_file
from qa_agent.project import SetupError, TeamProject
from qa_agent.renderers import RENDERERS
from qa_agent.results import read_results

MIN_RUNS = 2


@dataclass
class TestHistory:
    __test__ = False                                    # not a pytest test class
    test: str                                           # the full name, with its data row
    case_id: str
    outcomes: dict = field(default_factory=dict)        # run number -> passed / failed / skipped
    messages: dict = field(default_factory=dict)        # run number -> the failure's first line

    @property
    def counted(self) -> list:
        return [outcome for outcome in self.outcomes.values() if outcome != "skipped"]

    @property
    def last_failure(self) -> str:
        number = max(run for run, outcome in self.outcomes.items() if outcome == "failed")
        return f"run {number}: {self.messages.get(number) or 'no message'}"

    def as_line(self) -> str:
        counted = self.counted
        return (f"{self.case_id or '-':<7} {self.test}   passed {counted.count('passed')} of {len(counted)}   "
                f"last failure, {self.last_failure}")


@dataclass
class FlakyReport:
    team: str
    runs: int
    compared: int = 0
    flaky: list = field(default_factory=list)           # TestHistory
    failing: list = field(default_factory=list)         # failed in every run it ran in
    stable: int = 0
    not_in_every_run: list = field(default_factory=list)

    def as_text(self) -> str:
        lines = [f"qa-agent flaky: {self.team}, {self.runs} runs, {self.compared} tests compared", ""]
        if self.flaky:
            lines.append(f"Flaky ({len(self.flaky)}): passed in some runs, failed in others")
            lines += [f"  {item.as_line()}" for item in self.flaky]
        else:
            lines.append("Flaky: none")
        if self.failing:
            lines.append(f"Failed in every run ({len(self.failing)}): not flaky; a bug or a broken test")
            lines += [f"  {item.case_id or '-':<7} {item.test}   {item.last_failure}" for item in self.failing]
        lines.append(f"Passed in every run: {self.stable}")
        if self.not_in_every_run:
            lines.append(f"Not in every run, compared where they ran: {', '.join(self.not_in_every_run)}")
        return "\n".join(lines)

    def as_markdown(self) -> str:
        lines = [f"# Flaky tests: {self.team}", "",
                 f"{self.runs} runs, {self.compared} tests compared. Passed in every run: {self.stable}.", ""]
        lines += ["## Flaky: passed in some runs, failed in others", ""]
        if self.flaky:
            lines += ["| Case | Test | Passed | Last failure |", "|---|---|---|---|"]
            lines += [f"| {item.case_id or '-'} | `{item.test}` | {item.counted.count('passed')} of "
                      f"{len(item.counted)} | {item.last_failure} |" for item in self.flaky]
        else:
            lines.append("None.")
        if self.failing:
            lines += ["", "## Failed in every run: not flaky; a bug or a broken test", "",
                      "| Case | Test | Last failure |", "|---|---|---|"]
            lines += [f"| {item.case_id or '-'} | `{item.test}` | {item.last_failure} |" for item in self.failing]
        if self.not_in_every_run:
            lines += ["", f"Not in every run, compared where they ran: {', '.join(self.not_in_every_run)}."]
        return "\n".join(lines) + "\n"


def find_flaky(project: TeamProject, runs: list) -> FlakyReport:
    if len(runs) < MIN_RUNS:
        raise SetupError(f"give at least {MIN_RUNS} runs (--runs run1 run2): one run can't show a flaky test")
    per_run = [read_results([path]) for path in runs]
    empty = [project.relative(Path(path)) for path, run in zip(runs, per_run) if not run.runs]
    if empty:
        raise SetupError(f"no test results in: {', '.join(empty)}")
    names = [{test.full_name for test in run.runs} for run in per_run]
    if not set.intersection(*names):
        raise SetupError("the runs have no test in common: give runs of the same tests on the same build")
    case_of = _case_ids(project)
    history: dict = {}
    for number, run in enumerate(per_run, start=1):
        for test in run.runs:
            item = history.setdefault(test.full_name, TestHistory(test.full_name, test.case_id or case_of.get(test.name, "")))
            if item.outcomes.get(number) != "failed":        # the same test twice in one run: a failure wins
                item.outcomes[number] = test.outcome
                item.messages[number] = test.message
    report = FlakyReport(project.team, len(runs), compared=len(history))
    for name, item in sorted(history.items(), key=lambda pair: (pair[1].case_id or "~", pair[0])):
        counted = item.counted
        if len(item.outcomes) < len(runs):
            report.not_in_every_run.append(name)
        if "passed" in counted and "failed" in counted:
            report.flaky.append(item)
        elif counted and all(outcome == "failed" for outcome in counted):
            report.failing.append(item)
        elif counted:
            report.stable += 1
    return report


def _case_ids(project: TeamProject) -> dict:
    """Test name -> case id, from the cases' generated test names (for results without a case_id property)."""
    found = {}
    for path in project.case_files():
        try:
            cases = load_case_file(path).cases
        except CaseFormatError:
            continue
        for case in cases:
            for renderer in RENDERERS.values():
                for name in renderer.test_names(case):
                    found[name] = case.id
    return found
