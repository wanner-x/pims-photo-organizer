# Low-cost AI Series Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run the remaining PIMS series suggestions with DeepSeek V4 Flash, no thinking, a 600-token cap, and visible token usage.

**Architecture:** Keep the existing `DeepSeekClient.chat()` string interface so all callers remain compatible. Add a configurable output cap and retain the latest provider usage metadata on the client; update settings defaults and constructor wiring, then launch the safe worker against only candidates that still lack suggestions.

**Tech Stack:** Python 3.14, Pydantic Settings, httpx, SQLAlchemy, pytest.

---

### Task 1: Low-cost configuration defaults

**Files:**
- Modify: `tests/test_config.py`
- Modify: `src/pims_v1/config.py:31-35`

- [ ] **Step 1: Write the failing configuration test**

Change the DeepSeek assertions in `test_settings_accept_deepseek_api_key` to:

```python
assert settings.deepseek_model == "deepseek-v4-flash"
assert settings.deepseek_reasoning_effort == "low"
assert settings.deepseek_thinking_enabled is False
assert settings.deepseek_max_tokens == 600
```

- [ ] **Step 2: Run the test and verify RED**

Run: `pytest tests/test_config.py::test_settings_accept_deepseek_api_key -v`

Expected: FAIL because the current defaults are Pro/high/thinking and `deepseek_max_tokens` does not exist.

- [ ] **Step 3: Implement the minimal settings change**

Set these fields in `Settings`:

```python
deepseek_model: str = "deepseek-v4-flash"
deepseek_reasoning_effort: str = "low"
deepseek_thinking_enabled: bool = False
deepseek_max_tokens: int = 600
```

- [ ] **Step 4: Run the focused test and verify GREEN**

Run: `pytest tests/test_config.py::test_settings_accept_deepseek_api_key -v`

Expected: PASS.

### Task 2: Token cap and usage capture

**Files:**
- Modify: `tests/test_deepseek_client.py`
- Modify: `src/pims_v1/services/deepseek_client.py`

- [ ] **Step 1: Write failing client tests**

Extend the mock response in `test_deepseek_client_sends_chat_request_and_returns_content` with:

```python
"usage": {"prompt_tokens": 120, "completion_tokens": 80, "total_tokens": 200},
```

Pass `max_tokens=600` to the client and add:

```python
assert payload["max_tokens"] == 600
assert client.last_usage == {
    "prompt_tokens": 120,
    "completion_tokens": 80,
    "total_tokens": 200,
}
```

Add a separate test:

```python
def test_deepseek_client_uses_low_cost_non_thinking_payload():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["payload"] = json.loads(request.read().decode("utf-8"))
        return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})

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
    }
    assert client.last_usage == {}
```

- [ ] **Step 2: Run the tests and verify RED**

Run: `pytest tests/test_deepseek_client.py -v`

Expected: FAIL because `max_tokens` and `last_usage` are not implemented.

- [ ] **Step 3: Implement the minimal client behavior**

Add `max_tokens: int = 600` to `DeepSeekClient.__init__`, store it, initialize `self.last_usage: dict[str, object] = {}`, add `"max_tokens": self.max_tokens` to every payload, and after parsing the response assign:

```python
self.last_usage = dict(payload.get("usage") or {})
```

Keep `chat()` returning the stripped content string.

- [ ] **Step 4: Run the client tests and verify GREEN**

Run: `pytest tests/test_deepseek_client.py -v`

Expected: all tests PASS.

### Task 3: Wire the setting through application callers

**Files:**
- Modify: `src/pims_v1/cli.py:586-596,691-700,775-784`
- Modify: `src/pims_v1/api/review.py:122-130,146-154`

- [ ] **Step 1: Add `max_tokens` to every production constructor**

Add this argument beside the existing model/thinking arguments in all five settings-driven `DeepSeekClient` calls:

```python
max_tokens=settings.deepseek_max_tokens,
```

- [ ] **Step 2: Run caller regression tests**

Run: `pytest tests/test_cli.py tests/test_review_routes.py -q`

Expected: PASS with no constructor regressions.

### Task 4: Full verification and live cost smoke test

**Files:**
- No production file changes.

- [ ] **Step 1: Run the focused suite**

Run: `pytest tests/test_config.py tests/test_deepseek_client.py tests/test_cli.py tests/test_review_routes.py -q`

Expected: PASS.

- [ ] **Step 2: Run one controlled live request**

Build the normal organization prompt for one remaining high-ID candidate and call the configured client once without committing a suggestion. Record `client.last_usage`, returned JSON validity, model, elapsed time, and balance before/after.

Expected: model `deepseek-v4-flash`, no reasoning token field or zero reasoning tokens, valid JSON within 600 completion tokens, and lower cost than the Pro/high sample.

- [ ] **Step 3: Review the diff**

Run: `git diff --check && git diff -- tests/test_config.py tests/test_deepseek_client.py src/pims_v1/config.py src/pims_v1/services/deepseek_client.py src/pims_v1/cli.py src/pims_v1/api/review.py`

Expected: no whitespace errors and only the approved low-cost changes.

### Task 5: Resume and monitor the safe worker

**Files:**
- Runtime log: `data/logs/safe-ai-flash-<timestamp>.out.log`

- [ ] **Step 1: Start one worker**

Start a background worker that selects `pending` candidates with no `series_suggestions` row, constructs `DeepSeekClient` from the updated settings, and emits per-candidate usage plus per-batch token totals. It must stop on HTTP 402 and must not call move, delete, quarantine, archive, or approval operations.

- [ ] **Step 2: Verify the first ten candidates**

Confirm the log reports ten successful suggestions, model `deepseek-v4-flash`, `failed=0`, nonzero token totals, and no reasoning usage. Confirm the database suggestion count increased by ten without duplicate candidate IDs.

- [ ] **Step 3: Continue monitoring**

Keep the existing PIMS heartbeat active until `pending_without_suggestion=0`, then audit final counts and approval gates before marking the goal complete and deleting the monitor.
