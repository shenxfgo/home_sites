"""把 FastAPI 的路由表落成一份 ``openapi.json`` 提交进仓库。

动机是前端那 12 份请求模块（``src/api/*.ts``）里的路径全是手写字符串：
``frontend/tests/api/paths.spec.ts`` 只能验形状（不带 ``/api``、以 ``/`` 开头、没有 ``//``
和尾斜杠），验不了段名拼错——``/auth/session`` 少一个 ``s`` 在形状上完全合法，只有真后端
e2e 里恰好被界面点到的那条才会撞出 404。这份文件就是缺的那张对照表，前端那份契约测试拿它
逐条核对 URL 与方法。

导出不需要起着服务：``app.openapi()`` 只是遍历已注册的 ``APIRoute``，不建连接——实测把
``DATABASE_URL`` 指到一个不存在的端口照样能出全表（2026-10-08 复量：66 条路径 / 85 个操作）。
所以 ``python -m src.export_openapi`` 在任何机器上都能重跑。改完接口如果忘了跑，
``tests/test_openapi_snapshot.py`` 会红——那颗钉子防止这份契约悄悄腐烂。
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

# 仓库里的契约文件就放在后端包旁边：它是后端的出处，前端只读不写
DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "openapi.json"


def render() -> str:
    """生成 schema 文本；键排序、缩进两项是为了让 diff 只反映接口本身的变化。"""
    from src.main import app

    schema: dict[str, Any] = app.openapi()
    return json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def matches(output: Path) -> bool:
    """已提交的文件与代码是否一致；比的是解析后的对象，格式差异不算不一致。"""
    if not output.exists():
        return False
    try:
        committed: object = json.loads(output.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return bool(committed == json.loads(render()))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="src.export_openapi",
        description="导出后端 OpenAPI 路由表，供前端契约测试核对请求 URL",
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_OUTPUT, help="输出路径")
    parser.add_argument(
        "--check",
        action="store_true",
        help="只比对已提交的文件与代码是否一致，不写文件",
    )
    args = parser.parse_args(argv)

    if args.check:
        if matches(args.out):
            print(f"openapi 契约与代码一致：{args.out}")
            return 0
        print(
            f"openapi 契约已与代码不一致：{args.out}\n"
            "重跑 python -m src.export_openapi 并把 openapi.json 一起提交。",
            file=sys.stderr,
        )
        return 1

    text = render()
    # newline="\n"：这份文件会被前端读，两端换行一致省得 diff 里全是 ^M
    args.out.write_text(text, encoding="utf-8", newline="\n")
    paths = len(json.loads(text)["paths"])
    print(f"已写出 {args.out}（{paths} 条路径，{len(text.splitlines())} 行）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
