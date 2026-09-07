"""Enterprise WeChat webhook notifications with throttling.

Throttling rules (roadmap stage 5):

- Same batch is pushed at most once (subject-level dedupe records).
- Batches that have already been processed (status != "planned") are never
  pushed, even if no notification record exists yet.
- At most ``PIMS_WECHAT_HOURLY_LIMIT`` messages per rolling hour (default 3,
  0 disables the cap). Blocked batch sends are marked ``throttled`` and get
  retried by a later workflow round; they are not lost.
- Daily digest mode (``PIMS_WECHAT_DIGEST=1``): batch events are queued as
  digest entries instead of being sent one by one, and the safe workflow
  flushes them as a single summary message at most once per day.
"""
import json
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from urllib import request

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from pims_v1.config import settings
from pims_v1.models.notification import NotificationDigestEntry, NotificationRecord
from pims_v1.models.operation import OperationBatch

WechatSender = Callable[[str, str], dict]

# Reservation statuses that may be retried by a later attempt. Everything else
# ("sending", "sent", "digest_pending", "digested") keeps the subject deduped.
_RETRYABLE_STATUSES = ("failed", "throttled")

_EVENT_TYPE_LABELS = {
    "duplicate_approval_needed": "重复隔离待审核",
    "workflow_event": "工作流事件",
}

_DIGEST_MAX_DETAIL_LINES = 15


