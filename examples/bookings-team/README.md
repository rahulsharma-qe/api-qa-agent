# bookings-team: a team's project, for the reference API

This folder has exactly the shape of a team's own repository. It shows every `qa-agent` feature
against the reference API (`python -m mock_service`), with what each command printed. Generated
tests and the trace come next.

| File | What it is |
|---|---|
| `qa-agent.yaml` | The team, its main service, its stacks |
| `api/source/` | What the team brought: the OpenAPI description, and two curl commands with a sample response |
| `api/api.yaml` | The API model, imported from those sources |
| `criteria.yaml` | Six acceptance criteria of the bookings and cancellation feature |
| `existing/` | The team's cases as they were, in four formats: Excel in the API layout, Excel in the manual layout, a Postman collection, a Gherkin feature |
| `cases/bookings.yaml`, `cases/cancellation.yaml` | Cases written directly in the case format |
| `cases/bookings-api.yaml`, `cases/refunds.yaml`, `cases/bookings-smoke.yaml`, `cases/cancellation-scenarios.yaml` | The cases imported from `existing/`, one file per feature |
| `data/` | Data files: one row per run of a data-driven case (one came from the Gherkin outline's Examples) |
| `review/cases.xlsx` | The review sheet, filled in by the reviewer |
| `config/` | Environments and dependencies, read by env_check and the frameworks |

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
cases/refunds.yaml: TC020, TC021
cases/bookings-smoke.yaml: TC030, BOOKINGS-SMOKE-01
cases/cancellation-scenarios.yaml: TC040, TC041
data file written: data/cancellation-scenarios-tc040.csv
note: existing/bookings.postman_collection.json, TC030 step 2: pm.expect(body.passenger_name).to.match(/Meera/);
note: existing/cancel.feature, TC041: not in the fixed phrasing; kept in words (needs steps)
9 cases imported as drafts, 0 skipped
```

(Run it again and every case is skipped: their ids are already in the project.)

- **Excel, API layout:** one row per step, so TC010 to TC012 come in ready to run.
- **Excel, manual layout:** TC020 and TC021 have steps in words, so they come in as "needs steps".
- **Postman:** the folder "TC030 Create and read a booking" is one case of two requests; its test
  scripts became the status, fields, `contains`, a response-time limit and the captured PNR.
  `{{$randomInt}}` and `{{$guid}}` became `{{unique}}`, the token header was dropped, and the one
  line qa-agent can't read (`to.match(/Meera/)`) is in the case's notes. The health request had no
  id, so it got one: BOOKINGS-SMOKE-01.
- **Gherkin:** TC040 is in the fixed phrasing, so it became steps, and its Examples became a data
  file. TC041 is in words.

## 3. Check

```bash
qa-agent check
```

```
qa-agent check: bookings · 15 cases in 6 files

cases/bookings.yaml
  warning  TC005 step 1: status 400 is not documented for POST /bookings (documented: 201, 401, 422). Fix: check the expected status, or document it in the API
  warning  TC005 step 1: the body leaves out required email. Fine for a negative test; otherwise add them

cases/cancellation-scenarios.yaml
  info     TC041: needs steps (it has only steps_text). It is kept and traced, and can't be generated until it has steps

cases/cancellation.yaml
  info     TC006: needs steps (it has only steps_text). It is kept and traced, and can't be generated until it has steps

cases/refunds.yaml
  info     TC020: needs steps (it has only steps_text). It is kept and traced, and can't be generated until it has steps
  info     TC021: needs steps (it has only steps_text). It is kept and traced, and can't be generated until it has steps

0 errors · 2 warnings · 4 notes
```

- **TC005** expects 400 where the API returns 422: a mistake a person makes, caught before any
  test runs. Leaving out `email` is the point of this negative test, so that warning stays.
- **TC006, TC020, TC021, TC041** are in words. They are traced to their criteria, and become tests
  once they have steps.
- **AC-6** (listing bookings by status) has no case at all; the trace will show it as a gap.

## 4. Review

```bash
qa-agent review export       # review/cases.xlsx: every case still to review
# the reviewer fills Decision, Reviewer, Date and Comment, and saves
qa-agent review import
```

In the sheet, each case's steps and expected results are readable and locked, next to what check
found; Decision is a drop-down. The reviewer here:

| Decision | Cases | Why |
|---|---|---|
| Approve | TC001 to TC004, TC010 to TC012, TC030, TC040 | TC030 also got criterion AC-1, which the Postman collection didn't have |
| Changes needed | TC005 | "The API returns 422 for a missing field, not 400" |
| Reject | BOOKINGS-SMOKE-01 | "env_check already calls /health-check before every run; not a test case" |
| No decision | TC006, TC020, TC021, TC041 | In words: they can't be approved until they have steps |

```
applied  TC010: approved by qa-lead, 2026-10-21
...
applied  TC005: changes needed by qa-lead, 2026-10-21
applied  BOOKINGS-SMOKE-01: rejected by qa-lead, 2026-10-21
11 decisions applied, 0 refused
```

Each approved case now carries `review: {status: approved, by, date, fingerprint}`. If anyone edits
its steps later, check says "changed after it was approved", and it won't become a test until it is
reviewed again.
