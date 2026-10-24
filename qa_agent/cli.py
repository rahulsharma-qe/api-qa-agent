"""qa-agent: the command line.

    qa-agent init my-team --framework pytest             a working project, on day one (or --framework restassured)
    qa-agent import api api/source/openapi.json      the API description -> api/api.yaml
    qa-agent import cases existing/cases.xlsx        the team's cases (Excel, CSV, Postman, Gherkin)
    qa-agent check                                   the cases, checked with rules
    qa-agent review export | apply                   a person decides on each case, in Excel
    qa-agent generate                                approved cases -> tests, for every framework
    qa-agent trace --results reports/junit.xml       criteria -> cases -> tests -> results, and coverage
    qa-agent promote --runs r1 r2 r3 [--apply]       stable functional cases -> regression; a person applies it
    qa-agent suite TC010 functional --by --reason    a person moves a case between suites, on the record
    qa-agent bug-detection --seeded-bugs seeded-bugs.yaml --framework pytest   the bug-detection rate: seeded bugs, one at a time
    qa-agent draft criteria requirements/x.md        the AI layer: criteria and questions from a requirement in plain words
    qa-agent draft cases [--plan] [--max 10]         the AI layer: a draft case per coverage gap, for a person to review

Exit codes: 0 done (no errors), 1 errors found, 2 the project or an input can't be read.
"""

import argparse
import sys
from pathlib import Path
from typing import Optional

from qa_agent import __version__
from qa_agent.api_model import ApiModel, ApiModelError, load_api_model, save_api_model
from qa_agent.bug_detection import measure
from qa_agent.case_import import import_cases
from qa_agent.cases import CaseFormatError
from qa_agent.ai.models import ModelError, ModelSetupError
from qa_agent.ai.session import AiSession
from qa_agent.checks import check_project, plural
from qa_agent.criteria_drafting import draft_criteria
from qa_agent.criteria_review import pending as pending_criteria
from qa_agent.drafting import DEFAULT_MAX, draft_cases, plan
from qa_agent.generate import generate
from qa_agent.init_project import init_project
from qa_agent.promote import move_to_suite, promote
from qa_agent.trace import build_trace
from qa_agent.importers.common import CaseImportError
from qa_agent.importers.curl import CurlError, read_curl
from qa_agent.importers.openapi import OpenApiError, read_openapi
from qa_agent.project import SetupError, TeamProject
from qa_agent.review_sheet import export_review_sheet, import_review_sheet

DONE, FINDINGS, SETUP_PROBLEM = 0, 1, 2


