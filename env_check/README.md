# env_check: is the environment ready?

Before any suite runs, call the health endpoint of every service a team depends on. A critical
service that is down stops the run with **exit 3**: an environment problem, never reported as a
product bug. One tool for every framework (Python, REST Assured); it only ever sends `GET`.

```bash
pip install -e .                       # from the repository root
python -m env_check --env demo --environments config/environments.yaml --dependencies config/dependencies.yaml
```

```
demo · cancellations
  bookings        200   6 ms      ok
  notifications   503   2 ms      DOWN, not critical: tests still run (expected 200, got 503)
READY (exit 0)
```

**`dependencies.yaml`** (one per team; hosts come from `environments.yaml`):

```yaml
team: cancellations
attempts: 3            # default 3
wait_seconds: 2        # default 2, doubled after each failed attempt
checks:
  - service: bookings          # critical by default
  - service: notifications
    path: /health-check        # default; set it when a service uses another path
    expect_status: 200         # default
    timeout_seconds: 5         # default
    critical: false            # down -> listed, tests still run
```

| Exit code | Meaning |
|---|---|
| 0 | Ready (a non-critical service may be down; it is listed) |
| 2 | Setup problem: a file or setting is wrong |
| 3 | Not ready: a critical service is down |

`--json` prints the report as JSON. From Python: `check_environment(env, environments_path,
dependencies_path)` returns a `ReadinessReport`.
