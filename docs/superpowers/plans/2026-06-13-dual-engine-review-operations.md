# Dual-Engine Review Operations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the dual-engine backend into the review surface by adding anomaly, sampling, overview, execution ledger, rollback, and review-triggered auto-archive APIs, then expose those capabilities in the existing review UI.

**Architecture:** This slice keeps the current FastAPI app and single-file review UI, but pivots the review experience from AI-suggestion approval to operation monitoring. It builds service functions over the new archive decision tables, exposes them through review routes, adds rollback behavior to the decision service, and updates the review UI/JS to fetch and present the new data.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy ORM, SQLite schema hydration via `ensure_database_schema`, inline HTML/CSS/JS review UI, pytest

---

## File Structure

**Modify**

- `src/pims_v1/services/archive_decision_service.py`
  Add rollback behavior and richer result shapes for review operations.
- `src/pims_v1/services/review_service.py`
  Add overview, anomaly, sampling, execution-ledger, and rollback payload functions.
- `src/pims_v1/api/review.py`
  Add review routes for auto-archive, anomalies, overview, ledger, and rollback.
- `src/pims_v1/api/review_ui.py`
  Add anomaly-centric panels and JS data loading/actions.
- `tests/test_archive_decision_service.py`
  Add rollback coverage.
- `tests/test_review_service.py`
  Add service-level overview/anomaly/ledger coverage.
- `tests/test_review_routes.py`
  Add route coverage for auto-archive, overview, anomaly, ledger, and rollback.

## Task 1: Add Rollback Support To The Archive Decision Service

**Files:**

- Modify: `src/pims_v1/services/archive_decision_service.py`
- Modify: `tests/test_archive_decision_service.py`

- [x] **Step 1: Write the failing rollback test**

```python
def test_rollback_archive_execution_restores_original_asset_path(tmp_path):
    session, candidate_id, archive_root = build_candidate_fixture(tmp_path)
    client = StaticAIPlanClient({...})
    result = auto_archive_candidate(
        session=session,
        candidate_id=candidate_id,
        archive_root=str(archive_root),
        client=client,
    )

    execution_id = session.query(ArchiveExecutionRecord.id).one()[0]
    rollback = rollback_archive_execution(session=session, execution_id=execution_id, operator="tester")

    asset_row = session.query(Asset).one()
    assert rollback["status"] == "rolled_back"
    assert asset_row.current_path.endswith("001.jpg")
    assert "pc" in asset_row.current_path
```

