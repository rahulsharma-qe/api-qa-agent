# Using qa-agent

How a team uses `qa-agent`, one command at a time. To try it first, see
[Getting started](getting-started.md); for why it works this way, the [design](lld.md).

## Commands

| Command | What it does |
|---|---|
| `qa-agent init my-team --framework pytest` | A new team project that runs on day one (`--framework restassured` for Java) |
| `qa-agent import api openapi.json cancel.curl` | The API description (OpenAPI, or curl with a sample response) into `api/api.yaml` |
| `qa-agent import cases existing/cases.xlsx` | The team's cases (Excel, CSV, Postman, Gherkin) into `cases/<feature>.yaml`, as drafts |
| `qa-agent check` | Every case checked by rules, each finding with its fix; exit 1 on errors |
| `qa-agent review export` · `review apply` | The review sheet (`review/cases.xlsx`): a person approves, sends back or rejects each case, with who and when |
| `qa-agent generate [--check]` | Approved cases become pytest and REST Assured tests; `--check` fails when they are out of date |
| `qa-agent trace --results reports/junit.xml [--check] [--min-coverage 80]` | The traceability matrix: criteria to cases to tests to results, with coverage |
| `qa-agent promote --runs r1 r2 r3 [--apply]` | Functional cases stable in three runs join regression |
| `qa-agent flaky --runs r1 r2 r3` | Tests that passed in some runs and failed in others, with the case and the last failure |
| `qa-agent suite TC010 functional --by --reason` | A person moves a case between suites, on the record |
| `qa-agent impact-analysis --since v4.2` | What changed in the API since a release, and the cases to rerun, P0 first |
| `qa-agent bug-detection --framework pytest` | The tests run once per seeded bug: which bugs they catch, and by which cases |
| `qa-agent draft criteria requirements/x.md` | Acceptance criteria and questions drafted from a requirement in plain words |
| `qa-agent draft cases [--plan] [--max 10]` | A draft case for each coverage gap |

Every command takes `--project <folder>` (default: the current folder) and `--help`.

## Day to day

