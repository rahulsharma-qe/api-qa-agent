# Getting started

Everything here runs on your machine with Python 3.11 or newer, and needs no API key. Java 17 is
needed only for the REST Assured framework (Maven comes with the wrapper).

```bash
git clone https://github.com/rahulsharma-qe/api-qa-agent.git
cd api-qa-agent
pip install -e . -e frameworks/python_api          # the reference API, env_check, qa-agent, the Python framework
```

## 1. The frameworks, against the reference API

```bash
python -m demo_api &                               # bookings on :8000, notifications on :8001
cd frameworks/python_api
python -m env_check --env demo                     # is the environment ready?
pytest                                             # every example, against the reference API
```

The same examples in Java:

```bash
cd frameworks/restassured_api
./mvnw test                                        # with the reference API running, as above
```

When a test fails, the report shows the expectation that broke and every request and response of
the test, in order, with tokens masked. Each framework's README has the details:
[Python](../frameworks/python_api/README.md) and [REST Assured](../frameworks/restassured_api/README.md).

## 2. A team's project: from its API and existing cases to tests

```bash
cd examples/bookings-team
./run_all.sh --pytest-only                         # or ./run_all.sh with the Java framework installed:
                                                   # cd frameworks/restassured_api && ./mvnw -q install -DskipTests
```

The [example's README](../examples/bookings-team/README.md) walks through every step: the API, the
team's existing cases in four formats, what `check` finds, the review sheet, the generated tests in
both frameworks, the trace, promotion to regression, the bug-detection rate and an impact analysis.

## 3. The AI layer: from a ticket in plain words to tests

```bash
cd examples/from-a-requirement
./run_all.sh                                       # a ticket -> criteria -> cases -> three reviews and a redo -> tests
```

The [example's README](../examples/from-a-requirement/README.md) shows each step's output and what
each guardrail did. Its model replies are recorded and hand-written, and labelled so: they show the
flow, not how good a model is.

## 4. Your own project

```bash
qa-agent init my-team --framework pytest           # or --framework restassured
cd my-team
qa-agent check
```

A project that runs on day one: an API description, criteria, one case, its generated test, CI.
From there, the [guide](guide.md) has every command.

## 5. Without Python: the Docker image

```bash
cd your-team-project
docker run --rm -v "$PWD:/project" ghcr.io/rahulsharma-qe/qa-agent:0.4.0 check
```

See [Docker](guide.md#docker) in the guide.
