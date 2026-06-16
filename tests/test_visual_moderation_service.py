from pathlib import Path

from PIL import Image

from pims_v1.services.visual_moderation_service import HeuristicVisualModerationClient, build_visual_moderation_client


def test_build_visual_moderation_client_auto_falls_back_to_heuristic():
    client = build_visual_moderation_client(provider_name="auto")

    assert isinstance(client, HeuristicVisualModerationClient)


def test_heuristic_visual_moderation_flags_skin_tone_image(tmp_path):
    image_path = tmp_path / "skin.jpg"
    Image.new("RGB", (48, 48), color=(220, 180, 160)).save(image_path)

    result = HeuristicVisualModerationClient().moderate_image(image_path)

    assert result["provider"] == "heuristic"
    assert result["label"] == "nsfw_suspected"
    assert result["score"] >= 0.8
    assert "skin_ratio=" in result["reason"]


def test_heuristic_visual_moderation_keeps_blue_image_below_review_threshold(tmp_path):
    image_path = tmp_path / "safe.jpg"
    Image.new("RGB", (48, 48), color=(40, 80, 180)).save(image_path)

    result = HeuristicVisualModerationClient().moderate_image(image_path)

    assert result["provider"] == "heuristic"
    assert result["label"] == "safe"
    assert result["score"] < 0.55


def test_heuristic_visual_moderation_returns_error_for_decompression_bomb(tmp_path, monkeypatch):
    import pims_v1.services.image_open_service as image_open_service

    image_path = tmp_path / "huge.jpg"
    Image.new("RGB", (48, 48), color=(220, 180, 160)).save(image_path)

    def raise_decompression_bomb(_path):
        raise Image.DecompressionBombWarning("too many pixels")

    monkeypatch.setattr(image_open_service.Image, "open", raise_decompression_bomb)

    result = HeuristicVisualModerationClient().moderate_image(image_path)

    assert result["provider"] == "heuristic"
    assert result["label"] == "error"
    assert result["score"] == 0.0
    assert "too many pixels" in result["reason"]
