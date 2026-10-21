# External APIs: qa-agent on APIs this repository didn't write

The other examples test the reference API, which this repository wrote, so a reader may ask: was
the utility shaped around its own API? Each folder here answers that with someone else's public API,
taken through the same path: its own API description, a team's cases, review, generated tests in
pytest and REST Assured, a run, a trace.

| API | Folder | Runs in CI | Found |
|---|---|---|---|
| Swagger Petstore | [`petstore/`](petstore/) | Its official Docker image on every change; the public server by hand | Petstore accepts a pet with no name, against its own OpenAPI |

Adding another: `qa-agent init external-apis/<name> --stack restassured`, its OpenAPI or curl in
`api/source/`, its environments, a safe GET as its readiness check, cases that make and delete
their own data, and a job in [`external-apis.yml`](../../.github/workflows/external-apis.yml).
