# Python API framework (`api_test_framework`)

Plain API tests on pytest and httpx. A test only says what to send and what to expect; the
framework handles environments, tokens, values carried between steps, and readable failures.
`qa-agent generate` will write tests in exactly this shape.

```bash
pip install -e ../.. -e .                  # the reference API + env_check, then this framework
python -m demo_api &                       # the reference API (bookings :8000, notifications :8001)
python -m env_check --env demo && pytest   # is the environment ready? then run
```

## A test

```python
@pytest.mark.regression
@pytest.mark.writes
@pytest.mark.case("TC003")
def test_cancel_exactly_at_24_hours_gets_a_full_refund(api, context):
    created = api.post("/bookings", json={**new_passenger(), "amount": 250, "booked_at": "2026-01-15T10:00:00Z"})
    Expect(created).status_is(201)
    pnr = context.remember("pnr", created.value("pnr"))

    cancelled = api.post(f"/bookings/{pnr}/cancel", json={"cancelled_at": "2026-01-16T10:00:00Z"})
    Expect(cancelled).status_is(200).field_equals("refund_allowed", True).field_equals("refund_amount", 250)
```

## When it fails

The expectation that broke, with its request and response, then every step of the test in order:

```
E   ExpectationFailed: field 'refund_allowed': expected True, got False
E     POST http://localhost:8000/bookings/PUGWAY/cancel  {"cancelled_at": "2026-01-16T10:00:01Z"}
E     -> 200 {"pnr":"PUGWAY","refund_allowed":false,"refund_amount":0.0,...}  (2 ms)
----------------------------- API steps, in order ------------------------------
step 1
  POST http://localhost:8000/bookings  {"passenger_name": "Test Passenger 6656ce", ...}
  -> 201 {"pnr":"PUGWAY", ...}  (2 ms)
step 2
  POST http://localhost:8000/bookings/PUGWAY/cancel  {"cancelled_at": "2026-01-16T10:00:01Z"}
  -> 200 {"pnr":"PUGWAY","refund_allowed":false, ...}  (2 ms)
```

Tokens are masked (`***`) wherever a request is shown.

## Every feature, with its example

| Feature | How | Example |
|---|---|---|
| GET, 404, 401 | `api.get(...)`, `api.without_auth()` | [`test_get_booking.py`](tests/examples/test_get_booking.py) |
| A chain of calls | `context.remember("pnr", response.value("pnr"))` | [`test_booking_lifecycle.py`](tests/examples/test_booking_lifecycle.py) |
| A token carried into the next calls | `headers={"Authorization": ...}` | [`test_auth_chain.py`](tests/examples/test_auth_chain.py) |
| Data-driven | `load_rows("data/....csv")` (also JSON and Excel) | [`test_cancel_boundaries.py`](tests/examples/test_cancel_boundaries.py) |
| Lists: your items, never totals | `list_contains(...)`, `list_excludes(...)` | [`test_list_and_filters.py`](tests/examples/test_list_and_filters.py) |
| Another service, same environment | `api_for("notifications")` | [`test_other_services.py`](tests/examples/test_other_services.py) |
| Reading a field anywhere | `response.value("items[0].pnr")` | all of them |
| Data no other test is using | `unique_id()` (six characters, `7f3a9c`); `new_passenger()` uses it | `new_passenger()` in most examples; every test qa-agent generates |

**Expect:** `status_is` · `field_equals` · `field_exists` · `field_is_type` (string, number, integer,
boolean, list, object, null) · `field_contains` · `list_length` · `list_contains` · `list_excludes` ·
`header_equals` · `responded_within`.

## Environments

[`config/environments.yaml`](config/environments.yaml) lists every environment: its services, how to get a token,
a timeout, and whether tests may change data there.

```bash
pytest --env qa1                     # same tests, other hosts (or API_ENV=qa1)
pytest --env staging -m writes -rs   # read-only: every test that changes data is skipped, with the reason
```

| `auth.type` | Token from |
|---|---|
| `none` | no header |
| `static_token` | the environment variable named in `token_env` |
| `client_credentials` | the token endpoint, once per run; the id and secret from `client_id_env` and `client_secret_env` (plain values for the demo API only) |

A missing environment, file or variable stops the run with `SETUP PROBLEM` (exit 2), never a test failure.

## Markers

| Marker | Meaning |
|---|---|
| `smoke` | the few checks that say the service is up and usable: `pytest -m smoke` |
| `regression` | runs on every build: `pytest -m regression` |
| `functional` | new behaviour, run on demand until promoted |
| `writes` | changes data: skipped on a `read_only` environment, with the reason |
| `case("TC003")` | the test case it came from: a JUnit property and an Allure label |
| `priority("P0")` | P0 (highest) to P3: a JUnit property, and the severity in Allure (P0 blocker, P1 critical, P2 normal, P3 minor); the test is also marked `p0`, so `pytest -m p0` runs the P0 tests |

## Reports, evidence and retries

```bash
pytest --alluredir reports/allure-results --evidence reports/evidence --reruns 1 --junitxml reports/junit.xml
npx allure-commandline generate reports/allure-results -o reports/allure-report --single-file   # needs Java
```

| What | For whom |
|---|---|
| **Allure report** | People: every test with its steps; each request and response attached (token masked); case id, priority and markers as labels; the environment and hosts the run used |
| **Evidence folder** | Audits and sign-off: one text file per test, pass, fail or skipped, with every request and response |
| **JUnit XML** | CI: `case_id`, `priority` and `passed_on_retry` as properties. A data-driven test shows its case id once per row: one case, many runs |
| **Retry** (`--reruns 1`) | A failure is run once more. A test that passes only on retry is listed under *Passed on retry: look at these*, flagged in JUnit and Allure, never counted as a plain pass |

The framework never imports the service it tests (a unit test checks this): expected values come
from the test or its data. Its own tests: `pytest tests/unit` (no service needed).
