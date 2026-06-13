# R18 Visual Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a dual-mode R18 visual review pipeline with local coarse screening, persistent moderation records, workflow integration, manual CLI/API reruns, and minimal review UI visibility.

**Architecture:** This slice adds a new moderation subsystem beside the current AI naming path. Series candidates are sampled, images are screened by a local provider selected through a provider interface, summaries are persisted and exposed in review payloads, and auto-archive consults the latest moderation result before allowing aggressive execution.

**Tech Stack:** Python 3.11+, SQLAlchemy ORM, FastAPI, argparse CLI, Pillow, pytest

---

## File Structure

**Create**

- `src/pims_v1/models/series_moderation.py`
  Owns moderation run and sample tables.
- `src/pims_v1/services/visual_moderation_service.py`
  Owns provider protocol, provider selection, heuristic screening, and run aggregation.
- `src/pims_v1/services/series_moderation_service.py`
  Owns candidate sampling, run persistence, suggestion sync, and summary retrieval.
- `tests/test_visual_moderation_service.py`
  Covers provider selection, heuristic scoring shape, and series summary aggregation.
- `tests/test_series_moderation_service.py`
  Covers candidate sampling, run persistence, and suggestion synchronization.

**Modify**

- `src/pims_v1/models/__init__.py`
  Export new moderation models.
- `src/pims_v1/db.py`
  Create moderation tables and indexes safely for existing databases.
- `src/pims_v1/config.py`
  Add provider and threshold settings.
- `src/pims_v1/services/review_service.py`
  Add latest moderation payload to review candidate responses.
- `src/pims_v1/services/archive_decision_service.py`
  Merge latest visual moderation risk into auto-archive decisions.
- `src/pims_v1/services/safe_workflow_service.py`
  Add optional workflow-triggered R18 review and summary section.
- `src/pims_v1/api/review.py`
  Add manual review rerun endpoint.
- `src/pims_v1/api/review_ui.py`
  Add minimal visual moderation display and rerun action.
- `src/pims_v1/cli.py`
  Add manual scan command and workflow flag handling.
- `tests/test_schema.py`
  Cover moderation tables.
- `tests/test_review_service.py`
  Cover moderation payload in review candidates.
- `tests/test_archive_decision_service.py`
  Cover visual moderation risk blocking auto-archive.
- `tests/test_safe_workflow_service.py`
  Cover workflow-triggered R18 review summary.
- `tests/test_review_routes.py`
  Cover manual rerun API and UI markers.
- `tests/test_cli.py`
  Cover manual CLI scan and workflow R18 summary.

## Task 1: Add Moderation Schema And Settings

**Files:**

- Create: `src/pims_v1/models/series_moderation.py`
- Modify: `src/pims_v1/models/__init__.py`
- Modify: `src/pims_v1/db.py`
- Modify: `src/pims_v1/config.py`
- Modify: `tests/test_schema.py`

- [ ] **Step 1: Write the failing schema tests**

```python
def test_core_tables_exist(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'schema.db'}", future=True)
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    inspector = inspect(engine)

    table_names = set(inspector.get_table_names())

    assert "series_moderation_runs" in table_names
    assert "series_moderation_samples" in table_names


def test_series_moderation_runs_have_candidate_index(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'schema.db'}", future=True)

    ensure_database_schema(engine)
    inspector = inspect(engine)
    indexes = inspector.get_indexes("series_moderation_runs")

    assert any(index["name"] == "ix_series_moderation_runs_candidate_created_at" for index in indexes)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_schema.py -q -k moderation`
Expected: FAIL because moderation tables and indexes do not exist yet.

- [ ] **Step 3: Write the minimal models, schema hydration, and settings**

```python
class SeriesModerationRun(Base):
    __tablename__ = "series_moderation_runs"
    __table_args__ = (
        Index("ix_series_moderation_runs_candidate_created_at", "candidate_id", "created_at"),
    )
```

```python
class Settings(BaseSettings):
    ...
    r18_provider: str = "auto"
    r18_sample_limit: int = 7
    r18_high_threshold: float = 0.82
    r18_review_threshold: float = 0.55
    r18_scan_limit: int = 0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_schema.py -q -k moderation`
Expected: PASS with moderation tables and index present.

- [ ] **Step 5: Commit**

