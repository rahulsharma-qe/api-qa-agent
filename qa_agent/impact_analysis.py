"""`qa-agent impact-analysis --since <ref>`: what changed in the API since a release, and the cases to run.

    qa-agent impact-analysis --since v4.2

api/api.yaml now is compared with api/api.yaml at <ref> (a git tag, branch or commit). Each operation
is changed (its response codes or required body fields differ), added or removed. The cases that call
a changed or removed operation are affected; they are listed highest priority first, with the command
that runs the approved ones in each framework. Code only: no model, nothing written.
"""

import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from qa_agent.api_model import ApiModel, ApiModelError, Operation, load_api_model
from qa_agent.cases import PRIORITIES, Case, load_case_file
from qa_agent.checks import plural
from qa_agent.project import SetupError, TeamProject
from qa_agent.renderers import RENDERERS
from qa_agent.renderers.common import id_slug
from qa_agent.review_sheet import natural_order
from qa_agent.trace import read_api


@dataclass
class OperationChange:
    kind: str                 # changed, added or removed
    service: str
    operation: Operation
    what: str = ""            # for changed: "responses: +410 -404; required body fields: +phone"


@dataclass
class ImpactReport:
    since: str
    changes: list = field(default_factory=list)       # OperationChange
    unchanged: int = 0
    affected: list = field(default_factory=list)      # (CaseFile, Case), highest priority first
    note: str = ""
    frameworks: tuple = ()
    main_service: str = ""

    def as_text(self) -> str:
        lines = [f"Impact analysis since {self.since} (api/api.yaml)", ""]
        if self.note:
            lines += [self.note, ""]
        if not self.changes:
            return "\n".join(lines + [f"No operation changed since {self.since}."])
        width = max(len(self._label(change)) for change in self.changes)
        for change in self.changes:
            lines.append(f"{change.kind:<9} {self._label(change):<{width}}   {self._detail(change)}")
        lines.append(f"          {plural(self.unchanged, 'operation')} unchanged")
        if not self.affected:
            return "\n".join(lines + ["", "No case calls a changed or removed operation."])
        lines += ["", f"Affected cases ({len(self.affected)}), highest priority first:"]
        for _, case in self.affected:
            state = case.suite if case.is_approved else case.review.status.replace("_", " ")
            later = "" if case.is_approved else "   (not a test yet)"
            lines.append(f"  {case.id:<7} {case.priority}  {state:<15} {case.title}{later}")
        commands = self.run_commands()
        if commands:
            lines += ["", "Run them:"] + [f"  {command}" for command in commands]
        return "\n".join(lines)

    def run_commands(self) -> list:
        """The command that runs the approved affected cases, in each of the project's frameworks."""
        approved = [(case_file, case) for case_file, case in self.affected if case.is_approved]
        if not approved:
            return []
        commands = []
        if "pytest" in self.frameworks:
            names = " or ".join(f"test_{id_slug(case)}_" for _, case in approved)
            commands.append(f'pytest -k "{names}"')
        if "restassured" in self.frameworks:
            renderer = RENDERERS["restassured"]
            by_class: dict = {}
            for case_file, case in approved:
                by_class.setdefault(renderer.class_name(case_file), []).append(renderer.test_names(case)[0])
            selection = ",".join(f"{name}#{'+'.join(methods)}" for name, methods in by_class.items())
            commands.append(f'./mvnw test -Dtest="{selection}"')
        return commands

    def _label(self, change: OperationChange) -> str:
        service = "" if change.service == self.main_service else f"{change.service}: "
        return f"{service}{change.operation.method} {change.operation.path}"

    def _detail(self, change: OperationChange) -> str:
        if change.kind == "changed":
            return change.what
        callers = [case.id for _, case in self.affected if _calls(case, change, self.main_service)]
        if change.kind == "added":
            return "no case yet: draft one (qa-agent draft cases), or write one"
        return (f"{', '.join(callers)} still {'calls' if len(callers) == 1 else 'call'} it: check reports it"
                if callers else "no case calls it")


