# Low-cost AI series organization

## Goal

Complete the remaining PIMS series suggestions at substantially lower API cost without weakening JSON validation, retry behavior, or human approval gates.

## Selected approach

Use `deepseek-v4-flash` for series organization, disable thinking/reasoning mode, and cap generated output at 600 tokens. The task is structured extraction and naming from folder paths and file names, so high-effort hidden reasoning is unnecessary.

## Configuration and client behavior

- Default model: `deepseek-v4-flash`.
- Thinking: disabled.
- Temperature: low and deterministic (`0.2`).
- Maximum generated tokens: 600.
- Capture the provider `usage` object for each response so the worker can log prompt, completion, and total token counts.
- Preserve the existing `chat()` return value for callers; expose usage as client state or an equivalent backward-compatible interface.

## Worker flow

The resumed worker selects only pending candidates without a suggestion, sends one request per candidate, validates the JSON response, commits a pending-review suggestion, and advances to the next candidate. It records per-batch success/failure counts and aggregate token usage.

Transient malformed JSON may be retried by the existing next-batch behavior. HTTP 402 stops the worker instead of repeatedly calling the API. No worker action may move, delete, quarantine, or approve files.

## Validation

- Unit tests verify Flash/non-thinking payloads include `temperature=0.2` and `max_tokens=600` while omitting thinking fields.
- Unit tests verify response usage is captured without changing the returned content string.
- Existing DeepSeek client and series suggestion tests remain green.
- A controlled live request verifies valid JSON output and materially lower reasoning/token consumption before the full worker resumes.
- After restart, the first batch is checked for success rate, token totals, database growth, and balance consumption.

## Success criteria

- The worker runs with `deepseek-v4-flash`, thinking disabled, and a 600-token output cap.
- Suggestions continue from the current database state without duplicates.
- Token usage is visible in logs.
- Existing approval gates remain intact.
- The automated stage completes with every eligible candidate having a suggestion, or stops cleanly on an external billing error.
