"""`qa-agent generate`: approved cases -> tests, for every stack in qa-agent.yaml.

Only a case that is approved and unchanged since (its fingerprint matches) becomes code. The output
folders belong to qa-agent: a generated file whose cases are no longer approved is removed; a file
qa-agent didn't write is left alone, and reported. Same cases, same files, every time.
"""

from dataclasses import dataclass, field

from qa_agent.cases import load_case_file
from qa_agent.project import TeamProject
from qa_agent.renderers import RENDERERS, RenderError

SUFFIXES = (".py", ".java")


@dataclass
class GenerateResult:
    written: list = field(default_factory=list)       # files created or changed
    unchanged: list = field(default_factory=list)
    removed: list = field(default_factory=list)
    left_alone: list = field(default_factory=list)    # files in the output folder qa-agent didn't write
    tests: dict = field(default_factory=dict)         # stack -> number of tests
    not_generated: list = field(default_factory=list) # "TC005: changes needed"
    problems: list = field(default_factory=list)      # cases a framework can't express

    def as_text(self) -> str:
        lines = [f"wrote      {path}" for path in self.written] + [f"unchanged  {path}" for path in self.unchanged]
        lines += [f"removed    {path}" for path in self.removed]
        lines += [f"left alone {path} (not written by qa-agent)" for path in self.left_alone]
        lines += [f"not generated: {item}" for item in self.not_generated]
        lines += [f"problem: {item}" for item in self.problems]
        lines.append(" · ".join(f"{stack}: {count} tests" for stack, count in self.tests.items()) or "no stacks")
        return "\n".join(lines)


def generate(project: TeamProject) -> GenerateResult:
    result = GenerateResult()
    case_files = [load_case_file(path) for path in project.case_files()]
    for case_file in case_files:
        for case in case_file.cases:
            if not case.is_approved:
                result.not_generated.append(f"{case.id}: {_why_not(case)}")
    for stack in project.stacks:
        renderer = RENDERERS[stack]
        expected, approved_everywhere, count = {}, [], 0
        for case_file in case_files:
            cases = []
            for case in (c for c in case_file.cases if c.is_approved):
                try:
                    renderer.render_file(project.relative(case_file.path), case_file, [case])
                except RenderError as error:
                    result.problems.append(f"{stack}: {error}")
                    continue
                cases.append(case)
            if cases:
                generated = renderer.render_file(project.relative(case_file.path), case_file, cases)
                expected[generated.path] = generated.text
                approved_everywhere += cases
                count += len(cases)
        if approved_everywhere:
            for generated in renderer.support_files(approved_everywhere):
                expected[generated.path] = generated.text
        _write(project, renderer, expected, result)
        result.tests[stack] = count
    return result


def _write(project: TeamProject, renderer, expected: dict, result: GenerateResult) -> None:
    for relative, text in sorted(expected.items()):
        path = project.root / relative
        if path.is_file() and path.read_text(encoding="utf-8") == text:
            result.unchanged.append(relative)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        result.written.append(relative)
    folder = project.root / renderer.output_dir
    if not folder.is_dir():
        return
    for path in sorted(folder.iterdir()):
        relative = project.relative(path)
        if not path.is_file() or path.suffix not in SUFFIXES or relative in expected:
            continue
        if path.read_text(encoding="utf-8").startswith(renderer.header_mark):
            path.unlink()
            result.removed.append(relative)
        else:
            result.left_alone.append(relative)


def _why_not(case) -> str:
    if case.changed_after_approval:
        return "changed after approval; review it again"
    if case.needs_steps:
        return "needs steps"
    return {"draft": "not reviewed yet", "changes_needed": "changes needed", "rejected": "rejected"}.get(
        case.review.status, case.review.status)