def impact_analysis(project: TeamProject, since: str) -> ImpactReport:
    report = ImpactReport(since, frameworks=project.frameworks, main_service=project.main_service)
    now = read_api(project) or ApiModel()
    before = _api_at(project, since)
    if before is None:
        before = ApiModel()
        report.note = f"api/api.yaml was not there at {since}: every operation counts as added."
    report.changes, report.unchanged = _compare(before, now)
    touched = [change for change in report.changes if change.kind != "added"]
    found = []
    for path in project.case_files():
        case_file = load_case_file(path)
        for case in case_file.cases:
            if case.review.status != "rejected" and any(_calls(case, change, project.main_service) for change in touched):
                found.append((case_file, case))
    found.sort(key=lambda pair: (PRIORITIES.index(pair[1].priority) if pair[1].priority in PRIORITIES else 99,
                                 natural_order(pair[1].id)))
    report.affected = found
    return report


def _api_at(project: TeamProject, ref: str) -> Optional[ApiModel]:
    """api/api.yaml as it was at ref, or None when it wasn't there. Not git, or no such ref: SetupError."""
    def git(*args: str) -> subprocess.CompletedProcess:
        try:
            return subprocess.run(["git", "-C", str(project.root), *args], capture_output=True, text=True)
        except FileNotFoundError as error:
            raise SetupError("impact-analysis needs git, to read api/api.yaml as it was") from error

    if git("rev-parse", "--is-inside-work-tree").returncode != 0:
        raise SetupError(f"{project.root} is not in a git repository: impact-analysis compares api/api.yaml "
                         "with an earlier commit")
    if git("rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}").returncode != 0:
        raise SetupError(f"no {ref} in git: give a tag, a branch or a commit")
    shown = git("show", f"{ref}:./{project.relative(project.api_model_path)}")
    if shown.returncode != 0:
        return None
    with tempfile.TemporaryDirectory() as folder:
        old = Path(folder) / "api.yaml"
        old.write_text(shown.stdout, encoding="utf-8")
        try:
            return load_api_model(old)
        except ApiModelError as error:
            raise SetupError(f"api/api.yaml at {ref} can't be read: {error}") from error


def _compare(before: ApiModel, now: ApiModel) -> tuple:
    changes, unchanged = [], 0
    for service in sorted(set(before.services) | set(now.services)):
        old = {operation.key: operation for operation in before.operations(service)}
        new = {operation.key: operation for operation in now.operations(service)}
        for key in sorted(set(old) | set(new), key=lambda key: (key[1], key[0])):
            if key not in old:
                changes.append(OperationChange("added", service, new[key]))
            elif key not in new:
                changes.append(OperationChange("removed", service, old[key]))
            else:
                what = _differences(old[key], new[key])
                if what:
                    changes.append(OperationChange("changed", service, new[key], what))
                else:
                    unchanged += 1
    order = {"changed": 0, "added": 1, "removed": 2}
    changes.sort(key=lambda change: order[change.kind])
    return changes, unchanged


def _differences(old: Operation, new: Operation) -> str:
    parts = []
    for name, before, after in (("responses", old.responses, new.responses),
                                ("required body fields", old.body_required, new.body_required)):
        added = [f"+{item}" for item in sorted(set(after) - set(before), key=str)]
        removed = [f"-{item}" for item in sorted(set(before) - set(after), key=str)]
        if added or removed:
            parts.append(f"{name}: {' '.join(added + removed)}")
    return "; ".join(parts)


def _calls(case: Case, change: OperationChange, main_service: str) -> bool:
    """Whether a step of the case calls the changed or removed operation."""
    model = ApiModel({change.service: [change.operation]})
    return any((step.request.service or main_service) == change.service
               and model.find(change.service, step.request.method, step.request.path) for step in case.steps)

