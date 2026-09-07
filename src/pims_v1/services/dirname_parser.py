"""Deterministic directory-name parser for archive rule planning.

Parses a raw series directory name (single path segment) into structured
fields used by the archive rule planner:

- ``category_type``: person | studio | project | unknown
- ``archive_category``: first-level archive directory (person or brand name)
- ``archive_title``: the original name, spec suffixes preserved
- ``metadata``: persons, studio/project name, VOL/NO/EX numbers, date,
  themes, spec info (pictures/videos/size) and R18 flag
- ``confidence``: 0-1, higher when structural rules match unambiguously

Pattern priority (highest first):

1. Full-width bracket project structure: 【企划】-【VOL.001】-【人物】-【主题】-【规格】
2. Leading bracket brand prefix: [IMISS爱蜜社] 2025.08.27 VOL.800 许诺Sabrina [86+1P]
3. Keyword classified leading token: ``紧急企划 VOL.002 ...`` / ``蜜桃社 2024 ...``
4. Person-style leading name: ``雪琪SAMA JK白丝 [46P208MB]``
5. Unknown fallback (low confidence, callers keep their legacy behavior)
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re


PICTURES_PATTERN = re.compile(r"(?<![0-9A-Za-z])(\d+(?:\+\d+)*)\s*[Pp](?![A-Za-z])")
VIDEOS_PATTERN = re.compile(r"(?<!\d)(\d+)\s*[Vv](?![A-Za-z])")
SIZE_PATTERN = re.compile(
    r"(?<!\d)(\d+(?:\.\d+)?)\s*(KB|MB|GB|TB|K|M|G|T)(?![A-Za-z])",
    re.IGNORECASE,
)
NUMBER_PATTERN = re.compile(
    r"(?<![0-9A-Za-z])(VOL|NO|EX)\s*[.．]?\s*(\d+)(?![0-9A-Za-z])",
    re.IGNORECASE,
)
DATE_PATTERN = re.compile(r"(?<!\d)((?:19|20)\d{2})[.\-_/](\d{1,2})[.\-_/](\d{1,2})(?!\d)")
R18_PATTERN = re.compile(r"(?<![0-9A-Za-z])[\[【]?\s*R[-‐]?18\s*[\]】]?(?![0-9A-Za-z])", re.IGNORECASE)
CJK_PATTERN = re.compile(r"[\u3040-\u30ff\u3400-\u9fff\uf900-\ufaff]")
BRACKET_CHUNK_PATTERN = re.compile(r"\[([^\[\]]*)\]|【([^【】]*)】")
LEADING_BRACKET_PATTERN = re.compile(r"^\s*[\[【]([^\[\]【】]+)[\]】]\s*(?P<rest>.*)$", re.DOTALL)
PROJECT_STRUCTURE_PATTERN = re.compile(r"^\s*(?:【[^【】]*】[\s\-–—_~·]*){2,}$")
TOKEN_SPLIT_PATTERN = re.compile(r"[\s\-–—_·]+")
PERSON_SPLIT_PATTERN = re.compile(r"[&＆、，,]")
SPEC_SEPARATOR_PATTERN = re.compile(r"[\s\-–—_+~,;/xX×*&]+")

STUDIO_SUFFIX_KEYWORDS = ("社", "网", "传媒", "工作室", "映画", "机构")
PROJECT_SUFFIX_KEYWORDS = ("企划",)

# Below this confidence, callers should keep their legacy/fallback behavior.
DEFAULT_MIN_CONFIDENCE = 0.5

_MAX_CONFIDENCE = 0.97


@dataclass
class DirnameParseResult:
    raw_name: str
    category_type: str
    archive_category: str
    archive_title: str
    metadata: dict[str, object]
    confidence: float
    matched_rules: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "raw_name": self.raw_name,
            "category_type": self.category_type,
            "archive_category": self.archive_category,
            "archive_title": self.archive_title,
            "metadata": self.metadata,
            "confidence": self.confidence,
            "matched_rules": list(self.matched_rules),
        }


def _size_to_mb(value: float, unit: str) -> float:
    unit = unit.upper().rstrip("B") or "M"
    factor = {"K": 1 / 1024, "M": 1.0, "G": 1024.0, "T": 1024.0 * 1024.0}[unit]
    return round(value * factor, 2)


def _is_pure_spec(text: str) -> bool:
    """True when *text* only contains picture/video/size components and separators."""
    matched = False
    remaining = text
    for pattern in (PICTURES_PATTERN, VIDEOS_PATTERN, SIZE_PATTERN):
        remaining, count = pattern.subn(" ", remaining)
        matched = matched or count > 0
    remaining = SPEC_SEPARATOR_PATTERN.sub("", remaining)
    return matched and remaining == ""


def _extract_specs(name: str) -> dict[str, object] | None:
    pictures_match = PICTURES_PATTERN.search(name)
    videos_match = VIDEOS_PATTERN.search(name)
    size_match = SIZE_PATTERN.search(name)
    if not (pictures_match or videos_match or size_match):
        return None
    raw_tokens = [
        chunk.group(1) or chunk.group(2)
        for chunk in BRACKET_CHUNK_PATTERN.finditer(name)
        if _is_pure_spec(chunk.group(1) or chunk.group(2) or "")
    ]
    specs: dict[str, object] = {
        "raw": raw_tokens,
        "pictures": None,
        "picture_parts": None,
        "videos": None,
        "size_mb": None,
        "size_raw": None,
    }
    if pictures_match:
        parts = [int(part) for part in pictures_match.group(1).split("+")]
        specs["pictures"] = sum(parts)
        specs["picture_parts"] = parts
    if videos_match:
        specs["videos"] = int(videos_match.group(1))
    if size_match:
        specs["size_mb"] = _size_to_mb(float(size_match.group(1)), size_match.group(2))
        specs["size_raw"] = size_match.group(0).strip()
    return specs


def _extract_numbers(name: str) -> list[dict[str, object]]:
    return [
        {
            "kind": match.group(1).upper(),
            "value": int(match.group(2)),
            "raw": match.group(0).strip(),
        }
        for match in NUMBER_PATTERN.finditer(name)
    ]


def _extract_date(name: str) -> dict[str, str] | None:
    match = DATE_PATTERN.search(name)
    if match is None:
        return None
    year, month, day = match.group(1), match.group(2), match.group(3)
    return {
        "raw": match.group(0),
        "normalized": f"{year}-{int(month):02d}-{int(day):02d}",
    }


def _keyword_type(text: str) -> str | None:
    if any(text.endswith(keyword) for keyword in PROJECT_SUFFIX_KEYWORDS):
        return "project"
    if any(text.endswith(keyword) for keyword in STUDIO_SUFFIX_KEYWORDS):
        return "studio"
    return None


def _strip_structural_tokens(name: str) -> str:
    """Remove spec brackets, R18 marks, dates and VOL/NO/EX tokens for tokenization."""

    def _drop_spec_chunk(match: re.Match[str]) -> str:
        content = match.group(1) or match.group(2) or ""
        return " " if _is_pure_spec(content) else match.group(0)

    stripped = BRACKET_CHUNK_PATTERN.sub(_drop_spec_chunk, name)
    stripped = R18_PATTERN.sub(" ", stripped)
    stripped = DATE_PATTERN.sub(" ", stripped)
    stripped = NUMBER_PATTERN.sub(" ", stripped)
    return stripped


def _tokens(stripped: str) -> list[str]:
    tokens = []
    for token in TOKEN_SPLIT_PATTERN.split(stripped):
        token = token.strip("[]()【】（）「」〈〉<>·-–—_~*")
        if token:
            tokens.append(token)
    return tokens


def _split_persons(token: str) -> list[str]:
    return [part.strip() for part in PERSON_SPLIT_PATTERN.split(token) if part.strip()]


def _confidence(
    base: float,
    *,
    number: bool = False,
    date: bool = False,
    spec: bool = False,
    person: bool = False,
    theme: bool = False,
    boosts: dict[str, float] | None = None,
) -> float:
    boosts = boosts or {}
    value = base
    if number:
        value += boosts.get("number", 0.0)
    if date:
        value += boosts.get("date", 0.0)
    if spec:
        value += boosts.get("spec", 0.0)
    if person:
        value += boosts.get("person", 0.0)
    if theme:
        value += boosts.get("theme", 0.0)
    return round(min(value, _MAX_CONFIDENCE), 2)


def parse_dirname(raw_name: str) -> DirnameParseResult:
    name = (raw_name or "").strip()
    archive_title = name or raw_name

    specs = _extract_specs(name)
    numbers = _extract_numbers(name)
    date = _extract_date(name)
    r18 = R18_PATTERN.search(name) is not None

    metadata: dict[str, object] = {
        "persons": [],
        "studio": None,
        "project": None,
        "numbers": numbers,
        "date": date,
        "themes": [],
        "specs": specs,
        "r18": r18,
    }
    matched_rules: list[str] = []
    if numbers:
        matched_rules.append("has_volume_number")
    if date:
        matched_rules.append("has_date")
    if specs:
        matched_rules.append("has_spec")
    if r18:
        matched_rules.append("has_r18")

    def _result(category_type: str, archive_category: str, confidence: float) -> DirnameParseResult:
        return DirnameParseResult(
            raw_name=raw_name,
            category_type=category_type,
            archive_category=archive_category,
            archive_title=archive_title,
            metadata=metadata,
            confidence=confidence,
            matched_rules=matched_rules,
        )

    if not name:
        matched_rules.append("empty_name")
        return _result("unknown", raw_name, 0.0)

    # Priority 1: full-width bracket project structure.
    structural_probe = R18_PATTERN.sub(" ", name)
    structural_probe = BRACKET_CHUNK_PATTERN.sub(
        lambda match: " " if _is_pure_spec(match.group(1) or match.group(2) or "") else match.group(0),
        structural_probe,
    ).strip()
    fullwidth_segments = [
        chunk.group(2)
        for chunk in BRACKET_CHUNK_PATTERN.finditer(name)
        if chunk.group(2) is not None
    ]
    if PROJECT_STRUCTURE_PATTERN.match(structural_probe) or (
        PROJECT_STRUCTURE_PATTERN.match(name) and len(fullwidth_segments) >= 2
    ):
        text_segments = []
        for segment in fullwidth_segments:
            segment = segment.strip()
            if not segment or _is_pure_spec(segment):
                continue
            if NUMBER_PATTERN.search(segment) and not CJK_PATTERN.search(segment):
                continue
            if DATE_PATTERN.search(segment) and not CJK_PATTERN.search(segment):
                continue
            if R18_PATTERN.fullmatch(segment):
                continue
            text_segments.append(segment)
        if text_segments:
            head = text_segments[0]
            category_type = "studio" if _keyword_type(head) == "studio" else "project"
            if category_type == "project":
                metadata["project"] = head
            else:
                metadata["studio"] = head
            if len(text_segments) >= 2:
                metadata["persons"] = _split_persons(text_segments[1])
            metadata["themes"] = text_segments[2:]
            matched_rules.insert(0, "project_fullwidth_structure")
            confidence = _confidence(
                0.82,
                number=bool(numbers),
                person=bool(metadata["persons"]),
                spec=bool(specs),
                date=bool(date),
                boosts={"number": 0.06, "person": 0.04, "spec": 0.03, "date": 0.02},
            )
            return _result(category_type, head, confidence)

    # Priority 2: leading bracket brand prefix.
    leading = LEADING_BRACKET_PATTERN.match(name)
    if leading is not None:
        content = leading.group(1).strip()
        if (
            content
            and not _is_pure_spec(content)
            and not R18_PATTERN.fullmatch(content)
            and not DATE_PATTERN.fullmatch(content)
        ):
            category_type = "project" if _keyword_type(content) == "project" else "studio"
            if category_type == "project":
                metadata["project"] = content
            else:
                metadata["studio"] = content
            rest_tokens = _tokens(_strip_structural_tokens(leading.group("rest")))
            if rest_tokens:
                metadata["persons"] = _split_persons(rest_tokens[0])
                metadata["themes"] = rest_tokens[1:]
            matched_rules.insert(0, "studio_bracket_prefix")
            confidence = _confidence(
                0.65,
                number=bool(numbers),
                date=bool(date),
                spec=bool(specs),
                person=bool(metadata["persons"]),
                boosts={"number": 0.10, "date": 0.06, "spec": 0.06, "person": 0.08},
            )
            return _result(category_type, content, confidence)

    tokens = _tokens(_strip_structural_tokens(name))
    if not tokens:
        matched_rules.append("unknown_fallback")
        return _result("unknown", name, 0.3)

    head = tokens[0]
    head_type = _keyword_type(head)

    # Priority 3: keyword classified leading token (project / studio without brackets).
    if head_type == "project":
        metadata["project"] = head
        if len(tokens) >= 2:
            metadata["persons"] = _split_persons(tokens[1])
        metadata["themes"] = tokens[2:]
        matched_rules.insert(0, "project_keyword")
        confidence = _confidence(
            0.60,
            number=bool(numbers),
            person=bool(metadata["persons"]),
            spec=bool(specs),
            boosts={"number": 0.10, "person": 0.06, "spec": 0.04},
        )
        return _result("project", head, confidence)
    if head_type == "studio":
        metadata["studio"] = head
        if len(tokens) >= 2:
            metadata["persons"] = _split_persons(tokens[1])
        metadata["themes"] = tokens[2:]
        matched_rules.insert(0, "studio_suffix_keyword")
        confidence = _confidence(
            0.55,
            number=bool(numbers),
            date=bool(date),
            spec=bool(specs),
            person=bool(metadata["persons"]),
            boosts={"number": 0.10, "date": 0.06, "spec": 0.06, "person": 0.08},
        )
        return _result("studio", head, confidence)

    # Priority 4: person-style leading name.
    has_cjk_head = CJK_PATTERN.search(head) is not None
    has_theme = len(tokens) >= 2
    if has_cjk_head and (has_theme or specs):
        metadata["persons"] = _split_persons(head)
        metadata["themes"] = tokens[1:]
        matched_rules.insert(0, "person_leading_name")
        confidence = _confidence(
            0.55,
            spec=bool(specs),
            theme=has_theme,
            number=bool(numbers),
            date=bool(date),
            boosts={"spec": 0.15, "theme": 0.10, "number": 0.03, "date": 0.02},
        )
        person = metadata["persons"][0] if metadata["persons"] else head
        return _result("person", person, confidence)
    if not has_cjk_head and specs:
        metadata["persons"] = _split_persons(head)
        metadata["themes"] = tokens[1:]
        matched_rules.insert(0, "person_leading_name_ascii")
        confidence = _confidence(
            0.45,
            spec=True,
            theme=has_theme,
            boosts={"spec": 0.15, "theme": 0.05},
        )
        person = metadata["persons"][0] if metadata["persons"] else head
        return _result("person", person, confidence)

    # Priority 5: unknown fallback — bare names without structural signals.
    matched_rules.append("unknown_fallback")
    return _result("unknown", name, 0.3)
