# mock_service: the reference API

A small bookings API that `api-qa-agent`'s frameworks, examples and CI run against, plus a
stand-in notifications service for the environment check. Data lives in memory.

```bash
pip install -e .                       # from the repository root
python -m mock_service                 # bookings on :8000, notifications on :8001
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
| One service only | `python -m mock_service --only bookings` |
| OpenAPI | [`openapi.json`](openapi.json); after a change, `python -m mock_service --export-openapi mock_service/openapi.json` |
| A seeded bug | `python -m mock_service --bug refund-boundary` (or `MOCK_BUG=...`): one of seven small slips, so `qa-agent bug-detection` can measure whether tests catch bugs. The list is in [`seeded_bugs.py`](seeded_bugs.py) |

Settings: `MOCK_CLIENT_ID`, `MOCK_CLIENT_SECRET`, `MOCK_TEST_MODE` (on by default; turns `/test/*`
on), `NOTIFICATIONS_DOWN`, `MOCK_BUG` (none by default). Full contract: [`docs/lld.md`](../docs/lld.md), section 2.
