from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from pims_v1.db import Base
from pims_v1.models import asset, duplicate, library, operation, processing, review, series
from pims_v1.models.asset import Asset
from pims_v1.models.library import Library
from pims_v1.models.series import SeriesCandidate, SeriesCandidateAsset, SeriesSuggestion
from pims_v1.services.ai_naming_service import (
    build_series_title_prompt,
    build_series_organization_prompt,
    suggest_series_organization_candidates,
    suggest_series_organization,
    suggest_series_title,
)


class FakeNamingClient:
    def __init__(self) -> None:
        self.messages = []

    def chat(self, messages):
        self.messages = messages
        return "Clean Title"


class FakeOrganizationClient:
    def __init__(self) -> None:
        self.messages = []

    def chat(self, messages):
        self.messages = messages
        return (
            '{"title":"清晨海边写真","category":"写真合集","confidence":0.82,'
            '"plan_summary":"移动到 NAS 写真合集目录并保留原文件名",'
            '"risk_flags":["目标目录可能已存在"]}'
        )


class FakeBadXueqiOrganizationClient:
    def __init__(self) -> None:
        self.messages = []

    def chat(self, messages):
        self.messages = messages
        return (
            '{"title":"雪琪SAMA 透明女仆写真","category":"写真合集",'
            '"archive_path":"写真合集/雪琪SAMA 透明女仆写真",'
            '"plan_summary":"错误地放入写真合集","risk_flags":[],"confidence":0.92}'
        )


class FakeR18OrganizationClient:
    def __init__(self) -> None:
        self.messages = []

    def chat(self, messages):
        self.messages = messages
        return (
            '{"title":"随意改名","category":"写真合集","archive_path":"写真合集/随意改名",'
            '"plan_summary":"检测到成人内容标签，但不改变归档层级",'
            '"risk_flags":["需人工复核R18标签"],"tags":["R18","JK黑"],'
            '"r18_label":true,"r18_confidence":0.91,"r18_reason":"目录名已有R18或视觉审核标记",'
            '"confidence":0.88}'
        )


class SequencedOrganizationClient:
    def __init__(self, payloads: list[str]) -> None:
        self.payloads = list(payloads)
        self.messages = []

    def chat(self, messages):
        self.messages.append(messages)
        if not self.payloads:
            raise AssertionError("No organization payload left")
        return self.payloads.pop(0)


def make_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", future=True)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return session_factory()


def test_build_series_title_prompt_uses_source_and_sample_names():
    prompt = build_series_title_prompt(
        source_root="/library/model-a/set-01",
        file_names=["001.jpg", "002.jpg"],
    )

    assert "set-01" in prompt
    assert "001.jpg" in prompt
    assert "002.jpg" in prompt


def test_suggest_series_title_updates_candidate_with_ai_title(tmp_path):
    session = make_session(tmp_path)
    library_row = Library(name="Library", kind="local", root_path="/library")
    session.add(library_row)
    session.flush()
    asset_row = Asset(
        library_id=library_row.id,
        original_path="/library/set/a.jpg",
        current_path="/library/set/a.jpg",
        file_name="a.jpg",
        file_ext=".jpg",
        file_size=1,
        mtime=1.0,
    )
    session.add(asset_row)
    session.flush()
    candidate = SeriesCandidate(library_id=library_row.id, source_root="/library/set")
    session.add(candidate)
    session.flush()
    session.add(SeriesCandidateAsset(candidate_id=candidate.id, asset_id=asset_row.id))
    session.commit()
    client = FakeNamingClient()

    result = suggest_series_title(session=session, candidate_id=candidate.id, client=client)

    session.refresh(candidate)
    assert result == {"candidate_id": candidate.id, "title": "Clean Title"}
    assert candidate.title == "Clean Title"
    assert candidate.status == "ai_suggested"
    assert candidate.confidence == 0.6
    assert "a.jpg" in client.messages[0]["content"]


def test_build_series_organization_prompt_requests_reviewable_json():
    prompt = build_series_organization_prompt(
        source_root="/library/model-a/set-01",
        file_names=["001.jpg", "002.jpg"],
        archive_root="/nas/archive",
        existing_archive_dirs=["写真合集/旧系列"],
    )

    assert "set-01" in prompt
    assert "001.jpg" in prompt
    assert "title" in prompt
    assert "category" in prompt
    assert "archive_path" in prompt
    assert "/nas/archive" in prompt
    assert "写真合集/旧系列" in prompt


def test_build_series_organization_prompt_preserves_source_folder_structure():
    prompt = build_series_organization_prompt(
        source_root="D:/图册/雪琪SAMA/雪琪SAMA 透明女仆 [43P4V234MB]",
        file_names=["001.jpg", "002.mp4"],
        archive_root=r"\\nas\网络写真集",
        existing_archive_dirs=["雪琪SAMA/雪琪SAMA JK白丝 [46P208MB]"],
    )

    assert "推荐顶层目录: 雪琪SAMA" in prompt
    assert "推荐系列目录名: 雪琪SAMA 透明女仆 [43P4V234MB]" in prompt
    assert "不要追加“写真”" in prompt
    assert "不要归入“写真合集”" in prompt
    assert "[43P4V234MB]" in prompt