- [x] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_archive_decision_service.py -q -k rollback`
Expected: FAIL because rollback behavior does not exist yet.

- [x] **Step 3: Write the minimal rollback implementation**

```python
def rollback_archive_execution(*, session: Session, execution_id: int, operator: str | None = None) -> dict[str, object]:
    execution = session.get(ArchiveExecutionRecord, execution_id)
    if execution is None:
        raise ValueError(f"Archive execution record not found: {execution_id}")
    if execution.status != "done":
        raise ValueError(f"Archive execution is not completed: {execution.status}")

    asset = session.query(Asset).filter(Asset.current_path == execution.target_path).one_or_none()
    if asset is None:
        raise ValueError(f"Archived asset not found for execution: {execution_id}")

    source = Path(execution.target_path or "")
    destination = Path(execution.source_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    source.rename(destination)
    asset.current_path = str(destination)
    asset.status = "normal"
    execution.status = "rolled_back"
    session.add(
        ArchiveRollbackRecord(
            execution_record_id=execution.id,
            rollback_source_path=str(source),
            rollback_target_path=str(destination),
            status="done",
            operator=operator,
        )
    )
    session.commit()
    return {"execution_id": execution.id, "status": execution.status, "asset_id": asset.id}
```

- [x] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_archive_decision_service.py -q -k rollback`
Expected: PASS with archived files restored to their original paths.

- [x] **Step 5: Commit**

```bash
git add src/pims_v1/services/archive_decision_service.py tests/test_archive_decision_service.py
git commit -m "feat: add archive rollback support"
```

## Task 2: Add Review Service Payloads For Overview, Anomalies, Sampling, And Ledger

**Files:**

- Modify: `src/pims_v1/services/review_service.py`
- Modify: `tests/test_review_service.py`

- [x] **Step 1: Write the failing review service tests**

```python
def test_list_archive_anomalies_returns_risk_events_and_candidate_context(tmp_path):
    session = make_session(tmp_path)
    planning = seed_planning_record(...)
    session.add(ArchiveRiskEvent(planning_record_id=planning.id, event_type="r18_suspected", severity="warning"))
    session.commit()

    items = list_archive_anomalies(session=session, limit=10)

    assert items[0]["event_type"] == "r18_suspected"
    assert items[0]["candidate"]["source_root"].endswith("R18 [85P1V1.32G]")


def test_list_archive_execution_ledger_returns_execution_and_rollback_state(tmp_path):
    session = make_session(tmp_path)
    planning = seed_planning_record(...)
    session.add(ArchiveExecutionRecord(..., status="done"))
    session.commit()

    items = list_archive_execution_ledger(session=session, limit=10)

    assert items[0]["status"] == "done"
    assert items[0]["decision_type"] == "auto_apply"


def test_get_archive_review_overview_summarizes_auto_archive_state(tmp_path):
    session = make_session(tmp_path)
    planning = seed_planning_record(...)
    session.add(ArchiveExecutionRecord(..., status="done"))
    session.commit()

    summary = get_archive_review_overview(session=session)

    assert summary["planning"]["auto_apply"] == 1
    assert summary["executions"]["done"] == 1
```

- [x] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_review_service.py -q -k archive_`
Expected: FAIL because these review service helpers do not exist yet.

- [x] **Step 3: Write the minimal service helpers**

```python
def get_archive_review_overview(session: Session) -> dict[str, dict[str, int]]:
    planning_rows = session.query(ArchivePlanningRecord.decision_type, func.count(ArchivePlanningRecord.id)).group_by(ArchivePlanningRecord.decision_type).all()
    execution_rows = session.query(ArchiveExecutionRecord.status, func.count(ArchiveExecutionRecord.id)).group_by(ArchiveExecutionRecord.status).all()
    return {
        "planning": {row[0]: row[1] for row in planning_rows},
        "executions": {row[0]: row[1] for row in execution_rows},
        "risk_events": session.query(ArchiveRiskEvent).count(),
    }
```

```python
def list_archive_anomalies(session: Session, limit: int = 20) -> list[dict]:
    events = session.query(ArchiveRiskEvent).order_by(ArchiveRiskEvent.id.desc()).limit(limit).all()
    return [...]
```

```python
def list_archive_execution_ledger(session: Session, limit: int = 20) -> list[dict]:
    rows = session.query(ArchiveExecutionRecord, ArchivePlanningRecord).join(
        ArchivePlanningRecord, ArchivePlanningRecord.id == ArchiveExecutionRecord.planning_record_id
    ).order_by(ArchiveExecutionRecord.id.desc()).limit(limit).all()
    return [...]
```

- [x] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_review_service.py -q -k archive_`
Expected: PASS with overview, anomaly, and ledger payloads present.

- [x] **Step 5: Commit**

```bash
git add src/pims_v1/services/review_service.py tests/test_review_service.py
git commit -m "feat: add archive review service payloads"
```

## Task 3: Add Review API Endpoints For Auto-Archive, Overview, Anomalies, Ledger, And Rollback

**Files:**

- Modify: `src/pims_v1/api/review.py`
- Modify: `tests/test_review_routes.py`

- [x] **Step 1: Write the failing route tests**

```python
def test_review_auto_archive_series_api_executes_dual_engine_archive(tmp_path, monkeypatch):
    ...
    response = client.post(f"/review/series/{candidate_id}/auto-archive")
    assert response.status_code == 200
    assert response.json()["decision_type"] == "auto_apply"


def test_review_archive_overview_api_returns_planning_and_execution_counts(tmp_path):
    ...
    response = client.get("/review/archive/overview")
    assert response.status_code == 200
    assert "planning" in response.json()


def test_review_archive_anomalies_api_returns_risk_events(tmp_path):
    ...
    response = client.get("/review/archive/anomalies")
    assert response.status_code == 200
    assert response.json()["items"][0]["event_type"] == "r18_suspected"


def test_review_archive_rollback_api_restores_file(tmp_path):
    ...
    response = client.post(f"/review/archive/executions/{execution_id}/rollback")
    assert response.status_code == 200
    assert response.json()["status"] == "rolled_back"
```

- [x] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_review_routes.py -q -k "archive or auto_archive"`
Expected: FAIL because the routes do not exist yet.

- [x] **Step 3: Write the minimal route layer**

```python
@router.get("/archive/overview")
def archive_review_overview(session: Session = Depends(get_session)) -> dict:
    return get_archive_review_overview(session=session)


@router.get("/archive/anomalies")
def archive_anomalies(limit: int = 20, session: Session = Depends(get_session)) -> dict[str, list]:
    return {"items": list_archive_anomalies(session=session, limit=limit)}


@router.get("/archive/executions")
def archive_execution_ledger(limit: int = 20, session: Session = Depends(get_session)) -> dict[str, list]:
    return {"items": list_archive_execution_ledger(session=session, limit=limit)}


@router.post("/archive/executions/{execution_id}/rollback")
def rollback_archive_execution_route(...):
    return rollback_archive_execution(...)


@router.post("/series/{candidate_id}/auto-archive")
def auto_archive_series_route(...):
    client = DeepSeekClient(...)
    return auto_archive_candidate(...)
```

- [x] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_review_routes.py -q -k "archive or auto_archive"`
Expected: PASS with the new review APIs reachable and functional.

- [x] **Step 5: Commit**

```bash
git add src/pims_v1/api/review.py tests/test_review_routes.py
git commit -m "feat: add archive review api routes"
```

## Task 4: Update The Review UI Into An Anomaly And Ledger Console

**Files:**

- Modify: `src/pims_v1/api/review_ui.py`
- Modify: `tests/test_review_routes.py`

- [x] **Step 1: Write the failing UI assertions**

```python
def test_review_ui_includes_archive_anomaly_and_ledger_views():
    client = TestClient(app)
    response = client.get("/review-ui")

    assert response.status_code == 200
    assert 'data-view-target="archive"' in response.text
    assert 'data-view-target="anomalies"' in response.text
    assert 'data-view-target="ledger"' in response.text
    assert "loadArchiveOverview" in response.text
    assert "rollbackExecution" in response.text
```

- [x] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_review_routes.py -q -k "anomaly_and_ledger_views"`
Expected: FAIL because the review UI does not expose the new archive console yet.

- [x] **Step 3: Update the inline review UI**

```html
<button class="view-tab" data-view-target="archive" type="button">自动归档概览<span>看自动执行、抽检和失败统计</span></button>
<button class="view-tab" data-view-target="anomalies" type="button">异常队列<span>只看需要人工介入的高风险项目</span></button>
<button class="view-tab" data-view-target="ledger" type="button">执行账本<span>查看自动移动记录并支持回滚</span></button>
```

```javascript
const loadArchiveOverview = async () => {
  const data = await jsonFetch("/review/archive/overview");
  renderArchiveOverview(data);
};

const loadArchiveAnomalies = async () => {
  const data = await jsonFetch("/review/archive/anomalies?limit=30");
  renderArchiveAnomalies(data.items);
};

const loadArchiveLedger = async () => {
  const data = await jsonFetch("/review/archive/executions?limit=30");
  renderArchiveLedger(data.items);
};

const rollbackExecution = async (executionId) => {
  await jsonFetch(`/review/archive/executions/${executionId}/rollback`, {method: "POST", auth: true});
  await Promise.all([loadArchiveOverview(), loadArchiveAnomalies(), loadArchiveLedger(), loadSeries()]);
};
```

- [x] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_review_routes.py -q -k "anomaly_and_ledger_views"`
Expected: PASS with the new archive console markers and JS functions present.

- [x] **Step 5: Commit**

```bash
git add src/pims_v1/api/review_ui.py tests/test_review_routes.py
git commit -m "feat: redesign review ui for archive operations"
```

## Task 5: Full Verification

**Files:**

- Modify: `docs/superpowers/plans/2026-06-13-dual-engine-review-operations.md`

- [x] **Step 1: Run targeted verification**

Run: `python -m pytest tests/test_archive_decision_service.py tests/test_review_service.py tests/test_review_routes.py -q`
Expected: PASS with rollback, archive APIs, and updated review UI covered.

- [x] **Step 2: Run the full suite**

Run: `python -m pytest -q`
Expected: PASS with no regressions introduced.

- [x] **Step 3: Mark completed tasks in this plan**

Update the checkboxes in this plan file to reflect the executed steps.

- [x] **Step 4: Commit**

```bash
git add docs/superpowers/plans/2026-06-13-dual-engine-review-operations.md
git commit -m "docs: mark archive operations plan progress"
```
