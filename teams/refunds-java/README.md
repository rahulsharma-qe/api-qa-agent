# refunds-java: a team's API tests

One of two small teams in this repository, each shaped exactly like its own repository: made with
`qa-agent init`, then given its own criteria and four cases (the 24-hour refund rule, refund status, and a second cancel), reviewed by the team's lead
in the review sheet, and generated in REST Assured and TestNG.

CI: in its own repository, `.github/workflows/api-tests.yml` would call the platform's reusable
workflow in one job. Here, the repository's [`teams.yml`](../../.github/workflows/teams.yml) makes
that same call for both teams, each building only its own stack.

```bash
pip install -e .                                   # at the repository's root
(cd frameworks/restassured_api && ./mvnw -q install -DskipTests)
cd teams/refunds-java
python -m mock_service &                   # the reference API
python -m env_check --env mock
./mvnw test
qa-agent trace --results target/surefire-reports
```

| File | What it is |
|---|---|
| `qa-agent.yaml` | The team, its main service, its stack |
| `api/source/openapi.json`, `api/api.yaml` | The reference API's OpenAPI description, imported |
| `criteria.yaml` | The team's four acceptance criteria |
| `cases/` | Its four cases, approved in `review/cases.xlsx` |
| `src/test/java/generated/` | The generated tests |
