# bookings-team: a team's project, for the reference API

This folder has exactly the shape of a team's own repository. It shows every `qa-agent` feature
against the reference API (`python -m mock_service`). It grows as `qa-agent` does: review sheet,
generated tests and the trace come next.

| File | What it is |
|---|---|
| `qa-agent.yaml` | The team, its main service, its stacks |
| `api/source/` | What the team brought: the OpenAPI description, and two curl commands with a sample response |
| `api/api.yaml` | The API model, imported from those sources |
| `criteria.yaml` | Six acceptance criteria of the bookings and cancellation feature |
| `cases/bookings.yaml`, `cases/cancellation.yaml` | The cases, one file per feature |
| `data/cancellation_boundaries.csv` | One row per run of the data-driven case TC002 |
| `config/` | Environments and dependencies, read by env_check and the frameworks |

## Try it

From the repository's root, after `pip install -e .`:

```bash
cd examples/bookings-team
qa-agent import api api/source/openapi.json api/source/cancel_booking.curl
qa-agent import api api/source/notifications_health.curl --service notifications
qa-agent check
```

`import api` reads the OpenAPI description and the curl commands into one model. The curl's
`Authorization` header is not kept, and `/bookings/AB12CD/cancel` is read as `/bookings/{id}/cancel`,
the operation the OpenAPI description already has.

`check` finds what a reviewer should look at, and exits 0 because nothing is an error:

```
qa-agent check: bookings · 6 cases in 2 files

cases/bookings.yaml
  warning  TC005 step 1: status 400 is not documented for POST /bookings (documented: 201, 401, 422). Fix: check the expected status, or document it in the API
  warning  TC005 step 1: the body leaves out required email. Fine for a negative test; otherwise add them

cases/cancellation.yaml
  info     TC006: needs steps (it has only steps_text). It is kept and traced, and can't be generated until it has steps

0 errors · 2 warnings · 1 note
```

- **TC005** expects 400 where the API returns 422: a mistake a person makes, caught before any
  test runs. Leaving out `email` is the point of this negative test, so that warning stays.
- **TC006** is still in words, the way a manual test sheet holds it. It is traced to AC-5, and
  becomes a test once it has steps.
- **AC-6** (listing bookings by status) has no case at all; the trace will show it as a gap.
