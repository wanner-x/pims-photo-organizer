import httpx


class DeepSeekClient:
    def __init__(
        self,
        *,
        api_key: str | None,
        base_url: str = "https://api.deepseek.com",
        model: str = "deepseek-chat",
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("DeepSeek API key is required")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.transport = transport

    def chat(self, messages: list[dict[str, str]]) -> str:
        with httpx.Client(transport=self.transport, timeout=60.0) as client:
            response = client.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "authorization": f"Bearer {self.api_key}",
                    "content-type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": messages,
                    "temperature": 0.2,
                },
            )
            response.raise_for_status()
        payload = response.json()
        return str(payload["choices"][0]["message"]["content"]).strip()