def _utcnow() -> datetime:
    """Naive UTC now, matching SQLite CURRENT_TIMESTAMP server defaults."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def send_wechat_text_message(webhook_url: str, content: str, timeout: float = 10.0) -> dict:
    payload = {
        "msgtype": "text",
        "text": {
            "content": content,
        },
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    http_request = request.Request(
        webhook_url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(http_request, timeout=timeout) as response:
        response_body = response.read().decode("utf-8")
    return json.loads(response_body) if response_body else {}


def _sent_count_within_window(
    session: Session,
    *,
    channel: str,
    now: datetime,
    window: timedelta = timedelta(hours=1),
) -> int:
    return (
        session.query(NotificationRecord)
        .filter(
            NotificationRecord.channel == channel,
            NotificationRecord.status == "sent",
            NotificationRecord.updated_at >= now - window,
        )
        .count()
    )


def _hourly_budget_exhausted(
    session: Session,
    *,
    channel: str,
    hourly_limit: int,
    now: datetime,
) -> bool:
    if hourly_limit <= 0:
        return False
    return _sent_count_within_window(session, channel=channel, now=now) >= hourly_limit


def notify_workflow_event(
    *,
    webhook_url: str | None,
    title: str,
    lines: list[str] | tuple[str, ...] = (),
    sender: WechatSender | None = None,
    session: Session | None = None,
    database_url: str | None = None,
    hourly_limit: int | None = None,
    now: datetime | None = None,
) -> dict[str, int]:
    """Send a free-form workflow lifecycle message.

    Stateless when no session/database_url is given (legacy behaviour). With
    database access, sends respect the shared hourly budget and are recorded
    so batch notifications and lifecycle messages count against the same cap.
    Throttled lifecycle messages are informational and simply dropped.
    """
    if not webhook_url:
        return {"sent": 0, "failed": 0, "skipped": 1}

    send = sender or send_wechat_text_message
    owned_session = None
    if session is None and database_url:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker

        from pims_v1.db import ensure_database_schema

        engine = create_engine(database_url, future=True)
        ensure_database_schema(engine)
        owned_session = sessionmaker(
            bind=engine, autoflush=False, autocommit=False, future=True
        )()
        session = owned_session

    try:
        moment = now or _utcnow()
        if session is not None:
            limit = settings.wechat_hourly_limit if hourly_limit is None else hourly_limit
            if _hourly_budget_exhausted(
                session, channel="wechat", hourly_limit=limit, now=moment
            ):
                return {"sent": 0, "failed": 0, "skipped": 1, "throttled": 1}

        content = "\n".join([title, *[line for line in lines if line]])
        try:
            send(webhook_url, content)
        except Exception:
            return {"sent": 0, "failed": 1, "skipped": 0}

        if session is not None:
            _record_workflow_event_send(session, title=title, now=moment)
        return {"sent": 1, "failed": 0, "skipped": 0}
    finally:
        if owned_session is not None:
            owned_session.close()


def _record_workflow_event_send(session: Session, *, title: str, now: datetime) -> None:
    """Record a lifecycle send so it counts against the hourly budget."""
    record = NotificationRecord(
        dedupe_key=f"wechat:workflow_event:{now.isoformat()}:{abs(hash(title)) % 10_000_000}",
        channel="wechat",
        event_type="workflow_event",
        subject_type="workflow_event",
        subject_id=int(now.timestamp() * 1000) % 2_000_000_000,
        status="sent",
        created_at=now,
        updated_at=now,
    )
    session.add(record)
    try:
        session.commit()
    except IntegrityError:
        # Two lifecycle sends in the same millisecond: the send already
        # happened, losing one budget entry is acceptable.
        session.rollback()


def _reserve_notification(
    *,
    session: Session,
    dedupe_key: str,
    channel: str,
    event_type: str,
    subject_type: str,
    subject_id: int,
) -> NotificationRecord | None:
    existing_for_subject = (
        session.query(NotificationRecord)
        .filter(
            NotificationRecord.channel == channel,
            NotificationRecord.event_type == event_type,
            NotificationRecord.subject_type == subject_type,
            NotificationRecord.subject_id == subject_id,
            NotificationRecord.status.notin_(_RETRYABLE_STATUSES),
        )
        .first()
    )
    if existing_for_subject is not None:
        return None

    existing = session.query(NotificationRecord).filter(NotificationRecord.dedupe_key == dedupe_key).one_or_none()
    if existing and existing.status not in _RETRYABLE_STATUSES:
        return None
    if existing and existing.status in _RETRYABLE_STATUSES:
        updated = (
            session.query(NotificationRecord)
            .filter(
                NotificationRecord.dedupe_key == dedupe_key,
                NotificationRecord.status.in_(_RETRYABLE_STATUSES),
            )
            .update({"status": "sending", "last_error": None}, synchronize_session=False)
        )
        session.commit()
        if not updated:
            return None
        return session.query(NotificationRecord).filter(NotificationRecord.dedupe_key == dedupe_key).one()

    record = NotificationRecord(
        dedupe_key=dedupe_key,
        channel=channel,
        event_type=event_type,
        subject_type=subject_type,
        subject_id=subject_id,
        status="sending",
    )
    session.add(record)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        return None
    return record


def _batch_already_processed(session: Session, batch_id: int) -> bool:
    batch = session.get(OperationBatch, batch_id)
    return batch is not None and batch.status != "planned"


def _queue_digest_entry(
    session: Session,
    *,
    record: NotificationRecord,
    summary: str,
) -> None:
    record.status = "digest_pending"
    session.add(
        NotificationDigestEntry(
            record_id=record.id,
            channel=record.channel,
            event_type=record.event_type,
            summary=summary,
        )
    )
    session.commit()


def notify_duplicate_approval_needed(
    *,
    session: Session,
    webhook_url: str,
    batch_id: int,
    operations: int,
    review_url: str = "http://127.0.0.1:8000/review-ui",
    sender: WechatSender | None = None,
    digest_enabled: bool | None = None,
    hourly_limit: int | None = None,
    now: datetime | None = None,
) -> dict[str, int]:
    send = sender or send_wechat_text_message
    moment = now or _utcnow()
    use_digest = settings.wechat_digest if digest_enabled is None else digest_enabled
    limit = settings.wechat_hourly_limit if hourly_limit is None else hourly_limit

    # A batch the user already confirmed/executed must never be pushed again,
    # even when it was throttled earlier and never got a sent record.
    if _batch_already_processed(session, batch_id):
        return {"sent": 0, "failed": 0, "skipped": 1, "already_processed": 1}

    dedupe_key = f"wechat:duplicate_quarantine:{batch_id}"
    record = _reserve_notification(
        session=session,
        dedupe_key=dedupe_key,
        channel="wechat",
        event_type="duplicate_approval_needed",
        subject_type="operation_batch",
        subject_id=batch_id,
    )
    if record is None:
        return {"sent": 0, "failed": 0, "skipped": 1}

    if use_digest:
        _queue_digest_entry(
            session,
            record=record,
            summary=f"批次 #{batch_id}：{operations} 个疑似重复文件待审核",
        )
        return {"sent": 0, "failed": 0, "skipped": 0, "queued": 1}

    if _hourly_budget_exhausted(session, channel="wechat", hourly_limit=limit, now=moment):
        record.status = "throttled"
        record.last_error = f"hourly limit {limit} reached"
        session.commit()
        return {"sent": 0, "failed": 0, "skipped": 1, "throttled": 1}

    content = (
        "PIMS 照片整理待审核\n"
        f"批次 #{batch_id}：发现 {operations} 个疑似重复文件待审核。\n"
        "系统不会自动删除文件；确认后才会把重复副本移动到隔离区。\n"
        "请在审核页对比“已存在位置”和“重复位置”，确认无误后再批量处理。\n"
        f"审核入口：{review_url}\n"
        "如果该批次已经处理，可以忽略本提醒。"
    )
    try:
        send(webhook_url, content)
    except Exception as exc:
        record.status = "failed"
        record.last_error = str(exc)[:2048]
        session.commit()
        return {"sent": 0, "failed": 1, "skipped": 0}

    record.status = "sent"
    record.last_error = None
    record.updated_at = moment
    session.commit()
    return {"sent": 1, "failed": 0, "skipped": 0}


def send_wechat_daily_digest(
    *,
    session: Session,
    webhook_url: str | None,
    review_url: str = "http://127.0.0.1:8000/review-ui",
    sender: WechatSender | None = None,
    hourly_limit: int | None = None,
    now: datetime | None = None,
) -> dict[str, int]:
    """Flush pending digest entries as one summary message, at most once a day.

    Entries that cannot be reported today (digest already sent, throttled, or
    send failure) stay pending and are picked up by a later digest.
    """
    if not webhook_url:
        return {"sent": 0, "failed": 0, "skipped": 1, "entries": 0}

    send = sender or send_wechat_text_message
    moment = now or _utcnow()
    limit = settings.wechat_hourly_limit if hourly_limit is None else hourly_limit
    pending = (
        session.query(NotificationDigestEntry)
        .filter(
            NotificationDigestEntry.channel == "wechat",
            NotificationDigestEntry.status == "pending",
        )
        .order_by(NotificationDigestEntry.id)
        .all()
    )
    if not pending:
        return {"sent": 0, "failed": 0, "skipped": 1, "entries": 0}

    digest_date = moment.strftime("%Y-%m-%d")
    date_key = int(moment.strftime("%Y%m%d"))
    record = _reserve_notification(
        session=session,
        dedupe_key=f"wechat:daily_digest:{digest_date}",
        channel="wechat",
        event_type="daily_digest",
        subject_type="digest_date",
        subject_id=date_key,
    )
    if record is None:
        return {"sent": 0, "failed": 0, "skipped": 1, "entries": len(pending)}

    if _hourly_budget_exhausted(session, channel="wechat", hourly_limit=limit, now=moment):
        record.status = "throttled"
        record.last_error = f"hourly limit {limit} reached"
        session.commit()
        return {"sent": 0, "failed": 0, "skipped": 1, "throttled": 1, "entries": len(pending)}

    counts: dict[str, int] = {}
    for entry in pending:
        counts[entry.event_type] = counts.get(entry.event_type, 0) + 1
    lines = [f"PIMS 每日汇总（{digest_date}）", f"今日累计 {len(pending)} 条待审核事件。"]
    for event_type, count in sorted(counts.items()):
        label = _EVENT_TYPE_LABELS.get(event_type, event_type)
        lines.append(f"{label}：{count} 条")
    for entry in pending[:_DIGEST_MAX_DETAIL_LINES]:
        lines.append(f"- {entry.summary}")
    if len(pending) > _DIGEST_MAX_DETAIL_LINES:
        lines.append(f"…另有 {len(pending) - _DIGEST_MAX_DETAIL_LINES} 条，详见审核页。")
    lines.append(f"审核入口：{review_url}")
    lines.append("已处理的事件可以忽略本提醒。")
    content = "\n".join(lines)

    try:
        send(webhook_url, content)
    except Exception as exc:
        record.status = "failed"
        record.last_error = str(exc)[:2048]
        session.commit()
        return {"sent": 0, "failed": 1, "skipped": 0, "entries": len(pending)}

    record.status = "sent"
    record.last_error = None
    record.updated_at = moment
    for entry in pending:
        entry.status = "sent"
        entry.digest_date = digest_date
        related = session.get(NotificationRecord, entry.record_id)
        if related is not None and related.status == "digest_pending":
            related.status = "digested"
    session.commit()
    return {"sent": 1, "failed": 0, "skipped": 0, "entries": len(pending)}
