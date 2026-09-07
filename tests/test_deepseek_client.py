import json

import httpx

from pims_v1.services.deepseek_client import DeepSeekClient


def test_deepseek_client_sends_chat_request_and_returns_content():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["authorization"] = request.headers["authorization"]
        captured["path"] = request.url.path
        captured["payload"] = request.read().decode("utf-8")
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": "海边白裙写真",
                        }
                    }
                ],
                "usage": {
                    "prompt_tokens": 120,
                    "completion_tokens": 80,
                    "total_tokens": 200,
                },
            },
        )

    client = DeepSeekClient(
        api_key="secret",
        base_url="https://api.deepseek.test",
        model="deepseek-v4-pro",
        thinking_enabled=True,
        reasoning_effort="high",
        max_tokens=600,
        transport=httpx.MockTransport(handler),
    )

    content = client.chat([{"role": "user", "content": "Name this series"}])

    assert content == "海边白裙写真"
    assert captured["authorization"] == "Bearer secret"
    assert captured["path"] == "/chat/completions"
    payload = json.loads(captured["payload"])
    assert payload["model"] == "deepseek-v4-pro"
    assert payload["reasoning_effort"] == "high"
    assert payload["thinking"] == {"type": "enabled"}
    assert payload["max_tokens"] == 600
    assert "temperature" not in payload
    assert client.last_usage == {
        "prompt_tokens": 120,
        "completion_tokens": 80,
        "total_tokens": 200,
    }


def test_deepseek_client_uses_low_cost_non_thinking_payload():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = json.loads(request.read().decode("utf-8"))
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "{}"}}]},
        )

    client = DeepSeekClient(
        api_key="secret",
        model="deepseek-v4-flash",
        thinking_enabled=False,
        max_tokens=600,
        transport=httpx.MockTransport(handler),
    )

    assert client.chat([{"role": "user", "content": "organize"}]) == "{}"
    assert captured["payload"] == {
        "model": "deepseek-v4-flash",
        "messages": [{"role": "user", "content": "organize"}],
        "max_tokens": 600,
        "temperature": 0.2,
        "thinking": {"type": "disabled"},
    }
    assert client.last_usage == {}


def test_deepseek_client_requires_api_key():
    try:
        DeepSeekClient(api_key=None)
    except ValueError as exc:
        assert str(exc) == "DeepSeek API key is required"
    else:
        raise AssertionError("expected missing key to raise")
