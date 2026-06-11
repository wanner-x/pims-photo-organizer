def recover_stale_status(task: dict, stale_after_seconds: int) -> dict:
    if task["status"] == "running" and task["heartbeat_age_seconds"] > stale_after_seconds:
        return {"status": "pending", "attempts": task.get("attempts", 0) + 1}
    return {"status": task["status"], "attempts": task.get("attempts", 0)}