def test_suggest_series_organization_creates_review_suggestion(tmp_path):
    session = make_session(tmp_path)
    library_row = Library(name="Library", kind="local", root_path="/library")
    session.add(library_row)
    session.flush()
    asset_row = Asset(
        library_id=library_row.id,
        original_path="/library/set/a.jpg",
        current_path="/library/set/a.jpg",
        file_name="a.jpg",
        file_ext=".jpg",
        file_size=1,
        mtime=1.0,
    )
    session.add(asset_row)
    session.flush()
    candidate = SeriesCandidate(library_id=library_row.id, source_root="/library/set")
    session.add(candidate)
    session.flush()
    session.add(SeriesCandidateAsset(candidate_id=candidate.id, asset_id=asset_row.id))
    session.commit()
    client = FakeOrganizationClient()

    result = suggest_series_organization(
        session=session,
        candidate_id=candidate.id,
        client=client,
        archive_root="/nas/archive",
    )

    suggestion = session.query(SeriesSuggestion).one()
    session.refresh(candidate)
    assert result == {
        "candidate_id": candidate.id,
        "suggestion_id": suggestion.id,
        "title": "清晨海边写真",
        "category": "写真合集",
        "archive_path": "/nas/archive/写真合集/清晨海边写真",
        "plan_summary": "移动到 NAS 写真合集目录并保留原文件名",
        "risk_flags": ["目标目录可能已存在"],
        "tags": [],
        "r18_label": False,
        "r18_confidence": 0.0,
        "r18_reason": "",
        "confidence": 0.82,
    }
    assert suggestion.status == "pending_review"
    assert suggestion.suggested_title == "清晨海边写真"
    assert suggestion.suggested_category == "写真合集"
    assert suggestion.suggested_archive_path == "/nas/archive/写真合集/清晨海边写真"
    assert suggestion.plan_summary == "移动到 NAS 写真合集目录并保留原文件名"
    assert suggestion.risk_flags == '["目标目录可能已存在"]'
    assert candidate.status == "ai_suggested"
    assert candidate.title == "清晨海边写真"


def test_suggest_series_organization_candidates_batches_pending_candidates(tmp_path):
    session = make_session(tmp_path)
    library_row = Library(name="Library", kind="local", root_path="/library")
    session.add(library_row)
    session.flush()
    candidates = []
    for name in ["set-a", "set-b"]:
        asset_row = Asset(
            library_id=library_row.id,
            original_path=f"/library/{name}/001.jpg",
            current_path=f"/library/{name}/001.jpg",
            file_name="001.jpg",
            file_ext=".jpg",
            file_size=1,
            mtime=1.0,
        )
        session.add(asset_row)
        session.flush()
        candidate = SeriesCandidate(library_id=library_row.id, source_root=f"/library/{name}", status="pending")
        session.add(candidate)
        session.flush()
        session.add(SeriesCandidateAsset(candidate_id=candidate.id, asset_id=asset_row.id))
        candidates.append(candidate)
    session.commit()
    client = SequencedOrganizationClient(
        [
            '{"title":"Set A","category":"People","archive_path":"","plan_summary":"plan A","risk_flags":[],"tags":[],"r18_label":false,"r18_confidence":0.0,"r18_reason":"","confidence":0.81}',
            '{"title":"Set B","category":"People","archive_path":"","plan_summary":"plan B","risk_flags":[],"tags":[],"r18_label":false,"r18_confidence":0.0,"r18_reason":"","confidence":0.82}',
        ]
    )

    summary = suggest_series_organization_candidates(
        session=session,
        client=client,
        archive_root="/nas/archive",
        limit=10,
    )

    assert summary == {"considered": 2, "processed": 2, "suggested": 2, "skipped": 0, "failed": 0}
    assert session.query(SeriesSuggestion).count() == 2
    assert [candidate.status for candidate in candidates] == ["ai_suggested", "ai_suggested"]
    assert len(client.messages) == 2


