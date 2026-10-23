"""The regression suite: functional cases join it when they are stable; a person decides.

    qa-agent promote --runs reports/run1 reports/run2 reports/run3          lists, changes nothing
    qa-agent promote --runs ... --apply                                     sets suite: regression
    qa-agent suite TC010 functional --by qa-lead --reason "refund rule changing"

A case is ready when it is approved and functional, and passed in every run given (every data row),
in every stack that has results; at least three runs. A regression case that failed in any run is
flagged, never moved back by the tool: a person moves a case with `qa-agent suite`, which records
who, when and why in the case's notes.
"""

import datetime
from dataclasses import dataclass, field
from pathlib import Path

from qa_agent.cases import SUITES, Case, load_case_file, save_case_file
from qa_agent.project import SetupError, TeamProject
from qa_agent.renderers import RENDERERS
from qa_agent.results import read_results
from qa_agent.review_sheet import natural_order

MIN_RUNS = 3


@dataclass
class PromoteResult:
    ready: list = field(default_factory=list)          # case ids
    not_yet: list = field(default_factory=list)        # "TC003: failed in run 2 (python)"
    look_at: list = field(default_factory=list)        # regression cases that failed
    stacks: list = field(default_factory=list)         # the stacks the runs had results for
    without_results: list = field(default_factory=list)
    applied: bool = False

    def as_text(self, runs: int) -> str:
        lines = [f"From {runs} runs, with results for: {', '.join(self.stacks) or 'no stack'}"]
        lines += [f"No results for {stack}: promotion here rests on {', '.join(self.stacks)} only"
                  for stack in self.without_results]
        verb = "promoted to regression" if self.applied else "ready for regression"
        lines += [f"{verb}: {case_id}" for case_id in self.ready]
        lines += [f"not yet: {item}" for item in self.not_yet]
        lines += [f"look at this: {item}" for item in self.look_at]
        if self.ready and not self.applied:
            lines.append("Nothing changed. To move them: the same command with --apply.")
        return "\n".join(lines)


def promote(project: TeamProject, runs: list, apply: bool = False) -> PromoteResult:
    if len(runs) < MIN_RUNS:
        raise SetupError(f"give at least {MIN_RUNS} runs (--runs run1 run2 run3): one pass is not stability")
    per_run = [read_results([path]) for path in runs]
    result = PromoteResult(stacks=sorted(set().union(*(run.stacks for run in per_run)) & set(project.stacks)))
    if not result.stacks:
        raise SetupError("the runs have no results for this project's stacks")
    result.without_results = [stack for stack in project.stacks if stack not in result.stacks]
    files = [load_case_file(path) for path in project.case_files()]
    changed = set()
    pairs = sorted(((case_file, case) for case_file in files for case in case_file.cases),
                   key=lambda pair: natural_order(pair[1].id))
    for case_file, case in pairs:
        if not case.is_approved:
            continue
        problem = _problem(case, per_run, result.stacks)
        if case.suite == "regression":
            if problem:
                result.look_at.append(f"{case.id} (regression): {problem}")
        elif problem:
            result.not_yet.append(f"{case.id}: {problem}")
        else:
            result.ready.append(case.id)
            if apply:
                case.suite = "regression"
                _note(case, f"promoted to regression: passed in {len(runs)} runs ({', '.join(result.stacks)})")
                changed.add(case_file.path)
    for case_file in files:
        if case_file.path in changed:
            save_case_file(case_file)
    result.applied = apply
    return result


def move_to_suite(project: TeamProject, case_id: str, suite: str, by: str, reason: str) -> str:
    if suite not in SUITES:
        raise SetupError(f"suite '{suite}' (use {' or '.join(SUITES)})")
    if not by.strip() or not reason.strip():
        raise SetupError("say who and why: --by <name> --reason <text>")
    for path in project.case_files():
        case_file = load_case_file(path)
        for case in case_file.cases:
            if case.id == case_id:
                if case.suite == suite:
                    return f"{case_id} is already {suite}"
                was, case.suite = case.suite, suite
                _note(case, f"moved from {was} to {suite} by {by}: {reason}")
                save_case_file(case_file)
                return f"{case_id}: {was} -> {suite} ({project.relative(Path(path))}); run qa-agent generate"
    raise SetupError(f"no case {case_id} in the project")


def _problem(case: Case, runs: list, stacks: list) -> str:
    for stack in stacks:
        names = RENDERERS[stack].test_names(case)
        for number, run in enumerate(runs, start=1):
            outcomes = run.for_names(names)
            if not outcomes:
                return f"not run in run {number} ({stack})"
            if any(outcome != "passed" for outcome in outcomes):
                kind = "failed" if "failed" in outcomes else "skipped"
                return f"{kind} in run {number} ({stack})"
    return ""


def _note(case: Case, text: str) -> None:
    line = f"{datetime.date.today().isoformat()}: {text}"
    case.notes = f"{case.notes}\n{line}" if case.notes else line
