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
                ]
            },
        )

    client = DeepSeekClient(
        api_key="secret",
        base_url="https://api.deepseek.test",
        model="deepseek-v4-pro",
        thinking_enabled=True,
        reasoning_effort="high",
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
    assert "temperature" not in payload


def test_deepseek_client_requires_api_key():
    try:
        DeepSeekClient(api_key=None)
    except ValueError as exc:
        assert str(exc) == "DeepSeek API key is required"
    else:
        raise AssertionError("expected missing key to raise")
