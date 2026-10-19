import json

import httpx
import pytest

from env_check import SetupError, check_environment
from env_check.__main__ import main


def run(files, network, **file_overrides):
    environments, dependencies = files(**file_overrides)
    waits = []
    report = check_environment("mock", environments, dependencies, http=network.client(), sleep=waits.append)
    return report, waits


def test_ready_when_every_service_answers(files, network):
    report, waits = run(files, network)
    assert report.ready and report.exit_code == 0 and waits == []
    assert [str(r.url) for r in network.requests] == ["http://bookings.test/health-check",
                                                      "http://notify.test/health-check"]
    assert all(r.method == "GET" for r in network.requests)


def test_a_non_critical_service_down_still_ready_and_listed(files, network):
    network.status["notify.test"] = 503
    report, _ = run(files, network)
    assert report.ready and report.exit_code == 0
    assert "DOWN, not critical" in report.as_text()


def test_a_critical_service_down_is_not_ready_after_retries(files, network):
    network.status["bookings.test"] = 503
    report, waits = run(files, network)
    assert not report.ready and report.exit_code == 3
    bookings = report.results[0]
    assert bookings.attempts == 3 and waits == [1.0, 2.0]          # waits double between attempts
    assert "NOT READY (exit 3): bookings down" in report.as_text()


def test_a_service_that_recovers_on_retry_is_ok(files, network):
    answers = iter([503, 200])

    def flaky(request):
        return httpx.Response(next(answers) if request.url.host == "bookings.test" else 200)
    environments, dependencies = files()
    report = check_environment("mock", environments, dependencies,
                               http=httpx.Client(transport=httpx.MockTransport(flaky)), sleep=lambda s: None)
    assert report.ready and report.results[0].attempts == 2


def test_cannot_connect_and_timeout_are_reported(files, network):
    network.status["bookings.test"] = httpx.ConnectError("refused")
    network.status["notify.test"] = httpx.ReadTimeout("slow")
    report, _ = run(files, network)
    errors = [r.error for r in report.results]
    assert errors == ["cannot connect: ConnectError", "no answer within 5 s"]


def test_a_service_specific_path_and_status(files, network):
    report, _ = run(files, network, dependencies="""
checks:
  - service: bookings
    path: /actuator/health
    expect_status: 200
""")
    assert str(network.requests[0].url) == "http://bookings.test/actuator/health" and report.ready


@pytest.mark.parametrize("environments, dependencies, message", [
    ("environments: {}", "checks: [{service: bookings}]", "unknown environment 'mock'"),
    (None, "checks: [{service: payments}]", "service 'payments' is not in environment 'mock'"),
    (None, "checks: []", "'checks' must list at least one service"),
    (None, "checks: [{service: bookings, critcal: false}]", "unknown setting(s) for 'bookings': critcal"),
    (None, "checks: [{service: bookings}]\nattempts: 0", "'attempts' must be a whole number"),
    (None, "checks: [", "not valid YAML"),
])
def test_setup_problems_are_named(files, network, environments, dependencies, message):
    from tests.env_check.conftest import ENVIRONMENTS
    paths = files(environments=environments or ENVIRONMENTS, dependencies=dependencies)
    with pytest.raises(SetupError, match=message.replace("(", r"\(").replace(")", r"\)")):
        check_environment("mock", *paths, http=network.client())


def test_command_exit_codes_and_json(files, capsys, tmp_path):
    environments, dependencies = files()
    assert main(["--env", "nope", "--environments", str(environments), "--dependencies", str(dependencies)]) == 2
    assert "SETUP PROBLEM (exit 2): unknown environment 'nope'" in capsys.readouterr().err
    assert main(["--env", "mock", "--environments", str(tmp_path / "missing.yaml"),
                 "--dependencies", str(dependencies)]) == 2


def test_command_json_report(files, network, capsys, monkeypatch):
    environments, dependencies = files()
    fake_client = network.client()
    monkeypatch.setattr("env_check.readiness.httpx.Client", lambda: fake_client)
    assert main(["--env", "mock", "--environments", str(environments), "--dependencies", str(dependencies),
                 "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["ready"] is True and [r["service"] for r in report["results"]] == ["bookings", "notifications"]
