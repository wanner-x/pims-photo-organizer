from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from pims_v1.db import Base
from pims_v1.models import notification
from pims_v1.models.notification import NotificationDigestEntry, NotificationRecord
from pims_v1.models.operation import OperationBatch
from pims_v1.services.notification_service import (
    notify_duplicate_approval_needed,
    notify_workflow_event,
    send_wechat_daily_digest,
)

NOW = datetime(2026, 7, 17, 9, 0, 0)


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


def fail_sender(webhook_url: str, content: str) -> dict:
    raise AssertionError("webhook must not be called")


def recording_sender(bucket: list[str]):
    def sender(webhook_url: str, content: str) -> dict:
        bucket.append(content)
        return {"errcode": 0}

    return sender


def notify_batch(session, batch_id: int, *, sender, now=NOW, **kwargs):
    return notify_duplicate_approval_needed(
        session=session,
        webhook_url="https://example.test/webhook",
        batch_id=batch_id,
        operations=5,
        sender=sender,
        now=now,
        **kwargs,
    )


def test_notify_skips_batch_that_was_already_processed(tmp_path):
    session = make_session(tmp_path)
    session.add(OperationBatch(id=7, batch_type="duplicate_quarantine", status="executed"))
    session.commit()

    result = notify_batch(session, 7, sender=fail_sender)

    assert result == {"sent": 0, "failed": 0, "skipped": 1, "already_processed": 1}
    assert session.query(NotificationRecord).count() == 0


def test_notify_processed_batch_skipped_even_after_earlier_throttle(tmp_path):
    session = make_session(tmp_path)
    session.add(OperationBatch(id=7, batch_type="duplicate_quarantine", status="planned"))
    session.commit()
    sent: list[str] = []
    sender = recording_sender(sent)

    filler = notify_batch(session, 1, sender=sender, hourly_limit=1)
    throttled = notify_batch(session, 7, sender=sender, hourly_limit=1)

    assert filler == {"sent": 1, "failed": 0, "skipped": 0}
    assert throttled == {"sent": 0, "failed": 0, "skipped": 1, "throttled": 1}

    # The user processes the batch before the next workflow round retries.
    session.query(OperationBatch).filter(OperationBatch.id == 7).update({"status": "confirmed"})
    session.commit()

    retry = notify_batch(session, 7, sender=fail_sender, now=NOW + timedelta(hours=2))

    assert retry == {"sent": 0, "failed": 0, "skipped": 1, "already_processed": 1}
    assert len(sent) == 1


def test_notify_hourly_limit_throttles_and_later_round_retries(tmp_path):
    session = make_session(tmp_path)
    sent: list[str] = []
    sender = recording_sender(sent)

    first = notify_batch(session, 1, sender=sender, hourly_limit=2)
    second = notify_batch(session, 2, sender=sender, hourly_limit=2)
    third = notify_batch(session, 3, sender=sender, hourly_limit=2)

    assert first == {"sent": 1, "failed": 0, "skipped": 0}
    assert second == {"sent": 1, "failed": 0, "skipped": 0}
    assert third == {"sent": 0, "failed": 0, "skipped": 1, "throttled": 1}
    assert len(sent) == 2
    throttled_record = (
        session.query(NotificationRecord).filter(NotificationRecord.subject_id == 3).one()
    )
    assert throttled_record.status == "throttled"

    # One hour later the budget is free again and the throttled batch retries.
    retry = notify_batch(session, 3, sender=sender, hourly_limit=2, now=NOW + timedelta(minutes=61))

    assert retry == {"sent": 1, "failed": 0, "skipped": 0}
    assert len(sent) == 3
    session.expire_all()
    assert throttled_record.status == "sent"
    # The batch stays deduped after the successful retry.
    again = notify_batch(session, 3, sender=fail_sender, now=NOW + timedelta(minutes=62))
    assert again == {"sent": 0, "failed": 0, "skipped": 1}


def test_notify_hourly_limit_zero_disables_throttling(tmp_path):
    session = make_session(tmp_path)
    sent: list[str] = []
    sender = recording_sender(sent)

    for batch_id in range(1, 6):
        result = notify_batch(session, batch_id, sender=sender, hourly_limit=0)
        assert result == {"sent": 1, "failed": 0, "skipped": 0}

    assert len(sent) == 5


def test_digest_mode_queues_batch_instead_of_sending(tmp_path):
    session = make_session(tmp_path)

    first = notify_batch(session, 11, sender=fail_sender, digest_enabled=True)
    second = notify_batch(session, 11, sender=fail_sender, digest_enabled=True)

    assert first == {"sent": 0, "failed": 0, "skipped": 0, "queued": 1}
    assert second == {"sent": 0, "failed": 0, "skipped": 1}
    record = session.query(NotificationRecord).one()
    entry = session.query(NotificationDigestEntry).one()
    assert record.status == "digest_pending"
    assert entry.status == "pending"
    assert entry.record_id == record.id
    assert "批次 #11" in entry.summary


