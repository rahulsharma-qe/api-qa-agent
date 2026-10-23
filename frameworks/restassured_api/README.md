# REST Assured framework (TestNG)

Plain API tests on REST Assured and TestNG, in the layout Java QA teams know: a `BaseTest`,
groups and `testng.xml` suites, data providers, listeners, Allure. A test only says what to send
and what to expect; the framework handles environments, tokens, values carried between steps,
readable failures, evidence and retries. `qa-agent generate` will write tests in exactly this shape.

```bash
pip install -e ../..  &&  python -m demo_api &              # the reference API and env_check (from the repository root)
python -m env_check --env demo                              # is the environment ready?
./mvnw test                                                 # the Maven wrapper: Java 17 is all you need
```

## A test

```java
public class CancelRefundTest extends BaseTest {
    @Test(groups = {"regression", "writes"})
    @CaseId("TC003") @Priority("P1")
    public void cancelExactlyAt24HoursGetsAFullRefund() {
        ApiResponse created = api().post("/bookings", NewPassenger.with("amount", 250, "booked_at", "2026-01-15T10:00:00Z"));
        Expect.that(created).statusIs(201);
        String pnr = context().remember("pnr", created.text("pnr"));

        ApiResponse cancelled = api().post("/bookings/" + pnr + "/cancel", Map.of("cancelled_at", "2026-01-16T10:00:00Z"));
        Expect.that(cancelled).statusIs(200).fieldEquals("refund_allowed", true).fieldEquals("refund_amount", 250);
    }
}
```

When a test fails, the console and the TestNG report show the expectation that broke with its
request and response, then every step of the test in order. Tokens are masked (`***`).

## Every feature, with its example

| Feature | How | Example |
|---|---|---|
| GET, 404, 401 | `api().get(...)`, `api().withoutAuth()` | [`GetBookingTest`](src/test/java/apiqa/examples/GetBookingTest.java) |
| A chain of calls | `context().remember("pnr", response.text("pnr"))` | [`BookingLifecycleTest`](src/test/java/apiqa/examples/BookingLifecycleTest.java) |
| A token carried into the next calls | headers on `post(path, body, headers)` | [`AuthChainTest`](src/test/java/apiqa/examples/AuthChainTest.java) |
| Data-driven from Excel | `@DataProvider` + `TestData.rows("data/....xlsx")` (also CSV and JSON) | [`CancelBoundariesTest`](src/test/java/apiqa/examples/CancelBoundariesTest.java) |
| Lists: your items, never totals | `listContains(...)`, `listExcludes(...)` | [`ListAndFiltersTest`](src/test/java/apiqa/examples/ListAndFiltersTest.java) |
| Another service, same environment | `apiFor("notifications")` | [`OtherServicesTest`](src/test/java/apiqa/examples/OtherServicesTest.java) |
| Data no other test is using | `TestData.uniqueId()` (six characters, `7f3a9c`); `NewPassenger` uses it | `NewPassenger` in most examples; every test qa-agent generates |

**Expect:** `statusIs` · `fieldEquals` · `fieldExists` · `fieldIsType` (string, number, integer,
boolean, list, object, null) · `fieldContains` · `listLength` · `listContains` · `listExcludes` ·
`headerEquals` · `respondedWithin`.

## Groups, suites and environments

```bash
./mvnw test -Dgroups=smoke                                   # by group: smoke, regression, functional
./mvnw test -Dsurefire.suiteXmlFiles=suites/regression.xml   # or a testng.xml suite
./mvnw test -Denv=qa1                                        # same tests, other hosts (or API_ENV=qa1)
./mvnw test -Denv=staging -Dgroups=writes                    # read-only: every test that changes data is skipped, with the reason
```

The environments come from [`config/environments.yaml`](config/environments.yaml), the same format as the Python
framework and env_check: services, tokens (`none`, `static_token`, `client_credentials`), timeout, read-only.

| Annotation or group | Meaning |
|---|---|
| `groups = "smoke"`, `"regression"`, `"functional"` | which suite a test belongs to |
| `groups = "writes"` | changes data: skipped on a `read_only` environment |
| `@CaseId("TC003")` | the test case it came from: an Allure label and a TestNG attribute |
| `@Priority("P0")` | P0 (highest) to P3: the severity in Allure (P0 blocker, P1 critical, P2 normal, P3 minor) |

## Reports, evidence and retries

```bash
./mvnw test -Dretry=1 -Devidence=target/evidence
npx allure-commandline generate target/allure-results -o target/allure-report --single-file
```

| What | For whom |
|---|---|
| **Allure report** | People: every test with each request and response attached (token masked), case id and priority as labels |
| **Evidence folder** | Audits and sign-off: one text file per test, pass, fail or skipped, with every request and response |
| **Surefire and TestNG reports** | CI: `target/surefire-reports` |
| **Retry** (`-Dretry=1`) | A failure is run once more. A test that passes only on retry is listed under *Passed on retry: look at these*; TestNG counts the first try as skipped |

The framework never imports the service it tests: expected values come from the test or its data.
Its own tests (`FrameworkUnitTest`) need no service.
