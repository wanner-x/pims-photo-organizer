# Dual-Engine Backend Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first runnable backend slice of the dual-engine archive architecture with deterministic rule planning, score-based decision merge, durable planning/execution records, and a CLI entrypoint that can auto-archive one series candidate immediately.

**Architecture:** This slice introduces new decision-ledger models and a backend-only planning pipeline without changing the review UI yet. The implementation reuses the current candidate and asset models, adds a deterministic rule planner beside the existing AI planner, merges both outputs into a final decision, and executes ordinary archive moves while recording every move for later rollback work.

**Tech Stack:** Python 3.11+, SQLAlchemy ORM, SQLite schema hydration via `ensure_database_schema`, argparse CLI, pytest

---

## File Structure

**Create**

- `src/pims_v1/models/archive_decision.py`
  Owns planning, execution, rollback, and risk-event tables.
- `src/pims_v1/services/archive_rule_planner.py`
  Owns deterministic parsing and rule-plan generation.
- `src/pims_v1/services/archive_decision_service.py`
  Owns score merge, decision selection, record creation, and immediate execution.
- `tests/test_archive_rule_planner.py`
  Covers deterministic archive planning on named real-world path patterns.
- `tests/test_archive_decision_service.py`
  Covers score merge, blocking, auto-apply, and execution ledger persistence.

**Modify**

- `src/pims_v1/models/__init__.py`
  Export new archive decision models so metadata creation includes them.
- `src/pims_v1/db.py`
  Ensure legacy databases receive the new tables and indexes safely.
- `src/pims_v1/cli.py`
  Add a new command to auto-archive a single candidate with dual-engine planning.
- `tests/test_schema.py`
  Assert new tables and indexes exist.
- `tests/test_cli.py`
  Cover the new CLI command.
- `src/pims_v1/services/ai_naming_service.py`
  Export a reusable non-persisting AI plan helper so the new decision service can call AI planning without mutating old review-oriented suggestion rows.

## Task 1: Add Decision Ledger Models

**Files:**

- Create: `src/pims_v1/models/archive_decision.py`
- Modify: `src/pims_v1/models/__init__.py`
- Modify: `src/pims_v1/db.py`
- Test: `tests/test_schema.py`

- [x] **Step 1: Write the failing schema tests**

```python
def test_core_tables_exist(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'schema.db'}", future=True)
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    inspector = inspect(engine)

    table_names = set(inspector.get_table_names())

    assert "archive_planning_records" in table_names
    assert "archive_execution_records" in table_names
    assert "archive_rollback_records" in table_names
    assert "archive_risk_events" in table_names


def test_archive_planning_records_have_decision_index(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'schema.db'}", future=True)

    ensure_database_schema(engine)
    inspector = inspect(engine)
    indexes = inspector.get_indexes("archive_planning_records")

    assert any(
        index["name"] == "ix_archive_planning_records_decision_type_created_at"
        for index in indexes
    )
```

