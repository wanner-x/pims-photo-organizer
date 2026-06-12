import tomllib
from pathlib import Path


def test_runtime_dependencies_include_websocket_server_support():
    pyproject = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    dependencies = pyproject["project"]["dependencies"]

    assert any(dependency.startswith("websockets") for dependency in dependencies)
