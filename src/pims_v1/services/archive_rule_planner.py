from __future__ import annotations

import re


GENERIC_SOURCE_PARTS = {
    "archive",
    "d:",
    "e:",
    "library",
    "nas",
    "pc",
    "personal_folder",
    "图册",
    "图册整理",
    "本地图册",
    "网络写真集",
}
METADATA_PATTERN = re.compile(r"\[[^\]]*(?:\d+\s*[pPvV]|\d+(?:\.\d+)?\s*(?:KB|MB|GB|TB|K|M|G|T))[^\]]*\]")
BRACKET_BRAND_PATTERN = re.compile(r"^\[(?P<brand>[^\]]+)\]")


def _source_path_parts(source_root: str) -> list[str]:
    normalized = source_root.replace("\\", "/").strip("/")
    return [part for part in normalized.split("/") if part]


def _category_from_parent_or_title(*, parent_name: str, folder_name: str) -> tuple[str, list[str]]:
    matched_rules: list[str] = []
    if parent_name and parent_name.casefold() not in GENERIC_SOURCE_PARTS:
        matched_rules.append("parent_directory_match")
        return parent_name, matched_rules

    brand_match = BRACKET_BRAND_PATTERN.match(folder_name)
    if brand_match:
        matched_rules.append("title_brand_prefix_match")
        return brand_match.group("brand"), matched_rules

    matched_rules.append("fallback_folder_name")
    return folder_name, matched_rules


def plan_archive_from_source_root(source_root: str) -> dict[str, object]:
    parts = _source_path_parts(source_root)
    folder_name = parts[-1] if parts else source_root
    parent_name = parts[-2] if len(parts) >= 2 else ""
    category, matched_rules = _category_from_parent_or_title(parent_name=parent_name, folder_name=folder_name)
    metadata = {
        "has_volume": "VOL." in folder_name.upper(),
        "has_metadata_suffix": bool(METADATA_PATTERN.search(folder_name)),
        "source_parts": parts,
    }
    confidence = 0.95 if "parent_directory_match" in matched_rules else 0.82
    return {
        "category": category,
        "title": folder_name,
        "archive_path": None,
        "confidence": confidence,
        "matched_rules": matched_rules,
        "metadata": metadata,
        "risk_flags": [],
        "decision_reason": f"rule planner selected category={category} title={folder_name}",
    }
