# api-qa-agent

[![CI](https://github.com/rahulsharma-qe/api-qa-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/rahulsharma-qe/api-qa-agent/actions/workflows/ci.yml)

**AI drafts, humans approve.** api-qa-agent turns what a team already has about its API (an
OpenAPI description or a curl with a sample response, the acceptance criteria of a change, and the
test cases it already wrote) into runnable API tests in the team's own framework: Python with
pytest, or Java with REST Assured and TestNG. The AI drafts cases and data; a reviewer approves every
one; templates write the code. Regression runs need no AI and no API key.

It is the "AI for quality" side of my work. Its sibling,
[`ai-quality-lab`](https://github.com/rahulsharma-qe/ai-quality-lab), is the "quality of AI" side:
testing AI agents themselves.

## Where it stands

| | Status |
|---|---|
| Reference API to test against ([`mock_service/`](mock_service/)) | **Built**: bookings, tokens, cancel and refund rules, health checks; its OpenAPI description lists every status code and is checked in CI |
| Environment check ([`env_check/`](env_check/)) | **Built**: a dependency that is down stops the run as an environment problem, never a test failure |
| Python framework ([`frameworks/python_api/`](frameworks/python_api/)) | **Built**: environments, OAuth, API chaining, data-driven tests, readable failures; Allure report, smoke and priority tags, evidence, one retry shown separately |
| REST Assured framework with TestNG ([`frameworks/restassured_api/`](frameworks/restassured_api/)) | **Built**: the same features in Java, with TestNG groups and suites, Excel-driven data, Allure, evidence, retry |
| `qa-agent`: cases from the team's API and existing cases ([`qa_agent/`](qa_agent/), [example](examples/bookings-team/)) | **Built**: API import (OpenAPI, curl); existing cases from Excel, CSV, Postman and Gherkin; `check` with the fix for every finding; review in an Excel sheet, with who and when |
| `qa-agent`: tests, trace, new projects | **Built**: approved cases become pytest and REST Assured tests; the trace from criteria to results, with coverage; `init` makes a project that runs on day one |
| `qa-agent`: every day | **Built**: the drift check (`generate --check`), a coverage floor (`trace --min-coverage`), `promote` stable cases to regression, `suite` to move one back, on the record |
| Bug-detection rate | **Built**: the reference API can switch on one of seven planted bugs; `qa-agent bugs` runs the tests once per bug and says which bugs they catch, and by which cases |
| Many teams ([`teams/`](teams/)) | **Built**: a reusable CI workflow a team calls in one job, with its stack and environment; two teams (pytest, REST Assured) use it, each building only its own stack |
| External APIs ([`examples/external-apis/`](examples/external-apis/)) | **Built**: Swagger Petstore from its own OpenAPI and a team's Excel sheet, in both stacks; its Docker image on every change, the public server by hand. It found a real gap: Petstore accepts a pet with no name |
| A Docker image for qa-agent ([`Dockerfile`](Dockerfile)) | **Built**: qa-agent with no Python install, published with each release ([`ghcr.io/rahulsharma-qe/qa-agent`](https://github.com/rahulsharma-qe/api-qa-agent/pkgs/container/qa-agent)) or built from this repository; the tool only, so tests run where they always run |
| Cucumber on REST Assured | Later |
| User-interface tests, in their own repository (`playwright-qa-agent`) | Later |
| Jira and wiki; results back to TestRail, Zephyr or Xray | Later |
| The AI layer: drafting, review, the model in your own cloud | Later |

Everything that needs no AI comes first, so a team can use the utility end to end with its
existing test cases before any AI is switched on.

## How it works

```mermaid
flowchart LR
  IN["Your inputs<br/>OpenAPI or curl · acceptance criteria<br/>existing test cases"]
  DRAFT["AI drafts<br/>reviews existing cases,<br/>fills the gaps, drafts data"]
  REVIEW["A person approves<br/>every case and data set"]
  GEN["Code from templates<br/>pytest · REST Assured"]
  RUN["Run<br/>env_check first,<br/>then the tests"]
  OUT["Results<br/>by case id, traceable<br/>to the criteria"]
  IN --> DRAFT --> REVIEW --> GEN --> RUN --> OUT
  classDef built fill:#1e293b,stroke:#34d399,color:#f1f5f9,stroke-width:2px
  classDef later fill:#1e293b,stroke:#94a3b8,color:#cbd5e1,stroke-dasharray: 5 5
  class IN,REVIEW,GEN,RUN,OUT built
  class DRAFT later
  linkStyle default stroke:#94a3b8,stroke-width:2px
```

Green border: built. Dashed: the AI layer, coming later. Until then a person writes or imports the
cases, and everything after them works the same.

## Try it (no API key)

```bash
pip install -e . -e frameworks/python_api          # the reference API, env_check, qa-agent, the Python framework
python -m mock_service &                           # bookings on :8000, notifications on :8001
cd frameworks/python_api
python -m env_check --env mock                     # is the environment ready?
pytest                                             # every example, against the reference API
```

The same examples in Java (Java 17; Maven comes with the wrapper):

```bash
cd frameworks/restassured_api
./mvnw test                                        # with the reference API running, as above
```

When a test fails, the report shows the expectation that broke and every request and response of
the test, in order, with tokens masked. See each framework's README:
[Python](frameworks/python_api/README.md) and [REST Assured](frameworks/restassured_api/README.md).

And `qa-agent`, from a team's inputs to tests in both stacks and the trace:

```bash
cd examples/bookings-team
./run_all.sh --python-only                         # or ./run_all.sh with the Java framework installed
```

The [example's README](examples/bookings-team/README.md) walks through every step: the API, the
team's existing cases in four formats, what `check` finds, the review sheet, the generated tests in
both stacks, and the trace. A new team starts with `qa-agent init my-team --stack python` (or
`--stack restassured`): a project that runs on day one.

### Run with Docker (no Python install)

```bash
cd your-team-project
docker run --rm -v "$PWD:/project" ghcr.io/rahulsharma-qe/qa-agent:0.3.0 check
```

A version number keeps every run the same; `:latest` follows each release. Or build the image
yourself: `docker build -t qa-agent https://github.com/rahulsharma-qe/api-qa-agent.git`, then use
`qa-agent` in place of the image name.

In the image: `init`, `import`, `check`, `review`, `generate`, `trace`, `promote`, `suite`. Your
tests run where they always run (pytest or Maven), since they call your API.
On Linux, add `--user "$(id -u):$(id -g)"` so the files qa-agent writes are yours.
In Windows PowerShell, write `${PWD}` instead of `$PWD`.

## What's inside

| Folder | What it is |
|---|---|
| [`mock_service/`](mock_service/) | The reference API: bookings (create, read, update, delete, list), cancel with a 24-hour refund rule, refund status, tokens, health checks, and a stand-in dependency that can be switched down |
| [`env_check/`](env_check/) | Before a run: call every service a team depends on; exit 3 when a critical one is down. One tool for every framework |
| [`frameworks/python_api/`](frameworks/python_api/) | The Python framework (pytest, httpx), installable on its own, with an example for every feature |
| [`frameworks/restassured_api/`](frameworks/restassured_api/) | The Java framework (REST Assured, TestNG), a Maven library on its own, with an example for every feature |
| [`qa_agent/`](qa_agent/) | `qa-agent`, the command line: `init`, `import`, `check`, `review`, `generate`, `trace`, `promote`, `suite`, `bugs` |
| [`Dockerfile`](Dockerfile) | qa-agent in a container, for a team with no Python install |
| [`examples/bookings-team/`](examples/bookings-team/) | A team's project for the reference API: every `qa-agent` feature, with its output |
| [`teams/`](teams/) | Two small teams, each shaped like its own repository: `bookings-python` (pytest) and `refunds-java` (REST Assured) |
| [`examples/external-apis/`](examples/external-apis/) | qa-agent and both frameworks on APIs this repository didn't write; first, Swagger Petstore |
| [`.github/workflows/qa-agent-team.yml`](.github/workflows/qa-agent-team.yml) | The reusable workflow a team's CI calls: environment ready, generated tests up to date, tests, trace |
| [`docs/`](docs/) | The design: [high-level](docs/architecture.md) and [low-level](docs/lld.md) |
| `core/` | The first version's language-model steps (case and data drafting, a review step); reworked into the AI layer later |

## Design choices

- **AI drafts, humans approve.** Nothing the AI writes becomes a test until a person approves it.
- **Tests are data; templates write the code.** The code always runs, the same case runs in every
  framework, and a person who doesn't write code can review a case.
- **Existing cases first.** The AI reviews what the team already has and drafts only what is missing.
- **Regression needs no AI.** Generated code is committed; it runs on every build without a model.
- **Safe for regulated organisations.** Only the API's structure is sent to a model, after
  redaction; the model can run in the organisation's own cloud (AWS Bedrock, Google Vertex, Azure);
  every call is logged.
- **An environment problem is not a bug.** env_check stops a run with its own exit code.
- **Many teams.** Frameworks are versioned libraries; each team works in its own repository and
  builds only its own stack.

## The first version

This repository started as a smaller pipeline: a language model turned one requirement into test
cases and data, a second model reviewed them, and the package was rendered into five test stacks,
one of which ran. Its design is kept in [`docs/history/first-version.md`](docs/history/first-version.md),
and its code in the git history.

Released under the [MIT License](LICENSE).
