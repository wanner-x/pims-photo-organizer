import httpx


class DeepSeekClient:
    def __init__(
        self,
        *,
        api_key: str | None,
        base_url: str = "https://api.deepseek.com",
        model: str = "deepseek-v4-pro",
        reasoning_effort: str = "high",
        thinking_enabled: bool = True,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("DeepSeek API key is required")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.reasoning_effort = reasoning_effort
        self.thinking_enabled = thinking_enabled
        self.transport = transport

    def chat(self, messages: list[dict[str, str]]) -> str:
        payload = {
            "model": self.model,
            "messages": messages,
        }
        if self.thinking_enabled:
            payload["reasoning_effort"] = self.reasoning_effort
            payload["thinking"] = {"type": "enabled"}
        else:
            payload["temperature"] = 0.2
        with httpx.Client(transport=self.transport, timeout=60.0) as client:
            response = client.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "authorization": f"Bearer {self.api_key}",
                    "content-type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
        payload = response.json()
        return str(payload["choices"][0]["message"]["content"]).strip()
