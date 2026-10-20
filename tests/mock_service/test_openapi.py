"""The committed OpenAPI description must match the service: teams read it to write their tests."""

from pathlib import Path

from mock_service.__main__ import main, openapi_text

COMMITTED = Path(__file__).resolve().parents[2] / "mock_service" / "openapi.json"
EXPECTED_ROUTES = {"/auth/token", "/bookings", "/bookings/{pnr}", "/bookings/{pnr}/cancel",
                   "/bookings/{pnr}/refund", "/health-check", "/test/reset"}


def test_committed_openapi_matches_the_service():
    assert COMMITTED.read_text(encoding="utf-8") == openapi_text(), (
        "mock_service/openapi.json is out of date: run  python -m mock_service --export-openapi mock_service/openapi.json")


def test_openapi_lists_every_route():
    import json
    assert set(json.loads(openapi_text())["paths"]) == EXPECTED_ROUTES


def test_export_writes_the_file(tmp_path):
    target = tmp_path / "openapi.json"
    assert main(["--export-openapi", str(target)]) == 0
    assert target.read_text(encoding="utf-8") == openapi_text()


def test_every_error_the_service_returns_is_documented_with_the_one_error_shape():
    import json
    paths = json.loads(openapi_text())["paths"]
    documented = {(method.upper(), path): set(operation["responses"])
                  for path, methods in paths.items() for method, operation in methods.items()}
    assert {"401", "404", "409", "422"} <= documented[("POST", "/bookings/{pnr}/cancel")]
    assert all("401" in codes for (_, path), codes in documented.items() if path.startswith("/bookings"))
    assert all("404" in codes for (_, path), codes in documented.items() if "{pnr}" in path)
    cancel_409 = paths["/bookings/{pnr}/cancel"]["post"]["responses"]["409"]
    assert cancel_409["content"]["application/json"]["schema"]["$ref"].endswith("/ErrorResponse")
