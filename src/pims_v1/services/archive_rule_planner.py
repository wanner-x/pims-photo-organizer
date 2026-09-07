from __future__ import annotations

import re

from pims_v1.services.dirname_parser import DEFAULT_MIN_CONFIDENCE, parse_dirname


GENERIC_SOURCE_PARTS = {
    "archive",
    "d:",
    "e:",
    "library",
    "nas",
    "pc",
    "photos",
    "personal_folder",
    "图册",
    "图册整理",
    "本地图册",
    "网络写真集",
}
METADATA_PATTERN = re.compile(r"\[[^\]]*(?:\d+\s*[pPvV]|\d+(?:\.\d+)?\s*(?:KB|MB|GB|TB|K|M|G|T))[^\]]*\]")
BRACKET_BRAND_PATTERN = re.compile(r"^\[(?P<brand>[^\]]+)\]")
VOLUME_PATTERN = re.compile(r"\bVOL\.?\s*\d+\b", re.IGNORECASE)


def _source_path_parts(source_root: str) -> list[str]:
    normalized = source_root.replace("\\", "/").strip("/")
    return [part for part in normalized.split("/") if part]


def _category_from_parent_or_title(
    *,
    parent_name: str,
    folder_name: str,
    parsed_category: str | None = None,
    parsed_confidence: float = 0.0,
) -> tuple[str, list[str], float | None]:
    matched_rules: list[str] = []
    if parent_name and parent_name.casefold() not in GENERIC_SOURCE_PARTS:
        matched_rules.append("parent_directory_match")
        return parent_name, matched_rules, None

    brand_match = BRACKET_BRAND_PATTERN.match(folder_name)

    if parsed_category and parsed_confidence >= DEFAULT_MIN_CONFIDENCE:
        matched_rules.append("dirname_parser_match")
        if brand_match and brand_match.group("brand") == parsed_category:
            matched_rules.append("title_brand_prefix_match")
        return parsed_category, matched_rules, parsed_confidence

    if brand_match:
        matched_rules.append("title_brand_prefix_match")
        return brand_match.group("brand"), matched_rules, None

    matched_rules.append("fallback_folder_name")
    return folder_name, matched_rules, None


def _metadata_tokens(folder_name: str) -> list[str]:
    tokens = [match.group(0).strip("[]") for match in METADATA_PATTERN.finditer(folder_name)]
    for match in VOLUME_PATTERN.finditer(folder_name):
        token = match.group(0).replace(" ", "")
        if token not in tokens:
            tokens.insert(0, token)
    return tokens


def _series_brand(*, category: str, folder_name: str, matched_rules: list[str]) -> str | None:
    if "title_brand_prefix_match" in matched_rules:
        return category
    if folder_name.startswith(category):
        return category
    return None


def plan_archive_from_source_root(source_root: str) -> dict[str, object]:
    parts = _source_path_parts(source_root)
    folder_name = parts[-1] if parts else source_root
    parent_name = parts[-2] if len(parts) >= 2 else ""
    parsed = parse_dirname(folder_name)
    category, matched_rules, parsed_confidence = _category_from_parent_or_title(
        parent_name=parent_name,
        folder_name=folder_name,
        parsed_category=parsed.archive_category,
        parsed_confidence=parsed.confidence,
    )
    matched_rules.extend(rule for rule in parsed.matched_rules if rule not in matched_rules)
    metadata = {
        "has_volume": "VOL." in folder_name.upper(),
        "has_metadata_suffix": bool(METADATA_PATTERN.search(folder_name)),
        "metadata_tokens": _metadata_tokens(folder_name),
        "series_brand": _series_brand(category=category, folder_name=folder_name, matched_rules=matched_rules),
        "source_parts": parts,
        "category_type": parsed.category_type,
        "parsed": parsed.metadata,
        "parsed_confidence": parsed.confidence,
    }
    if "parent_directory_match" in matched_rules:
        confidence = 0.95
    elif parsed_confidence is not None:
        confidence = parsed_confidence
    else:
        confidence = 0.82
    return {
        "category": category,
        "title": folder_name,
        "archive_category": category,
        "archive_title": folder_name,
        "archive_path": None,
        "confidence": confidence,
        "matched_rules": matched_rules,
        "metadata": metadata,
        "risk_flags": [],
        "decision_reason": f"rule planner selected category={category} title={folder_name}",
    }
