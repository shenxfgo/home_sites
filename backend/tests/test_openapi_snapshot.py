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


def test_a_file_that_is_not_there_yet_does_not_match(tmp_path: Path) -> None:
    """文件还没生成时 ``--check`` 要说不一致，不能把"读不到"演成"一致"。

    新克隆的仓库在第一次导出之前就是这个状态；这一格和下面两格钉的是同一句
    ``if not output.exists(): return False``——三种"读不出一个 schema"的面目。
    """
    missing = tmp_path / "openapi.json"
    assert not missing.exists()
    assert export_openapi.matches(missing) is False
    assert export_openapi.main(["--check", "--out", str(missing)]) == 1


def test_a_path_that_is_a_directory_instead_of_a_file_does_not_match(tmp_path: Path) -> None:
    """`--out` 指到一个目录时 `exists()` 是真的，读它会抛 `OSError`。

    这条走的是 `except OSError` 那一支（Windows 上是 `PermissionError`，POSIX 上是
    `IsADirectoryError`——两支都属于 `OSError`，所以断言不写死 errno）。没有这一支的话，
    手滑把 `--out` 写成目录名就会在核对时炸回溯，而不是老实说一句"不一致"。
    """
    as_directory = tmp_path / "openapi.json"
    as_directory.mkdir()
    assert export_openapi.matches(as_directory) is False


def test_a_file_that_is_not_json_does_not_match(tmp_path: Path) -> None:
    """半截写入、或者被某个补丁工具换成 HTML 冲突标记时，`json.loads` 抛的是
    `JSONDecodeError`；那也算"不一致"，不算"这个测试自己坏了"。
    """
    not_json = tmp_path / "openapi.json"
    not_json.write_text("{not json at all\n", encoding="utf-8")
    assert export_openapi.matches(not_json) is False


def test_the_export_writes_lf_only_and_the_checker_then_agrees(tmp_path: Path) -> None:
    """导出那一趟（`--out` 不带 `--check`）：写出来的必须能被同一份代码认回来。

    钉三件事：字节里一个 `\\r` 都没有（`newline="\\n"` 那一参不是装饰——这份文件会被前端读，
    两端换行不一致时 diff 里全是 `^M`）；解析后与 `render()` 逐字相等；写完立刻 `matches()`
    为真，也就是写的人和核对的人用的是同一份判断。
    """
    target = tmp_path / "openapi.json"
    assert export_openapi.main(["--out", str(target)]) == 0

    raw = target.read_bytes()
    assert b"\r" not in raw, "导出必须只写 LF"
    assert json.loads(raw.decode("utf-8")) == json.loads(export_openapi.render())
    assert export_openapi.matches(target) is True


def test_a_reformatted_but_identical_schema_still_matches(tmp_path: Path) -> None:
    """核对比的是解析后的对象，不是字节——docstring 里那句"格式差异不算不一致"得有机器管。

    同一份路由表换个缩进、换个键序写出去，人眼看 diff 全是改动，`--check` 却应当闭嘴；
    反过来（拿字符串相等来比）会让"谁顺手跑了个格式化"变成一次假的不一致。
    """
    schema = json.loads(export_openapi.render())
    reformatted = tmp_path / "openapi.json"
    reformatted.write_text(
        json.dumps(schema, ensure_ascii=True, indent=4, sort_keys=False), encoding="utf-8"
    )
    assert export_openapi.matches(reformatted) is True
    assert export_openapi.main(["--check", "--out", str(reformatted)]) == 0


def test_the_export_says_the_same_path_count_it_wrote(tmp_path: Path, capsys) -> None:
    """打印那句里的路径条数必须来自刚写出去的那份文件，不能是另一处数出来的。

    数字本身不写死在断言里（写死就等于又造一处会腐烂的文档）——这里核的是"嘴上说的"和
    "文件里的"是同一个数。
    """
    target = tmp_path / "openapi.json"
    assert export_openapi.main(["--out", str(target)]) == 0

    printed = capsys.readouterr().out
    written = len(json.loads(target.read_text(encoding="utf-8"))["paths"])
    assert f"{written} 条路径" in printed, printed
    assert str(target) in printed, printed

