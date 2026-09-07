"""审核页静态化重构的冒烟测试。

验证 /review-ui 的 HTML 骨架引用的静态资源（CSS 与 ES module JS）
都能通过 /static 路由以 200 返回，且 JS 模块间的相对导入指向真实文件。
"""

import re
from pathlib import Path

from fastapi.testclient import TestClient

import pims_v1
from pims_v1.main import app

STATIC_ROOT = Path(pims_v1.__file__).parent / "static"
JS_ROOT = STATIC_ROOT / "review" / "js"


def test_review_ui_returns_html_skeleton_referencing_static_assets():
    client = TestClient(app)

    response = client.get("/review-ui")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert '<link rel="stylesheet" href="/static/review/review.css">' in response.text
    assert '<script type="module" src="/static/review/js/main.js"></script>' in response.text


def test_review_ui_referenced_static_assets_are_served():
    client = TestClient(app)
    page = client.get("/review-ui").text
    referenced = re.findall(r'(?:href|src)="(/static/[^"]+)"', page)

    assert referenced, "页面骨架应至少引用一个静态资源"
    for url in referenced:
        response = client.get(url)
        assert response.status_code == 200, url


def test_all_review_static_files_are_served_with_expected_content_type():
    client = TestClient(app)
    files = [path for path in STATIC_ROOT.rglob("*") if path.is_file()]

    assert files, "静态目录不应为空"
    for path in files:
        url = "/static/" + path.relative_to(STATIC_ROOT).as_posix()
        response = client.get(url)
        assert response.status_code == 200, url
        content_type = response.headers["content-type"]
        if path.suffix == ".css":
            assert "text/css" in content_type, url
        elif path.suffix == ".js":
            assert "javascript" in content_type, url


def test_js_module_relative_imports_resolve_to_real_files():
    js_files = sorted(JS_ROOT.glob("*.js"))

    assert js_files, "JS 模块目录不应为空"
    for js_file in js_files:
        source = js_file.read_text(encoding="utf-8")
        for spec in re.findall(r'from\s+"(\./[^"]+)"', source):
            target = (js_file.parent / spec).resolve()
            assert target.is_file(), f"{js_file.name} 引用的模块不存在: {spec}"


def test_api_module_preserves_token_header_mechanism():
    api_source = (JS_ROOT / "api.js").read_text(encoding="utf-8")

    assert "x-pims-api-token" in api_source
    assert 'el("token").value.trim()' in api_source
