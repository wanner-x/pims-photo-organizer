from pims_v1.services.task_service import recover_stale_status


def test_recover_stale_running_tasks():
    task = {"status": "running", "heartbeat_age_seconds": 1200}

    recovered = recover_stale_status(task, stale_after_seconds=300)

    assert recovered["status"] == "pending"
    assert recovered["attempts"] == 1