def test_daily_digest_aggregates_queued_batches_into_one_message(tmp_path):
    session = make_session(tmp_path)
    sent: list[str] = []
    sender = recording_sender(sent)

    notify_batch(session, 11, sender=fail_sender, digest_enabled=True)
    notify_batch(session, 12, sender=fail_sender, digest_enabled=True)

    result = send_wechat_daily_digest(
        session=session,
        webhook_url="https://example.test/webhook",
        review_url="http://192.168.31.98:8000/review-ui",
        sender=sender,
        now=NOW,
    )

    assert result == {"sent": 1, "failed": 0, "skipped": 0, "entries": 2}
    assert len(sent) == 1
    assert "PIMS 每日汇总（2026-07-17）" in sent[0]
    assert "批次 #11" in sent[0]
    assert "批次 #12" in sent[0]
    assert "http://192.168.31.98:8000/review-ui" in sent[0]
    statuses = {entry.status for entry in session.query(NotificationDigestEntry).all()}
    assert statuses == {"sent"}
    record_statuses = sorted(
        record.status for record in session.query(NotificationRecord).all()
    )
    assert record_statuses == ["digested", "digested", "sent"]


def test_daily_digest_sends_at_most_once_per_day(tmp_path):
    session = make_session(tmp_path)
    sent: list[str] = []
    sender = recording_sender(sent)

    notify_batch(session, 11, sender=fail_sender, digest_enabled=True)
    first = send_wechat_daily_digest(
        session=session, webhook_url="https://example.test/webhook", sender=sender, now=NOW
    )
    notify_batch(session, 12, sender=fail_sender, digest_enabled=True)
    same_day = send_wechat_daily_digest(
        session=session,
        webhook_url="https://example.test/webhook",
        sender=sender,
        now=NOW + timedelta(hours=2),
    )
    next_day = send_wechat_daily_digest(
        session=session,
        webhook_url="https://example.test/webhook",
        sender=sender,
        now=NOW + timedelta(days=1),
    )

    assert first["sent"] == 1
    assert same_day == {"sent": 0, "failed": 0, "skipped": 1, "entries": 1}
    assert next_day == {"sent": 1, "failed": 0, "skipped": 0, "entries": 1}
    assert len(sent) == 2
    assert "批次 #12" in sent[1]


def test_daily_digest_skips_without_pending_entries_or_webhook(tmp_path):
    session = make_session(tmp_path)

    no_webhook = send_wechat_daily_digest(session=session, webhook_url=None, sender=fail_sender)
    no_entries = send_wechat_daily_digest(
        session=session, webhook_url="https://example.test/webhook", sender=fail_sender
    )

    assert no_webhook == {"sent": 0, "failed": 0, "skipped": 1, "entries": 0}
    assert no_entries == {"sent": 0, "failed": 0, "skipped": 1, "entries": 0}
    assert session.query(NotificationRecord).count() == 0


def test_daily_digest_failure_keeps_entries_pending_for_retry(tmp_path):
    session = make_session(tmp_path)
    sent: list[str] = []

    notify_batch(session, 11, sender=fail_sender, digest_enabled=True)

    def broken_sender(webhook_url: str, content: str) -> dict:
        raise RuntimeError("webhook down")

    failed = send_wechat_daily_digest(
        session=session, webhook_url="https://example.test/webhook", sender=broken_sender, now=NOW
    )
    retried = send_wechat_daily_digest(
        session=session,
        webhook_url="https://example.test/webhook",
        sender=recording_sender(sent),
        now=NOW + timedelta(minutes=5),
    )

    assert failed == {"sent": 0, "failed": 1, "skipped": 0, "entries": 1}
    assert retried == {"sent": 1, "failed": 0, "skipped": 0, "entries": 1}
    assert len(sent) == 1


def test_workflow_event_respects_shared_hourly_budget_when_session_given(tmp_path):
    session = make_session(tmp_path)
    sent: list[str] = []
    sender = recording_sender(sent)

    # Two batch messages consume the whole budget of 2.
    notify_batch(session, 1, sender=sender, hourly_limit=2)
    notify_batch(session, 2, sender=sender, hourly_limit=2)

    throttled = notify_workflow_event(
        webhook_url="https://example.test/webhook",
        title="PIMS full detection complete",
        lines=["assets=10"],
        sender=fail_sender,
        session=session,
        hourly_limit=2,
        now=NOW,
    )
    later = notify_workflow_event(
        webhook_url="https://example.test/webhook",
        title="PIMS full detection complete",
        lines=["assets=10"],
        sender=sender,
        session=session,
        hourly_limit=2,
        now=NOW + timedelta(minutes=61),
    )

    assert throttled == {"sent": 0, "failed": 0, "skipped": 1, "throttled": 1}
    assert later == {"sent": 1, "failed": 0, "skipped": 0}
    assert len(sent) == 3
    # The lifecycle send is recorded so it counts against later budgets.
    assert (
        session.query(NotificationRecord)
        .filter(NotificationRecord.event_type == "workflow_event", NotificationRecord.status == "sent")
        .count()
        == 1
    )


def test_workflow_event_stays_stateless_without_session():
    sent: list[str] = []

    result = notify_workflow_event(
        webhook_url="https://example.test/webhook",
        title="PIMS started",
        lines=["round=1"],
        sender=recording_sender(sent),
    )

    assert result == {"sent": 1, "failed": 0, "skipped": 0}
    assert sent == ["PIMS started\nround=1"]
