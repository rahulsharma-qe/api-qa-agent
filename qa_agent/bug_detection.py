"""`qa-agent bug-detection`: the bug-detection rate. Do the tests catch bugs, or only pass?

    qa-agent bug-detection --seeded-bugs seeded-bugs.yaml --framework pytest

seeded-bugs.yaml says how to start the API under test with each seeded bug, one at a time:

    start_with_bug: python -m mock_service --bug {bug}
    start_clean: python -m mock_service
    environment: mock                       # checked with env_check before each run
    bugs:
      refund-boundary: a cancel at exactly 24 hours gets no refund
      token-not-checked: a call with no token is let through

First a run with no bug: it must pass, or the rate means nothing (a failing suite "catches" every
bug). Then, for each bug: start the API with it, wait until env_check says ready, run the framework's
tests, stop the API. A bug is caught when at least one test fails; the cases whose tests failed are
named. Reports: the console and reports/bug-detection.md.
"""

import shlex
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from qa_agent.cases import load_case_file
from qa_agent.project import SetupError, TeamProject
from qa_agent.renderers import RENDERERS
from qa_agent.results import read_results
from qa_agent.review_sheet import natural_order
from qa_agent.yaml_files import FileFormatError, read_yaml, write_yaml

READY_WAIT_SECONDS = 30


@dataclass
class BugRun:
    bug: str
    description: str
    caught: bool
    caught_by: list = field(default_factory=list)      # case ids whose tests failed


@dataclass
class BugReport:
    framework: str
    runs: list = field(default_factory=list)

    @property
    def caught(self) -> int:
        return sum(1 for run in self.runs if run.caught)

    def as_text(self) -> str:
        total = len(self.runs)
        lines = [f"qa-agent bug-detection: {self.framework} · {self.caught} of {total} seeded bugs caught "
                 f"({100 * self.caught / total:.0f}%)" if total else "qa-agent bug-detection: no bugs listed", ""]
        for run in self.runs:
            if run.caught:
                lines.append(f"  caught  {run.bug:<24} by {', '.join(run.caught_by) or 'a test with no case'}")
            else:
                lines.append(f"  missed  {run.bug:<24} {run.description}: no test noticed")
        return "\n".join(lines)

    def as_markdown(self) -> str:
        lines = [f"# Bug-detection rate: {self.framework}", "",
                 f"{self.caught} of {len(self.runs)} seeded bugs caught.", "",
                 "| Bug | What it changes | Caught | By |", "|---|---|---|---|"]
        for run in self.runs:
            lines.append(f"| `{run.bug}` | {run.description} | {'yes' if run.caught else '**no**'} | "
                         f"{', '.join(run.caught_by) or '-'} |")
        return "\n".join(lines) + "\n"


def measure(project: TeamProject, seeded_bugs_file: Path, framework: str) -> BugReport:
    if framework not in project.frameworks:
        raise SetupError(f"framework '{framework}' is not in qa-agent.yaml (it has: {', '.join(project.frameworks)})")
    seeded = _read_seeded_bugs(seeded_bugs_file)
    folder = project.root / "reports" / "bug-detection"
    folder.mkdir(parents=True, exist_ok=True)
    if _ready(project, seeded["environment"], one_try=_one_try_dependencies(project, folder)):
        raise SetupError("the API is already up: stop it first, qa-agent bug-detection starts it once per bug")
    clean = _run_once(project, seeded, framework, "", folder)
    if clean.failed:
        raise SetupError(f"the tests fail with no bug switched on ({', '.join(clean.failed) or 'see the log'}): "
                         "fix that first; a failing suite would 'catch' every bug")
    report = BugReport(framework)
    for bug, description in seeded["bugs"].items():
        result = _run_once(project, seeded, framework, bug, folder)
        report.runs.append(BugRun(bug, description, bool(result.failed) or result.exit_code != 0,
                                  sorted(result.failed, key=natural_order)))
    (project.root / "reports" / "bug-detection.md").write_text(report.as_markdown(), encoding="utf-8")
    return report


@dataclass
class _Outcome:
    exit_code: int
    failed: list                 # case ids with a failing test


def _read_seeded_bugs(path: Path) -> dict:
    try:
        data = read_yaml(path)
    except (FileFormatError, OSError) as error:
        raise SetupError(f"{path}: can't be read ({error})") from error
    if not isinstance(data, dict) or "{bug}" not in str(data.get("start_with_bug", "")) or not data.get("bugs") \
            or not data.get("start_clean"):
        raise SetupError(f"{path}: needs 'start_with_bug' (a command with {{bug}} in it), 'start_clean' and 'bugs'")
    bugs = data["bugs"]
    bugs = {str(name): "" for name in bugs} if isinstance(bugs, list) else {str(k): str(v) for k, v in bugs.items()}
    start_with_bug = str(data["start_with_bug"])
    return {"start_with_bug": start_with_bug, "bugs": bugs, "environment": str(data.get("environment") or "mock"),
            "start_clean": str(data["start_clean"])}


def _run_once(project: TeamProject, seeded: dict, framework: str, bug: str, folder: Path) -> _Outcome:
    command = seeded["start_with_bug"].replace("{bug}", bug) if bug else seeded["start_clean"]
    name = bug or "no-bug"
    with (folder / f"{name}.api.log").open("w") as log:
        api = subprocess.Popen(shlex.split(command), cwd=project.root, stdout=log, stderr=subprocess.STDOUT)
        try:
            _wait(lambda: _ready(project, seeded["environment"]), f"the API ({command}) didn't become ready")
            return _tests(project, framework, folder / name)
        finally:
            api.terminate()                       # the next run starts only once this one has exited
            try:
                api.wait(timeout=10)
            except subprocess.TimeoutExpired:
                api.kill()
                api.wait()


def _tests(project: TeamProject, framework: str, results: Path) -> _Outcome:
    if framework == "pytest":
        command = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", f"--junitxml={results}.xml"]
        finished = subprocess.run(command, cwd=project.root, capture_output=True, text=True)
        paths = [Path(f"{results}.xml")]
    else:
        finished = subprocess.run(["./mvnw", "-q", "-B", "test"], cwd=project.root, capture_output=True, text=True)
        target = Path(f"{results}-surefire")
        shutil.rmtree(target, ignore_errors=True)
        if (project.root / "target" / "surefire-reports").is_dir():
            shutil.copytree(project.root / "target" / "surefire-reports", target)
        paths = [target]
    outcomes = read_results(paths)
    failed = set()
    for path in project.case_files():
        for case in load_case_file(path).cases:
            if "failed" in outcomes.for_names(RENDERERS[framework].test_names(case)):
                failed.add(case.id)
    return _Outcome(finished.returncode, sorted(failed))


def _ready(project: TeamProject, environment: str, one_try: Path = None) -> bool:
    command = [sys.executable, "-m", "env_check", "--env", environment]
    if one_try is not None:
        command += ["--dependencies", str(one_try)]
    return subprocess.run(command, cwd=project.root, capture_output=True).returncode == 0


def _one_try_dependencies(project: TeamProject, folder: Path) -> Path:
    """The team's dependencies with one attempt: 'is it already up?' needs no retries."""
    plan = read_yaml(project.root / "config" / "dependencies.yaml") or {}
    plan["attempts"] = 1
    path = folder / "dependencies-one-try.yaml"
    write_yaml(path, plan)
    return path


def _wait(condition, problem: str) -> None:
    deadline = time.monotonic() + READY_WAIT_SECONDS
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(0.5)
    raise SetupError(problem)
