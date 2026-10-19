"""Run the reference API, or export its OpenAPI description.

    python -m mock_service                          bookings on :8000, notifications on :8001
    python -m mock_service --only bookings          one service (stop it to see env_check say "not ready")
    python -m mock_service --export-openapi mock_service/openapi.json
"""

import argparse
import asyncio
import json
from pathlib import Path

from mock_service.bookings_app import create_bookings_app
from mock_service.notifications_app import create_notifications_app
from mock_service.settings import MockSettings

SERVICES = {"bookings": (create_bookings_app, 8000), "notifications": (create_notifications_app, 8001)}


def openapi_text() -> str:
    """The bookings service's OpenAPI description, from default settings so it is the same everywhere."""
    return json.dumps(create_bookings_app(MockSettings()).openapi(), indent=2) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m mock_service", description="The reference API for api-qa-agent.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--only", choices=sorted(SERVICES), help="run one service instead of both")
    parser.add_argument("--export-openapi", metavar="PATH", help="write the OpenAPI description and exit")
    args = parser.parse_args(argv)

    if args.export_openapi:
        Path(args.export_openapi).write_text(openapi_text(), encoding="utf-8")
        print(f"OpenAPI description written to {args.export_openapi}")
        return 0

    import uvicorn

    settings = MockSettings.from_environment()
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