- [x] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_schema.py -q`
Expected: FAIL because the archive decision tables and indexes do not exist yet.

- [x] **Step 3: Write the model and schema hydration code**

```python
class ArchivePlanningRecord(Base):
    __tablename__ = "archive_planning_records"
    __table_args__ = (
        Index("ix_archive_planning_records_decision_type_created_at", "decision_type", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("series_candidates.id"))
    source_root: Mapped[str] = mapped_column(String(2048))
    rule_plan_json: Mapped[str] = mapped_column(Text)
    ai_plan_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    final_plan_json: Mapped[str] = mapped_column(Text)
    decision_type: Mapped[str] = mapped_column(String(50))
    rule_score: Mapped[float] = mapped_column(Float, default=0.0)
    ai_score: Mapped[float] = mapped_column(Float, default=0.0)
    risk_score: Mapped[float] = mapped_column(Float, default=0.0)
    decision_reason: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
```

```python
from pims_v1.models.archive_decision import (
    ArchiveExecutionRecord,
    ArchivePlanningRecord,
    ArchiveRiskEvent,
    ArchiveRollbackRecord,
)
```

```python
connection.exec_driver_sql(
    """
    CREATE INDEX IF NOT EXISTS ix_archive_planning_records_decision_type_created_at
    ON archive_planning_records (decision_type, created_at)
    """
)
```

- [x] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_schema.py -q`
Expected: PASS with the new tables and decision index present.

- [x] **Step 5: Commit**

```bash
git add tests/test_schema.py src/pims_v1/models/archive_decision.py src/pims_v1/models/__init__.py src/pims_v1/db.py
git commit -m "feat: add archive decision ledger models"
```

## Task 2: Build Deterministic Rule Planner

**Files:**

- Create: `src/pims_v1/services/archive_rule_planner.py`
- Test: `tests/test_archive_rule_planner.py`

- [x] **Step 1: Write the failing rule planner tests**

```python
def test_plan_archive_for_named_person_series_preserves_parent_and_metadata():
    plan = plan_archive_from_source_root(
        "D:/图册/雪琪SAMA/雪琪SAMA 透明女仆 [43P4V234MB]"
    )

    assert plan["category"] == "雪琪SAMA"
    assert plan["title"] == "雪琪SAMA 透明女仆 [43P4V234MB]"
    assert plan["confidence"] >= 0.9
    assert "parent_directory_match" in plan["matched_rules"]


def test_plan_archive_for_project_series_preserves_project_root():
    plan = plan_archive_from_source_root(
        "D:/图册/紧急企划/【紧急企划】-【VOL.001】-【樱樱樱可】-【JK黑】-【45P1V-858M】"
    )

    assert plan["category"] == "紧急企划"
    assert plan["title"] == "【紧急企划】-【VOL.001】-【樱樱樱可】-【JK黑】-【45P1V-858M】"
    assert plan["metadata"]["has_volume"] is True


def test_plan_archive_for_imiss_series_uses_brand_bucket_when_parent_is_generic():
    plan = plan_archive_from_source_root(
        "D:/图册/[IMISS爱蜜社] 2025.08.27 VOL.800 许诺Sabrina [86+1P]"
    )

    assert plan["category"] == "IMISS爱蜜社"
    assert plan["title"] == "[IMISS爱蜜社] 2025.08.27 VOL.800 许诺Sabrina [86+1P]"
    assert plan["metadata"]["has_metadata_suffix"] is True
```

- [x] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_archive_rule_planner.py -q`
Expected: FAIL because the planner module and helper do not exist yet.

- [x] **Step 3: Write the minimal rule planner**

```python
GENERIC_SOURCE_PARTS = {
    "archive",
    "d:",
    "e:",
    "library",
    "nas",
    "pc",
    "personal_folder",
    "图册",
    "图册整理",
    "本地图册",
    "网络写真集",
}


def plan_archive_from_source_root(source_root: str) -> dict[str, object]:
    normalized = source_root.replace("\\", "/").strip("/")
    parts = [part for part in normalized.split("/") if part]
    folder_name = parts[-1]
    parent_name = parts[-2] if len(parts) >= 2 else ""
    category = _category_from_parent_or_title(parent_name=parent_name, folder_name=folder_name)
    matched_rules = _matched_rules(parent_name=parent_name, folder_name=folder_name, category=category)
    metadata = {
        "has_volume": "VOL." in folder_name.upper(),
        "has_metadata_suffix": bool(METADATA_PATTERN.search(folder_name)),
        "source_parts": parts,
    }
    confidence = 0.95 if "parent_directory_match" in matched_rules else 0.82
    return {
        "category": category,
        "title": folder_name,
        "archive_path": None,
        "confidence": confidence,
        "matched_rules": matched_rules,
        "metadata": metadata,
        "risk_flags": [],
        "decision_reason": f"rule planner selected category={category} title={folder_name}",
    }
```

- [x] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_archive_rule_planner.py -q`
Expected: PASS with the three named archive patterns preserved.

- [x] **Step 5: Commit**

```bash
git add tests/test_archive_rule_planner.py src/pims_v1/services/archive_rule_planner.py
git commit -m "feat: add deterministic archive rule planner"
```

## Task 3: Add Decision Merge And Auto-Archive Service

**Files:**

- Modify: `src/pims_v1/services/ai_naming_service.py`
- Create: `src/pims_v1/services/archive_decision_service.py`
- Test: `tests/test_archive_decision_service.py`

- [x] **Step 1: Write the failing decision-service tests**

```python
def test_auto_archive_candidate_applies_when_rule_and_ai_agree(tmp_path):
    session, candidate_id, archive_root = build_candidate_fixture(tmp_path)
    client = StaticAIPlanClient(
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
    )

    result = auto_archive_candidate(
        session=session,
        candidate_id=candidate_id,
        archive_root=str(archive_root),
        client=client,
    )

    assert result["decision_type"] == "auto_apply"
    assert result["status"] == "confirmed"
    assert result["moved"] == 1
    assert result["risk_events"] == 0
```

```python
def test_auto_archive_candidate_blocks_r18_suspicion(tmp_path):
    session, candidate_id, archive_root = build_candidate_fixture(
        tmp_path,
        source_root="D:/图册/紧急企划/紧急企划 - 见希-JK-R18 [85P1V1.32G]",
    )
    client = StaticAIPlanClient(
        {
            "title": "紧急企划 - 见希-JK-R18 [85P1V1.32G]",
            "category": "紧急企划",
            "archive_path": "",
            "plan_summary": "疑似成人内容",
            "risk_flags": ["r18_suspected"],
            "tags": ["R18"],
            "r18_label": True,
            "r18_confidence": 0.91,
            "r18_reason": "目录名含R18",
            "confidence": 0.9,
        }
    )

    result = auto_archive_candidate(
        session=session,
        candidate_id=candidate_id,
        archive_root=str(archive_root),
        client=client,
    )

    assert result["decision_type"] == "manual_review"
    assert result["moved"] == 0
    assert result["status"] == "pending_review"
```

- [x] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_archive_decision_service.py -q`
Expected: FAIL because the decision service and reusable AI plan helper do not exist yet.

- [x] **Step 3: Write the minimal AI-plan helper and decision service**

```python
def generate_ai_archive_plan(
    *,
    source_root: str,
    file_names: list[str],
    archive_root: str | None,
    existing_archive_dirs: list[str],
    client: NamingClient,
) -> dict[str, str | float | list[str] | bool]:
    prompt = build_series_organization_prompt(
        source_root=source_root,
        file_names=file_names,
        archive_root=archive_root,
        existing_archive_dirs=existing_archive_dirs,
    )
    raw_response = client.chat([{"role": "user", "content": prompt}])
    return _parse_organization_response(raw_response) | {"raw_response": raw_response}
```

```python
def auto_archive_candidate(*, session: Session, candidate_id: int, archive_root: str, client: NamingClient) -> dict[str, object]:
    candidate = session.get(SeriesCandidate, candidate_id)
    rule_plan = plan_archive_from_source_root(candidate.source_root)
    ai_plan = generate_ai_archive_plan(
        source_root=candidate.source_root,
        file_names=_candidate_sample_file_names(session, candidate_id),
        archive_root=archive_root,
        existing_archive_dirs=_existing_archive_dirs(session, archive_root),
        client=client,
    )
    merged = merge_archive_plans(rule_plan=rule_plan, ai_plan=ai_plan)
    planning = _persist_planning_record(session=session, candidate=candidate, rule_plan=rule_plan, ai_plan=ai_plan, merged=merged)
    if merged["decision_type"] != "auto_apply":
        _create_risk_events(session=session, planning_record=planning, merged=merged)
        session.commit()
        return {"decision_type": merged["decision_type"], "status": "pending_review", "moved": 0, "risk_events": len(merged["risk_flags"])}
    return _execute_archive_move(session=session, candidate=candidate, planning_record=planning, merged=merged, archive_root=archive_root)
```

- [x] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_archive_decision_service.py -q`
Expected: PASS with ordinary moves auto-applied and `R18`-tagged cases routed into review.

- [x] **Step 5: Commit**

```bash
git add tests/test_archive_decision_service.py src/pims_v1/services/ai_naming_service.py src/pims_v1/services/archive_decision_service.py
git commit -m "feat: add dual-engine archive decision service"
```

## Task 4: Expose A Runnable CLI Command

**Files:**

- Modify: `src/pims_v1/cli.py`
- Test: `tests/test_cli.py`

- [x] **Step 1: Write the failing CLI test**

```python
def test_auto_archive_series_cli_executes_dual_engine_archive(tmp_path, capsys, monkeypatch):
    database_url, candidate_id, archive_root = build_auto_archive_cli_fixture(tmp_path)

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
            "auto-archive-series",
            str(candidate_id),
            "--archive-root",
            str(archive_root),
            "--database-url",
            database_url,
        ],
    )

    assert main() == 0
    output = capsys.readouterr().out
    assert "decision_type=auto_apply" in output
    assert "status=confirmed" in output
```

- [x] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_cli.py -q -k auto_archive_series`
Expected: FAIL because the command does not exist yet.

- [x] **Step 3: Add the parser entry and command runner**

```python
auto_archive_series = subparsers.add_parser("auto-archive-series")
auto_archive_series.add_argument("candidate_id", type=int)
auto_archive_series.add_argument("--archive-root", required=True)
auto_archive_series.add_argument("--database-url", default=settings.database_url)
```

```python
def run_auto_archive_series(candidate_id: int, archive_root: str, database_url: str) -> int:
    session = make_session(database_url)
    client = DeepSeekClient(
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
        model=settings.deepseek_model,
        reasoning_effort=settings.deepseek_reasoning_effort,
        thinking_enabled=settings.deepseek_thinking_enabled,
    )
    try:
        result = auto_archive_candidate(
            session=session,
            candidate_id=candidate_id,
            archive_root=archive_root,
            client=client,
        )
    finally:
        session.close()

    print(f"candidate_id={result['candidate_id']}")
    print(f"decision_type={result['decision_type']}")
    print(f"status={result['status']}")
    print(f"moved={result['moved']}")
    return 0
```

- [x] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_cli.py -q -k auto_archive_series`
Expected: PASS with the command printing `decision_type=auto_apply`.

- [x] **Step 5: Commit**

```bash
git add tests/test_cli.py src/pims_v1/cli.py
git commit -m "feat: add auto archive series cli"
```

## Task 5: Full Verification

**Files:**

- Modify: `docs/superpowers/plans/2026-06-13-dual-engine-backend-foundation.md`

- [x] **Step 1: Run targeted backend verification**

Run: `python -m pytest tests/test_schema.py tests/test_archive_rule_planner.py tests/test_archive_decision_service.py tests/test_cli.py -q`
Expected: PASS with the new archive-decision slice covered end to end.

- [x] **Step 2: Run the full suite**

Run: `python -m pytest -q`
Expected: PASS with no new failures introduced.

- [x] **Step 3: Mark completed tasks in this plan**

Update the checkboxes for the completed tasks in this plan file so the execution history remains accurate.

- [x] **Step 4: Commit**

```bash
git add docs/superpowers/plans/2026-06-13-dual-engine-backend-foundation.md
git commit -m "docs: mark backend foundation plan progress"
```
