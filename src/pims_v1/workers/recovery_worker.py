from pims_v1.services.task_service import recover_stale_status


def recover_task_snapshot(task_snapshot: dict) -> dict:
    return recover_stale_status(task_snapshot, stale_after_seconds=300)
