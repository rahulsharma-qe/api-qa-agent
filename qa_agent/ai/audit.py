"""Every model call, on the record: reports/ai-audit-log.jsonl, one line per call.

What was sent (after redaction) and what was redacted, the provider and model, the reply, the tokens,
the cost when prices are set, how long it took, and the error if it failed. Appended, never
rewritten: an audit trail for a regulated team, and the data for measuring the AI layer.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


class AuditLog:
    def __init__(self, path: Path):
        self.path = Path(path)

    def record(self, *, name: str, provider: str, model: str, system: str, user: str, redactions: dict,
               reply: str = "", input_tokens: int = 0, output_tokens: int = 0, cost_usd: Optional[float] = None,
               duration_ms: int = 0, error: str = "") -> dict:
        entry = {"time": datetime.now(timezone.utc).isoformat(timespec="seconds"), "name": name,
                 "provider": provider, "model": model, "sent": {"system": system, "user": user},
                 "redactions": dict(redactions), "reply": reply, "input_tokens": input_tokens,
                 "output_tokens": output_tokens, "cost_usd": cost_usd, "duration_ms": duration_ms}
        if error:
            entry["error"] = error
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as log:
            log.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return entry

    def entries(self) -> list[dict]:
        if not self.path.is_file():
            return []
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip()]
