# bookings-team: a team's project, for the reference API

This folder has exactly the shape of a team's own repository. It shows every `qa-agent` feature
against the reference API (`python -m demo_api`), with what each command printed: from the API
and the team's existing cases to tests in both frameworks and the trace.

```bash
./run_all.sh                  # every step from the inputs, both frameworks' tests, the trace (what CI runs)
./run_all.sh --pytest-only    # the same, without Java
```

| File | What it is |
|---|---|
| `qa-agent.yaml` | The team, its main service, its frameworks |
| `api/source/` | What the team brought: the OpenAPI description, and two curl commands with a sample response |
| `api/api.yaml` | The API model, imported from those sources |
| `acceptance-criteria.yaml` | Six acceptance criteria of the bookings and cancellation feature |
| `existing/` | The team's cases as they were, in four formats: Excel in the API layout, Excel in the manual layout, a Postman collection, a Gherkin feature |
| `cases/bookings.yaml`, `cases/cancellation.yaml` | Cases written directly in the case format |
| `cases/bookings-api.yaml`, `cases/refunds.yaml`, `cases/bookings-smoke.yaml`, `cases/cancellation-scenarios.yaml` | The cases imported from `existing/`, one file per feature |
| `data/` | Data files: one row per run of a data-driven case (one came from the Gherkin outline's Examples) |
| `review/cases.xlsx` | The review sheet, filled in by the reviewer |
| `config/` | Environments and dependencies, read by env_check and the frameworks |
| `tests/generated/`, `src/test/java/generated/` | The tests `qa-agent generate` wrote from the approved cases, in pytest and in REST Assured |
| `pytest.ini`, `pom.xml`, `mvnw` | How each framework runs here, as `qa-agent init` makes them |
| `run_all.sh` | Every step, from the inputs to the trace |

## 1. The API

```bash
cd examples/bookings-team                  # after pip install -e . at the repository's root
qa-agent import api api/source/openapi.json api/source/cancel_booking.curl
qa-agent import api api/source/notifications_health.curl --service notifications
```

The OpenAPI description and the curl commands become one model. The curl's `Authorization` header
is not kept, and `/bookings/AB12CD/cancel` is read as `/bookings/{id}/cancel`, the operation the
OpenAPI description already has.

## 2. The team's existing cases

```bash
qa-agent import cases existing/booking_cases.xlsx existing/manual_cases.xlsx \
  existing/bookings.postman_collection.json existing/cancel.feature
```

```
cases/bookings-api.yaml: TC010, TC011, TC012
cases/refunds.yaml: TC020, TC021, TC022
cases/bookings-smoke.yaml: TC030, TC042
cases/cancellation-scenarios.yaml: TC040, TC041
new id TC042: Health check
data file written: data/cancellation-scenarios-tc040.csv
note: existing/bookings.postman_collection.json, 'Create and read a booking' step 2: pm.expect(body.passenger_name).to.match(/Meera/);
note: existing/cancel.feature, 'Cancelling twice tells the passenger it is already cancelled': not in the fixed phrasing; kept in words (needs steps)
10 cases imported as drafts, 0 skipped
```

(Run it again and every case is skipped: their ids are already in the project, and the health
request keeps the id it was given.)

**Case ids** are the team's own, never renumbered: they are what TestRail, Jira and old reports know
a case by. Here each source had its own series (TC001 to TC006 written directly, TC010 from the API
sheet, TC020 from the manual sheet, TC030 and TC040 from Postman and Gherkin). A case with no id
gets the next free one with the project's prefix (`case_id_prefix: TC` in `qa-agent.yaml`): TC042.

**Tags** are the team's labels for picking runs (`smoke`, `crud`, `negative`, `refund`); they become
pytest markers and TestNG groups. They come from a sheet's Tags column or Gherkin tags; Postman has
none, so the reviewer adds them in the review sheet.

- **Excel, API layout:** one row per step, so TC010 to TC012 come in ready to run.
- **Excel, manual layout:** TC020 to TC022 have steps in words, so they come in as "needs steps".
  TC022 is TC020 again under another title, as happens in a sheet that grew over the years.
- **Postman:** the folder "TC030 Create and read a booking" is one case of two requests; its test
  scripts became the status, fields, `contains`, a response-time limit and the captured PNR.
  `{{$randomInt}}` and `{{$guid}}` became `{{unique}}`, the token header was dropped, and the one
  line qa-agent can't read (`to.match(/Meera/)`) is in the case's notes. The health request had no
  id, so it got the next free one: TC042.
- **Gherkin:** TC040 is in the fixed phrasing, so it became steps, and its Examples became a data
  file. TC041 is in words.

## 3. Check

```bash
qa-agent check
```

```
qa-agent check: bookings · 16 cases in 6 files

cases/refunds.yaml
  warning  TC022: same steps as TC020 (cases/refunds.yaml). Fix: reject one in the review sheet, or remove it
  info     TC020: needs steps (it has manual steps only). It is kept and traced, and can't be generated until it has steps
  info     TC021: needs steps (it has manual steps only). It is kept and traced, and can't be generated until it has steps
  info     TC022: needs steps (it has manual steps only). It is kept and traced, and can't be generated until it has steps

cases/bookings-smoke.yaml
  warning  TC030: linked to no criterion. Fix: add criteria: [AC-…] so it can be traced
  warning  TC042: linked to no criterion. Fix: add criteria: [AC-…] so it can be traced

cases/bookings.yaml
  warning  TC005 step 1: status 400 is not documented for POST /bookings (documented: 201, 401, 422). Fix: check the expected status, or document it in the API
  warning  TC005 step 1: the body leaves out required email. Fine for a negative test; otherwise add them

cases/cancellation-scenarios.yaml
  info     TC041: needs steps (it has manual steps only). It is kept and traced, and can't be generated until it has steps

cases/cancellation.yaml
  info     TC006: needs steps (it has manual steps only). It is kept and traced, and can't be generated until it has steps

1 group of duplicate cases (1 case repeating another case's steps)

0 errors · 5 warnings · 5 notes
```

- **TC005** expects 400 where the API returns 422: a mistake a person makes, caught before any
  test runs. Leaving out `email` is the point of this negative test, so that warning stays.
- **TC030 and TC042** came from Postman, which has no criteria: the reviewer links TC030 to AC-1
  and rejects TC042 (below).
- **TC022** repeats TC020's steps under another title: a duplicate, caught by comparing the steps,
  not the ids or titles. The reviewer decides which one stays.
- **TC006, TC020, TC021, TC041** are in words. They are traced to their criteria, and become tests
  once they have steps.
- **AC-6** (listing bookings by status) has no case at all; the trace will show it as a gap.

## 4. Review

```bash
qa-agent review export       # review/cases.xlsx: every case still to review
# the reviewer fills Decision, Reviewer, Date and Comment, and saves
qa-agent review apply
```

In the sheet, cases are in id order; each case's steps and expected results are readable and
locked, next to what check found; Decision is a drop-down. A case in words shows its expected
result in words, marked "needs steps". The reviewer here:

| Decision | Cases | Why |
|---|---|---|
| Approve | TC001 to TC004, TC010 to TC012, TC030, TC040 | TC030 also got criterion AC-1 and the tag `smoke`, which the Postman collection didn't have |
| Changes needed | TC005 | "The API returns 422 for a missing field, not 400" |
| Reject | TC042 | "env_check already calls /health-check before every run; not a test case" |
| Reject | TC022 | "Duplicate of TC020: the same case under another title in the manual sheet" |
| No decision | TC006, TC020, TC021, TC041 | In words: they can't be approved until they have steps |

```
applied  TC010: approved by qa-lead, 2026-10-21
...
applied  TC005: changes needed by qa-lead, 2026-10-21
...
applied  TC042: rejected by qa-lead, 2026-10-21
applied  TC022: rejected by qa-lead, 2026-10-21
12 decisions applied, 0 refused
```

Each approved case now carries `review: {status: approved, by, date, fingerprint}`. If anyone edits
its steps later, check says "changed after it was approved", and it won't become a test until it is
reviewed again.

## 5. Generate

```bash
qa-agent generate
```

```
wrote      tests/generated/conftest.py
wrote      tests/generated/test_bookings.py
...
wrote      src/test/java/generated/CancellationTest.java
not generated: TC005: changes needed
not generated: TC006: needs steps
...
not generated: TC042: rejected
pytest: 9 tests · restassured: 9 tests
```

Only approved, unchanged cases become tests: one test file per case file, one test per case, in
each framework (`frameworks: [pytest, restassured]`). The same case reads like this in each:

```python
@pytest.mark.functional
@pytest.mark.negative
@pytest.mark.writes
@pytest.mark.case("TC003")
@pytest.mark.priority("P1")
def test_tc003_a_second_cancel_is_refused(api, context):
    """A second cancel is refused. Criteria: AC-4."""
    unique = unique_id()
    # 1. POST /bookings
    response = api.post("/bookings", json={
        "passenger_name": f"Asha Rao {unique}",
        ...
    })
    Expect(response).status_is(201)
    context.remember("pnr", response.value("pnr"))
    ...
    # 3. POST /bookings/{{pnr}}/cancel
    response = api.post(f"/bookings/{context.get('pnr')}/cancel", json={"cancelled_at": "2026-01-20T11:00:00Z"})
    Expect(response).status_is(409).field_equals("error.code", "already_cancelled")
```

```java
    /** A second cancel is refused. Criteria: AC-4. */
    @Test(groups = {"functional", "negative", "writes"})
    @CaseId("TC003") @Priority("P1")
    public void tc003ASecondCancelIsRefused() {
        String unique = TestData.uniqueId();
        ApiResponse response;
        ...
        // 3. POST /bookings/{{pnr}}/cancel
        response = api().post("/bookings/" + context().get("pnr") + "/cancel", Map.of("cancelled_at", "2026-01-20T11:00:00Z"));
        Expect.that(response).statusIs(409).fieldEquals("error.code", "already_cancelled");
    }
```

`qa-agent generate --check` is the drift check CI runs: it writes nothing, and fails if a generated
test was edited by hand or a case was approved without generating.

`writes` is added because the case changes data, so a read-only environment skips it. The team's
tags (`negative`) become pytest markers (registered in `tests/generated/conftest.py`) and TestNG
groups: `pytest -m negative`, `./mvnw test -Dgroups=negative`.

## 6. Run

```bash
python -m demo_api &                       # the reference API
python -m env_check --env demo             # READY (exit 0)
python -m pytest --junitxml=reports/junit.xml      # 12 passed: TC002 runs once per data row, TC040 too
./mvnw test                                # the same tests in Java
```

## 7. Trace

```bash
qa-agent trace --results reports/junit.xml target/surefire-reports
```

```
qa-agent trace: bookings

Criteria        4 of 6   missing: AC-5 (not approved: TC006, TC020, TC021), AC-6 (no case)
Operations      5 of 8   missing: POST /auth/token, GET /bookings, GET /bookings/{pnr}/refund
Response codes  9 of 19   missing: POST /auth/token 200, POST /auth/token 422, GET /bookings 200, POST /bookings 422, PUT /bookings/{pnr} 404, DELETE /bookings/{pnr} 404, POST /bookings/{pnr}/cancel 422, GET /bookings/{pnr}/refund 200, GET /bookings/{pnr}/refund 404, 401 (bookings, any operation)
Cases to tests  9 of 9
Not tested      on purpose: GET /health-check: env_check calls it before every run; POST /test/reset: a test-only route; it resets the data; GET /health-check (notifications): env_check calls it before every run
Case types      9 approved: 5 positive · 4 negative · 0 auth · 1 edge
Results         pytest 12 passed · restassured 12 passed
```

`Case types` comes from what each case expects: a 4xx makes it negative, 401 or 403 auth, a tag
`edge` or `boundary` edge. No case here calls without a token, so auth is 0: the
same gap as `401 (bookings, any operation)` under Response codes. A criterion whose approved cases were all positive would be named on a `Happy path only` line.

It also writes the traceability matrix, `reports/trace.md` (for a pull request) and `reports/trace.xlsx`: every criterion,
its cases with their review status, each case's tests in both frameworks, and the latest result per
framework.

What it says about this example, honestly: the cases cover the booking and cancellation flows well,
and the gaps are plain. AC-5 has cases only in words, AC-6 has none, nothing calls the token or
refund-status endpoints, no case sends a request without a token (401), and several error codes (a
422 on create and cancel, a 404 on update, delete and refund status) are never expected. These are the gaps a team (or, later, the AI layer) writes cases for next.
`/test/reset` and the health checks are left out on purpose, with the reason, in `api/api.yaml`.

`qa-agent trace --min-coverage 80` also fails the run when criteria or operations coverage is below
80% (here both are below it: 67% and 62%). It is off unless a team sets it.

## 8. Promote

New cases start as `functional`. A case joins `regression` once it is stable: passed in three runs,
every data row, in every framework with results.

```bash
qa-agent promote --runs reports/run1.xml reports/run2.xml reports/run3.xml
```

```
From 3 runs, with results for: python
No results for restassured: promotion here rests on python only
ready for regression: TC001
...
ready for regression: TC040
Nothing changed. To move them: the same command with --apply.
```

It only lists; a person moves them with `--apply`, and each moved case gets a dated line in its
notes. The tool never moves a case back: a regression case that fails is listed as "look at this".
When a change makes a regression case wrong, a person moves it, on the record:

```bash
qa-agent suite TC010 functional --by qa-lead --reason "refund rule changing in the next release"
```

(If the case's steps change instead, its fingerprint no longer matches and it goes back to review by
itself; the reviewer can set Suite there.)

**Flaky tests.** A test that passes on one run and fails on the next, with no change to the code,
costs reruns and teaches the team to ignore red. `recorded-runs/` holds three nightly runs of this
example in which TC003 failed once:

```bash
qa-agent flaky --runs recorded-runs/run1.xml recorded-runs/run2.xml recorded-runs/run3.xml
```

```
qa-agent flaky: bookings, 3 runs, 12 tests compared

Flaky (1): passed in some runs, failed in others
  TC003   test_tc003_a_second_cancel_is_refused   passed 2 of 3   last failure, run 2: ExpectationFailed: expected status 409, got 200
Passed in every run: 11

Written: reports/flaky.md
```

TC003 cancels a booking twice and expects 409 the second time; one night the second cancel got 200.
That is worth a look before it's waved away: two cancels racing is a real bug in some services.
On these runs `promote` keeps TC003 out of regression (`not yet: TC003: failed in run 2 (pytest)`) and says
no more; `flaky` names it with the failure. It only reports (exit 0). Runs from different builds aren't flaky, they're a change: compare runs of
one build.

## 9. Do the tests catch bugs?

The reference API can switch on one seeded bug at a time (`python -m demo_api --bug
refund-boundary`). `seeded-bugs.yaml` says how to start it with each; `qa-agent bug-detection` runs the tests once
with no bug (they must pass), then once per bug:

```bash
qa-agent bug-detection --framework pytest          # with the reference API stopped: it starts it once per bug
```

```
qa-agent bug-detection: pytest · 5 of 7 seeded bugs caught (71%)

  caught  refund-boundary          by TC002
  caught  wrong-refund-amount      by TC002, TC040
  caught  second-cancel-allowed    by TC003
  caught  deleted-still-readable   by TC011
  caught  amount-changeable        by TC012
  missed  token-not-checked        a call with no token is let through: no test noticed
  missed  status-filter-ignored    listing by status returns every booking: no test noticed
```

The two missed bugs are the trace's gaps seen from the other side: no case calls without a token
(the untested 401), and no case lists bookings (`GET /bookings`, AC-6). Passing tests alone would
not have said so.

## 10. The API changed: which cases to run?

The next release adds a 410 to cancel: a booking whose flight has left can't be cancelled. The team
imports the new curl ([`api/source/next-release/`](api/source/next-release/)) and asks what that
change affects since the last release (`run_all.sh` does this in its scratch copy, tagged `v4.2`):

```bash
qa-agent import api api/source/next-release/cancel_after_departure.curl
qa-agent impact-analysis --since v4.2
```

```
changed   POST /bookings/{pnr}/cancel   responses: +410
          10 operations unchanged

Affected cases (4), highest priority first:
  TC002   P0  functional      The refund at the 24-hour boundary
  TC040   P0  functional      The refund depends on when the booking is cancelled
  TC003   P1  functional      A second cancel is refused
  TC004   P2  functional      An unknown PNR can't be cancelled

Run them:
  pytest -k "test_tc002_ or test_tc040_ or test_tc003_ or test_tc004_"
  ./mvnw test -Dtest="CancellationTest#tc002TheRefundAtThe24HourBoundary+...,CancellationScenariosTest#..."
```

The four cases to rerun, P0 first, out of every case in the project; and the new code, 410, has no
case yet: the trace shows it as a gap, and `qa-agent draft cases` drafts one.
