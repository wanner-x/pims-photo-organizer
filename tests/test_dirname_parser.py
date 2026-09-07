"""目录名解析器回归测试。

用参数化表组织，方便日后直接往 CASES 里加真实样本。
每条用例：目录名 + 期望字段子集（只断言写出来的键，未写的不检查）。
"""

import pytest

from pims_v1.services.dirname_parser import DEFAULT_MIN_CONFIDENCE, parse_dirname


def _assert_subset(actual: dict, expected: dict, path: str = "") -> None:
    for key, expected_value in expected.items():
        assert key in actual, f"missing key: {path}{key}"
        if isinstance(expected_value, dict):
            _assert_subset(actual[key], expected_value, path=f"{path}{key}.")
        else:
            assert actual[key] == expected_value, (
                f"{path}{key}: expected {expected_value!r}, got {actual[key]!r}"
            )


# (id, 目录名, 期望字段子集)
CASES = [
    # --- 路线图点名的三类真实样本 ---
    (
        "roadmap_person_xueqi",
        "雪琪SAMA JK白丝 [46P208MB]",
        {
            "category_type": "person",
            "archive_category": "雪琪SAMA",
            "archive_title": "雪琪SAMA JK白丝 [46P208MB]",
            "metadata": {
                "persons": ["雪琪SAMA"],
                "themes": ["JK白丝"],
                "specs": {"pictures": 46, "videos": None, "size_mb": 208.0, "raw": ["46P208MB"]},
                "r18": False,
            },
        },
    ),
    (
        "roadmap_project_jinji",
        "【紧急企划】-【VOL.001】-【樱樱樱可】-【JK黑】-【45P1V-858M】",
        {
            "category_type": "project",
            "archive_category": "紧急企划",
            "archive_title": "【紧急企划】-【VOL.001】-【樱樱樱可】-【JK黑】-【45P1V-858M】",
            "metadata": {
                "project": "紧急企划",
                "persons": ["樱樱樱可"],
                "themes": ["JK黑"],
                "numbers": [{"kind": "VOL", "value": 1, "raw": "VOL.001"}],
                "specs": {"pictures": 45, "videos": 1, "size_mb": 858.0},
            },
        },
    ),
    (
        "roadmap_studio_imiss",
        "[IMISS爱蜜社] 2025.08.27 VOL.800 许诺Sabrina [86+1P]",
        {
            "category_type": "studio",
            "archive_category": "IMISS爱蜜社",
            "archive_title": "[IMISS爱蜜社] 2025.08.27 VOL.800 许诺Sabrina [86+1P]",
            "metadata": {
                "studio": "IMISS爱蜜社",
                "persons": ["许诺Sabrina"],
                "numbers": [{"kind": "VOL", "value": 800, "raw": "VOL.800"}],
                "date": {"raw": "2025.08.27", "normalized": "2025-08-27"},
                "specs": {"pictures": 87, "picture_parts": [86, 1], "raw": ["86+1P"]},
            },
        },
    ),
    # --- 人物型变体 ---
    (
        "person_video_spec",
        "雪琪SAMA 透明女仆 [43P4V234MB]",
        {
            "category_type": "person",
            "archive_category": "雪琪SAMA",
            "metadata": {"specs": {"pictures": 43, "videos": 4, "size_mb": 234.0}},
        },
    ),
    (
        "person_no_spec_with_theme",
        "雪琪SAMA JK白丝",
        {
            "category_type": "person",
            "archive_category": "雪琪SAMA",
            "metadata": {"persons": ["雪琪SAMA"], "themes": ["JK白丝"], "specs": None},
        },
    ),
    (
        "person_multi_ampersand",
        "雪琪SAMA&小仓千代 双人企划服 [60P512MB]",
        {
            "category_type": "person",
            "archive_category": "雪琪SAMA",
            "metadata": {"persons": ["雪琪SAMA", "小仓千代"], "themes": ["双人企划服"]},
        },
    ),
    (
        "person_multi_dunhao",
        "桜井宁宁、蜜汁猫裘 联动 [88P]",
        {
            "category_type": "person",
            "archive_category": "桜井宁宁",
            "metadata": {"persons": ["桜井宁宁", "蜜汁猫裘"], "specs": {"pictures": 88}},
        },
    ),
    (
        "person_r18_suffix",
        "雪琪SAMA 白丝女仆 [40P] [R18]",
        {
            "category_type": "person",
            "archive_category": "雪琪SAMA",
            "metadata": {"r18": True, "specs": {"pictures": 40}},
        },
    ),
    (
        "person_gb_size",
        "面饼仙儿 兔女郎 [120P1.2GB]",
        {
            "category_type": "person",
            "archive_category": "面饼仙儿",
            "metadata": {"specs": {"pictures": 120, "size_mb": 1228.8}},
        },
    ),
    (
        "person_lowercase_units",
        "面饼仙儿 睡衣 [30p2v666m]",
        {
            "category_type": "person",
            "archive_category": "面饼仙儿",
            "metadata": {"specs": {"pictures": 30, "videos": 2, "size_mb": 666.0}},
        },
    ),
    (
        "person_spec_only_no_theme",
        "轩萧学姐 [52P388MB]",
        {
            "category_type": "person",
            "archive_category": "轩萧学姐",
            "metadata": {"persons": ["轩萧学姐"], "themes": [], "specs": {"pictures": 52}},
        },
    ),
    (
        "person_no_number",
        "抖娘利世 NO.021 白色情人节 [45P]",
        {
            "category_type": "person",
            "archive_category": "抖娘利世",
            "metadata": {"numbers": [{"kind": "NO", "value": 21, "raw": "NO.021"}]},
        },
    ),
    (
        "person_ex_number",
        "过期米线线喵 EX.05 特典 [12P3V]",
        {
            "category_type": "person",
            "archive_category": "过期米线线喵",
            "metadata": {
                "numbers": [{"kind": "EX", "value": 5, "raw": "EX.05"}],
                "specs": {"pictures": 12, "videos": 3},
            },
        },
    ),
    # --- 厂牌/机构型变体 ---
    (
        "studio_xiuren_no",
        "[XiuRen秀人网] NO.8899 王雨纯 私房黑丝 [80P]",
        {
            "category_type": "studio",
            "archive_category": "XiuRen秀人网",
            "metadata": {
                "studio": "XiuRen秀人网",
                "persons": ["王雨纯"],
                "themes": ["私房黑丝"],
                "numbers": [{"kind": "NO", "value": 8899, "raw": "NO.8899"}],
            },
        },
    ),
    (
        "studio_dash_date",
        "[YOUMI尤蜜荟] 2024-01-15 VOL.1050 王馨瑶yanni [90P]",
        {
            "category_type": "studio",
            "archive_category": "YOUMI尤蜜荟",
            "metadata": {
                "persons": ["王馨瑶yanni"],
                "date": {"normalized": "2024-01-15"},
                "numbers": [{"kind": "VOL", "value": 1050, "raw": "VOL.1050"}],
            },
        },
    ),
    (
        "studio_fullwidth_single_bracket",
        "【蜜桃社】 VOL.233 美七Mia [66P388MB]",
        {
            "category_type": "studio",
            "archive_category": "蜜桃社",
            "metadata": {"studio": "蜜桃社", "persons": ["美七Mia"]},
        },
    ),
    (
        "studio_english_brand",
        "[MetArt] 2023.11.02 Kalisy Presenting [120P1.5GB]",
        {
            "category_type": "studio",
            "archive_category": "MetArt",
            "metadata": {"persons": ["Kalisy"], "themes": ["Presenting"]},
        },
    ),
    (
        "studio_keyword_no_bracket",
        "爱蜜社 VOL.100 许诺Sabrina [50P]",
        {
            "category_type": "studio",
            "archive_category": "爱蜜社",
            "metadata": {"studio": "爱蜜社", "persons": ["许诺Sabrina"]},
        },
    ),
    (
        "studio_brand_only_low_info",
        "[某某社] 未整理",
        {"category_type": "studio", "archive_category": "某某社"},
    ),
    # --- 企划型变体 ---
    (
        "project_vol_002",
        "【紧急企划】-【VOL.002】-【木花琳琳是勇者】-【体操服】-【52P-666M】",
        {
            "category_type": "project",
            "archive_category": "紧急企划",
            "metadata": {
                "project": "紧急企划",
                "persons": ["木花琳琳是勇者"],
                "themes": ["体操服"],
                "numbers": [{"kind": "VOL", "value": 2, "raw": "VOL.002"}],
                "specs": {"pictures": 52, "size_mb": 666.0},
            },
        },
    ),
    (
        "project_r18_tail",
        "【紧急企划】-【VOL.001】-【樱樱樱可】-【JK黑】-【45P1V-858M】 [R18]",
        {
            "category_type": "project",
            "archive_category": "紧急企划",
            "metadata": {"r18": True, "persons": ["樱樱樱可"]},
        },
    ),
    (
        "project_keyword_no_bracket",
        "紧急企划 VOL.003 米线线 [30P]",
        {
            "category_type": "project",
            "archive_category": "紧急企划",
            "metadata": {"project": "紧急企划", "persons": ["米线线"]},
        },
    ),
    (
        "project_leading_bracket_keyword",
        "【某某企划】 EX.01 樱桃 [20P1V]",
        {
            "category_type": "project",
            "archive_category": "某某企划",
            "metadata": {"numbers": [{"kind": "EX", "value": 1, "raw": "EX.01"}]},
        },
    ),
    # --- 编号 / 规格 / 日期细节 ---
    (
        "vol_no_dot_space",
        "[Brand] VOL 12 Alice [10P]",
        {"metadata": {"numbers": [{"kind": "VOL", "value": 12, "raw": "VOL 12"}]}},
    ),
    (
        "size_m_shorthand",
        "雪琪SAMA 黑裙 [45P1V-858M]",
        {"metadata": {"specs": {"pictures": 45, "videos": 1, "size_mb": 858.0}}},
    ),
    (
        "plus_pictures_sum",
        "[ABC] 2024.02.02 VOL.9 小美 [86+1P]",
        {"metadata": {"specs": {"pictures": 87, "picture_parts": [86, 1]}}},
    ),
    (
        "underscore_date",
        "[ABC] 2024_3_5 VOL.10 小美 [10P]",
        {"metadata": {"date": {"normalized": "2024-03-05"}}},
    ),
    # --- 裸目录名 / 未知型 ---
    (
        "bare_single_token",
        "新建文件夹",
        {"category_type": "unknown", "archive_category": "新建文件夹"},
    ),
    (
        "bare_english_words",
        "misc downloads backup",
        {"category_type": "unknown", "archive_category": "misc downloads backup"},
    ),
    (
        "english_person_with_spec",
        "Kalisy Garden Morning [55P800MB]",
        {
            "category_type": "person",
            "archive_category": "Kalisy",
            "metadata": {"persons": ["Kalisy"], "specs": {"pictures": 55, "size_mb": 800.0}},
        },
    ),
    (
        "empty_string",
        "",
        {"category_type": "unknown"},
    ),
    (
        "spec_only_brackets",
        "[46P208MB]",
        {"category_type": "unknown"},
    ),
]


