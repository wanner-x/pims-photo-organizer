"""Read-only comparison of heuristic vs onnx NSFW verdicts on real samples.

Samples image paths from series_moderation_samples in data/pims.db (opened
read-only), keeps the ones whose files are still accessible, runs both
backends, and writes a markdown comparison table. Never writes to the DB.

Usage:
    python scripts/compare_nsfw_backends.py [--limit 20] [--out reports/nsfw_backend_comparison.md]
"""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from pims_v1.services.nsfw_detector import HeuristicNsfwDetector, OnnxNsfwDetector

DB_PATH = "data/pims.db"

SAMPLE_QUERY = """
SELECT s.sample_path, s.label, s.score, s.run_id
FROM series_moderation_samples AS s
WHERE s.label = ?
GROUP BY s.sample_path
ORDER BY s.id DESC
LIMIT ?
"""


def pick_paths(cursor: sqlite3.Cursor, label: str, want: int, probe_limit: int) -> list[tuple[str, str, float]]:
    rows = cursor.execute(SAMPLE_QUERY, (label, probe_limit)).fetchall()
    picked: list[tuple[str, str, float]] = []
    for sample_path, prior_label, prior_score, _run_id in rows:
        try:
            accessible = Path(sample_path).is_file()
        except OSError:
            accessible = False
        if accessible:
            picked.append((sample_path, prior_label, float(prior_score or 0.0)))
        if len(picked) >= want:
            break
    return picked


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--out", default="reports/nsfw_backend_comparison.md")
    args = parser.parse_args()

    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    cursor = conn.cursor()
    per_bucket = max(1, args.limit // 2)
    flagged = pick_paths(cursor, "nsfw_suspected", per_bucket, probe_limit=300)
    safe = pick_paths(cursor, "safe", args.limit - len(flagged), probe_limit=300)
    conn.close()

    samples = flagged + safe
    if not samples:
        print("no accessible sample files found (NAS offline?); comparison skipped")
        return 2

    heuristic = HeuristicNsfwDetector()
    onnx = OnnxNsfwDetector()
    paths = [Path(sample_path) for sample_path, _, _ in samples]
    heuristic_results = heuristic.detect(paths)
    onnx_results = onnx.detect(paths)

    agree = 0
    lines = [
        "# NSFW 后端对照抽样（heuristic vs onnx）",
        "",
        f"样本来源：`series_moderation_samples`（只读），可访问文件 {len(samples)} 个",
        f"（历史 nsfw_suspected {len(flagged)} 个 / 历史 safe {len(safe)} 个）。",
        "",
        "| # | 历史标签 | heuristic 概率/标签 | onnx 概率/标签 | 一致 | 文件 |",
        "|---|----------|--------------------|----------------|------|------|",
    ]
    for index, ((sample_path, prior_label, _prior_score), h, o) in enumerate(
        zip(samples, heuristic_results, onnx_results), start=1
    ):
        same = h.label == o.label
        agree += int(same)
        name = Path(sample_path).name
        parent = Path(sample_path).parent.name
        lines.append(
            f"| {index} | {prior_label} | {h.nsfw_probability:.3f} {h.label} | "
            f"{o.nsfw_probability:.3f} {o.label} | {'✓' if same else '✗'} | {parent}/{name} |"
        )
    lines += [
        "",
        f"标签一致率：{agree}/{len(samples)}",
        "",
        "说明：heuristic 分数是肤色像素占比（不是概率）；onnx 分数是 NudeNet 分类器的",
        "unsafe 类 softmax 概率。两者共用 0.55 的单图标签阈值。",
    ]

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"samples={len(samples)} agree={agree} -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
