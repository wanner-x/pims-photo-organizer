import json
from collections.abc import Callable
from urllib import request

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from pims_v1.models.notification import NotificationRecord

WechatSender = Callable[[str, str], dict]


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


def notify_workflow_event(
    *,
    webhook_url: str | None,
    title: str,
    lines: list[str] | tuple[str, ...] = (),
    sender: WechatSender = send_wechat_text_message,
) -> dict[str, int]:
    if not webhook_url:
        return {"sent": 0, "failed": 0, "skipped": 1}

    content = "\n".join([title, *[line for line in lines if line]])
    try:
        sender(webhook_url, content)
    except Exception:
        return {"sent": 0, "failed": 1, "skipped": 0}
    return {"sent": 1, "failed": 0, "skipped": 0}


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
            NotificationRecord.status != "failed",
        )
        .first()
    )
    if existing_for_subject is not None:
        return None

    existing = session.query(NotificationRecord).filter(NotificationRecord.dedupe_key == dedupe_key).one_or_none()
    if existing and existing.status != "failed":
        return None
    if existing and existing.status == "failed":
        updated = (
            session.query(NotificationRecord)
            .filter(NotificationRecord.dedupe_key == dedupe_key, NotificationRecord.status == "failed")
            .update({"status": "sending", "last_error": None})
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


def notify_duplicate_approval_needed(
    *,
    session: Session,
    webhook_url: str,
    batch_id: int,
    operations: int,
    review_url: str = "http://127.0.0.1:8000/review-ui",
    sender: WechatSender = send_wechat_text_message,
) -> dict[str, int]:
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

    content = (
        "PIMS 照片整理待审核\n"
        f"批次 #{batch_id}：发现 {operations} 个疑似重复文件待审核。\n"
        "系统不会自动删除文件；确认后才会把重复副本移动到隔离区。\n"
        "请在审核页对比“已存在位置”和“重复位置”，确认无误后再批量处理。\n"
        f"审核入口：{review_url}\n"
        "如果该批次已经处理，可以忽略本提醒。"
    )
    try:
        sender(webhook_url, content)
    except Exception as exc:
        record.status = "failed"
        record.last_error = str(exc)[:2048]
        session.commit()
        return {"sent": 0, "failed": 1, "skipped": 0}

    record.status = "sent"
    record.last_error = None
    session.commit()
    return {"sent": 1, "failed": 0, "skipped": 0}
