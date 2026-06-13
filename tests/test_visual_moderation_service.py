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
