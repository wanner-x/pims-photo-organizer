from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from pims_v1.db import Base
from pims_v1.models import notification
from pims_v1.models.notification import NotificationRecord
from pims_v1.services.notification_service import notify_duplicate_approval_needed, notify_workflow_event


def make_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", future=True)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return session_factory()


def test_notify_workflow_event_sends_multiline_message():
    sent_messages = []

    result = notify_workflow_event(
        webhook_url="https://example.test/webhook",
        title="PIMS workflow failed",
        lines=["round=3", "error=boom"],
        sender=lambda webhook_url, content: sent_messages.append((webhook_url, content)) or {"errcode": 0},
    )

    assert result == {"sent": 1, "failed": 0, "skipped": 0}
    assert sent_messages == [
        (
            "https://example.test/webhook",
            "PIMS workflow failed\nround=3\nerror=boom",
        )
    ]


def test_notify_workflow_event_skips_without_webhook():
    result = notify_workflow_event(
        webhook_url=None,
        title="PIMS workflow started",
        lines=["round=1"],
        sender=lambda webhook_url, content: {"errcode": 0},
    )

    assert result == {"sent": 0, "failed": 0, "skipped": 1}


def test_notify_duplicate_approval_needed_skips_already_sent_batch(tmp_path):
    session = make_session(tmp_path)
    sent_messages = []

    def fake_sender(webhook_url: str, content: str) -> dict[str, int]:
        sent_messages.append({"webhook_url": webhook_url, "content": content})
        return {"errcode": 0}

    first = notify_duplicate_approval_needed(
        session=session,
        webhook_url="https://example.test/webhook",
        batch_id=12,
        operations=34,
        sender=fake_sender,
    )
    second = notify_duplicate_approval_needed(
        session=session,
        webhook_url="https://example.test/webhook",
        batch_id=12,
        operations=34,
        sender=fake_sender,
    )

    assert first == {"sent": 1, "failed": 0, "skipped": 0}
    assert second == {"sent": 0, "failed": 0, "skipped": 1}
    assert len(sent_messages) == 1
    assert "批次 #12" in sent_messages[0]["content"]


def test_notify_duplicate_approval_needed_skips_legacy_record_for_same_batch(tmp_path):
    session = make_session(tmp_path)
    session.add(
        NotificationRecord(
            dedupe_key="old-format:12",
            channel="wechat",
            event_type="duplicate_approval_needed",
            subject_type="operation_batch",
            subject_id=12,
            status="sent",
        )
    )
    session.commit()
    sent_messages = []

    result = notify_duplicate_approval_needed(
        session=session,
        webhook_url="https://example.test/webhook",
        batch_id=12,
        operations=34,
        sender=lambda webhook_url, content: sent_messages.append(content) or {"errcode": 0},
    )

    assert result == {"sent": 0, "failed": 0, "skipped": 1}
    assert sent_messages == []


def test_notify_duplicate_approval_needed_message_is_actionable(tmp_path):
    session = make_session(tmp_path)
    sent_messages = []

    result = notify_duplicate_approval_needed(
        session=session,
        webhook_url="https://example.test/webhook",
        batch_id=12,
        operations=34,
        review_url="http://192.168.31.98:8000/review-ui",
        sender=lambda webhook_url, content: sent_messages.append(content) or {"errcode": 0},
    )

    assert result == {"sent": 1, "failed": 0, "skipped": 0}
    assert len(sent_messages) == 1
    assert "发现 34 个疑似重复文件待审核" in sent_messages[0]
    assert "不会自动删除" in sent_messages[0]
    assert "http://192.168.31.98:8000/review-ui" in sent_messages[0]
