# External API: Swagger Petstore

The other examples test the reference API, which this repository wrote. This one tests
[Swagger Petstore](https://github.com/swagger-api/swagger-petstore), the public demo API many
tools use: its own OpenAPI description, cases from a team's Excel sheet, reviewed, generated in
pytest and REST Assured, run and traced.

| Where it runs | How | When |
|---|---|---|
| `local` | The official Docker image, `swaggerapi/petstore3:unstable` on port 8080: our own copy, clean data, the same every time | Every change, in CI ([`external-apis.yml`](../../../.github/workflows/external-apis.yml)) |
| `public` | `petstore3.swagger.io`: shared with everyone, so its data changes and it is sometimes down | By hand: Actions → External APIs → Run workflow → public |

```bash
docker run -d -p 8080:8080 swaggerapi/petstore3:unstable     # or use --env public below
cd examples/external-apis/petstore
python -m env_check --env local            # Petstore has no health endpoint: the check reads the inventory
python -m pytest --env local --junitxml=reports/junit.xml
./mvnw test -Denv=local
qa-agent trace --results reports/junit.xml target/surefire-reports
```

## How it was made

1. `qa-agent init`, then Petstore's `openapi.json` (downloaded from the server) imported:
   `qa-agent import api api/source/openapi.json`. 19 operations; the image upload is marked
   `not_tested` (a binary upload; the case format sends JSON).
2. What Petstore really returns was checked against the public server first, call by call, so no
   expected result is a guess: it answers 200 (not 201) when a pet is created, takes the pet's id
   from the client, and says "Pet not found" as plain text.
3. The team's cases, in the API layout of `existing/petstore_cases.xlsx`, imported:
   `qa-agent import cases existing/petstore_cases.xlsx`. Each case makes its own pet or order (fixed
   ids, a unique name) and deletes it, so it never depends on anyone else's data.
4. Reviewed in `review/cases.xlsx` by the team's lead, then generated in both stacks.

## What it found

**Petstore accepts a pet with no name.** Its OpenAPI says `name` is required and documents 422 for a
validation error, but `POST /pet` without a name answers 200 and stores the pet. Case TC106 checks
exactly this; `qa-agent check` flagged the missing field as a possible negative test, and the
reviewer kept TC106 out of the run with "changes needed" and the reason, until Petstore is fixed.
That is the job the review step is for: the case is right, the API is not, and a person decides
what the build should do about it.

The trace also shows what isn't covered, plainly: 7 of 18 operations have an approved case. The user
endpoints, finding pets by status or tag, the inventory and updating a pet with form data have none.
They are the gaps a team would fill next.
