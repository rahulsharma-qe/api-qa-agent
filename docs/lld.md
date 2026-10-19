# api-qa-agent: low-level design

The high-level design ([architecture.md](architecture.md)) says what the utility is and why. This
document says how each part is built. It grows phase by phase: this version covers **phase 0**
(the mock service) and **phase 1** (the Python framework and env_check) in full; later phases
get their sections when they are designed.

## 1. Repository layout after phase 1

```
api-qa-agent/
  README.md  LICENSE  CHANGELOG.md
  mock_service/                  the reference API under test (FastAPI)
    __main__.py                  python -m mock_service  -> bookings on :8000, notifications on :8001
    bookings_app.py              create_bookings_app(): routes for auth, bookings, refunds, health
    notifications_app.py         create_notifications_app(): a stand-in dependency that can be switched down
    booking_store.py             BookingStore: in-memory bookings, reset for tests
    refund_rules.py              decide_refund(booking, cancelled_at): the 24-hour rule, in one place
    models.py                    request and response shapes (pydantic)
    errors.py                    one error shape for every failure
    openapi.json                 the OpenAPI description, exported from the app and committed
  env_check/                     is the environment ready? (one tool for every framework)
    __main__.py                  python -m env_check --env qa2 --dependencies teams/x/dependencies.yaml
    readiness.py                 check_environment() -> ReadinessReport
    settings.py                  reads environments.yaml and dependencies.yaml
  frameworks/
    python_api/                  installable on its own: pip install ./frameworks/python_api
      pyproject.toml
      api_test_framework/
        environment.py           EnvironmentConfig, load_environment()
        auth.py                  NoAuth, StaticToken, ClientCredentials
        api_client.py            ApiClient: get / post / put / patch / delete -> ApiResponse
        api_response.py          ApiResponse: status, json, headers, elapsed, value("a.b[0].c")
        expect.py                Expect(response).status_is(201).field_equals("status", "active") ...
        scenario_context.py      ScenarioContext: values carried between steps, and the step history
        test_data.py             load_rows() from JSON, CSV or Excel; new_passenger()
        pytest_plugin.py         fixtures, --env, markers, the chain shown on failure
      config/environments.yaml   mock, qa1, qa2, staging
      data/cancellation_boundaries.csv
      tests/examples/            one runnable example per feature, shaped like generated tests
      tests/unit/                the framework's own tests (no network)
  tests/mock_service/            the mock service's own tests
  docs/  architecture.md  lld.md  history/first-version.md
  .github/workflows/ci.yml
```

**Rules**
- `frameworks/python_api` never imports `mock_service`: expected values come from the test or
  its data, never from the service's code. A unit test fails the build if such an import appears.
- `env_check` and the framework read the same `environments.yaml` format.
- Every folder has a README with how to run it in three commands or fewer.
- Tests make their own data and check their own items, never totals: they pass in any order and on
  an environment other teams are using.

```mermaid
flowchart TB
  subgraph REF["Reference API (phase 0)"]
    MS["mock_service<br/>bookings · notifications"]
  end
  subgraph TOOLS["Tools (phase 1)"]
    EC["env_check"]
    FW["api_test_framework"]
  end
  EX["tests/examples<br/>and a team's tests"]
  CFG["environments.yaml<br/>dependencies.yaml"]
  EX --> FW
  FW -->|"HTTP only"| MS
  EC -->|"GET /health-check only"| MS
  CFG --> EC
  CFG --> FW
  classDef box fill:#1e293b,stroke:#94a3b8,color:#f1f5f9
  class MS,EC,FW,EX,CFG box
  style REF fill:#1f2937,stroke:#64748b,color:#e2e8f0
  style TOOLS fill:#111827,stroke:#94a3b8,color:#f1f5f9
  linkStyle default stroke:#94a3b8,stroke-width:2px
```

## 2. Mock service (phase 0)

### 2.1 Endpoints

All `/bookings` endpoints need `Authorization: Bearer <token>`; without it, or with a wrong
token: **401**.

