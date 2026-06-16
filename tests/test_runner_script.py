from pathlib import Path


def test_full_detection_runner_sends_wechat_notifications():
    script = Path("scripts/run_full_detection.ps1").read_text(encoding="utf-8")

    assert "function Invoke-WechatNotify" in script
    assert '"notify-wechat"' in script
    assert "PIMS full detection started" in script
    assert "PIMS full detection round failed" in script
    assert "PIMS full detection complete" in script
