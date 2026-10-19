"""The plugin, run inside a throwaway pytest session (pytester)."""

ENVIRONMENTS = """
environments:
  mock:
    services: {bookings: "http://bookings.test"}
  staging:
    services: {bookings: "http://staging.test"}
    read_only: true
"""


def make_project(pytester, test_code):
    pytester.makefile(".yaml", **{"config/environments": ENVIRONMENTS})
    pytester.makepyfile(test_code)


def test_writes_tests_are_skipped_on_a_read_only_environment(pytester):
    make_project(pytester, """
        import pytest

        @pytest.mark.writes
        def test_changes_data():
            pass

        def test_reads_only(environment):
            assert environment.name == "staging"
    """)
    result = pytester.runpytest("--env", "staging", "-rs")
    result.assert_outcomes(passed=1, skipped=1)
    result.stdout.fnmatch_lines(["*changes data; environment 'staging' is read-only*"])


def test_the_environment_comes_from_env_option_or_api_env(pytester, monkeypatch):
    make_project(pytester, """
        def test_name(environment):
            assert environment.base_url() == "http://staging.test"
    """)
    monkeypatch.setenv("API_ENV", "staging")
    pytester.runpytest().assert_outcomes(passed=1)
    monkeypatch.delenv("API_ENV")
    pytester.runpytest("--env", "staging").assert_outcomes(passed=1)


def test_the_case_id_goes_into_the_junit_report(pytester):
    make_project(pytester, """
        import pytest

        @pytest.mark.case("TC003")
        def test_x():
            pass
    """)
    pytester.runpytest("--junitxml=report.xml").assert_outcomes(passed=1)
    assert '<property name="case_id" value="TC003"' in (pytester.path / "report.xml").read_text()


def test_a_failure_shows_every_step_in_order(pytester):
    make_project(pytester, """
        import httpx
        from api_test_framework import ApiClient, Expect

        def test_chain(context):
            answers = iter([httpx.Response(201, json={"pnr": "AB12CD"}), httpx.Response(404, json={"error": {}})])
            api = ApiClient("http://bookings.test", httpx.Client(transport=httpx.MockTransport(lambda r: next(answers))),
                            context=context)
            pnr = api.post("/bookings", json={"amount": 1}).value("pnr")
            Expect(api.get(f"/bookings/{pnr}")).status_is(200)
    """)
    result = pytester.runpytest()
    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines(["*API steps, in order*", "step 1", "*POST http://bookings.test/bookings*",
                                 "*-> 201*", "step 2", "*GET http://bookings.test/bookings/AB12CD*", "*-> 404*"])


def test_a_missing_environment_stops_the_run_with_a_clear_message(pytester):
    make_project(pytester, """
        def test_x(api):
            pass
    """)
    result = pytester.runpytest("--env", "qa9")
    result.stdout.fnmatch_lines(["*SETUP PROBLEM: unknown environment 'qa9'*"])
    assert result.ret == 2
