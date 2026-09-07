from pathlib import Path

import pytest
from PIL import Image

from pims_v1.services.nsfw_detector import (
    LABEL_ERROR,
    LABEL_NSFW,
    LABEL_SAFE,
    HeuristicNsfwDetector,
    NsfwBackendUnavailableError,
    NsfwDetection,
    OnnxNsfwDetector,
    build_nsfw_detector,
    resolve_nsfw_backend_name,
)

ONNX_MODEL_PATH = Path("data/models/nudenet_classifier_model.onnx")

try:  # noqa: SIM105
    import onnxruntime  # noqa: F401

    HAS_ONNXRUNTIME = True
except ImportError:
    HAS_ONNXRUNTIME = False

onnx_available = pytest.mark.skipif(
    not (HAS_ONNXRUNTIME and ONNX_MODEL_PATH.is_file()),
    reason="onnxruntime or the NudeNet model file is not available",
)


def make_images(tmp_path):
    skin_path = tmp_path / "skin.jpg"
    Image.new("RGB", (48, 48), color=(220, 180, 160)).save(skin_path)
    blue_path = tmp_path / "safe.jpg"
    Image.new("RGB", (48, 48), color=(40, 80, 180)).save(blue_path)
    return skin_path, blue_path


def test_heuristic_detector_scores_batch_in_input_order(tmp_path):
    skin_path, blue_path = make_images(tmp_path)

    detections = HeuristicNsfwDetector().detect([blue_path, skin_path, str(blue_path)])

    assert [detection.path for detection in detections] == [blue_path, skin_path, blue_path]
    assert detections[0].label == LABEL_SAFE
    assert detections[0].nsfw_probability < 0.55
    assert detections[1].label == LABEL_NSFW
    assert detections[1].nsfw_probability >= 0.8
    assert detections[1].reason.startswith("skin_ratio=")
    assert all(detection.backend == "heuristic" for detection in detections)


def test_heuristic_detector_reports_unreadable_file_as_error(tmp_path):
    broken_path = tmp_path / "broken.jpg"
    broken_path.write_bytes(b"not an image")

    detection = HeuristicNsfwDetector().detect([broken_path])[0]

    assert detection.label == LABEL_ERROR
    assert detection.nsfw_probability == 0.0
    assert detection.backend == "heuristic"


def test_build_nsfw_detector_defaults_to_heuristic():
    detector = build_nsfw_detector("auto")

    assert isinstance(detector, HeuristicNsfwDetector)


def test_resolve_backend_uses_nsfw_backend_setting_when_provider_is_auto(monkeypatch):
    monkeypatch.setattr("pims_v1.services.nsfw_detector.settings.nsfw_backend", "onnx")

    assert resolve_nsfw_backend_name("auto") == "onnx"
    assert resolve_nsfw_backend_name("") == "onnx"
    # An explicit legacy provider still wins over the new setting.
    assert resolve_nsfw_backend_name("heuristic") == "heuristic"


def test_build_nsfw_detector_rejects_unknown_backend():
    with pytest.raises(ValueError):
        build_nsfw_detector("cloud-vision")


def test_onnx_detector_reports_missing_model_file(tmp_path):
    with pytest.raises(NsfwBackendUnavailableError):
        OnnxNsfwDetector(model_path=tmp_path / "missing.onnx")


def test_visual_moderation_client_routes_through_nsfw_backend_setting(monkeypatch, tmp_path):
    from pims_v1.services.visual_moderation_service import build_visual_moderation_client

    class FakeDetector:
        backend_name = "fake"

        def detect(self, paths):
            return [
                NsfwDetection(
                    path=Path(path),
                    nsfw_probability=0.42,
                    label=LABEL_SAFE,
                    reason="fake",
                    backend=self.backend_name,
                )
                for path in paths
            ]

    monkeypatch.setattr("pims_v1.services.nsfw_detector.settings.nsfw_backend", "onnx")
    monkeypatch.setattr(
        "pims_v1.services.visual_moderation_service.build_nsfw_detector",
        lambda backend_name: FakeDetector(),
    )

    client = build_visual_moderation_client("auto")
    result = client.moderate_image(tmp_path / "any.jpg")

    assert client.provider_name == "fake"
    assert result == {"label": LABEL_SAFE, "score": 0.42, "reason": "fake", "provider": "fake"}


@onnx_available
def test_onnx_detector_smoke_scores_safe_synthetic_image(tmp_path):
    _, blue_path = make_images(tmp_path)

    detector = OnnxNsfwDetector(model_path=ONNX_MODEL_PATH)
    detections = detector.detect([blue_path, blue_path])

    assert len(detections) == 2
    for detection in detections:
        assert detection.backend == "onnx"
        assert 0.0 <= detection.nsfw_probability <= 1.0
        assert detection.label == LABEL_SAFE
        assert "nsfw_probability=" in detection.reason


@onnx_available
def test_onnx_detector_handles_unreadable_file_without_breaking_batch(tmp_path):
    _, blue_path = make_images(tmp_path)
    broken_path = tmp_path / "broken.jpg"
    broken_path.write_bytes(b"not an image")

    detections = OnnxNsfwDetector(model_path=ONNX_MODEL_PATH).detect([broken_path, blue_path])

    assert detections[0].label == LABEL_ERROR
    assert detections[1].label == LABEL_SAFE


@onnx_available
def test_build_visual_moderation_client_onnx_provider_end_to_end(monkeypatch, tmp_path):
    from pims_v1.services.visual_moderation_service import build_visual_moderation_client

    monkeypatch.setattr(
        "pims_v1.services.nsfw_detector.settings.nsfw_onnx_model_path",
        str(ONNX_MODEL_PATH),
    )
    _, blue_path = make_images(tmp_path)

    client = build_visual_moderation_client("onnx")
    result = client.moderate_image(blue_path)

    assert client.provider_name == "onnx"
    assert result["provider"] == "onnx"
    assert result["label"] == LABEL_SAFE
    assert 0.0 <= float(result["score"]) <= 1.0
