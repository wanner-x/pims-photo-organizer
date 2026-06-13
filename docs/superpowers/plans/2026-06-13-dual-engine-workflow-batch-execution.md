# Dual-Engine Workflow Batch Execution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the existing dual-engine archive flow so `run-safe-workflow` can automatically process a bounded batch of eligible series candidates, execute ordinary archive moves immediately, and report the outcome in CLI-visible workflow summaries.

**Architecture:** This slice keeps the existing single-candidate decision service and adds a thin batch orchestrator above it. The workflow service remains the integration point: it builds candidates, invokes the batch orchestrator only when an archive root and limit are provided, and returns a structured summary that the CLI prints without needing any review-UI changes.

**Tech Stack:** Python 3.11+, SQLAlchemy ORM, argparse CLI, pytest

---

## File Structure

**Create**

- None.

**Modify**

- `src/pims_v1/services/archive_decision_service.py`
  Add candidate selection and bounded batch execution helpers over the existing single-candidate auto-archive path.
- `src/pims_v1/services/safe_workflow_service.py`
  Invoke the new batch helper and expose an `archive_auto` summary block.
- `src/pims_v1/cli.py`
  Add workflow flags and instantiate the AI client for batch execution.
- `tests/test_archive_decision_service.py`
  Cover batch selection and mixed decision outcomes.
- `tests/test_safe_workflow_service.py`
  Cover workflow-level batch archive execution and summary counts.
- `tests/test_cli.py`
  Cover CLI-visible workflow output for batch auto-archive.

## Task 1: Add Batch Auto-Archive Helper

**Files:**

- Modify: `src/pims_v1/services/archive_decision_service.py`
- Modify: `tests/test_archive_decision_service.py`

- [x] **Step 1: Write the failing batch helper test**

```python
def test_auto_archive_candidates_processes_only_pending_candidates(tmp_path):
    session, first_candidate_id, archive_root = build_candidate_fixture(tmp_path)
    second_candidate = build_extra_candidate(
        session=session,
        source_root="D:/photos/R18/Series R18 [12P]",
        title="Series R18 [12P]",
        file_name="002.jpg",
        status="pending",
    )
    confirmed_candidate = build_extra_candidate(
        session=session,
        source_root="D:/photos/Done/Archived Set [8P]",
        title="Archived Set [8P]",
        file_name="003.jpg",
        status="confirmed",
    )
    client = SequencedAIPlanClient(
        [
            {
                "title": "雪琪SAMA 透明女仆 [43P4V234MB]",
                "category": "雪琪SAMA",
                "archive_path": "",
                "plan_summary": "保持人物目录结构",
                "risk_flags": [],
                "tags": [],
                "r18_label": False,
                "r18_confidence": 0.0,
                "r18_reason": "",
                "confidence": 0.93,
            },
            {
                "title": "Series R18 [12P]",
                "category": "R18",
                "archive_path": "",
                "plan_summary": "疑似成人内容",
                "risk_flags": ["r18_suspected"],
                "tags": ["R18"],
                "r18_label": True,
                "r18_confidence": 0.91,
                "r18_reason": "目录名含 R18",
                "confidence": 0.9,
            },
        ]
    )

    summary = auto_archive_candidates(
        session=session,
        archive_root=str(archive_root),
        client=client,
        limit=10,
    )

    assert summary["considered"] == 2
    assert summary["processed"] == 2
    assert summary["auto_apply"] == 1
    assert summary["manual_review"] == 1
    assert summary["confirmed"] == 1
    assert summary["pending_review"] == 1
    assert summary["moved"] == 1
    assert session.get(SeriesCandidate, confirmed_candidate.id).status == "confirmed"
```

- [x] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_archive_decision_service.py -q -k auto_archive_candidates`
Expected: FAIL because the batch helper does not exist yet.

- [x] **Step 3: Write the minimal batch orchestration**

```python
def auto_archive_candidates(
    *,
    session: Session,
    archive_root: str,
    client: NamingClient,
    limit: int = 20,
    candidate_statuses: tuple[str, ...] = ("pending", "ai_suggested"),
) -> dict[str, int]:
    candidate_ids = [
        row[0]
        for row in (
            session.query(SeriesCandidate.id)
            .filter(SeriesCandidate.status.in_(candidate_statuses))
            .order_by(SeriesCandidate.id)
            .limit(limit)
            .all()
        )
    ]
    summary = {
        "considered": len(candidate_ids),
        "processed": 0,
        "auto_apply": 0,
        "auto_apply_sampled": 0,
        "manual_review": 0,
        "confirmed": 0,
        "pending_review": 0,
        "failed": 0,
        "moved": 0,
        "risk_events": 0,
    }
    for candidate_id in candidate_ids:
        result = auto_archive_candidate(
            session=session,
            candidate_id=candidate_id,
            archive_root=archive_root,
            client=client,
        )
        summary["processed"] += 1
        summary[str(result["decision_type"])] += 1
        summary[str(result["status"])] += 1
        summary["moved"] += int(result.get("moved", 0))
        summary["risk_events"] += int(result.get("risk_events", 0))
    return summary
```

- [x] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_archive_decision_service.py -q -k auto_archive_candidates`
Expected: PASS with pending candidates processed in order and non-pending candidates skipped.

- [x] **Step 5: Commit**

```bash
git add tests/test_archive_decision_service.py src/pims_v1/services/archive_decision_service.py
git commit -m "feat: add batch auto archive helper"
```

## Task 2: Wire Batch Auto-Archive Into Safe Workflow

**Files:**

- Modify: `src/pims_v1/services/safe_workflow_service.py`
- Modify: `tests/test_safe_workflow_service.py`

- [x] **Step 1: Write the failing workflow integration test**

