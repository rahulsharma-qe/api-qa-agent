# demo_api: the reference API

A small bookings API that `api-qa-agent`'s frameworks, examples and CI run against, plus a
stand-in notifications service for the environment check. Data lives in memory.

```bash
pip install -e .                       # from the repository root
python -m demo_api                     # bookings on :8000, notifications on :8001
curl localhost:8000/health-check
```

| What | How |
|---|---|
| A token | `POST /auth/token {"client_id": "demo-client", "client_secret": "demo-secret"}` |
| Bookings | create, read, update (name and email), delete, list with `?status=` and `?limit=` |
| Cancel | `POST /bookings/{pnr}/cancel {"cancelled_at": "..."}`: a full refund up to 24 hours after `booked_at`, exactly 24 hours included |
| Refund status | `GET /bookings/{pnr}/refund`: `refunded`, `no_refund` or `not_cancelled` |
| Errors | always `{"error": {"code", "message"}}` |
| Notifications down | `POST localhost:8001/test/state {"down": true}`, or start with `NOTIFICATIONS_DOWN=1` |
| One service only | `python -m demo_api --only bookings` |
| OpenAPI | [`openapi.json`](openapi.json); after a change, `python -m demo_api --export-openapi demo_api/openapi.json` |
| A seeded bug | `python -m demo_api --bug refund-boundary` (or `DEMO_BUG=...`): one of seven small slips, so `qa-agent bug-detection` can measure whether tests catch bugs. The list is in [`seeded_bugs.py`](seeded_bugs.py) |

Settings: `DEMO_CLIENT_ID`, `DEMO_CLIENT_SECRET`, `DEMO_TEST_MODE` (on by default; turns `/test/*`
on), `NOTIFICATIONS_DOWN`, `DEMO_BUG` (none by default). Full contract: [`docs/lld.md`](../docs/lld.md), section 2.
