# bookings-python: a team's API tests

One of two small teams in this repository, each shaped exactly like its own repository: made with
`qa-agent init`, then given its own criteria and four cases (create, read, delete, list by status, and no token), reviewed by the team's lead
in the review sheet, and generated in pytest.

CI: in its own repository, `.github/workflows/api-tests.yml` would call the platform's reusable
workflow in one job. Here, the repository's [`teams.yml`](../../.github/workflows/teams.yml) makes
that same call for both teams, each building only its own framework.

```bash
pip install -e . -e frameworks/python_api          # at the repository's root
cd teams/bookings-python
python -m mock_service &                   # the reference API
python -m env_check --env mock
python -m pytest --junitxml=reports/junit.xml
qa-agent trace --results reports/junit.xml
```

| File | What it is |
|---|---|
| `qa-agent.yaml` | The team, its main service, its framework |
| `api/source/openapi.json`, `api/api.yaml` | The reference API's OpenAPI description, imported |
| `acceptance-criteria.yaml` | The team's four acceptance criteria |
| `cases/` | Its four cases, approved in `review/cases.xlsx` |
| `tests/generated/` | The generated tests |
