"""72 字节那道闸门从来没挡过任何人，坏哈希那一路从来没被喂过坏哈希。

#163 的两格都是**行覆盖率看不见**的那种缺口，读数只能指出方向：

- `utils/password.py` 85%，缺的是 21-22 两行——`verify_password` 里那句
  `except ValueError: return False`。库里躺着的哈希要是被写坏（手改过、搬迁搬坏、
  早期版本留下过别的格式），`bcrypt.checkpw` 抛出来的是一个 ValueError，这一句把它
  接成"口令不对"。以前没有任何用例给过它一个真坏掉的哈希。
- `src/services/auth_service.py:369`，也就是 `raise ValueError("密码过长（上限 72 字节）")`。
  它上面那一行 `if password_too_long(...)` **每次建号都会被执行**（所以 `password.py:27`
  的 `return len(plain.encode("utf-8")) > 72` 是覆盖到的），但从来没有一次算出过 True——
  369 那一行在 783 条用例的全量覆盖率读数是缺的。这一族钉的就是"算出 True"那一支。

为什么这一支值得单独钉，而不是"能过就行"：上面那层 Pydantic 校验数的是**字符**
（`min_length=1, max_length=200`），下面 bcrypt 的限制是**字节**，而且它超了是抛
ValueError 不是返回 False。一个 25 个汉字的口令（75 字节）在 Pydantic 那一头合法得
不能再合法——只有服务层这一道按字节算，才会给出那句中文原因。
"""

import pytest
from sqlalchemy import select

from src.models.user import User
from src.services.auth_service import login_rate_limiter
from src.utils.password import password_too_long, verify_password

PASSWORD = "a-quiet-home-lab"
LONG_MESSAGE = "密码过长（上限 72 字节）"

#: 汉字在 UTF-8 里每个占 3 字节，所以字符数和字节数在这里天然分家。
HAN = "影"


@pytest.fixture(autouse=True)
def _fresh_rate_limit():
    """用例之间不互相锁定：登录尝试会经过同一个进程内限流器。"""
    login_rate_limiter().reset()
    yield
    login_rate_limiter().reset()


async def _create(client, username: str, password: str) -> int:
    """从用户管理那一头建一个账号，返回它的 id（口令由调用方决定）。"""
    response = await client.post(
        "/api/users", json={"username": username, "password": password}
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _row(db_session, username: str) -> User:
    return (
        await db_session.execute(select(User).where(User.username == username))
    ).scalar_one()


async def _sign_in(browser, username: str, password: str):
    return await browser.post(
        "/api/auth/login", json={"username": username, "password": password}
    )


async def test_the_byte_gate_stops_a_non_ascii_password_bcrypt_would_refuse(
    client, db_session, new_browser
):
    """24 个汉字（正好 72 字节）建得成也登得进，25 个（75 字节）被那道闸门挡在门外。

    两边在 Pydantic 那一头都只有 24/25 个字符，离 `max_length=200` 还远。少了服务层
    这一道，75 字节那一路不是 500 也不是"过长"，而是 bcrypt 自己抛出的那句英文
    （`password cannot be longer than 72 bytes`）被路由当成 400 送回来——状态码一样，
    中文 toast 里那句话换成一句 bcrypt 术语，所以钉的是整句 detail 而不是 400。
    """
    assert len(HAN * 24) == 24 and len((HAN * 24).encode("utf-8")) == 72
    assert len((HAN * 25).encode("utf-8")) == 75

    for n in (18, 24):
        await _create(client, f"han{n}", HAN * n)
        # 建号只是写进库；真能登录才证明哈希是按那 54/72 字节算的。
        assert (await _sign_in(await new_browser(), f"han{n}", HAN * n)).status_code == 200

    response = await client.post(
        "/api/users", json={"username": "han25", "password": HAN * 25}
    )

    assert response.status_code == 400, response.text
    assert response.json()["detail"] == LONG_MESSAGE
    # 拒绝得干净：没有这个人，也没有半条写坏的哈希留在库里。
    assert (
        await db_session.execute(select(User).where(User.username == "han25"))
    ).scalar_one_or_none() is None


def test_password_too_long_is_the_byte_boundary_itself():
    """单元那一头把边界钉死：72 收、73 拒，ASCII 和汉字在字节上等价。

    这一条不经过任何接口，因为 API 那一头只能试出"越界被拒"，试不出边界正好落在
    72 这一格：`>=` 写成 `>` 的话，上一条用例仍然全绿（25 个汉字照样越界）。
    """
    assert password_too_long("a" * 72) is False
    assert password_too_long("a" * 73) is True
    assert password_too_long(HAN * 24) is False
    assert password_too_long(HAN * 24 + "a") is True


async def test_a_corrupted_hash_answers_wrong_password_not_500(
    client, db_session, new_browser
):
    """哈希列被写坏时登录给的是那句"账号或密码错误"，不是 500。

    两种坏法抛的本来不是同一个异常：纯 ASCII 的乱串能编成 ascii 字节，走到 bcrypt 里面的
    `ValueError: Invalid salt`；带非 ASCII 的那一串在 `hashed.encode("ascii")` 这一步就先抛
    UnicodeEncodeError——它是 ValueError 的子类，所以那一句 `except ValueError` 两种都接得住
    （实测 M3：把它换成 `except TypeError` 红在这一条上，`ValueError: Invalid salt` 一路穿到
    ASGI）。顺带记一条测不出来的：把 `.encode("ascii")` 换成 `.encode("utf-8")` 三条照旧全绿
    （实测 M4）——两种编法得到的字节 bcrypt 都不认识，最后都归成同一句 Invalid salt，所以
    这一条钉的是"任何坏哈希都只能是 401"，钉不到"哪一种异常从哪一行出来"。
    """
    for index, broken in enumerate(("not-a-bcrypt-hash", "这串不是 bcrypt 哈希")):
        username = f"broken{index}"
        member_id = await _create(client, username, PASSWORD)
        row = await _row(db_session, username)
        assert verify_password(PASSWORD, row.password_hash)  # 建出来时是好的

        row.password_hash = broken
        await db_session.commit()
        assert member_id == row.id

        response = await _sign_in(await new_browser(), username, PASSWORD)

        assert response.status_code == 401, f"{broken!r} → {response.text}"
        assert response.json()["detail"] == "账号或密码错误", broken
        # 坏哈希不是"绕过校验"，是"谁都拒"：换任何口令都进不来。
        assert verify_password(PASSWORD, broken) is False