| Method and path | Request | Success | Other responses |
|---|---|---|---|
| `POST /auth/token` | `{client_id, client_secret}` | 200 `{access_token, token_type: "Bearer", expires_in: 3600}` | 401 wrong credentials |
| `POST /bookings` | `{passenger_name, email, amount, booked_at?}` | 201 the booking | 422 invalid field |
| `GET /bookings/{pnr}` | | 200 the booking | 404 |
| `GET /bookings?status=active&limit=20` | | 200 `{items: [...], count}` | 422 bad filter |
| `PUT /bookings/{pnr}` | `{passenger_name, email}` | 200 the booking | 404; 422 invalid, or `amount` sent (it can't change) |
| `DELETE /bookings/{pnr}` | | 204 | 404 |
| `POST /bookings/{pnr}/cancel` | `{cancelled_at?}` | 200 `{pnr, refund_allowed, refund_amount, reason}` | 404; 409 already cancelled; 422 cancelled before booked |
| `GET /bookings/{pnr}/refund` | | 200 `{pnr, refund_status: "refunded" \| "no_refund" \| "not_cancelled", refund_amount}` | 404 |
| `GET /health-check` | no token needed | 200 `{status: "ok", service: "bookings"}` | |
| `POST /test/reset` | no token needed | 204, every booking removed | 404 when test mode is off |

**Notifications stand-in (port 8001):** `GET /health-check` returns 200, or 503 while it is
switched down (`POST /test/state {"down": true}` or `NOTIFICATIONS_DOWN=1`). Bookings never call
it; it exists so env_check has a non-critical dependency to report on.

### 2.2 The booking

| Field | Rule |
|---|---|
| `pnr` | 6 upper-case letters and digits, made by the service, unique |
| `passenger_name` | 1 to 100 characters |
| `email` | a valid address |
| `amount` | a number, 0 or more; fixed after creation |
| `status` | `active` or `cancelled` |
| `booked_at` | ISO 8601 with a time zone; the caller may set it (so time boundaries can be tested), otherwise now |
| `cancelled_at` | empty until cancelled |

### 2.3 The refund rule (`refund_rules.decide_refund`)

| Hours from `booked_at` to `cancelled_at` | Result |
|---|---|
| less than 0 | 422: cancelled before it was booked |
| 0 to 24, **24 included** | refund allowed, full amount |
| more than 24 | no refund, amount 0 |

`cancelled_at` defaults to now. A second cancel returns 409 and changes nothing.

### 2.4 Errors, configuration, OpenAPI

- **One error shape** for every failure, including validation:
  `{"error": {"code": "booking_not_found", "message": "No booking with PNR AB12CD"}}`.
- **Configuration by environment variables:** `MOCK_CLIENT_ID` and `MOCK_CLIENT_SECRET`
  (defaults `demo-client` and `demo-secret`), `MOCK_TEST_MODE` (default on; turns `/test/*` on).
- **OpenAPI:** `python -m mock_service --export-openapi mock_service/openapi.json`. A test fails if the
  committed file differs from what the app produces, so the description never drifts.

## 3. env_check (phase 1)

### 3.1 Files

```yaml
# environments.yaml (shared with the framework)
environments:
  mock:
    services: {bookings: "http://localhost:8000", notifications: "http://localhost:8001"}
    auth: {type: client_credentials, service: bookings, token_path: /auth/token,
           client_id: demo-client, client_secret: demo-secret}   # plain values: mock only
    timeout_seconds: 10
    read_only: false
  qa1:
    services: {bookings: "https://qa1.example/bookings", notifications: "https://qa1.example/notify"}
    auth: {type: client_credentials, service: bookings, token_path: /auth/token,
           client_id_env: QA1_CLIENT_ID, client_secret_env: QA1_CLIENT_SECRET}
    read_only: false
  staging:
    services: {bookings: "https://staging.example/bookings"}
    auth: {type: static_token, token_env: STAGING_TOKEN}
    read_only: true
```

```yaml
# dependencies.yaml (one per team)
team: cancellations
checks:
  - service: bookings                 # host from environments.yaml
    critical: true
  - service: notifications
    path: /health-check               # default; set it when a service uses another path
    critical: false
```

Per check, with defaults: `path: /health-check`, `expect_status: 200`, `timeout_seconds: 5`,
`critical: true`. Per file: `attempts: 3`, `wait_seconds: 2` (doubled after each failed attempt).

### 3.2 Behaviour

1. Read both files; a missing service, a bad field or an unknown environment is a setup error.
2. For each check, `GET` (only `GET`) the service's path; retry a failed attempt after the wait.
3. Print one line per check (service, status, time, ok / DOWN) and a verdict.

| Exit code | Meaning |
|---|---|
| 0 | Ready (a non-critical service may be down; it is listed) |
| 2 | Setup problem: a file or setting is wrong |
| 3 | Not ready: a critical service is down. Not a test failure |

`--json` prints the same report as JSON for CI pages. From Python: `check_environment(name,
environments_path, dependencies_path) -> ReadinessReport`.

## 4. Python framework (phase 1)

### 4.1 Classes

```mermaid
classDiagram
  direction LR
  class EnvironmentConfig {
    name
    services
    auth
    read_only
    base_url(service)
  }
  class ApiClient {
    get(path, params, headers)
    post(path, json, headers)
    put(path, json, headers)
    patch(path, json, headers)
    delete(path, headers)
  }
  class ApiResponse {
    status_code
    json
    headers
    elapsed_ms
    request
    value(path)
  }
  class Expect {
    status_is(code)
    field_equals(path, value)
    field_exists(path)
    field_is_type(path, type)
    field_contains(path, text)
    list_length(path, n)
    header_equals(name, value)
    responded_within(ms)
  }
  class ScenarioContext {
    remember(name, value)
    get(name)
    steps
  }
  class TokenProvider {
    <<interface>>
    header()
  }
  ApiClient --> EnvironmentConfig : base URL, timeout
  ApiClient --> TokenProvider : Authorization header
  ApiClient --> ApiResponse : returns
  ApiClient --> ScenarioContext : records each step
  Expect --> ApiResponse : checks
  TokenProvider <|-- NoAuth
  TokenProvider <|-- StaticToken
  TokenProvider <|-- ClientCredentials
```

| Class | Responsibility | Notes |
|---|---|---|
| `EnvironmentConfig` | One environment from `environments.yaml` | Chosen by `--env` or `API_ENV` (default `mock`) |
| `TokenProvider` | The `Authorization` header | `NoAuth`; `StaticToken` from an environment variable; `ClientCredentials` asks the token endpoint once per run and reuses it |
| `ApiClient` | One service's HTTP calls | Base URL from the environment; timeout; records every request and response in the scenario context; the token is masked in every log; `without_auth()` gives the same client with no token, for 401 tests |
| `ApiResponse` | What came back | `value("items[0].pnr")` reads any field by a dotted path; a missing field fails with the path and the body |
| `Expect` | Checks, chained | Each failure says what was expected, what came back, and the request that produced it |
| `ScenarioContext` | Values carried between steps, and the steps so far | Fresh for every test |

### 4.2 pytest plugin

| Gives | How |
|---|---|
| `--env qa2` | Same as `API_ENV=qa2` |
| Fixtures | `environment`; `api` (client for the default service); `api_for("notifications")`; `context` |
| Markers | `regression`, `functional`, `writes` (changes data: skipped on a `read_only` environment, with the reason in the report), `case("TC003")` (the case id, written into the JUnit report for traceability) |
| On failure | The whole chain: every step's request and response, then the expectation that broke |
| Report | `pytest --junitxml=reports/junit.xml` |

### 4.3 A test written with it

```python
@pytest.mark.functional
@pytest.mark.writes
@pytest.mark.case("TC003")
def test_cancel_exactly_at_24_hours_gets_a_full_refund(api, context):
    created = api.post("/bookings", json={**new_passenger(), "amount": 250,
                                           "booked_at": "2026-10-20T10:00:00Z"})
    Expect(created).status_is(201)
    context.remember("pnr", created.value("pnr"))

    cancelled = api.post(f"/bookings/{context.get('pnr')}/cancel",
                         json={"cancelled_at": "2026-10-21T10:00:00Z"})
    Expect(cancelled).status_is(200).field_equals("refund_allowed", True).field_equals("refund_amount", 250)
```

This is the shape `qa-agent generate` will write in phase 3: no logic, only steps and checks.

### 4.4 Examples (one per feature)

| Example | Shows |
|---|---|
| `test_get_booking.py` | GET: 200, 404, and 401 without a token |
| `test_booking_lifecycle.py` | Create → read → update → read → delete → read gives 404, the PNR carried between steps |
| `test_auth_chain.py` | Token → create → cancel → refund status, across three endpoints |
| `test_cancel_boundaries.py` | Data-driven from `data/cancellation_boundaries.csv`: 23:59, exactly 24:00, 24:01, cancelled before booked, already cancelled |
| `test_list_and_filters.py` | List with a filter, count, list length |
| Environments | README: the same tests with `--env qa1`; a `writes` test skipped on a `read_only` environment |
| env_check | README: ready, then the notifications stand-in switched down (warned, still ready), then bookings stopped (exit 3) |

## 5. CI (phases 0 and 1)

| Job | Steps |
|---|---|
| `mock-service` | Install; the mock's own tests; the OpenAPI drift test |
| `python-framework` | Install the mock and the framework; start both services in the background; `python -m env_check --env mock`; unit tests; examples with a JUnit report; keep the report |

Both on Python 3.11 and 3.12, on every push and pull request. No API key anywhere.

## 6. Dependencies

| Part | Packages |
|---|---|
| mock_service | fastapi, uvicorn, pydantic |
| env_check | httpx, pyyaml |
| api_test_framework | httpx, pyyaml, pytest, openpyxl (Excel data) |

## 7. What happens to the current code

| Today | Phase 0 and 1 |
|---|---|
| `README.md` | Phase 0: a short note at the top that the repository is being rebuilt, with links to the new design; rewritten when phase 1 ends, after your review |
| `.github/workflows/ci.yml` | Keeps running the first version's tests until they are removed; the new jobs are added next to it |
| `docs/architecture.md` (first version's decisions) | Moves to `docs/history/first-version.md`, unchanged; the new design takes its place |
| `core/` (the language-model pipeline) | Stays until phase 6 reworks it into the AI layer |
| `adapters/`, `examples/` (first version's engine, reference stacks and mock) | Stay until phase 1 ends, then are removed; the reference stacks are on the later list; git history keeps them |
| Numbered labels in docstrings and docs | Replaced with plain names in phase 0 |
| No licence | MIT in phase 0 |