def main(argv: Optional[list[str]] = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if not getattr(args, "run", None):
        parser.print_help()
        return SETUP_PROBLEM
    try:
        return args.run(args)
    except (SetupError, ApiModelError, OpenApiError, CurlError, CaseImportError, CaseFormatError,
            ModelSetupError) as error:
        print(f"qa-agent: {error}", file=sys.stderr)
        return SETUP_PROBLEM


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="qa-agent", description="Test cases as data: import, check, review, "
                                                                   "generate and trace, in the team's framework.")
    parser.add_argument("--version", action="version", version=f"qa-agent {__version__}")
    parser.add_argument("--project", type=Path, default=Path("."), help="the team's project folder (default: here)")
    commands = parser.add_subparsers(title="commands", metavar="<command>")

    init = commands.add_parser("init", help="a new team project that runs on day one")
    init.add_argument("folder", type=Path, help="a new or empty folder")
    init.add_argument("--framework", required=True, choices=["pytest", "restassured"])
    init.add_argument("--team", default="", help="the team's name (default: the folder's name)")
    init.add_argument("--service", default="bookings", help="the main service's name (default: bookings)")
    init.set_defaults(run=run_init)

    importing = commands.add_parser("import", help="read what the team already has").add_subparsers(
        title="what to import", metavar="<what>")
    api = importing.add_parser("api", help="an API description (OpenAPI, or curl with a sample response) "
                                           "-> api/api.yaml")
    api.add_argument("files", nargs="+", type=Path, help="openapi.json, openapi.yaml, or .curl files")
    api.add_argument("--service", help="the service these operations belong to (default: the project's service)")
    api.set_defaults(run=import_api)

    cases = importing.add_parser("cases", help="the team's existing cases: Excel or CSV, a Postman collection, "
                                               "Gherkin -> cases/<feature>.yaml, as drafts")
    cases.add_argument("files", nargs="+", type=Path, help=".xlsx, .csv, .json (Postman) or .feature files")
    cases.add_argument("--into", type=Path, help="one case file for everything imported (default: one per feature)")
    cases.add_argument("--overwrite", action="store_true", help="replace cases (and data files) already there")
    cases.set_defaults(run=import_existing_cases)

    check = commands.add_parser("check", help="check every case with rules; exit 1 on errors")
    check.set_defaults(run=run_check)

    review = commands.add_parser("review", help="the review sheet").add_subparsers(title="review", metavar="<step>")
    export = review.add_parser("export", help="write review/cases.xlsx: every case still to review")
    export.add_argument("--all", action="store_true", help="every case, approved ones too")
    export.add_argument("--sheet", type=Path, default=Path("review/cases.xlsx"))
    export.set_defaults(run=review_export)
    apply = review.add_parser("apply", help="apply the decisions in review/cases.xlsx; exit 1 if any is refused")
    apply.add_argument("--sheet", type=Path, default=Path("review/cases.xlsx"))
    apply.set_defaults(run=review_import)

    write = commands.add_parser("generate", help="approved cases -> tests for every framework; exit 1 if a case "
                                                  "can't be written")
    write.add_argument("--check", action="store_true",
                       help="write nothing; exit 1 if the generated tests don't match the approved cases (CI)")
    write.set_defaults(run=run_generate)

    trace = commands.add_parser("trace", help="criteria -> cases -> tests -> results, and coverage; "
                                              "writes reports/trace.md and trace.xlsx")
    trace.add_argument("--results", nargs="*", type=Path, default=[],
                       help="JUnit XML files or folders: reports/junit.xml target/surefire-reports")
    trace.add_argument("--out", type=Path, default=Path("reports"), help="where trace.md and trace.xlsx go")
    trace.add_argument("--check", action="store_true", help="exit 1 when an approved case has no test")
    trace.add_argument("--min-coverage", type=float, metavar="PERCENT",
                       help="exit 1 when criteria or operations coverage is below it (off unless given)")
    trace.set_defaults(run=run_trace)

    stable = commands.add_parser("promote", help="list functional cases stable enough for regression; --apply "
                                                 "moves them")
    stable.add_argument("--runs", nargs="+", type=Path, required=True,
                        help="three or more runs, each a JUnit file or folder: reports/run1.xml reports/run2.xml ...")
    stable.add_argument("--apply", action="store_true", help="set suite: regression on the ready cases")
    stable.set_defaults(run=run_promote)

    move = commands.add_parser("suite", help="move a case to another suite, with who and why")
    move.add_argument("case_id")
    move.add_argument("suite", choices=["functional", "regression"])
    move.add_argument("--by", required=True, help="who decided")
    move.add_argument("--reason", required=True, help="why, in a few words")
    move.set_defaults(run=run_suite)

    detection = commands.add_parser("bug-detection", help="the bug-detection rate: run the tests once per seeded bug")
    detection.add_argument("--seeded-bugs", type=Path, default=Path("seeded-bugs.yaml"),
                           help="how to start the API with each seeded bug (default: seeded-bugs.yaml)")
    detection.add_argument("--framework", choices=["pytest", "restassured"], required=True)
    detection.set_defaults(run=run_bug_detection)

    drafting = commands.add_parser("draft", help="the AI layer: drafts for a person to review").add_subparsers(
        title="draft", metavar="<what>")
    criteria = drafting.add_parser("criteria", help="acceptance criteria and questions from a requirement in plain words")
    criteria.add_argument("requirement", type=Path, help="a text or markdown file: a story, a part of a spec")
    criteria.set_defaults(run=run_draft_criteria)
    cases = drafting.add_parser("cases", help="a draft case for each coverage gap (criteria, operations, codes)")
    cases.add_argument("--plan", action="store_true", help="list the gaps, the calls and an estimate; call no model")
    cases.add_argument("--max", type=int, default=DEFAULT_MAX, help=f"at most this many gaps (default: {DEFAULT_MAX})")
    cases.set_defaults(run=run_draft_cases)
    return parser


def run_init(args) -> int:
    result = init_project(args.folder, args.framework, args.team, args.service)
    print(result.as_text(args.framework))
    return DONE


def import_api(args) -> int:
    project = TeamProject.load(args.project)
    service = args.service or project.main_service
    model = load_api_model(project.api_model_path) if project.api_model_path.is_file() else ApiModel()
    before = model.count()
    missing = [str(path) for path in args.files if not path.is_file()]
    if missing:
        raise SetupError(f"no such file: {', '.join(missing)}")
    for path in args.files:
        notes = []
        if path.suffix in (".curl", ".txt"):
            imported = read_curl(path)
            operations = [imported.operation]
            notes = [f"read {found}; rename the parameter in api/api.yaml if you like" for found in imported.parameters_found]
        else:
            operations = read_openapi(path)
        new = sum(model.add(service, operation) for operation in operations)
        print(f"{path.name}: {plural(len(operations), 'operation')} for '{service}', {new} new")
        for note in notes:
            print(f"  {note}")
    save_api_model(model, project.api_model_path)
    print(f"api/api.yaml: {plural(model.count(), 'operation')} ({model.count() - before} added)")
    return DONE


