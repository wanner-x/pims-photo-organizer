from pathlib import PurePath
from typing import Protocol

from sqlalchemy.orm import Session

from pims_v1.models.asset import Asset
from pims_v1.models.series import SeriesCandidate, SeriesCandidateAsset


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


def suggest_series_title(
    *,
    session: Session,
    candidate_id: int,
    client: NamingClient,
) -> dict[str, int | str]:
    candidate = session.get(SeriesCandidate, candidate_id)
    if candidate is None:
        raise ValueError(f"Series candidate not found: {candidate_id}")

    rows = (
        session.query(Asset.file_name)
        .join(SeriesCandidateAsset, SeriesCandidateAsset.asset_id == Asset.id)
        .filter(SeriesCandidateAsset.candidate_id == candidate_id)
        .order_by(SeriesCandidateAsset.sort_order, Asset.id)
        .limit(12)
        .all()
    )
    prompt = build_series_title_prompt(
        source_root=candidate.source_root,
        file_names=[row.file_name for row in rows],
    )
    title = client.chat([{"role": "user", "content": prompt}]).strip().strip("\"'")
    if not title:
        raise ValueError("AI title suggestion was empty")

    candidate.title = title[:255]
    candidate.status = "ai_suggested"
    candidate.confidence = 0.6
    session.commit()
    return {"candidate_id": candidate.id, "title": candidate.title}
