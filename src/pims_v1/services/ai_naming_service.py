from pathlib import PurePath


def build_series_title_prompt(source_root: str, file_names: list[str]) -> str:
    folder_name = PurePath(source_root).name
    sample_names = "\n".join(f"- {name}" for name in file_names[:12])
    return (
        "你是一个本地图片整理助手。请根据来源文件夹和样例文件名，"
        "为这一组网络写真/摄影收藏生成一个简洁中文系列标题。\n"
        f"来源文件夹: {folder_name}\n"
        f"样例文件名:\n{sample_names}\n"
        "要求: 只返回一个中文标题，不要解释，不要加引号。"
    )
