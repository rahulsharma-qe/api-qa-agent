"""python -m env_check --env demo [--environments config/environments.yaml] [--dependencies config/dependencies.yaml] [--json]"""

import argparse
import json
import sys

from env_check.readiness import EXIT_SETUP_PROBLEM, check_environment
from env_check.settings import SetupError


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m env_check",
                                     description="Before tests run: is every service this team depends on up?")
    parser.add_argument("--env", required=True, help="environment name in environments.yaml, e.g. demo, qa2")
    parser.add_argument("--environments", default="config/environments.yaml", help="where each service lives")
    parser.add_argument("--dependencies", default="config/dependencies.yaml", help="which services this team needs")
    parser.add_argument("--json", action="store_true", help="print the report as JSON")
    args = parser.parse_args(argv)
    try:
        report = check_environment(args.env, args.environments, args.dependencies)
    except SetupError as error:
        print(f"SETUP PROBLEM (exit {EXIT_SETUP_PROBLEM}): {error}", file=sys.stderr)
        return EXIT_SETUP_PROBLEM
    print(json.dumps(report.as_dict(), indent=2) if args.json else report.as_text())
    return report.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
