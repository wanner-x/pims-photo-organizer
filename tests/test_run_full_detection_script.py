from pathlib import Path


def test_full_detection_script_enables_ai_suggestions_by_default():
    script = Path("scripts/run_full_detection.ps1").read_text(encoding="utf-8")

    assert "[int]$AiSuggestLimit = 50" in script
    assert '"--ai-suggest-limit", "$AiSuggestLimit"' in script
    assert "[int]$R18ScanLimit = 50" in script
    assert '"--r18-scan-limit", "$R18ScanLimit"' in script
    assert "[int]$AutoArchiveLimit = 20" in script
    assert '"--auto-archive-limit", "$AutoArchiveLimit"' in script
