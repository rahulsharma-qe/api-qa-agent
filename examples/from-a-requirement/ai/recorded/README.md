# Recorded replies: hand-written, no model was called

`qa-agent.yaml` says `ai: {provider: recorded, recorded: ai/recorded}`: when qa-agent needs a
model's reply, it reads it from this folder instead of calling a model, by the request's name
(`draft criteria BOOK-101` reads `draft-criteria-book-101.txt`). Like a mock service in a test, it
lets anyone run the example with no API key, and gives CI the same reply every time.

**Every reply here was written by hand**, in the shape a model replies, with the mistakes models
make, so each guardrail can be seen at work:

| Reply | What is in it | What qa-agent did |
|---|---|---|
| `draft-criteria-book-101.txt` | A criterion quoting words that aren't in the requirement (an email) | Refused it: not grounded |
| `draft-ac-1.txt` | Its own id and `review: approved` | Dropped both: ids and review come from code |
| `draft-ac-3.txt` | None: it didn't know an error code, so it wrote `TBD`, as the prompt asks | `check` made it an error; the reviewer sent it back; `redo-tc005.txt` fixed it |
| `draft-post-bookings-pnr-cancel.txt` | A call to `POST /bookings/{{pnr}}/cancellations`, which the API doesn't have | Refused the whole reply |

They show the flow and the guardrails, not how good a model is: replies recorded from a real
model replace them in a later release, and that run is measured.
