from pims_v1.services.ai_naming_service import build_series_title_prompt


def test_build_series_title_prompt_uses_source_and_sample_names():
    prompt = build_series_title_prompt(
        source_root="/library/model-a/set-01",
        file_names=["001.jpg", "002.jpg"],
    )

    assert "set-01" in prompt
    assert "001.jpg" in prompt
    assert "002.jpg" in prompt
    assert "只返回一个中文标题" in prompt