```python
def test_run_safe_workflow_executes_batch_auto_archive_when_enabled(tmp_path):
    session = make_session(tmp_path)
    archive_root = seed_dual_engine_workflow_fixture(session=session, tmp_path=tmp_path)
    client = SequencedAIPlanClient(
        [
            {
                "title": "雪琪SAMA 透明女仆 [43P4V234MB]",
                "category": "雪琪SAMA",
                "archive_path": "",
                "plan_summary": "保持人物目录结构",
                "risk_flags": [],
                "tags": [],
                "r18_label": False,
                "r18_confidence": 0.0,
                "r18_reason": "",
                "confidence": 0.93,
            }
        ]
    )

    summary = run_safe_workflow(
        session=session,
        keep_root=str(archive_root),
        cache_root=tmp_path / ".cache",
        md5_limit=10,
        phash_limit=10,
        thumbnail_limit=10,
        min_series_assets=1,
        auto_archive_limit=5,
        archive_client=client,
    )

    assert summary["archive_auto"]["processed"] == 1
    assert summary["archive_auto"]["auto_apply"] == 1
    assert summary["archive_auto"]["moved"] == 1
```

- [x] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_safe_workflow_service.py -q -k batch_auto_archive`
Expected: FAIL because the workflow does not expose or invoke batch auto-archive yet.

- [x] **Step 3: Add workflow integration**

```python
def run_safe_workflow(..., auto_archive_limit: int = 20, archive_client: NamingClient | None = None) -> dict[str, dict[str, int]]:
    ...
    archive_auto = {
        "considered": 0,
        "processed": 0,
        "auto_apply": 0,
        "auto_apply_sampled": 0,
        "manual_review": 0,
        "confirmed": 0,
        "pending_review": 0,
        "failed": 0,
        "moved": 0,
        "risk_events": 0,
    }
    if keep_root and auto_archive_limit > 0 and archive_client is not None:
        archive_auto = auto_archive_candidates(
            session=session,
            archive_root=keep_root,
            client=archive_client,
            limit=auto_archive_limit,
        )
    ...
    return {
        ...,
        "archive_auto": archive_auto,
    }
```

- [x] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_safe_workflow_service.py -q -k batch_auto_archive`
Expected: PASS with workflow summaries reporting batch archive execution.

- [x] **Step 5: Commit**

```bash
git add tests/test_safe_workflow_service.py src/pims_v1/services/safe_workflow_service.py
git commit -m "feat: add batch auto archive to workflow"
```

## Task 3: Surface Batch Results In The CLI

**Files:**

- Modify: `src/pims_v1/cli.py`
- Modify: `tests/test_cli.py`

- [x] **Step 1: Write the failing CLI workflow test**

```python
def test_run_safe_workflow_cli_reports_batch_auto_archive_summary(tmp_path, capsys, monkeypatch):
    database_url, archive_root = build_workflow_auto_archive_fixture(tmp_path)

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def chat(self, messages):
            return (
                '{"title":"雪琪SAMA 透明女仆 [43P4V234MB]","category":"雪琪SAMA",'
                '"archive_path":"","plan_summary":"保持人物目录结构","risk_flags":[],'
                '"tags":[],"r18_label":false,"r18_confidence":0.0,"r18_reason":"","confidence":0.93}'
            )

    monkeypatch.setattr("pims_v1.cli.DeepSeekClient", FakeClient)
    monkeypatch.setattr(
        "sys.argv",
        [
            "pims",
            "run-safe-workflow",
            "--keep-root",
            str(archive_root),
            "--cache-root",
            str(tmp_path / ".cache"),
            "--auto-archive-limit",
            "5",
            "--database-url",
            database_url,
        ],
    )

    assert main() == 0
    output = capsys.readouterr().out
    assert "archive_auto.processed=1" in output
    assert "archive_auto.auto_apply=1" in output
```

- [x] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_cli.py -q -k workflow_cli_reports_batch_auto_archive`
Expected: FAIL because the CLI neither accepts the flag nor prints the new summary.

- [x] **Step 3: Add CLI flag handling and client injection**

```python
safe_workflow.add_argument("--auto-archive-limit", type=int, default=20)
```

```python
archive_client = None
if keep_root and auto_archive_limit > 0:
    archive_client = DeepSeekClient(
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
        model=settings.deepseek_model,
        reasoning_effort=settings.deepseek_reasoning_effort,
        thinking_enabled=settings.deepseek_thinking_enabled,
    )
summary = run_safe_workflow(
    ...,
    auto_archive_limit=auto_archive_limit,
    archive_client=archive_client,
)
```

- [x] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_cli.py -q -k workflow_cli_reports_batch_auto_archive`
Expected: PASS with `archive_auto.*` keys printed in the workflow output.

- [x] **Step 5: Commit**

```bash
git add tests/test_cli.py src/pims_v1/cli.py
git commit -m "feat: expose batch auto archive in workflow cli"
```

## Task 4: Full Verification

**Files:**

- Modify: `docs/superpowers/plans/2026-06-13-dual-engine-workflow-batch-execution.md`

- [x] **Step 1: Run targeted verification**

Run: `python -m pytest tests/test_archive_decision_service.py tests/test_safe_workflow_service.py tests/test_cli.py -q`
Expected: PASS with batch auto-archive covered at service, workflow, and CLI levels.

- [x] **Step 2: Run the full suite**

Run: `python -m pytest -q`
Expected: PASS with no regressions introduced.

- [x] **Step 3: Mark completed tasks in this plan**

Update the checkboxes in this plan file to reflect the executed work.

- [x] **Step 4: Commit**

```bash
git add docs/superpowers/plans/2026-06-13-dual-engine-workflow-batch-execution.md
git commit -m "docs: mark workflow batch execution plan progress"
```