```bash
git add tests/test_schema.py src/pims_v1/models/series_moderation.py src/pims_v1/models/__init__.py src/pims_v1/db.py src/pims_v1/config.py
git commit -m "feat: add series moderation schema"
```

## Task 2: Add Local Moderation Provider And Series Sampling

**Files:**

- Create: `src/pims_v1/services/visual_moderation_service.py`
- Create: `src/pims_v1/services/series_moderation_service.py`
- Create: `tests/test_visual_moderation_service.py`
- Create: `tests/test_series_moderation_service.py`

- [ ] **Step 1: Write the failing service tests**

```python
def test_select_candidate_image_samples_balances_front_middle_and_tail(tmp_path):
    session, candidate_id = build_candidate_with_images(tmp_path, image_count=10)

    samples = select_candidate_image_samples(session=session, candidate_id=candidate_id, limit=7)

    assert len(samples) == 7
    assert samples[0].asset_id != samples[-1].asset_id
```

```python
def test_review_series_r18_marks_candidate_when_local_provider_returns_high_score(tmp_path):
    session, candidate_id = build_candidate_with_images(tmp_path, image_count=2)
    provider = StaticVisualModerationClient(
        [
            {"label": "safe", "score": 0.18, "reason": "low skin ratio"},
            {"label": "nsfw_suspected", "score": 0.91, "reason": "high skin ratio"},
        ]
    )

    result = review_series_r18(
        session=session,
        candidate_id=candidate_id,
        provider=provider,
        mode="manual",
        sample_limit=7,
        high_threshold=0.82,
        review_threshold=0.55,
    )

    assert result["r18_label"] is True
    assert result["positive_samples"] == 1
    assert "visual_r18_suspected" in result["risk_flags"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_visual_moderation_service.py tests/test_series_moderation_service.py -q`
Expected: FAIL because the provider and moderation services do not exist yet.

- [ ] **Step 3: Write the minimal provider and sampling services**

```python
class HeuristicVisualModerationClient:
    provider_name = "heuristic"

    def moderate_image(self, path: Path) -> dict[str, object]:
        with Image.open(path) as image:
            rgb = image.convert("RGB")
            score = _estimate_skin_ratio_score(rgb)
        return {
            "label": "nsfw_suspected" if score >= 0.55 else "safe",
            "score": score,
            "reason": f"skin_ratio={score:.3f}",
            "provider": self.provider_name,
        }
```

```python
def review_series_r18(...):
    sampled_assets = select_candidate_image_samples(...)
    run = SeriesModerationRun(...)
    ...
    return {
        "candidate_id": candidate_id,
        "r18_label": max_score >= high_threshold,
        "r18_confidence": max_score,
        "risk_flags": risk_flags,
        "sample_count": len(sampled_assets),
        "positive_samples": positive_samples,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_visual_moderation_service.py tests/test_series_moderation_service.py -q`
Expected: PASS with stable sampling and persisted local moderation summaries.

- [ ] **Step 5: Commit**

```bash
git add tests/test_visual_moderation_service.py tests/test_series_moderation_service.py src/pims_v1/services/visual_moderation_service.py src/pims_v1/services/series_moderation_service.py
git commit -m "feat: add local visual moderation pipeline"
```

## Task 3: Feed Moderation Into Review Payloads And Archive Decisions

**Files:**

- Modify: `src/pims_v1/services/review_service.py`
- Modify: `src/pims_v1/services/archive_decision_service.py`
- Modify: `tests/test_review_service.py`
- Modify: `tests/test_archive_decision_service.py`

- [ ] **Step 1: Write the failing integration tests**

```python
def test_list_series_review_candidates_includes_latest_moderation_summary(tmp_path):
    session, candidate_id = build_review_candidate_fixture(tmp_path)
    seed_completed_moderation_run(session=session, candidate_id=candidate_id, r18_label=True)

    candidates = list_series_review_candidates(session=session, limit=10)

    assert candidates[0]["moderation"]["r18_label"] is True
    assert candidates[0]["moderation"]["provider"] == "heuristic"
```

```python
def test_auto_archive_candidate_blocks_visual_r18_risk(tmp_path):
    session, candidate_id, archive_root = build_candidate_fixture(tmp_path)
    seed_completed_moderation_run(session=session, candidate_id=candidate_id, r18_label=True)
    client = StaticAIPlanClient({... clean AI plan ...})

    result = auto_archive_candidate(
        session=session,
        candidate_id=candidate_id,
        archive_root=str(archive_root),
        client=client,
    )

    assert result["decision_type"] == "manual_review"
    assert result["status"] == "pending_review"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_review_service.py tests/test_archive_decision_service.py -q -k moderation`
