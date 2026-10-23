"""The one way the AI layer talks to a model: redact, call, log.

Every command that uses a model asks through an AiSession, so no call can skip redaction or the audit
log: the guardrails are in this code, not in a prompt.

    session = AiSession.for_project(project)
    text = session.ask("draft AC-3", system, user)
"""

import time
from pathlib import Path
from typing import Optional

from qa_agent.ai.audit import AuditLog
from qa_agent.ai.models import Model, ModelError, ModelRequest, model_from_settings
from qa_agent.ai.redaction import redact

LOG_FILE = Path("reports") / "ai-audit-log.jsonl"


class AiSession:
    def __init__(self, model: Model, log: AuditLog, prices: Optional[dict] = None):
        self.model = model
        self.log = log
        self.prices = prices or {}
        self.calls = 0

    @classmethod
    def for_project(cls, project, model: Optional[Model] = None) -> "AiSession":
        settings = project.ai or {}
        prices = {kind: settings[f"{kind}_price_per_million"] for kind in ("input", "output")
                  if settings.get(f"{kind}_price_per_million") is not None}
        return cls(model or model_from_settings(settings, project.root), AuditLog(project.root / LOG_FILE), prices)

    def ask(self, name: str, system: str, user: str, max_tokens: int = 2000) -> str:
        system_sent, user_sent = redact(system), redact(user)
        redactions = system_sent.counts + user_sent.counts
        started = time.monotonic()
        self.calls += 1
        details = dict(name=name, provider=self.model.provider, model=self.model.model, system=system_sent.text,
                       user=user_sent.text, redactions=redactions)
        try:
            reply = self.model.complete(ModelRequest(name, system_sent.text, user_sent.text, max_tokens))
        except ModelError as error:
            self.log.record(**details, duration_ms=_ms_since(started), error=str(error))
            raise
        self.log.record(**details, reply=reply.text, input_tokens=reply.input_tokens,
                        output_tokens=reply.output_tokens, cost_usd=self.cost(reply.input_tokens, reply.output_tokens),
                        duration_ms=_ms_since(started))
        return reply.text

    def cost(self, input_tokens: int, output_tokens: int) -> Optional[float]:
        """In US dollars, when qa-agent.yaml gives both prices (per million tokens)."""
        if set(self.prices) != {"input", "output"}:
            return None
        return round((input_tokens * self.prices["input"] + output_tokens * self.prices["output"]) / 1_000_000, 6)


def _ms_since(started: float) -> int:
    return int((time.monotonic() - started) * 1000)
