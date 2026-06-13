from __future__ import annotations

from pathlib import Path
from typing import Protocol

from PIL import Image


class VisualModerationClient(Protocol):
    provider_name: str

    def moderate_image(self, path: Path) -> dict[str, object]:
        ...


class HeuristicVisualModerationClient:
    provider_name = "heuristic"

    def moderate_image(self, path: Path) -> dict[str, object]:
        with Image.open(path) as image:
            rgb = image.convert("RGB")
            score = _estimate_skin_ratio_score(rgb)
        return {
            "label": "nsfw_suspected" if score >= 0.55 else "safe",
            "score": score,
            "reason": f"skin_ratio={score:.3f}",
            "provider": self.provider_name,
        }


def build_visual_moderation_client(provider_name: str = "auto") -> VisualModerationClient:
    normalized = provider_name.strip().lower()
    if normalized in {"", "auto", "heuristic"}:
        return HeuristicVisualModerationClient()
    raise ValueError(f"Unsupported visual moderation provider: {provider_name}")


def _estimate_skin_ratio_score(image: Image.Image) -> float:
    width, height = image.size
    if width == 0 or height == 0:
        return 0.0
    skin_pixels = 0
    total_pixels = width * height
    pixels = image.load()
    for x in range(width):
        for y in range(height):
            red, green, blue = pixels[x, y]
            maximum = max(red, green, blue)
            minimum = min(red, green, blue)
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
