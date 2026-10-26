"""The model behind the AI layer: one small interface, any provider.

    complete(ModelRequest) -> ModelReply

Providers: anthropic and openai (a model name in qa-agent.yaml, the key from an environment
variable, never from a file), and recorded: replies kept in a folder, one file per request name, so
tests, CI and the examples run with no key and give the same answer every time.

    ai:
      provider: anthropic                  # anthropic, openai or recorded
      model: <the provider's model name>
      recorded: ai/recorded                # provider recorded: the folder of replies
      base_url: http://localhost:11434/v1  # provider openai only: any OpenAI-compatible server (Ollama,
                                           # vLLM, LM Studio), e.g. a model in your own network; the key
                                           # is then optional
      input_price_per_million: 3.0         # optional: the audit log then shows each call's cost
      output_price_per_million: 15.0
"""

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Protocol

KEY_VARIABLES = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY"}
PROVIDERS = ("anthropic", "openai", "recorded")
NO_KEY = "not-needed"           # a local server ignores the key, but the client library wants one


class ModelError(Exception):
    """The model couldn't be reached or gave no usable reply."""


class ModelSetupError(Exception):
    """The ai: settings, the key or the provider's package are missing or wrong."""


@dataclass(frozen=True)
class ModelRequest:
    name: str                  # what the call is for ("draft AC-3"): the audit log's label, the recorded reply's file
    system: str
    user: str
    max_tokens: int = 2000


@dataclass(frozen=True)
class ModelReply:
    text: str
    input_tokens: int = 0
    output_tokens: int = 0


class Model(Protocol):
    provider: str
    model: str

    def complete(self, request: ModelRequest) -> ModelReply: ...


class AnthropicModel:
    provider = "anthropic"

    def __init__(self, model: str, client=None):
        self.model = model
        self._client = client or _sdk_client("anthropic", lambda sdk, key: sdk.Anthropic(api_key=key))

    def complete(self, request: ModelRequest) -> ModelReply:
        try:
            reply = self._client.messages.create(
                model=self.model, max_tokens=request.max_tokens, temperature=0, system=request.system,
                messages=[{"role": "user", "content": request.user}])
        except Exception as error:                      # the SDK's errors: network, limits, a bad request
            raise ModelError(f"{self.provider}: {error}") from error
        text = "".join(part.text for part in reply.content if getattr(part, "type", "text") == "text")
        return ModelReply(text, reply.usage.input_tokens, reply.usage.output_tokens)


class OpenAIModel:
    provider = "openai"

    def __init__(self, model: str, client=None, base_url: Optional[str] = None):
        self.model = model
        self.base_url = base_url
        build = (lambda sdk, key: sdk.OpenAI(api_key=key, base_url=base_url)) if base_url else \
            (lambda sdk, key: sdk.OpenAI(api_key=key))
        self._client = client or _sdk_client("openai", build, key_required=not base_url)

    def complete(self, request: ModelRequest) -> ModelReply:
        try:
            reply = self._client.chat.completions.create(
                model=self.model, max_tokens=request.max_tokens, temperature=0,
                messages=[{"role": "system", "content": request.system}, {"role": "user", "content": request.user}])
        except Exception as error:
            raise ModelError(f"{self.provider}: {error}") from error
        return ModelReply(reply.choices[0].message.content or "", reply.usage.prompt_tokens,
                          reply.usage.completion_tokens)


class RecordedModel:
    """Replies from a folder: <folder>/<request name as a file name>.txt. No key, no network."""
    provider = "recorded"
    model = "recorded"

    def __init__(self, folder: Path):
        self.folder = Path(folder)

    def reply_file(self, name: str) -> Path:
        return self.folder / f"{file_name(name)}.txt"

    def complete(self, request: ModelRequest) -> ModelReply:
        path = self.reply_file(request.name)
        if not path.is_file():
            raise ModelError(f"recorded: no reply for '{request.name}' (expected {path})")
        return ModelReply(path.read_text(encoding="utf-8"))


def model_from_settings(settings: Optional[dict], root: Path) -> Model:
    """The model the project's ai: settings name."""
    if not settings:
        raise ModelSetupError("qa-agent.yaml has no ai: settings (provider, and model or recorded)")
    provider = str(settings.get("provider") or "")
    if provider not in PROVIDERS:
        raise ModelSetupError(f"ai.provider '{provider}' (use {', '.join(PROVIDERS)})")
    if provider == "recorded":
        if not settings.get("recorded"):
            raise ModelSetupError("ai.provider recorded needs ai.recorded: the folder of replies")
        return RecordedModel(Path(root) / str(settings["recorded"]))
    if not settings.get("model"):
        raise ModelSetupError(f"ai.provider {provider} needs ai.model: the provider's model name")
    base_url = str(settings.get("base_url") or "")
    if base_url and provider != "openai":
        raise ModelSetupError("ai.base_url works with ai.provider openai (any OpenAI-compatible server), "
                              f"not {provider}")
    if base_url and not base_url.startswith(("http://", "https://")):
        raise ModelSetupError(f"ai.base_url '{base_url}' should start with http:// or https://, "
                              "e.g. http://localhost:11434/v1")
    if provider == "anthropic":
        return AnthropicModel(str(settings["model"]))
    return OpenAIModel(str(settings["model"]), base_url=base_url or None)


def file_name(name: str) -> str:
    """'draft AC-3' -> 'draft-ac-3'."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "reply"


def _sdk_client(package: str, build, key_required: bool = True):
    variable = KEY_VARIABLES[package]
    key = os.getenv(variable)
    if not key and key_required:
        raise ModelSetupError(f"set {variable} in the environment (never in a file) to use ai.provider {package}")
    key = key or NO_KEY
    try:
        sdk = __import__(package)
    except ImportError as error:
        raise ModelSetupError(f"pip install {package} to use ai.provider {package}") from error
    return build(sdk, key)
