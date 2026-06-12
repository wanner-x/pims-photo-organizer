from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from pims_v1.db import Base
from pims_v1.models import notification
from pims_v1.services.notification_service import notify_duplicate_approval_needed


def make_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", future=True)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    return session_factory()


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
