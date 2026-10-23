"""The AI layer: a model drafts, code checks, a person approves.

Everything that talks to a model goes through AiSession (session.py): redaction first
(redaction.py), then the model (models.py: anthropic, openai, or recorded replies), then the audit
log (audit.py). Nothing the model writes is approved by the model.
"""

from qa_agent.ai.audit import AuditLog
from qa_agent.ai.models import (Model, ModelError, ModelReply, ModelRequest, ModelSetupError, RecordedModel,
                                model_from_settings)
from qa_agent.ai.redaction import redact
from qa_agent.ai.session import AiSession

__all__ = ["AiSession", "AuditLog", "Model", "ModelError", "ModelReply", "ModelRequest", "ModelSetupError",
           "RecordedModel", "model_from_settings", "redact"]
