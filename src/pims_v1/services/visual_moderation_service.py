"""Moderation-client facade over the pluggable NSFW detector backends.

The R18 scan chain (manual API, CLI, workflow) talks to a
``VisualModerationClient`` with a per-image ``moderate_image`` call. Detection
itself now lives in ``pims_v1.services.nsfw_detector`` behind a unified
batch interface; this module adapts detectors to the legacy client protocol.

Backend selection: an explicit ``PIMS_R18_PROVIDER`` (``heuristic``/``onnx``)
wins; when it is ``auto`` (the default), ``PIMS_NSFW_BACKEND`` decides and
defaults to ``heuristic``, so behaviour is unchanged unless the ONNX backend
is explicitly enabled.
"""
from __future__ import annotations

from pathlib import Path
from typing import Protocol

from pims_v1.services.nsfw_detector import (
    HeuristicNsfwDetector,
    NsfwDetector,
    build_nsfw_detector,
    detection_to_moderation_result,
    resolve_nsfw_backend_name,
)


class VisualModerationClient(Protocol):
    provider_name: str

    def moderate_image(self, path: Path) -> dict[str, object]:
        ...


class DetectorVisualModerationClient:
    """Adapts any NsfwDetector to the VisualModerationClient protocol."""

    def __init__(self, detector: NsfwDetector) -> None:
        self.detector = detector
        self.provider_name = detector.backend_name

    def moderate_image(self, path: Path) -> dict[str, object]:
        return detection_to_moderation_result(self.detector.detect([path])[0])


class HeuristicVisualModerationClient(DetectorVisualModerationClient):
    """Skin-ratio heuristic client (previous default), same behaviour."""

    def __init__(self) -> None:
        super().__init__(HeuristicNsfwDetector())


def build_visual_moderation_client(provider_name: str = "auto") -> VisualModerationClient:
    backend_name = resolve_nsfw_backend_name(provider_name)
    if backend_name == "heuristic":
        return HeuristicVisualModerationClient()
    return DetectorVisualModerationClient(build_nsfw_detector(backend_name))
