"""Pluggable NSFW detection backends for the R18 visual scan chain.

The unified interface takes a list of image paths and returns, per image, an
NSFW probability plus a coarse label. Two backends are provided:

- ``heuristic``: the pre-existing skin-ratio heuristic, moved here verbatim.
  This stays the default so the scan chain behaves exactly as before unless
  the ONNX backend is explicitly enabled.
- ``onnx``: local inference with the NudeNet ONNX classifier (256x256 RGB
  input, softmax over [unsafe, safe]). The model file lives in a git-ignored
  directory (``data/models/`` by default) and is only loaded when the backend
  is explicitly selected.

Selection is driven by ``PIMS_NSFW_BACKEND`` (default ``heuristic``). The
legacy ``PIMS_R18_PROVIDER`` value still wins when it names a concrete
backend, so existing configurations keep working unchanged.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from PIL import Image

from pims_v1.config import settings
from pims_v1.services.image_open_service import ImageProcessingError, safe_image_open

LABEL_SAFE = "safe"
LABEL_NSFW = "nsfw_suspected"
LABEL_ERROR = "error"

# Same per-image label threshold the heuristic has always used. For the ONNX
# backend the score is a real class probability; the series-level decision
# still applies settings.r18_high_threshold / r18_review_threshold on top.
DEFAULT_LABEL_THRESHOLD = 0.55

# Skin-ratio heuristics are scale invariant, so downscale to a small fixed
# analysis size before the per-pixel scan. This keeps the pure-Python loop
# bounded (a few thousand pixels) regardless of the source resolution.
_ANALYSIS_SIZE = (128, 128)

# NudeNet v0 classifier: input NHWC float32 /255, output softmax [unsafe, safe].
_NUDENET_INPUT_SIZE = (256, 256)
_NUDENET_UNSAFE_INDEX = 0


class NsfwBackendUnavailableError(ValueError):
    """Raised when an explicitly requested backend cannot be constructed.

    Subclasses ValueError so existing API/CLI error handling (HTTP 400 on
    ValueError) reports the problem instead of crashing with a 500.
    """


@dataclass(frozen=True)
class NsfwDetection:
    path: Path
    nsfw_probability: float
    label: str
    reason: str
    backend: str


class NsfwDetector(Protocol):
    backend_name: str

    def detect(self, paths: Sequence[Path | str]) -> list[NsfwDetection]:
        ...


class HeuristicNsfwDetector:
    """Skin-ratio heuristic (previous default), unchanged behaviour."""

    backend_name = "heuristic"

    def detect(self, paths: Sequence[Path | str]) -> list[NsfwDetection]:
        return [self._detect_one(Path(raw_path)) for raw_path in paths]

    def _detect_one(self, path: Path) -> NsfwDetection:
        try:
            with safe_image_open(path, prescale=_ANALYSIS_SIZE) as image:
                rgb = image.convert("RGB")
                rgb.thumbnail(_ANALYSIS_SIZE)
                score = _estimate_skin_ratio_score(rgb)
        except ImageProcessingError as exc:
            return NsfwDetection(
                path=path,
                nsfw_probability=0.0,
                label=LABEL_ERROR,
                reason=str(exc),
                backend=self.backend_name,
            )
        return NsfwDetection(
            path=path,
            nsfw_probability=score,
            label=LABEL_NSFW if score >= DEFAULT_LABEL_THRESHOLD else LABEL_SAFE,
            reason=f"skin_ratio={score:.3f}",
            backend=self.backend_name,
        )


class OnnxNsfwDetector:
    """Local NudeNet ONNX classifier inference (CPU)."""

    backend_name = "onnx"

    def __init__(
        self,
        model_path: str | Path | None = None,
        *,
        label_threshold: float = DEFAULT_LABEL_THRESHOLD,
        batch_size: int = 8,
    ) -> None:
        resolved = Path(model_path or settings.nsfw_onnx_model_path)
        if not resolved.is_file():
            raise NsfwBackendUnavailableError(
                f"NSFW ONNX model not found: {resolved}. "
                "Download it with scripts/download_nsfw_model.py or set PIMS_NSFW_ONNX_MODEL_PATH."
            )
        try:
            import numpy  # noqa: F401
            import onnxruntime
        except ImportError as exc:
            raise NsfwBackendUnavailableError(
                f"onnxruntime/numpy is required for the onnx NSFW backend: {exc}"
            ) from exc

        self.model_path = resolved
        self.label_threshold = label_threshold
        self.batch_size = max(1, batch_size)
        session_options = onnxruntime.SessionOptions()
        # The 2019 NudeNet export triggers benign graph-input warnings on every
        # session; only surface real errors.
        session_options.log_severity_level = 3
        self._session = onnxruntime.InferenceSession(
            str(resolved), sess_options=session_options, providers=["CPUExecutionProvider"]
        )
        input_meta = self._session.get_inputs()[0]
        self._input_name = input_meta.name
        shape = input_meta.shape
        # NHWC with static spatial dims when the model declares them; fall back
        # to the published NudeNet input size for dynamic axes.
        if len(shape) == 4 and isinstance(shape[1], int) and isinstance(shape[2], int):
            self._input_size = (int(shape[2]), int(shape[1]))
        else:
            self._input_size = _NUDENET_INPUT_SIZE

    def _preprocess(self, path: Path):
        import numpy

        with safe_image_open(path, prescale=self._input_size) as image:
            rgb = image.convert("RGB").resize(self._input_size, Image.BILINEAR)
        return numpy.asarray(rgb, dtype=numpy.float32) / 255.0

    def detect(self, paths: Sequence[Path | str]) -> list[NsfwDetection]:
        import numpy

        ordered_paths = [Path(raw_path) for raw_path in paths]
        detections: dict[int, NsfwDetection] = {}
        pending: list[tuple[int, Path, object]] = []

        for index, path in enumerate(ordered_paths):
            try:
                pending.append((index, path, self._preprocess(path)))
            except ImageProcessingError as exc:
                detections[index] = NsfwDetection(
                    path=path,
                    nsfw_probability=0.0,
                    label=LABEL_ERROR,
                    reason=str(exc),
                    backend=self.backend_name,
                )

        for start in range(0, len(pending), self.batch_size):
            chunk = pending[start : start + self.batch_size]
            batch = numpy.stack([array for _, _, array in chunk])
            try:
                outputs = self._session.run(None, {self._input_name: batch})[0]
            except Exception as exc:  # pragma: no cover - defensive per-batch guard
                for index, path, _ in chunk:
                    detections[index] = NsfwDetection(
                        path=path,
                        nsfw_probability=0.0,
                        label=LABEL_ERROR,
                        reason=f"onnx inference failed: {exc}",
                        backend=self.backend_name,
                    )
                continue
            for (index, path, _), row in zip(chunk, outputs):
                probability = float(row[_NUDENET_UNSAFE_INDEX])
                detections[index] = NsfwDetection(
                    path=path,
                    nsfw_probability=probability,
                    label=LABEL_NSFW if probability >= self.label_threshold else LABEL_SAFE,
                    reason=f"nsfw_probability={probability:.3f} (nudenet onnx classifier)",
                    backend=self.backend_name,
                )

        return [detections[index] for index in range(len(ordered_paths))]


def detection_to_moderation_result(detection: NsfwDetection) -> dict[str, object]:
    """Convert a detection into the legacy moderation dict shape."""
    return {
        "label": detection.label,
        "score": detection.nsfw_probability,
        "reason": detection.reason,
        "provider": detection.backend,
    }


def resolve_nsfw_backend_name(provider_name: str = "auto") -> str:
    """Map the legacy provider setting plus PIMS_NSFW_BACKEND to a backend."""
    normalized = (provider_name or "").strip().lower()
    if normalized in {"", "auto"}:
        configured = (settings.nsfw_backend or "").strip().lower()
        return configured or "heuristic"
    return normalized


def build_nsfw_detector(
    backend_name: str = "auto",
    *,
    model_path: str | Path | None = None,
) -> NsfwDetector:
    resolved = resolve_nsfw_backend_name(backend_name)
    if resolved == "heuristic":
        return HeuristicNsfwDetector()
    if resolved == "onnx":
        return OnnxNsfwDetector(model_path=model_path)
    raise ValueError(f"Unsupported NSFW backend: {backend_name}")


def _estimate_skin_ratio_score(image: Image.Image) -> float:
    width, height = image.size
    total_pixels = width * height
    if total_pixels == 0:
        return 0.0
    skin_pixels = 0
    raw = image.tobytes()
    for offset in range(0, len(raw), 3):
        red = raw[offset]
        green = raw[offset + 1]
        blue = raw[offset + 2]
        maximum = red if red > green else green
        if blue > maximum:
            maximum = blue
        minimum = red if red < green else green
        if blue < minimum:
            minimum = blue
        if (
            red > 95
            and green > 40
            and blue > 20
            and (maximum - minimum) > 15
            and abs(red - green) > 15
            and red > green
            and red > blue
        ):
            skin_pixels += 1
    return skin_pixels / total_pixels