def import_existing_cases(args) -> int:
    project = TeamProject.load(args.project)
    missing = [str(path) for path in args.files if not path.is_file()]
    if missing:
        raise SetupError(f"no such file: {', '.join(missing)}")
    print(import_cases(project, args.files, args.into, args.overwrite).as_text())
    print("Next: qa-agent check, then qa-agent review export")
    return DONE


def review_export(args) -> int:
    project = TeamProject.load(args.project)
    sheet = args.sheet if args.sheet.is_absolute() else project.root / args.sheet
    count = export_review_sheet(project, sheet, args.all)
    criteria, questions = pending_criteria(project)
    extra = (f", {plural(len(criteria), 'criterion', 'criteria')} and {plural(len(questions), 'open question')}"
             if criteria or questions else "")
    print(f"{project.relative(sheet)}: {plural(count, 'case')}{extra} to review. Fill Decision, Reviewer and Comment "
          f"(and Answer for questions), save, then: qa-agent review apply")
    return DONE


def review_import(args) -> int:
    project = TeamProject.load(args.project)
    sheet = args.sheet if args.sheet.is_absolute() else project.root / args.sheet
    if not sheet.is_file():
        raise SetupError(f"no review sheet at {project.relative(sheet)}: run qa-agent review export first")
    result = import_review_sheet(project, sheet)
    print(result.as_text())
    return FINDINGS if result.refused else DONE


def run_generate(args) -> int:
    result = generate(TeamProject.load(args.project), check=args.check)
    print(result.as_text())
    return FINDINGS if result.problems or result.drifted else DONE


def run_trace(args) -> int:
    project = TeamProject.load(args.project)
    results = [path if path.is_absolute() else project.root / path for path in args.results]
    missing = [project.relative(path) for path in results if not path.exists()]
    if missing:
        raise SetupError(f"no such results: {', '.join(missing)}")
    report = build_trace(project, results)
    if args.min_coverage is not None:
        report.apply_floor(args.min_coverage)
    out = args.out if args.out.is_absolute() else project.root / args.out
    out.mkdir(parents=True, exist_ok=True)
    (out / "trace.md").write_text(report.as_markdown(), encoding="utf-8")
    report.write_excel(out / "trace.xlsx")
    print(report.as_text())
    print(f"\nWritten: {project.relative(out / 'trace.md')}, {project.relative(out / 'trace.xlsx')}")
    failed = (args.check and report.missing_tests) or report.below_floor
    return FINDINGS if failed else DONE


def run_promote(args) -> int:
    project = TeamProject.load(args.project)
    runs = [path if path.is_absolute() else project.root / path for path in args.runs]
    missing = [project.relative(path) for path in runs if not path.exists()]
    if missing:
        raise SetupError(f"no such runs: {', '.join(missing)}")
    print(promote(project, runs, args.apply).as_text(len(runs)))
    return DONE


def run_suite(args) -> int:
    print(move_to_suite(TeamProject.load(args.project), args.case_id, args.suite, args.by, args.reason))
    return DONE


def run_bug_detection(args) -> int:
    project = TeamProject.load(args.project)
    seeded_bugs = args.seeded_bugs if args.seeded_bugs.is_absolute() else project.root / args.seeded_bugs
    print(measure(project, seeded_bugs, args.framework).as_text())
    print("\nWritten: reports/bug-detection.md")
    return DONE


def run_draft_cases(args) -> int:
    project = TeamProject.load(args.project)
    if args.plan:
        try:
            session = AiSession.for_project(project)
        except ModelSetupError:
            session = None                   # a plan needs no model; the cost shows once ai: is set
        print(plan(project, args.max, session))
        return DONE
    report = draft_cases(project, AiSession.for_project(project), args.max)
    print(report.as_text())
    if report.stopped:
        return SETUP_PROBLEM
    return FINDINGS if report.refused else DONE


def run_draft_criteria(args) -> int:
    project = TeamProject.load(args.project)
    try:
        report = draft_criteria(project, AiSession.for_project(project), args.requirement)
    except ModelError as error:
        print(f"qa-agent: the model couldn't be reached: {error}", file=sys.stderr)
        return SETUP_PROBLEM
    print(report.as_text())
    return FINDINGS if report.refused else DONE


def run_check(args) -> int:
    report = check_project(TeamProject.load(args.project))
    print(report.as_text())
    return FINDINGS if report.has_errors else DONE


if __name__ == "__main__":
    sys.exit(main())
