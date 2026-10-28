"""The regression suite: functional cases join it when they are stable; a person decides.

    qa-agent promote --runs reports/run1 reports/run2 reports/run3          lists, changes nothing
    qa-agent promote --runs ... --apply                                     sets suite: regression
    qa-agent promote --runs ... --feature cancellation --priority P0 P1 --reason "released in 4.3"
    qa-agent suite TC010 functional --by qa-lead --reason "refund rule changing"

A case is ready when it is approved and functional, and passed in every run given (every data row),
in every framework that has results; at least three runs. A regression case that failed in any run is
flagged, never moved back by the tool: a person moves a case with `qa-agent suite`, which records
who, when and why in the case's notes.

--feature looks only at one feature's cases (the case file's feature, or its file name). --priority
moves only those priorities; without it, regression: {priorities: [P0, P1]} in qa-agent.yaml, else
every priority. A stable case of another priority is listed as left out, never dropped silently.
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
    not_yet: list = field(default_factory=list)        # "TC003: failed in run 2 (pytest)"
    look_at: list = field(default_factory=list)        # regression cases that failed
    left_out: list = field(default_factory=list)       # "TC031 (P2)": approved functional, not in --priority
    priorities: tuple = ()                             # the priorities moved; empty: every one
    frameworks: list = field(default_factory=list)         # the frameworks the runs had results for
    without_results: list = field(default_factory=list)
    identical: list = field(default_factory=list)          # runs whose files are byte for byte the same
    applied: bool = False

    def as_text(self, runs: int) -> str:
        lines = [f"From {runs} runs, with results for: {', '.join(self.frameworks) or 'no framework'}"]
        lines += [f"Note: {' and '.join(names)} are byte for byte the same: if one is a copy, this isn't stability"
                  for names in self.identical]
        lines += [f"No results for {framework}: promotion here rests on {', '.join(self.frameworks)} only"
                  for framework in self.without_results]
        verb = "promoted to regression" if self.applied else "ready for regression"
        lines += [f"{verb}: {case_id}" for case_id in self.ready]
        lines += [f"not yet: {item}" for item in self.not_yet]
        lines += [f"look at this: {item}" for item in self.look_at]
        if self.left_out:
            lines.append(f"left out, not {'/'.join(self.priorities)}: {', '.join(self.left_out)} "
                         "(stays functional; --priority to include)")
        if self.ready and not self.applied:
            lines.append("Nothing changed. To move them: the same command with --apply.")
        return "\n".join(lines)


def promote(project: TeamProject, runs: list, apply: bool = False, feature: str = "",
            priorities: tuple = (), reason: str = "") -> PromoteResult:
    if len(runs) < MIN_RUNS:
        raise SetupError(f"give at least {MIN_RUNS} runs (--runs run1 run2 run3): one pass is not stability")
    paths = [Path(path).resolve() for path in runs]
    twice = sorted({str(path) for path in paths if paths.count(path) > 1})
    if twice:
        raise SetupError(f"{', '.join(twice)} is given more than once: one run given twice is not stability; "
                         "give results from different runs")
    same = {}
    for path in runs:
        same.setdefault(_content(Path(path)), []).append(Path(path).name)
    per_run = [read_results([path]) for path in runs]
    copies = [names for names in same.values() if len(names) > 1]
    result = PromoteResult(frameworks=sorted(set().union(*(run.frameworks for run in per_run)) & set(project.frameworks)))
    result.identical = copies
    if not result.frameworks:
        raise SetupError("the runs have no results for this project's frameworks")
    result.without_results = [framework for framework in project.frameworks if framework not in result.frameworks]
    result.priorities = tuple(priorities) or project.regression_priorities
    files = [load_case_file(path) for path in project.case_files()]
    if feature:
        files = _of_feature(files, feature, project)
    changed = set()
    pairs = sorted(((case_file, case) for case_file in files for case in case_file.cases),
                   key=lambda pair: natural_order(pair[1].id))
    for case_file, case in pairs:
        if not case.is_approved:
            continue
        problem = _problem(case, per_run, result.frameworks)
        if case.suite == "regression":
            if problem:
                result.look_at.append(f"{case.id} (regression): {problem}")
        elif result.priorities and case.priority not in result.priorities:
            result.left_out.append(f"{case.id} ({case.priority})")
        elif problem:
            result.not_yet.append(f"{case.id}: {problem}")
        else:
            result.ready.append(case.id)
            if apply:
                case.suite = "regression"
                why = f": {reason.strip()}" if reason.strip() else ""
                _note(case, f"promoted to regression: passed in {len(runs)} runs ({', '.join(result.frameworks)}){why}")
                changed.add(case_file.path)
    for case_file in files:
        if case_file.path in changed:
            save_case_file(case_file)
    result.applied = apply
    return result


def _content(path: Path) -> str:
    """A run's results, as a hash: a file, or every XML file in a folder."""
    import hashlib
    files = sorted(path.glob("*.xml")) if path.is_dir() else [path]
    digest = hashlib.sha256()
    for item in files:
        digest.update(item.read_bytes())
    return digest.hexdigest()


def _of_feature(files: list, feature: str, project: TeamProject) -> list:
    """The case files of one feature: by the file's feature: name or its file name, any case."""
    wanted = feature.strip().lower()
    found = [case_file for case_file in files
             if wanted in (case_file.feature.strip().lower(), Path(case_file.path).stem.lower())]
    if not found:
        names = sorted({case_file.feature for case_file in files})
        raise SetupError(f"no feature '{feature}' (the features: {', '.join(names) or 'none'})")
    return found


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


def _problem(case: Case, runs: list, frameworks: list) -> str:
    for framework in frameworks:
        names = RENDERERS[framework].test_names(case)
        for number, run in enumerate(runs, start=1):
            outcomes = run.for_names(names)
            if not outcomes:
                return f"not run in run {number} ({framework})"
            if any(outcome != "passed" for outcome in outcomes):
                kind = "failed" if "failed" in outcomes else "skipped"
                return f"{kind} in run {number} ({framework})"
    return ""


def _note(case: Case, text: str) -> None:
    line = f"{datetime.date.today().isoformat()}: {text}"
    case.notes = f"{case.notes}\n{line}" if case.notes else line
