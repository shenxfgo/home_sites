"""第五层静态守卫：服务端写给界面看的每一句错误文案必须是中文（#188 / #153）。

`frontend/src/api/client.ts:100` 把 `error.response.data.detail` 原样当 Error message，每个 view
再拼成「加载失败: ${服务端那句}」弹进 ElMessage——**detail 写哪种语言，用户就看到哪种语言**。
#131 那层守卫钉的是界面自己写死的文案（`ElMessage.error('…')` 的字面量），钉不到这一路：那句话是
运行时从后端来的，静态看界面代码只看到 `${err.message}`。反过来，这一层也不管界面写的中文——两条
守卫各管一半出面。

为什么这一层用 **Python 的 ast** 而不是隔壁四条 Vitest 守卫那种正则遍历：被扫的源是 Python。用正则
在 TypeScript 里再解析一遍 Python 字符串会漏掉隐式拼接（`raise ValueError(f"a" "b")`）、docstring
里的假命中，还有 `detail=某个常量名` 这种要查定义的写法——`ast` 对这些是免费的。三段式照抄
`frontend/tests/views/toast-language.spec.ts`：扫描下限 / 命中下限 / offenders 为空。

出海的面是**三种形状**：`detail="…"`（api 写死）、`raise ValueError("…")`（经路由的
`detail=str(e)` 原样出海，抛它的可能是 `src/services`、`src/utils`（字幕转换、ffprobe）或
`src/storage`），以及 `return False, "…"`（`transcode_video` 那一族不抛异常，那句进 `job.error`、
经 `/api/transcode/status` 原样落进 `ElMessage.error(…)`——见 `_failure_reason`）。只扫 api，
守卫会在全绿的同时留一句服务层的英文原话（这一单之前它就是「Video with id 7 not found」）继续进
toast——那正是这一单要治的病。

`passthrough` 那一格是这一层自觉的边界：正文是一个变量（`FileNotFoundError(filepath)`
把路径当消息）、`str(exc)` 转发、或别的没有自撰句子的表达式时，这里没有可判的语言，跳过并计数。
判的是**我们写下的那句话**，不是它转发的东西——ffmpeg 自己的 stderr、操作系统那句
`[Errno 2]`，语言不由我们决定，所以也不由这一层负责。
"""

from __future__ import annotations

import ast
import pathlib

SRC = pathlib.Path(__file__).resolve().parents[1] / "src"
LAYERS = ("api", "services", "utils", "storage")


def _has_cjk(text: str) -> bool:
    return any("一" <= ch <= "鿿" for ch in text)


def _constants_of(tree: ast.Module) -> dict[str, str]:
    """Module-level ``NAME = "…"`` bindings, so ``detail=NAME`` can be followed."""
    table: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant):
            if isinstance(node.value.value, str):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        table[target.id] = node.value.value
    return table


