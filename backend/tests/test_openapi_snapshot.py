"""提交进仓库的 ``openapi.json`` 必须与路由表一致。

这份文件是前端契约测试（``frontend/tests/api/openapi-contract.spec.ts``）的对照表，
所以它腐烂的方式很糟：不一致时前端要么红在错误的地方（把"接口改了"演成"URL 写错了"），
要么更糟——照着旧表放行一条已经不存在的路径。这条测试把责任放回改接口的人身上：
改完跑 ``python -m src.export_openapi``，把 ``openapi.json`` 一起提交。
"""

from __future__ import annotations

import json
from pathlib import Path

from src import export_openapi


def test_committed_openapi_matches_the_route_table() -> None:
    output = export_openapi.DEFAULT_OUTPUT
    assert output.exists(), f"缺少 {output}；跑 python -m src.export_openapi 生成它"

    committed = json.loads(output.read_text(encoding="utf-8"))
    assert committed == json.loads(export_openapi.render()), (
        f"{output} 已与路由表不一致；跑 python -m src.export_openapi 重新生成并一起提交"
    )


def test_check_mode_agrees_with_the_snapshot() -> None:
    """``--check`` 是给人和 CI 用的那条命令，它必须与上面的判断同进同退。"""
    assert export_openapi.matches(export_openapi.DEFAULT_OUTPUT) is True
    assert export_openapi.main(["--check", "--out", str(export_openapi.DEFAULT_OUTPUT)]) == 0


def test_check_mode_is_red_against_a_stale_file(tmp_path: Path) -> None:
    stale = tmp_path / "openapi.json"
    stale.write_text('{"paths": {}}', encoding="utf-8")
    assert export_openapi.matches(stale) is False
    assert export_openapi.main(["--check", "--out", str(stale)]) == 1