@pytest.mark.parametrize(("name", "expected"), [(c[1], c[2]) for c in CASES], ids=[c[0] for c in CASES])
def test_parse_dirname_table(name: str, expected: dict) -> None:
    result = parse_dirname(name)
    _assert_subset(result.as_dict(), expected)


# --- 置信度分层：命中越明确越高，低信号必须低于阈值 ---
HIGH_CONFIDENCE_NAMES = [
    "雪琪SAMA JK白丝 [46P208MB]",
    "【紧急企划】-【VOL.001】-【樱樱樱可】-【JK黑】-【45P1V-858M】",
    "[IMISS爱蜜社] 2025.08.27 VOL.800 许诺Sabrina [86+1P]",
    "[XiuRen秀人网] NO.8899 王雨纯 私房黑丝 [80P]",
]

LOW_CONFIDENCE_NAMES = [
    "新建文件夹",
    "misc downloads backup",
    "",
    "[46P208MB]",
]


@pytest.mark.parametrize("name", HIGH_CONFIDENCE_NAMES)
def test_high_signal_names_pass_threshold(name: str) -> None:
    result = parse_dirname(name)
    assert result.confidence >= 0.75, result.as_dict()


@pytest.mark.parametrize("name", LOW_CONFIDENCE_NAMES)
def test_low_signal_names_stay_below_threshold(name: str) -> None:
    result = parse_dirname(name)
    assert result.confidence < DEFAULT_MIN_CONFIDENCE, result.as_dict()


def test_archive_title_always_preserves_raw_specs() -> None:
    for _, name, _ in CASES:
        if not name.strip():
            continue
        assert parse_dirname(name).archive_title == name.strip()


def test_confidence_monotonic_with_more_signals() -> None:
    bare = parse_dirname("雪琪SAMA JK白丝")
    with_spec = parse_dirname("雪琪SAMA JK白丝 [46P208MB]")
    assert with_spec.confidence > bare.confidence