1. **Bring what you have.** `import api` for the API, `import cases` for the cases you already have.
   A pack the team signed off already can come in approved (see [Regression](#regression)).
2. **Check.** `check` finds what would make a test wrong: a call to an operation the API doesn't
   have, a value still to confirm (`TBD`), a case that checks nothing, a criterion that doesn't exist,
   a case that repeats another's steps under a different id.
3. **Review.** `review export` writes the sheet; a person fills Decision, Reviewer and Comment;
   `review apply` records it. A case edited after approval goes back to review by itself: its
   steps, or a row of its data file.
4. **Generate and run.** `generate` writes the tests; they run in your framework as always.
   In CI, `generate --check` stops a build whose tests are older than its cases.
5. **Trace.** `trace` shows what is covered and what isn't; `--min-coverage` sets a floor. It
   also counts the cases by type (positive, negative, auth, edge) and names a criterion tested on
   the happy path only.
6. **When the API changes.** Import it again, then `impact-analysis --since <last release>`
   lists the cases to rerun.

## The AI layer

The AI drafts; a person approves; code checks everything in between. Nothing a model writes becomes
a test without a reviewer.

| Command | What it does |
|---|---|
| `qa-agent draft criteria requirements/x.md` | Criteria and questions (ambiguity, omission, contradiction, dependency); each must quote the requirement's own words |
| `qa-agent draft criteria - --ref PROJ-123` | The same, the requirement pasted or piped in from a ticket; the criteria point back to it |
| `qa-agent draft criteria - --ref PROJ-123 --plan` | Run again when the ticket changes: the criteria whose words are gone go back to review |
| `qa-agent draft cases --plan` | The gaps, the calls and an estimate; nothing sent |
| `qa-agent draft cases [--max 10]` | A draft for each gap: a criterion with no case, response codes no case expects, a call without a token |
| `qa-agent draft cases --redo TC045` | A new draft for one a reviewer rejected or sent back, using the comment |

Settings, in `qa-agent.yaml`:

```yaml
ai:
  provider: anthropic          # or openai; the key comes only from the environment
  model: <model name>
  # provider: recorded         # replies read from files instead: no key, the same every time
  # recorded: ai/recorded
```

A model on your own server, so nothing leaves your network: any OpenAI-compatible server (Ollama,
vLLM, LM Studio) with `provider: openai` and its address. The key is then optional.

```yaml
ai:
  provider: openai
  model: llama3.1
  base_url: http://localhost:11434/v1     # Ollama on this machine: ollama pull llama3.1, then ollama serve
```

What is sent is redacted (tokens, keys, passwords, emails) and every call is logged in
`reports/ai-audit-log.jsonl`. Drafts go to their own files (`cases/<area>-drafts.yaml`,
`acceptance-criteria-drafts.yaml`); the review sheet gains Criteria and Questions tabs.
The [example](../examples/from-a-requirement/README.md) shows every step and every guardrail.

### What the AI did, and who approved it

```bash
qa-agent ai-report                  # reports/ai-report/index.html, ai-report.md, ai-report.json
qa-agent ai-report --since 20-10-2026   # only this sprint: the calls since that day, and their drafts
```

One report for a reviewer, a QA manager or an auditor, read from the audit log and the drafts:

| Part | What it shows |
|---|---|
| Look at first | A case approved and then changed, an approval with no reviewer named, a draft whose call isn't in the log, a missing log, failed calls, drafts and questions still waiting |
| AI drafts and decisions | Every drafted criterion and case: approved, changes needed, rejected or waiting, who decided, when, and why. Each opens to its chain: requirement, criterion, call, decision |
| Questions | What the model asked about the requirement, and who answered |
| Where the approved cases came from | Drafted by AI, imported, or written by hand |
| AI calls | Each call's purpose, model, tokens, time and what was redacted; cost when `qa-agent.yaml` sets prices |

No prompt and no reply goes into the report: they stay in the audit log, so the report can be shared.
It reads only, and says "recorded replies" when no model was called. It is evidence of how AI was used
and reviewed, not a compliance decision, and it can't show that the log wasn't edited.

## Suites

| Suite | What it is | How a case gets there | Run it (pytest · REST Assured) |
|---|---|---|---|
| functional | New and changed behaviour; every case starts here | `suite: functional`, the default | `pytest -m functional` · `./mvnw test -Dgroups=functional` |
| regression | Stable cases that run on every build | `qa-agent promote` (stable in three runs), `qa-agent suite`, or a signed-off pack imported with `--suite regression` | `pytest -m regression` · `-Dgroups=regression` |
| sanity | A quick check of one area, after a fix | `tags: [sanity]` | `pytest -m sanity` · `-Dgroups=sanity` |
| by priority | P0 to P3, from each case's `priority` | `priority: P0` | `pytest -m p0` · `-Dgroups=p0` |

A case is in one suite and can have many tags: a regression case can also be sanity.

## Regression

When a feature ships, its important cases join regression:

```bash
qa-agent promote --runs r1.xml r2.xml r3.xml --feature cancellation --priority P0 P1 --reason "released in 4.3"
```

It lists what is ready and what it left out; `--apply` moves them, with the reason in each case's
notes. Set `regression: {priorities: [P0, P1]}` in `qa-agent.yaml` once, and `--priority` can be
left out. A regression case that fails is flagged, never moved back by the tool: a person does
that with `qa-agent suite`.

A pack the team signed off already comes in approved, without a second review:

```bash
qa-agent import cases regression-pack.xlsx --approved-by qa-lead --reason "signed-off pack" --suite regression
```

Each case is approved by that name, with the reason; a case `check` finds an error in stays a draft.

## Docker

```bash
cd your-team-project
docker run --rm -v "$PWD:/project" ghcr.io/rahulsharma-qe/qa-agent:0.4.0 check
```

A version number keeps every run the same; `:latest` follows each release. Or build the image
yourself: `docker build -t qa-agent https://github.com/rahulsharma-qe/api-qa-agent.git`, then use
`qa-agent` in place of the image name.

In the image: `init`, `import`, `check`, `review`, `generate`, `trace`, `promote`, `suite`. From the
next release, or in an image you build from this repository, `draft` too (the model's key from your
environment: `docker run -e ANTHROPIC_API_KEY ...`). Your tests run where they always run (pytest or
Maven), since they call your API.

- On Linux, add `--user "$(id -u):$(id -g)"` so the files qa-agent writes are yours.
- In Windows PowerShell, write `${PWD}` instead of `$PWD`.

## In CI

A team's CI calls one reusable workflow,
[`.github/workflows/qa-agent-team.yml`](../.github/workflows/qa-agent-team.yml): environment ready,
generated tests up to date, tests, trace. [`teams/`](../teams/) has two teams using it, one per
framework.
