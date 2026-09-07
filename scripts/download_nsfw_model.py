"""Download the NudeNet ONNX classifier into data/models/.

The plain browser_download_url for the 2019 "v0" release now serves an HTML
interstitial page to non-browser clients, so we resolve the asset through the
GitHub REST API and request application/octet-stream explicitly.

Usage:
    python scripts/download_nsfw_model.py [target_path]
"""
from __future__ import annotations

import sys
from pathlib import Path

import httpx

RELEASE_API = "https://api.github.com/repos/notAI-tech/NudeNet/releases/tags/v0"
ASSET_NAME = "classifier_model.onnx"
DEFAULT_TARGET = Path("data/models/nudenet_classifier_model.onnx")


def main() -> int:
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_TARGET
    target.parent.mkdir(parents=True, exist_ok=True)

    with httpx.Client(follow_redirects=True, timeout=120.0) as client:
        release = client.get(RELEASE_API, headers={"Accept": "application/vnd.github+json"})
        release.raise_for_status()
        assets = {asset["name"]: asset for asset in release.json().get("assets", [])}
        if ASSET_NAME not in assets:
            print(f"asset {ASSET_NAME} not found in release; available: {sorted(assets)}")
            return 1
        asset = assets[ASSET_NAME]
        print(f"asset id={asset['id']} size={asset['size']} bytes")

        with client.stream(
            "GET",
            f"https://api.github.com/repos/notAI-tech/NudeNet/releases/assets/{asset['id']}",
            headers={"Accept": "application/octet-stream"},
        ) as response:
            response.raise_for_status()
            written = 0
            with open(target, "wb") as handle:
                for chunk in response.iter_bytes(chunk_size=1 << 20):
                    handle.write(chunk)
                    written += len(chunk)
        print(f"written={written} bytes -> {target}")
        if written != asset["size"]:
            print("WARNING: size mismatch, file may be corrupt")
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