Expected: FAIL because review payloads and archive decisions do not consult moderation yet.

- [ ] **Step 3: Wire moderation into review and decision services**

```python
def latest_series_moderation_summary(session: Session, candidate_id: int) -> dict | None:
    ...
```

```python
if moderation_summary and moderation_summary["r18_label"]:
    merged_risk_flags.add("visual_r18_suspected")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_review_service.py tests/test_archive_decision_service.py -q -k moderation`
Expected: PASS with review payloads exposing moderation and auto-archive blocked by visual risk.

- [ ] **Step 5: Commit**

```bash
git add tests/test_review_service.py tests/test_archive_decision_service.py src/pims_v1/services/review_service.py src/pims_v1/services/archive_decision_service.py
git commit -m "feat: merge visual moderation into review and archive decisions"
```

## Task 4: Add Workflow, CLI, Review API, And Minimal UI Wiring

**Files:**

- Modify: `src/pims_v1/services/safe_workflow_service.py`
- Modify: `src/pims_v1/api/review.py`
- Modify: `src/pims_v1/api/review_ui.py`
- Modify: `src/pims_v1/cli.py`
- Modify: `tests/test_safe_workflow_service.py`
- Modify: `tests/test_review_routes.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write the failing workflow, API, and CLI tests**

```python
def test_run_safe_workflow_runs_r18_scan_before_auto_archive(tmp_path):
    ...
    summary = run_safe_workflow(..., r18_scan_limit=5)
    assert summary["r18_scan"]["processed"] == 1
```

```python
def test_review_series_scan_r18_api_persists_latest_moderation(tmp_path):
    ...
    response = client.post(f"/review/series/{candidate_id}/scan-r18")
    assert response.status_code == 200
    assert response.json()["r18_label"] is True
```

```python
def test_run_safe_workflow_cli_reports_r18_scan_summary(tmp_path, capsys, monkeypatch):
    ...
    assert "r18_scan.processed=1" in output
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_safe_workflow_service.py tests/test_review_routes.py tests/test_cli.py -q -k r18`
Expected: FAIL because these entrypoints do not exist yet.

- [ ] **Step 3: Add workflow, API, CLI, and UI integration**

```python
safe_workflow.add_argument("--r18-scan-limit", type=int, default=settings.r18_scan_limit)
scan_r18 = subparsers.add_parser("scan-series-r18")
```

```python
@router.post("/series/{candidate_id}/scan-r18")
def review_series_scan_r18(...):
    return review_series_r18(...)
```

```javascript
node.querySelector('[data-action="scan-r18"]').addEventListener("click", ...)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_safe_workflow_service.py tests/test_review_routes.py tests/test_cli.py -q -k r18`
Expected: PASS with dual-mode visual review reachable from workflow, API, CLI, and visible in the review UI.

- [ ] **Step 5: Commit**

```bash
git add tests/test_safe_workflow_service.py tests/test_review_routes.py tests/test_cli.py src/pims_v1/services/safe_workflow_service.py src/pims_v1/api/review.py src/pims_v1/api/review_ui.py src/pims_v1/cli.py
git commit -m "feat: expose r18 visual review controls"
```

## Task 5: Full Verification

**Files:**

- Modify: `docs/superpowers/plans/2026-06-13-r18-visual-review.md`

- [ ] **Step 1: Run targeted verification**

Run: `python -m pytest tests/test_schema.py tests/test_visual_moderation_service.py tests/test_series_moderation_service.py tests/test_review_service.py tests/test_archive_decision_service.py tests/test_safe_workflow_service.py tests/test_review_routes.py tests/test_cli.py -q`
Expected: PASS with the new moderation slice covered end to end.

- [ ] **Step 2: Run the full suite**

Run: `python -m pytest -q`
Expected: PASS with no regressions introduced.

- [ ] **Step 3: Mark completed tasks in this plan**

Update the checkboxes in this plan file to reflect the executed work.

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/plans/2026-06-13-r18-visual-review.md
git commit -m "docs: mark r18 visual review plan progress"
```
