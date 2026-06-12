import json
from pathlib import PurePath
from typing import Protocol

from sqlalchemy.orm import Session

from pims_v1.models.asset import Asset
from pims_v1.models.series import SeriesCandidate, SeriesCandidateAsset, SeriesSuggestion
from pims_v1.services.series_confirm_service import safe_series_path_segment


class NamingClient(Protocol):
    def chat(self, messages: list[dict[str, str]]) -> str:
        ...


def build_series_title_prompt(source_root: str, file_names: list[str]) -> str:
    folder_name = PurePath(source_root).name
    sample_names = "\n".join(f"- {name}" for name in file_names[:12])
    return (
        "\u4f60\u662f\u4e00\u4e2a\u672c\u5730\u56fe\u7247\u6574\u7406\u52a9\u624b\u3002"
        "\u8bf7\u6839\u636e\u6765\u6e90\u6587\u4ef6\u5939\u548c\u6837\u4f8b\u6587\u4ef6\u540d\uff0c"
        "\u4e3a\u8fd9\u4e00\u7ec4\u7f51\u7edc\u5199\u771f/\u6444\u5f71\u6536\u85cf"
        "\u751f\u6210\u4e00\u4e2a\u7b80\u6d01\u4e2d\u6587\u7cfb\u5217\u6807\u9898\u3002\n"
        f"\u6765\u6e90\u6587\u4ef6\u5939: {folder_name}\n"
        f"\u6837\u4f8b\u6587\u4ef6\u540d:\n{sample_names}\n"
        "\u8981\u6c42: \u53ea\u8fd4\u56de\u4e00\u4e2a\u4e2d\u6587\u6807\u9898\uff0c"
        "\u4e0d\u8981\u89e3\u91ca\uff0c\u4e0d\u8981\u52a0\u5f15\u53f7\u3002"
    )


def build_series_organization_prompt(source_root: str, file_names: list[str]) -> str:
    folder_name = PurePath(source_root).name
    sample_names = "\n".join(f"- {name}" for name in file_names[:20])
    return (
        "你是一个本地照片/写真整理助手。请根据来源文件夹和样例文件名，"
        "给这一组照片生成可审核的整理建议。\n"
        f"来源文件夹: {folder_name}\n"
        f"样例文件名:\n{sample_names}\n"
        "请只返回 JSON，不要解释，不要 Markdown。格式必须是："
        '{"title":"简洁中文系列名","category":"一级分类","confidence":0.0到1.0}。'
        "分类建议使用短中文，例如：写真合集、家庭生活、旅行记录、工作资料、待整理。"
    )


def _parse_organization_response(response: str) -> dict[str, str | float]:
    cleaned = response.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
    payload = json.loads(cleaned)
    title = safe_series_path_segment(str(payload.get("title", "")))
    category = safe_series_path_segment(str(payload.get("category", "未分类")))
    confidence = float(payload.get("confidence", 0.6))
    if not title:
        raise ValueError("AI series title suggestion was empty")
    return {
        "title": title[:255],
        "category": (category or "未分类")[:255],
        "confidence": max(0.0, min(confidence, 1.0)),
    }


def _candidate_sample_file_names(session: Session, candidate_id: int, limit: int = 20) -> list[str]:
    rows = (
        session.query(Asset.file_name)
        .join(SeriesCandidateAsset, SeriesCandidateAsset.asset_id == Asset.id)
        .filter(SeriesCandidateAsset.candidate_id == candidate_id)
        .order_by(SeriesCandidateAsset.sort_order, Asset.id)
        .limit(limit)
        .all()
    )
    return [row.file_name for row in rows]


def suggest_series_title(
    *,
    session: Session,
    candidate_id: int,
    client: NamingClient,
) -> dict[str, int | str]:
    candidate = session.get(SeriesCandidate, candidate_id)
    if candidate is None:
        raise ValueError(f"Series candidate not found: {candidate_id}")

    prompt = build_series_title_prompt(
        source_root=candidate.source_root,
        file_names=_candidate_sample_file_names(session, candidate_id, limit=12),
    )
    title = client.chat([{"role": "user", "content": prompt}]).strip().strip("\"'")
    if not title:
        raise ValueError("AI title suggestion was empty")

    candidate.title = title[:255]
    candidate.status = "ai_suggested"
    candidate.confidence = 0.6
    session.commit()
    return {"candidate_id": candidate.id, "title": candidate.title}


def suggest_series_organization(
    *,
    session: Session,
    candidate_id: int,
    client: NamingClient,
) -> dict[str, int | str | float]:
    candidate = session.get(SeriesCandidate, candidate_id)
    if candidate is None:
        raise ValueError(f"Series candidate not found: {candidate_id}")

    prompt = build_series_organization_prompt(
        source_root=candidate.source_root,
        file_names=_candidate_sample_file_names(session, candidate_id),
    )
    raw_response = client.chat([{"role": "user", "content": prompt}])
    parsed = _parse_organization_response(raw_response)

    suggestion = (
        session.query(SeriesSuggestion)
        .filter(SeriesSuggestion.candidate_id == candidate_id)
        .one_or_none()
    )
    if suggestion is None:
        suggestion = SeriesSuggestion(candidate_id=candidate_id)
        session.add(suggestion)
    suggestion.suggested_title = str(parsed["title"])
    suggestion.suggested_category = str(parsed["category"])
    suggestion.confidence = float(parsed["confidence"])
    suggestion.status = "pending_review"
    suggestion.raw_response = raw_response
    candidate.title = suggestion.suggested_title
    candidate.status = "ai_suggested"
    candidate.confidence = suggestion.confidence
    session.commit()
    return {
        "candidate_id": candidate.id,
        "suggestion_id": suggestion.id,
        "title": suggestion.suggested_title,
        "category": suggestion.suggested_category,
        "confidence": suggestion.confidence,
    }
