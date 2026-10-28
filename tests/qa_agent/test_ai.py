"""The AI layer's base: redaction, the providers (no network), the audit log and the session."""

import json
import sys
import types
from types import SimpleNamespace

import pytest

from qa_agent.ai import (AiSession, AuditLog, ModelError, ModelReply, ModelSetupError, RecordedModel,
                         model_from_settings, redact)
from qa_agent.ai.models import AnthropicModel, OpenAIModel, file_name
from qa_agent.project import TeamProject


def test_redaction_replaces_emails_tokens_keys_and_secret_values_and_counts_them():
    text = ('passenger: a.k@example.com\nAuthorization: Bearer abc.def-123456789\n'
            '{"client_secret": "s3cr3t-value", "password": hunter2}\nkey sk-live_1234567890abcdefXYZ\n'
            'jwt eyJhbGciOiJIUzI1.eyJzdWIiOiIxMjM0.SflKxwRJSMeKKF2QT4\nAuthorization: Basic dXNlcjpwYXNz\n')
    redacted = redact(text)
    for gone in ("a.k@example.com", "abc.def-123456789", "s3cr3t-value", "hunter2", "sk-live_1234567890abcdefXYZ",
                 "eyJhbGciOiJIUzI1", "dXNlcjpwYXNz"):
        assert gone not in redacted.text
    assert "[email]" in redacted.text and "Bearer [token]" in redacted.text and "[key]" in redacted.text
    assert redacted.counts["email"] == 1 and redacted.counts["key"] == 1 and redacted.counts["token"] == 3


def test_redaction_keeps_what_says_what_to_test():
    text = 'body: {passenger_name: "A {{unique}}", email: "{{email}}", password: "{{row.password}}"}\n' \
           "expect: {fields: {token_type: bearer}}\ncapture: {token: access_token}\nrequired: [email, password]"
    assert redact(text).text == text and not redact(text).counts


def test_a_recorded_reply_comes_from_its_file_and_a_missing_one_names_the_file(tmp_path):
    (tmp_path / "draft-ac-3.txt").write_text("cases: []\n", encoding="utf-8")
    model = RecordedModel(tmp_path)
    assert model.complete(_request("draft AC-3")).text == "cases: []\n"
    with pytest.raises(ModelError, match="draft-ac-4.txt"):
        model.complete(_request("draft AC-4"))
    assert file_name("Draft: POST /bookings 409") == "draft-post-bookings-409"


@pytest.mark.parametrize("settings, problem", [
    ({}, "no ai: settings"),
    ({"provider": "gemini"}, "use anthropic, openai, recorded"),
    ({"provider": "recorded"}, "needs ai.recorded"),
    ({"provider": "anthropic"}, "needs ai.model"),
])
def test_wrong_settings_say_what_to_add(settings, problem, tmp_path):
    with pytest.raises(ModelSetupError, match=problem):
        model_from_settings(settings, tmp_path)


def test_a_key_comes_only_from_the_environment(monkeypatch, tmp_path):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(ModelSetupError, match="set ANTHROPIC_API_KEY in the environment"):
        model_from_settings({"provider": "anthropic", "model": "a-model"}, tmp_path)
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(OpenAI=lambda api_key: ("client", api_key)))
    assert model_from_settings({"provider": "openai", "model": "m"}, tmp_path)._client == ("client", "k")


def test_a_model_on_your_own_server_through_base_url(monkeypatch, tmp_path):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)                  # a local server needs no key
    monkeypatch.setitem(sys.modules, "openai", types.SimpleNamespace(
        OpenAI=lambda api_key, base_url=None: ("client", api_key, base_url)))
    local = {"provider": "openai", "model": "llama3.1", "base_url": "http://localhost:11434/v1"}
    model = model_from_settings(local, tmp_path)
    assert model._client == ("client", "not-needed", "http://localhost:11434/v1")
    assert (model.provider, model.model) == ("openai", "llama3.1")     # what the audit log and ai-report show
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    assert model_from_settings(local, tmp_path)._client == ("client", "k", "http://localhost:11434/v1")


@pytest.mark.parametrize("settings, problem", [
    ({"provider": "anthropic", "model": "m", "base_url": "http://localhost:11434/v1"}, "works with ai.provider openai"),
    ({"provider": "openai", "model": "m", "base_url": "localhost:11434"}, "should start with http:// or https://"),
])
def test_base_url_is_checked(tmp_path, settings, problem):
    with pytest.raises(ModelSetupError, match=problem):
        model_from_settings(settings, tmp_path)


