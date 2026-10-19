# AeroAssist QA Agent

> **Being rebuilt.** This repository is becoming **api-qa-agent**: an AI-assisted pipeline, with
> people at every gate, that turns a team's API description, acceptance criteria and existing test
> cases into runnable API tests in the team's own framework. The new design:
> [high-level](docs/architecture.md) · [low-level](docs/lld.md). Below is the first version, which
> still runs until the new phases replace it.

An AI-assisted **QA framework** that turns a plain-English requirement into a validated test
package, then renders it into **five different test stacks** from one framework-agnostic core.

Built around a mock airline-support service (**AeroAssist**), it demonstrates the full loop most
demos skip: **AI generates the tests, the framework runs them against a real API, and it
produces actual pass/fail** — not just "the AI wrote a test."

```
requirement  ->  [ generate -> AI review -> human/auto approve -> revise -> data -> validate ]
             ->  framework-agnostic package  ->  { Python | REST Assured | Apache+TestNG | BDD | Playwright }
```

## Why this exists

Real quality orgs run many stacks and can't trust AI-generated artifacts blindly. This project
shows a way to get AI's speed **with** engineering discipline:

- **One core, many adapters** — build the intelligence once; each team's stack is a thin adapter.
- **Gates everywhere** — a review gate on cases, a hybrid validator on data, an oracle on every test.
- **Human-in-the-loop by design** — the AI reviewer is itself an LLM and can over-correct, so a
  human holds the veto; regression runs automatically, new features pause for approval.
- **Honest scope** — one adapter is executed live; the rest are idiomatic reference implementations.

## Quickstart (no API key needed)

The repo ships with a committed sample package, so it runs green out of the box.

```bash
pip install -r requirements.txt

# run the committed samples through the engine against the mock service
python -m examples.run_demo

# or run the deterministic test suite (this is what CI runs)
python -m pytest -q
```

Expected: **12/12 API tests pass** (6 records x 2 endpoints), pytest green.

## Live mode (optional — regenerates cases/data via an LLM)

The LLM layer is **provider-agnostic** (`core/llm.py`): pick a provider with `LLM_PROVIDER`
(default `anthropic`, `openai` supported) and set the matching key. The framework is not
locked to one vendor — swapping providers is a small change in one file.

```bash
cp .env.example .env          # set LLM_PROVIDER and the matching API key
python -m examples.run_live   # re-generates package.json + all adapter outputs
```

Secrets are read from the environment only. `.env` is gitignored; nothing is ever committed.

## Repository layout

```
core/                 the framework-agnostic brain
  generate_cases.py   requirement -> cases
  review_gate.py      a 2nd LLM critiques the cases
  revise_cases.py     apply only human-approved feedback
  generate_data.py    synthetic, privacy-safe test data
  validate_data.py    hybrid check: rules (facts) + LLM (judgment)
  orchestrator.py     one flow, two modes (HITL / auto-CI), bounded retry + flag
adapters/             pure translators (no LLM, no re-generation)
  python_api.py       SOLID  - generic, service-agnostic engine (runnable)
  rest_assured.py     reference - Java fluent DSL
  apache_testng.py    reference - Apache HttpClient + TestNG (build-your-own style)
  bdd_gherkin.py      reference - plain-English .feature
  playwright.py       reference - UI
examples/
  sut/app.py          mock AeroAssist service under test (FastAPI, POST + GET)
  service_spec.py     thin per-service spec + oracles
  oracles.py          the single source of truth (should_refund / is_well_formed)
  run_demo.py         deterministic demo (no key)
  run_live.py         full live generation (needs key)
  output/             committed sample package + generated artifacts (all 5 stacks)
tests/test_engine.py  deterministic engine test (CI)
docs/history/first-version.md  the first version's design decisions + rationale
```

## The core ideas in one screen

| Idea | Where |
|---|---|
| Orchestrated pipeline, autonomy staged by risk | `core/orchestrator.py` |
| Review gate — and the reviewer is also an LLM (human holds veto) | `core/review_gate.py` |
| Hybrid validation: rules for facts, LLM for judgment | `core/validate_data.py` |
| One core -> many stacks, all sharing one oracle | `adapters/`, `examples/oracles.py` |
| Service-agnostic engine driven by a thin spec | `adapters/python_api.py`, `examples/service_spec.py` |
| Oracle is a role, not a database (computed + reference-data) | `examples/service_spec.py` |

See [`docs/history/first-version.md`](docs/history/first-version.md) for the reasoning behind each.

## Scope (named != claimed)

- **Executed live:** the Python API adapter + engine (`pytest`, green against the mock SUT).
- **Reference implementations:** REST Assured, Apache HttpClient + TestNG, BDD/Gherkin, Playwright —
  idiomatic and review-ready; they run in their own stack's environment.

---

*A learning/portfolio project: a mock service, exercised end-to-end, to demonstrate AI-assisted
quality engineering with real guardrails.*
