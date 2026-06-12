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


def _reserve_notification(
    *,
    session: Session,
    dedupe_key: str,
    channel: str,
    event_type: str,
    subject_type: str,
    subject_id: int,
) -> NotificationRecord | None:
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
        "PIMS 照片整理提醒\n"
        f"有新的重复文件隔离批次需要批量审批：批次 #{batch_id}\n"
        f"待审批操作数：{operations}\n"
        "请打开审核页查看“已存在位置”和“重复位置”，确认无误后再批量确认。"
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