def test_suggest_series_organization_overrides_generic_ai_for_named_parent_series(tmp_path):
    session = make_session(tmp_path)
    library_row = Library(name="Library", kind="local", root_path="/library")
    session.add(library_row)
    session.flush()
    asset_row = Asset(
        library_id=library_row.id,
        original_path="/library/雪琪SAMA/雪琪SAMA 透明女仆 [43P4V234MB]/001.jpg",
        current_path="/library/雪琪SAMA/雪琪SAMA 透明女仆 [43P4V234MB]/001.jpg",
        file_name="001.jpg",
        file_ext=".jpg",
        file_size=1,
        mtime=1.0,
    )
    session.add(asset_row)
    session.flush()
    candidate = SeriesCandidate(
        library_id=library_row.id,
        source_root="/library/雪琪SAMA/雪琪SAMA 透明女仆 [43P4V234MB]",
    )
    session.add(candidate)
    session.flush()
    session.add(SeriesCandidateAsset(candidate_id=candidate.id, asset_id=asset_row.id))
    session.commit()
    client = FakeBadXueqiOrganizationClient()

    result = suggest_series_organization(
        session=session,
        candidate_id=candidate.id,
        client=client,
        archive_root="/nas/archive",
    )

    suggestion = session.query(SeriesSuggestion).one()
    assert result["title"] == "雪琪SAMA 透明女仆 [43P4V234MB]"
    assert result["category"] == "雪琪SAMA"
    assert result["archive_path"] == "/nas/archive/雪琪SAMA/雪琪SAMA 透明女仆 [43P4V234MB]"
    assert suggestion.suggested_title == "雪琪SAMA 透明女仆 [43P4V234MB]"
    assert suggestion.suggested_category == "雪琪SAMA"
    assert suggestion.suggested_archive_path == "/nas/archive/雪琪SAMA/雪琪SAMA 透明女仆 [43P4V234MB]"


def test_suggest_series_organization_adds_r18_as_leaf_tag_without_changing_category(tmp_path):
    session = make_session(tmp_path)
    library_row = Library(name="Library", kind="local", root_path="/library")
    session.add(library_row)
    session.flush()
    asset_row = Asset(
        library_id=library_row.id,
        original_path="/library/紧急企划/【紧急企划】-【VOL.001】-【樱樱樱可】-【JK黑】-【45P1V-858M】/001.jpg",
        current_path="/library/紧急企划/【紧急企划】-【VOL.001】-【樱樱樱可】-【JK黑】-【45P1V-858M】/001.jpg",
        file_name="001.jpg",
        file_ext=".jpg",
        file_size=1,
        mtime=1.0,
    )
    session.add(asset_row)
    session.flush()
    candidate = SeriesCandidate(
        library_id=library_row.id,
        source_root="/library/紧急企划/【紧急企划】-【VOL.001】-【樱樱樱可】-【JK黑】-【45P1V-858M】",
    )
    session.add(candidate)
    session.flush()
    session.add(SeriesCandidateAsset(candidate_id=candidate.id, asset_id=asset_row.id))
    session.commit()
    client = FakeR18OrganizationClient()

    result = suggest_series_organization(
        session=session,
        candidate_id=candidate.id,
        client=client,
        archive_root="/nas/archive",
    )

    suggestion = session.query(SeriesSuggestion).one()
    assert result["title"] == "【紧急企划】-【VOL.001】-【樱樱樱可】-【JK黑】-【45P1V-858M】 [R18]"
    assert result["category"] == "紧急企划"
    assert result["archive_path"] == "/nas/archive/紧急企划/【紧急企划】-【VOL.001】-【樱樱樱可】-【JK黑】-【45P1V-858M】 [R18]"
    assert result["tags"] == ["R18", "JK黑"]
    assert result["r18_label"] is True
    assert result["r18_confidence"] == 0.91
    assert suggestion.suggested_category == "紧急企划"
    assert suggestion.suggested_title.endswith("[R18]")


def test_suggest_series_organization_does_not_duplicate_existing_r18_tag(tmp_path):
    session = make_session(tmp_path)
    library_row = Library(name="Library", kind="local", root_path="/library")
    session.add(library_row)
    session.flush()
    asset_row = Asset(
        library_id=library_row.id,
        original_path="/library/紧急企划/紧急企划 - 见希-JK-R18 [85P1V1.32G]/001.jpg",
        current_path="/library/紧急企划/紧急企划 - 见希-JK-R18 [85P1V1.32G]/001.jpg",
        file_name="001.jpg",
        file_ext=".jpg",
        file_size=1,
        mtime=1.0,
    )
    session.add(asset_row)
    session.flush()
    candidate = SeriesCandidate(
        library_id=library_row.id,
        source_root="/library/紧急企划/紧急企划 - 见希-JK-R18 [85P1V1.32G]",
    )
    session.add(candidate)
    session.flush()
    session.add(SeriesCandidateAsset(candidate_id=candidate.id, asset_id=asset_row.id))
    session.commit()

    result = suggest_series_organization(
        session=session,
        candidate_id=candidate.id,
        client=FakeR18OrganizationClient(),
        archive_root="/nas/archive",
    )

    assert result["title"] == "紧急企划 - 见希-JK-R18 [85P1V1.32G]"
    assert result["archive_path"] == "/nas/archive/紧急企划/紧急企划 - 见希-JK-R18 [85P1V1.32G]"