def _classify(node: ast.expr) -> tuple[str, str]:
    """(shape, authored text). ``judged`` shapes are the ones carrying a sentence we wrote.

    For an f-string only the literal segments count: an interpolated value can be anything,
    but the sentence around it is what the user reads.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return "judged", node.value
    if isinstance(node, ast.JoinedStr):
        parts = [
            value.value
            for value in node.values
            if isinstance(value, ast.Constant) and isinstance(value.value, str)
        ]
        return "judged", "".join(parts)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "str":
        return "passthrough", ""
    embedded = [
        child.value
        for child in ast.walk(node)
        if isinstance(child, ast.Constant) and isinstance(child.value, str)
    ]
    if embedded:
        return "judged", "".join(embedded)
    return "passthrough", ast.unparse(node)


def _failure_reason(node: ast.stmt) -> ast.expr | None:
    """The message half of ``return False, <reason>`` — the third way a sentence leaves.

    ``transcode_video`` 那一族不抛异常，回 `(success, error)`；那句 error 原样进
    ``job.error``、经 `/api/transcode/status` 落到 `ElMessage.error(…)`.实测这四条站点全在
    `src/utils/ffmpeg.py`，且都是同一个「操作失败，原因是……」约定，所以按形状收而不是按文件收。
    """
    if not (isinstance(node, ast.Return) and isinstance(node.value, ast.Tuple)):
        return None
    first, *rest = node.value.elts
    if len(rest) != 1 or not (isinstance(first, ast.Constant) and first.value is False):
        return None
    return rest[0]


class Site:
    def __init__(self, where: str, kind: str, shape: str, text: str) -> None:
        self.where = where
        self.kind = kind
        self.shape = shape
        self.text = text

    @property
    def label(self) -> str:
        return f"{self.where} {self.kind} [{self.shape}] {self.text!r}"


def _layer_paths() -> list[pathlib.Path]:
    paths: list[pathlib.Path] = []
    for layer in LAYERS:
        paths += [p for p in sorted((SRC / layer).glob("*.py")) if p.name != "__init__.py"]
    return paths


def _all_constants() -> dict[str, str]:
    table: dict[str, str] = {}
    for path in _layer_paths():
        table.update(_constants_of(ast.parse(path.read_text(encoding="utf-8"))))
    return table


def _collect() -> tuple[list[str], list[Site]]:
    constants = _all_constants()
    files: list[str] = []
    sites: list[Site] = []
    for path in _layer_paths():
        files.append(f"{path.parent.name}/{path.name}")
        tree = ast.parse(path.read_text(encoding="utf-8"))
        own = _constants_of(tree)
        for node in ast.walk(tree):
            targets: list[tuple[str, ast.expr]] = []
            if isinstance(node, ast.Call):
                targets += [("detail", kw.value) for kw in node.keywords if kw.arg == "detail"]
            if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call) and node.exc.args:
                targets.append(("raise", node.exc.args[0]))
            reason = _failure_reason(node)
            if reason is not None:
                targets.append(("return", reason))
            for kind, expr in targets:
                if isinstance(expr, ast.Name) and expr.id not in own:
                    # `detail=INVALID_CREDENTIALS` (a constant defined in another module of
                    # these layers) is a sentence we wrote, so follow it. A bare local name is
                    # not: `raise FileNotFoundError(filepath)` hands the reader a path.
                    resolved = constants.get(expr.id)
                    if resolved is None:
                        sites.append(Site(files[-1], kind, "variable", expr.id))
                        continue
                    sites.append(Site(files[-1], kind, "judged", resolved))
                    continue
                shape, text = _classify(expr)
                sites.append(Site(files[-1], kind, shape, text))
    return files, sites


FILES, SITES = _collect()
JUDGED = [site for site in SITES if site.shape == "judged"]
PASSTHROUGH = [site for site in SITES if site.shape != "judged"]


def test_scans_every_layer_that_can_author_a_toast() -> None:
    # 目录走错一步就是「零条文案、零条违规」的全绿，先把扫描本身钉住（同 #123 的闸门）。
    # 实测基线：src/api 17 个模块 + services 13 + utils 5 + storage 6 = 41。
    assert len(FILES) >= 35, FILES


def test_examines_every_message_that_can_reach_a_toast() -> None:
    # 遍历器写坏同样是「一条都没看到」的绿——这几条下限是给守卫自己用的。
    # 实测基线：站点 140 处，其中带自撰句子（字面量 / f-string / 常量 / 拼接里的字面量）的 94 处，
    # 转发型（`str(e)`、纯变量）46 处。
    assert len(SITES) >= 120, len(SITES)
    assert len(JUDGED) >= 80, len(JUDGED)
    assert len(PASSTHROUGH) >= 35, len(PASSTHROUGH)


def test_no_english_sentence_leaves_the_backend() -> None:
    offenders = [
        site.label for site in JUDGED if not _has_cjk(site.text)
    ]
    assert offenders == []
