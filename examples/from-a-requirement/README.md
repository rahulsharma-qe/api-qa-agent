# from-a-requirement: from a ticket in plain words to tests that run

A team has two things: its API's description and a requirement written in a ticket. No acceptance
criteria, no test cases. This example goes from there to pytest tests that pass against the
reference API (`python -m demo_api`), and a person approves every step the AI drafts.

```bash
./run_all.sh          # every step, from the inputs, then the tests and the trace (what CI runs)
```

No API key is needed: `qa-agent.yaml` says `ai: {provider: recorded}`, so the model's replies are
read from [`ai/recorded/`](ai/recorded/). **They are hand-written**, in the shape a model replies,
with the mistakes models make, so each guardrail can be seen at work. They show the flow, not how
good a model is: replies from a real model replace them in a later release, and that run is measured.

| File | What it is |
|---|---|
| `requirements/BOOK-101.md` | The requirement, as the ticket says it. `BOOK-101-v2.md` is the same ticket after a change |
| `api/api.yaml` | The three endpoints BOOK-101 uses: create a booking, cancel it, read its refund status |
| `qa-agent.yaml` | The team, its service, pytest, and the recorded replies |
| `ai/recorded/` | The replies, one file per request, and a README of the mistake in each |
| `review/1-criteria.xlsx`, `2-cases.xlsx`, `3-redo.xlsx` | The three review sheets, as the reviewer filled them |
| `acceptance-criteria-drafts.yaml` | The criteria and questions, with each one's review (written by qa-agent) |
| `cases/bookings-drafts.yaml` | The drafted cases, with each one's review (written by qa-agent) |
| `tests/generated/` | The tests `qa-agent generate` wrote from the approved cases |
| `config/`, `pytest.ini` | Environments and dependencies; how pytest runs here |

## 1. Criteria and questions from the requirement

The requirement is pasted in, named by its ticket, so every criterion points back to `BOOK-101`:

```bash
qa-agent draft criteria - --ref BOOK-101 < requirements/BOOK-101.md
```

```
drafted   AC-1: A booking cancelled within 24 hours of being made gets a full refund.
...
question  Q-1 (ambiguity): Is a booking cancelled at exactly 24 hours refunded in full, or not at all?
question  Q-2 (omission): What should the passenger see when the PNR doesn't exist?
question  Q-3 (dependency): What does the passenger see if the payments service is down when they cancel?
refused   The passenger gets an email when the refund is paid.: 'an email is sent when the refund is paid' is not in the requirement
```

Every criterion and question must quote the requirement's own words. The reply had a criterion
about an email the ticket never mentions: refused, so nothing is added that the requirement doesn't say.

## 2. A person approves the criteria and answers the questions

In `review/1-criteria.xlsx` the QA lead approved four criteria, rewording two with what the answers
settled (exactly 24 hours is refunded; an unknown PNR can't be cancelled), and rejected one:
"Refunds are paid by the payments service" can't be tested through this API. The product owner
answered the three questions. `qa-agent review apply` records who decided, and when.

## 3. A draft case for each gap

```
8 gaps to draft; 0 drafted before.
  AC-1 ... AC-4                  no case: <the criterion>
  POST /bookings                 no case expects 201, 422
  POST /bookings/{pnr}/cancel    no case expects 200, 404, 409, 422
  GET /bookings/{pnr}/refund     no case expects 200, 404
  401 (bookings)                 no call without a valid token
```

`--plan` lists them, with the most calls a run can make and their cost; nothing is sent. Then:

```
drafted   AC-1: TC001, TC002 -> cases/bookings-drafts.yaml
...
refused   POST /bookings/{pnr}/cancel: "A cancel with a date that isn't a date is refused" calls POST /bookings/{{pnr}}/cancellations, not in api/api.yaml
covered   GET /bookings/{pnr}/refund: by a draft made earlier in this run, no call
```

What the guardrails did:

- The reply for AC-1 numbered its case `TC999` and marked it approved: the id and the review come
  from code, so it is `TC001`, a draft.
- One reply called an operation the API doesn't have: the whole reply was refused, and nothing written.
- The refund operation's codes were covered by the AC-4 drafts in the same run: no call for it.
- The model didn't know the error code for a second cancel and wrote `TBD`: `check` makes that an
  error, so the case can't be approved until a person gives the value.

## 4. A person decides on each draft

In `review/2-cases.xlsx` the QA lead approved eight, rejected TC004 ("same rule as TC003"), and
sent TC005 back as *Changes needed*: "A second cancel answers 409 with error code already_cancelled:
check that code, not TBD". TC009 (a booking without an email) and TC010 (a call without a token)
are approved with a warning: no criterion says them, and the trace shows them as such.

## 5. The case sent back is redone

```bash
qa-agent draft cases --redo TC005
```

```
redone    TC005: TC011 -> cases/bookings-drafts.yaml (TC005 is now rejected)
```

The model gets the old draft and the reviewer's comment. TC011 checks `already_cancelled`, its
source says it replaces TC005, and TC005 stays in the file as history. Asked again:
`not redone TC005: already redone as TC011`, with no call.

## 6. A person approves the redone case

`review/3-redo.xlsx`: TC011 approved.

## 7. The requirement changed

The ticket now says 48 hours. Before anything is sent:

```bash
qa-agent draft criteria - --ref BOOK-101 --plan < requirements/BOOK-101-v2.md
```

```
BOOK-101: 5 criteria drafted from it before (AC-1, AC-2, AC-3, AC-4, AC-5).
  changed   AC-1: 'Cancel within 24 hours of booking and get all your money back' is no longer in it
  changed   AC-2: 'After 24 hours, the booking can still be cancelled, but no refund is given' is no longer in it
```

Run without `--plan`, AC-1 and AC-2 go back to review, `check` warns on every case linked to them,
and the model drafts them as the ticket reads now. The example stops at the plan.

## 8 and 9. Tests, and the trace

`qa-agent generate` writes the approved cases as pytest tests; they run against the reference API:

```
9 passed
Criteria        4 of 4
Operations      3 of 3
Response codes  8 of 9   missing: POST /bookings/{pnr}/cancel 422
```

The one code missing is the gap whose reply was refused: the trace says so, rather than hiding it.
A new reply for it, or a case a person writes, closes it.
