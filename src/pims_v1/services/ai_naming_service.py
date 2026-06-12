import json
from pathlib import Path, PurePath, PurePosixPath
from typing import Protocol

from sqlalchemy.orm import Session

from pims_v1.models.asset import Asset
from pims_v1.models.series import Series, SeriesCandidate, SeriesCandidateAsset, SeriesSuggestion
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


def _archive_path_preview(archive_root: str, category: str, title: str) -> str:
    safe_category = safe_series_path_segment(category)
    safe_title = safe_series_path_segment(title)
    if archive_root.startswith("/") and "\\" not in archive_root:
        return str(PurePosixPath(archive_root) / safe_category / safe_title)
    return str(Path(archive_root) / safe_category / safe_title)


def build_series_organization_prompt(
    source_root: str,
    file_names: list[str],
    archive_root: str | None = None,
    existing_archive_dirs: list[str] | None = None,
) -> str:
    folder_name = PurePath(source_root).name
    sample_names = "\n".join(f"- {name}" for name in file_names[:20])
    existing_dirs = "\n".join(f"- {name}" for name in (existing_archive_dirs or [])[:20]) or "- 暂无"
    archive_root_text = archive_root or "未配置"
    return (
        "你是一个有审核约束的本地照片/写真整理规划助手。"
        "你可以基于来源路径、样例文件名、NAS 根目录和已有归档目录生成整理计划；"
        "你不能要求直接删除或绕过人工确认。\n"
        f"来源文件夹: {folder_name}\n"
        f"完整来源路径: {source_root}\n"
        f"NAS 归档根目录: {archive_root_text}\n"
        f"已有归档目录样例:\n{existing_dirs}\n"
        f"样例文件名:\n{sample_names}\n"
        "请只返回 JSON，不要解释，不要 Markdown。格式必须是："
        '{"title":"简洁中文系列名","category":"一级分类","archive_path":"建议目标路径",'
        '"plan_summary":"一句话说明移动计划","risk_flags":["风险1"],"confidence":0.0到1.0}。'
        "分类建议使用短中文，例如：写真合集、家庭生活、旅行记录、工作资料、待整理。"
        "archive_path 必须位于 NAS 归档根目录下，风险包含重名、来源不清晰、疑似重复、需要人工复核等。"
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
    plan_summary = str(payload.get("plan_summary", "")).strip()
    raw_risk_flags = payload.get("risk_flags", [])
    if isinstance(raw_risk_flags, str):
        risk_flags = [raw_risk_flags] if raw_risk_flags else []
    elif isinstance(raw_risk_flags, list):
        risk_flags = [str(flag)[:255] for flag in raw_risk_flags if str(flag).strip()]
    else:
        risk_flags = []
    if not title:
        raise ValueError("AI series title suggestion was empty")
    return {
        "title": title[:255],
        "category": (category or "未分类")[:255],
        "plan_summary": plan_summary[:1024],
        "risk_flags": risk_flags[:10],
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


def _existing_archive_dirs(session: Session, archive_root: str | None, limit: int = 20) -> list[str]:
    if not archive_root:
        return []
    rows = session.query(Series.archive_path).order_by(Series.id.desc()).limit(limit).all()
    prefix = archive_root.rstrip("\\/")
    result = []
    for row in rows:
        archive_path = str(row.archive_path)
        if archive_path.startswith(prefix):
            result.append(archive_path[len(prefix) :].lstrip("\\/"))
        else:
            result.append(archive_path)
    return result


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
    archive_root: str | None = None,
) -> dict[str, int | str | float]:
    candidate = session.get(SeriesCandidate, candidate_id)
    if candidate is None:
        raise ValueError(f"Series candidate not found: {candidate_id}")

    prompt = build_series_organization_prompt(
        source_root=candidate.source_root,
        file_names=_candidate_sample_file_names(session, candidate_id),
        archive_root=archive_root,
        existing_archive_dirs=_existing_archive_dirs(session, archive_root),
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
    suggestion.suggested_archive_path = (
        _archive_path_preview(archive_root, suggestion.suggested_category, suggestion.suggested_title)
        if archive_root
        else None
    )
    suggestion.plan_summary = str(parsed.get("plan_summary", ""))
    suggestion.risk_flags = json.dumps(parsed.get("risk_flags", []), ensure_ascii=False)
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
        "archive_path": suggestion.suggested_archive_path,
        "plan_summary": suggestion.plan_summary,
        "risk_flags": json.loads(suggestion.risk_flags or "[]"),
        "confidence": suggestion.confidence,
    }
