"""Run the reference API, or export its OpenAPI description.

    python -m demo_api                          bookings on :8000, notifications on :8001
    python -m demo_api --only bookings          one service (stop it to see env_check say "not ready")
    python -m demo_api --export-openapi demo_api/openapi.json
    python -m demo_api --bug refund-boundary    one seeded bug switched on (for qa-agent bug-detection)
"""

import argparse
import asyncio
import json
from dataclasses import replace
from pathlib import Path

from demo_api.bookings_app import create_bookings_app
from demo_api.notifications_app import create_notifications_app
from demo_api.seeded_bugs import BUGS, UnknownBug, checked
from demo_api.settings import DemoApiSettings

SERVICES = {"bookings": (create_bookings_app, 8000), "notifications": (create_notifications_app, 8001)}


def openapi_text() -> str:
    """The bookings service's OpenAPI description, from default settings so it is the same everywhere."""
    return json.dumps(create_bookings_app(DemoApiSettings()).openapi(), indent=2) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m demo_api", description="The reference API for api-qa-agent.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--only", choices=sorted(SERVICES), help="run one service instead of both")
    parser.add_argument("--export-openapi", metavar="PATH", help="write the OpenAPI description and exit")
    parser.add_argument("--bug", metavar="NAME", help=f"switch on one seeded bug: {', '.join(BUGS)}")
    args = parser.parse_args(argv)

    if args.export_openapi:
        Path(args.export_openapi).write_text(openapi_text(), encoding="utf-8")
        print(f"OpenAPI description written to {args.export_openapi}")
        return 0

    import uvicorn

    settings = DemoApiSettings.from_environment()
    try:
        bug = checked(args.bug or settings.bug)
    except UnknownBug as error:
        print(f"demo_api: {error}")
        return 2
    settings = replace(settings, bug=bug)
    if bug:
        print(f"seeded bug switched on: {bug} ({BUGS[bug]})")
    names = [args.only] if args.only else list(SERVICES)
    servers = []
    for name in names:
        create_app, port = SERVICES[name]
        servers.append(uvicorn.Server(uvicorn.Config(create_app(settings), host=args.host, port=port,
                                                     log_level="warning")))
        print(f"{name}: http://{args.host}:{port}  (health: /health-check)")
    try:
        asyncio.run(_serve(servers))
    except KeyboardInterrupt:
        print("stopped")
    return 0


async def _serve(servers) -> None:
    await asyncio.gather(*(server.serve() for server in servers))


if __name__ == "__main__":
    raise SystemExit(main())