def test_each_provider_sends_the_request_and_reads_the_reply_and_tokens():
    sent = {}

    def anthropic_create(**kwargs):
        sent["anthropic"] = kwargs
        return SimpleNamespace(content=[SimpleNamespace(type="text", text="hello")],
                               usage=SimpleNamespace(input_tokens=11, output_tokens=3))

    def openai_create(**kwargs):
        sent["openai"] = kwargs
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="hi"))],
                               usage=SimpleNamespace(prompt_tokens=7, completion_tokens=2))

    anthropic = AnthropicModel("a-model", client=SimpleNamespace(messages=SimpleNamespace(create=anthropic_create)))
    openai = OpenAIModel("o-model", client=SimpleNamespace(chat=SimpleNamespace(
        completions=SimpleNamespace(create=openai_create))))
    assert anthropic.complete(_request("x")) == ModelReply("hello", 11, 3)
    assert openai.complete(_request("x")) == ModelReply("hi", 7, 2)
    assert sent["anthropic"]["temperature"] == 0 and sent["anthropic"]["system"] == "rules"
    assert sent["openai"]["messages"][0] == {"role": "system", "content": "rules"}


def test_the_session_redacts_before_sending_and_logs_every_call(make_project):
    root = make_project({}, config="team: t\nservice: bookings\nframeworks: [pytest]\nai:\n  provider: recorded\n"
                                   "  recorded: ai/recorded\n  input_price_per_million: 3\n  output_price_per_million: 15\n")
    seen = []

    class Fake:
        provider, model = "fake", "fake-1"

        def complete(self, request):
            seen.append(request)
            if request.name == "fails":
                raise ModelError("down")
            return ModelReply("draft", 1000, 200)

    session = AiSession.for_project(TeamProject.load(root), model=Fake())
    assert session.ask("draft AC-1", "system", "passenger a@b.co") == "draft"
    with pytest.raises(ModelError):
        session.ask("fails", "system", "x")
    assert seen[0].user == "passenger [email]" and session.calls == 2
    first, second = [json.loads(line) for line in (root / "reports/ai-audit-log.jsonl").read_text().splitlines()]
    assert (first["name"], first["provider"], first["sent"]["user"], first["redactions"]) == \
        ("draft AC-1", "fake", "passenger [email]", {"email": 1})
    assert (first["input_tokens"], first["output_tokens"], first["cost_usd"]) == (1000, 200, 0.006)
    assert second["error"] == "down" and second["reply"] == ""
    assert len(AuditLog(root / "reports/ai-audit-log.jsonl").entries()) == 2


def test_a_project_without_ai_settings_still_loads_and_a_wrong_one_is_named(make_project):
    assert TeamProject.load(make_project({})).ai == {}
    root = make_project({}, config="team: t\nservice: bookings\nframeworks: [pytest]\nai: anthropic\n")
    with pytest.raises(Exception, match="'ai' should be a mapping"):
        TeamProject.load(root)


def _request(name):
    from qa_agent.ai import ModelRequest
    return ModelRequest(name, "rules", "the question")


def test_redaction_also_covers_api_key_headers_access_tokens_cards_and_phones():
    text = ('"X-Api-Key": "a1b2c3d4e5f6g7h8"\naccess_token: 9f8e7d6c5b4a3210\nAuthorization: Token abcdef1234567890xyz\n'
            "card 4111 1111 1111 1111, order 1234567890123\nphone +91 98765 43210, 9876543210\n"
            "epoch 1761638400, amount 4000\ncapture: {token: access_token}")
    redacted = redact(text)
    for gone in ("a1b2c3d4e5f6g7h8", "9f8e7d6c5b4a3210", "abcdef1234567890xyz", "4111 1111 1111 1111", "98765 43210",
                 "9876543210"):
        assert gone not in redacted.text
    for kept in ("order 1234567890123", "epoch 1761638400", "amount 4000", "capture: {token: access_token}"):
        assert kept in redacted.text                                          # not a card (Luhn), not a phone, a name
    assert dict(redacted.counts) == {"card": 1, "token": 1, "secret": 2, "phone": 2}
