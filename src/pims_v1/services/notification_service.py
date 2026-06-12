import json
from urllib import request


def send_wechat_text_message(webhook_url: str, content: str, timeout: float = 10.0) -> dict:
    payload = {
        "msgtype": "text",
        "text": {
            "content": content,
        },
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    http_request = request.Request(
        webhook_url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(http_request, timeout=timeout) as response:
        response_body = response.read().decode("utf-8")
    return json.loads(response_body) if response_body else {}
