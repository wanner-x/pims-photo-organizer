import json

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from pims_v1.db import Base
from pims_v1.models import archive_decision, asset, duplicate, library, operation, processing, review, series
from pims_v1.models.archive_decision import ArchiveExecutionRecord, ArchivePlanningRecord, ArchiveRiskEvent
from pims_v1.models.asset import Asset
from pims_v1.models.library import Library
from pims_v1.models.series import Series, SeriesCandidate, SeriesCandidateAsset
from pims_v1.services.archive_decision_service import auto_archive_candidate


class StaticAIPlanClient:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def chat(self, messages):
        return json.dumps(self.payload, ensure_ascii=False)


def make_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", future=True)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return session_factory()


def build_candidate_fixture(tmp_path, source_root: str = "D:/图册/雪琪SAMA/雪琪SAMA 透明女仆 [43P4V234MB]"):
    session = make_session(tmp_path)
    source_dir = tmp_path / "pc" / "source"
    source_dir.mkdir(parents=True)
    file_path = source_dir / "001.jpg"
    file_path.write_bytes(b"sample")
    archive_root = tmp_path / "nas"

    library_row = Library(name="Photos", kind="local", root_path=str(tmp_path / "pc"))
    session.add(library_row)
    session.flush()
    asset_row = Asset(
        library_id=library_row.id,
        original_path=str(file_path),
        current_path=str(file_path),
        file_name="001.jpg",
        file_ext=".jpg",
        file_size=file_path.stat().st_size,
        mtime=1.0,
    )
    session.add(asset_row)
    session.flush()
    candidate = SeriesCandidate(
        library_id=library_row.id,
        source_root=source_root,
        title=source_root.rsplit("/", 1)[-1],
        status="pending",
    )
    session.add(candidate)
    session.flush()
    session.add(SeriesCandidateAsset(candidate_id=candidate.id, asset_id=asset_row.id, sort_order=0))
    session.commit()
    return session, candidate.id, archive_root


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

    planning_row = session.query(ArchivePlanningRecord).one()
    execution_row = session.query(ArchiveExecutionRecord).one()
    series_row = session.query(Series).one()

    assert result["candidate_id"] == candidate_id
    assert result["decision_type"] == "auto_apply"
    assert result["status"] == "confirmed"
    assert result["moved"] == 1
    assert result["risk_events"] == 0
    assert planning_row.decision_type == "auto_apply"
    assert execution_row.status == "done"
    assert series_row.archive_path == str(archive_root / "雪琪SAMA" / "雪琪SAMA 透明女仆 [43P4V234MB]")


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

    planning_row = session.query(ArchivePlanningRecord).one()
    risk_row = session.query(ArchiveRiskEvent).one()

    assert result["decision_type"] == "manual_review"
    assert result["moved"] == 0
    assert result["status"] == "pending_review"
    assert result["risk_events"] == 1
    assert planning_row.decision_type == "manual_review"
    assert risk_row.event_type == "r18_suspected"
    assert session.query(ArchiveExecutionRecord).count() == 0
