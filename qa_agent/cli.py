"""qa-agent: the command line.

    qa-agent import api api/source/openapi.json      the API description -> api/api.yaml
    qa-agent check                                   the cases, checked with rules

Exit codes: 0 done (no errors), 1 errors found, 2 the project or an input can't be read.
"""

import argparse
import sys
from pathlib import Path
from typing import Optional

from qa_agent import __version__
from qa_agent.api_model import ApiModel, ApiModelError, load_api_model, save_api_model
from qa_agent.checks import check_project, plural
from qa_agent.importers.curl import CurlError, read_curl
from qa_agent.importers.openapi import OpenApiError, read_openapi
from qa_agent.project import SetupError, TeamProject

DONE, FINDINGS, SETUP_PROBLEM = 0, 1, 2


def main(argv: Optional[list[str]] = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if not getattr(args, "run", None):
        parser.print_help()
        return SETUP_PROBLEM
    try:
        return args.run(args)
    except (SetupError, ApiModelError, OpenApiError, CurlError) as error:
        print(f"qa-agent: {error}", file=sys.stderr)
        return SETUP_PROBLEM


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="qa-agent", description="Test cases as data: import, check, review, "
                                                                   "generate and trace, in the team's framework.")
    parser.add_argument("--version", action="version", version=f"qa-agent {__version__}")
    parser.add_argument("--project", type=Path, default=Path("."), help="the team's project folder (default: here)")
    commands = parser.add_subparsers(title="commands", metavar="<command>")

    importing = commands.add_parser("import", help="read what the team already has").add_subparsers(
        title="what to import", metavar="<what>")
    api = importing.add_parser("api", help="an API description (OpenAPI, or curl with a sample response) "
                                           "-> api/api.yaml")
    api.add_argument("files", nargs="+", type=Path, help="openapi.json, openapi.yaml, or .curl files")
    api.add_argument("--service", help="the service these operations belong to (default: the project's service)")
    api.set_defaults(run=import_api)

    check = commands.add_parser("check", help="check every case with rules; exit 1 on errors")
    check.set_defaults(run=run_check)
    return parser


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


def run_check(args) -> int:
    report = check_project(TeamProject.load(args.project))
    print(report.as_text())
    return FINDINGS if report.has_errors else DONE


if __name__ == "__main__":
    sys.exit(main())
