from pathlib import Path


def test_full_detection_script_enables_ai_suggestions_by_default():
    script = Path("scripts/run_full_detection.ps1").read_text(encoding="utf-8")

    assert "[int]$AiSuggestLimit = 50" in script
    assert '"--ai-suggest-limit", "$AiSuggestLimit"' in script
    assert "[int]$R18ScanLimit = 50" in script
    assert '"--r18-scan-limit", "$R18ScanLimit"' in script
    assert "[int]$AutoArchiveLimit = 20" in script
    assert '"--auto-archive-limit", "$AutoArchiveLimit"' in script
    assert "[int]$SimilarLimit = 0" in script
    assert '"--similar-limit", "$SimilarLimit"' in script
    assert "[int]$SeriesLimit = 0" in script
    assert '"--series-limit", "$SeriesLimit"' in script
    assert "try {" in script
    assert "catch {" in script
    assert "Round $round failed" in script
    assert "===== Round $round completed =====" in script
    assert "Full detection stopped. exit_code=$exitCode" in script
