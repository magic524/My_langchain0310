from __future__ import annotations

from typing import Any

import pytest
import requests

from contract_metrics.prompt_runner import PromptRuntimeConfig, _send_chat, load_prompt_runtime_config


class _FakeResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return {"choices": [{"message": {"content": "{\"has_risk\": false}"}}]}


def test_load_prompt_runtime_config_reads_timeout_and_retry_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_BASE", "http://example.test/v1")
    monkeypatch.setenv("OPENAI_TIMEOUT_SECONDS", "600")
    monkeypatch.setenv("OPENAI_MAX_RETRIES", "4")
    monkeypatch.setenv("OPENAI_RETRY_BACKOFF_SECONDS", "1.5")

    runtime = load_prompt_runtime_config()

    assert runtime.timeout_seconds == 600.0
    assert runtime.max_retries == 4
    assert runtime.retry_backoff_seconds == 1.5


def test_send_chat_retries_after_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = PromptRuntimeConfig(
        model_name="demo-model",
        api_key="EMPTY",
        base_url="http://example.test/v1",
        temperature=0.0,
        extra_body=None,
        timeout_seconds=300.0,
        max_retries=1,
        retry_backoff_seconds=0.0,
    )
    calls = {"count": 0}

    def fake_post(*args: Any, **kwargs: Any) -> _FakeResponse:
        calls["count"] += 1
        if calls["count"] == 1:
            raise requests.exceptions.ReadTimeout("timed out")
        assert kwargs["timeout"] == 300.0
        return _FakeResponse()

    monkeypatch.setattr("contract_metrics.prompt_runner.requests.post", fake_post)

    content = _send_chat(runtime, system_prompt="sys", user_prompt="user")

    assert content == "{\"has_risk\": false}"
    assert calls["count"] == 2


def test_send_chat_raises_after_retry_budget_exhausted(monkeypatch: pytest.MonkeyPatch) -> None:
    runtime = PromptRuntimeConfig(
        model_name="demo-model",
        api_key="EMPTY",
        base_url="http://example.test/v1",
        temperature=0.0,
        extra_body=None,
        timeout_seconds=180.0,
        max_retries=2,
        retry_backoff_seconds=0.0,
    )
    calls = {"count": 0}

    def fake_post(*args: Any, **kwargs: Any) -> _FakeResponse:
        calls["count"] += 1
        raise requests.exceptions.ReadTimeout("still timed out")

    monkeypatch.setattr("contract_metrics.prompt_runner.requests.post", fake_post)

    with pytest.raises(requests.exceptions.ReadTimeout):
        _send_chat(runtime, system_prompt="sys", user_prompt="user")

    assert calls["count"] == 3
