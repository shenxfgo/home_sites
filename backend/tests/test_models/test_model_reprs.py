"""模型层 18 个 ``__repr__`` 的 return 逐条敲到（#200 钉下 17 个，#215 补齐最后那一个）。

盘点（不是估算，是从 ``src/models/*.py`` 的 AST 数出来的）：18 个映射类**现在全都有**
``__repr__``。#200 那一单量到的缺口只有一个 ``Setting``（``settings`` 表）——它当时落回默认实现
``<src.models.setting.Setting object at 0x...>``，含地址、不确定，所以那一单为它写的是一条
「它确实没有 repr」的事实用例；#215 按第五块面板⑧甲给它补上了真正的 repr，那条事实用例同时
删除，18 条等式从此是同一族。

为什么用等式钉，而不是给这 18 行标 ``# pragma: no cover``：

1. 标 pragma 是一句**假话**。这一行了——``repr(User(id=1, username=..., role=...))`` 就是它，
   所以 pragma 声明的「没有测试够得着」在这里不成立。仓里已有的那处 repr pragma
   （``src/services/auth_service.py:426`` 的 ``LoginRateLimiter``）是另一回事：它内插的是
   ``len(self._failures)``，值随测试推进漂移，等式钉不住；模型这 18 个全是纯字段拼接。
2. 这些字符串是**人唯一会读的东西**：出问题时日志里、调试器里、``print`` 出来的就是它。
   同一个仓里已经有一条为这个理由存在的测试——``tests/test_backup.py:262`` 就为了
   「口令不能出现在 repr 里」而真去调 ``repr()``。有产口的 repr 值得钉，这条先例就在旁边。
3. 拼接的形状里有三处不是「看不出来错」的：``PlayHistory`` 那个 ``s`` 后缀、
   ``UserPreference`` 的 ``sorted(self.prefs)``（钉序而不是钉原顺序）、
   五个多行 f-string 的**接缝空格**（少一个空格就是 ``user_id=7video_id=8``）。

每条用例的值都取成互不相同（11/12/13 这样），所以「把 ``id`` 写成 ``user_id``」这类串字段
当场红，不需要靠 18 条共享一条断言。整文件不碰数据库：全是内存里的实例，两种方言同一条命令，
所以它不进 SQLite 分支的差异清单。

最后一条用例钉的是**今天量到的行为**，不是想要的行为：``UserPreference`` 的 ``prefs`` 列
带 ``default=dict``，那个默认值在 INSERT 时才由 ORM 填，内存里刚 new 出来的实例上它是
``None``，于是 ``sorted(None)`` 抛 ``TypeError``——为调试而生的 repr 在调试现场炸掉。
全仓唯一的构造点（``src/services/preference_service.py:38``）永远显式传 ``prefs``，所以线上
走不到；这一格因此留源码不动，作为分叉交回用户（见 ``backend/CLAUDE.md`` 的 #200 段）。

变异电池（19 格，一次一格，每格改完立即还原并核对字节，整轮跑两遍结果一致）：
17 格各把一条 repr 的一个字段换成同类的另一个字段（``id={self.id}`` → ``id={self.user_id}``
这种），**每格红 1 条**——17 条签名确实是 17 个独立的把手，没有任何一条 repr 靠别人代签。
外加两格：``history.py`` 接缝上那个空格删掉红 1 条；``video.py`` 开头的 ``<`` 删掉红 1 条。
第 5 格（``sorted(self.prefs)`` → ``self.prefs``）是本轮唯一的**红 2 条**：它同时红掉
``UserPreference`` 的等式那条和上面那条 ``TypeError``——因为让未落库实例炸掉的正是
``sorted`` 这一手。换句话说「顺手把 sorted 去掉」看着像修了个 bug，实际是把排序这条契约
和崩溃记录一起抹了，而这两件事分别有名字。

``Setting`` 那一格是 #215 补的，它自己配了一组 7 张电池，两种方言各跑一遍逐格结果一致：
6 格红、1 格该绿的对照。**红的六格各红 1 条**，形状互不相同——只留 value（少一个字段）、
key 与 value 对调（字段串了）、去掉 key 两侧的引号（引号也是签名的一部分）、去掉收尾的
``>``、整个 ``__repr__`` 删掉（红回默认实现那串含地址的 ``<... object at 0x...>``，这一格
同时就是本单「红在改前 HEAD 上」那一手）、``return None``（红成 ``TypeError: __repr__
returned non-string``）。该绿的那格是把 ``key`` 那列的 ``String(100)`` 改成 ``String(120)``：
这一族用例从不看列宽，它必须绿——它是这台机器上「电池整片红其实是用法子坏了」那类假象
（#210/#211 各踩过一次）的探测器。
"""

from datetime import datetime, timezone

import pytest

from src.models.favorite import Favorite
from src.models.history import PlayHistory
from src.models.new_video import NewVideo
from src.models.notification import Notification
from src.models.preference import UserPreference
from src.models.read_state import NewVideoRead, NotificationRead
from src.models.setting import Setting
from src.models.source import VideoSource
from src.models.subtitle import Subtitle
from src.models.tag import Tag
from src.models.transcode_output import TranscodeOutput
from src.models.user import User, UserSession
from src.models.video import Video
from src.models.watch_event import WatchEvent
from src.models.watchlist import Watchlist, WatchlistItem

SESSION_EXPIRES = datetime(2026, 10, 10, 12, 30, tzinfo=timezone.utc)

CASES = [
    (
        "Favorite",
        lambda: Favorite(id=11, user_id=12, video_id=13),
        "<Favorite(id=11, user_id=12, video_id=13)>",
    ),
    (
        "PlayHistory",
        lambda: PlayHistory(id=21, user_id=22, video_id=23, progress=245),
        "<PlayHistory(id=21, user_id=22, video_id=23, progress=245s)>",
    ),
    (
        "NewVideo",
        lambda: NewVideo(id=31, video_id=32),
        "<NewVideo(id=31, video_id=32)>",
    ),
    (
        "Notification",
        lambda: Notification(id=41, type="scan", title="发现 3 部新片"),
        "<Notification(id=41, type='scan', title='发现 3 部新片')>",
    ),
    (
        # 字面顺序是 autoscroll 在前，repr 必须按 key 排序后给出。
        "UserPreference",
        lambda: UserPreference(user_id=51, prefs={"theme": "dark", "autoscroll": 1}),
        "<UserPreference(user_id=51, keys=['autoscroll', 'theme'])>",
    ),
    (
        "NewVideoRead",
        lambda: NewVideoRead(new_video_id=61, user_id=62),
        "<NewVideoRead(new_video_id=61, user_id=62)>",
    ),
    (
        "NotificationRead",
        lambda: NotificationRead(notification_id=71, user_id=72),
        "<NotificationRead(notification_id=71, user_id=72)>",
    ),
    (
        "VideoSource",
        lambda: VideoSource(id=81, name="客厅 NAS", type="local"),
        "<VideoSource(id=81, name='客厅 NAS', type='local')>",
    ),
    (
        "Subtitle",
        lambda: Subtitle(id=91, video_id=92, language="zh"),
        "<Subtitle(id=91, video_id=92, language='zh')>",
    ),
    (
        "Tag",
        lambda: Tag(id=101, name="纪录片"),
        "<Tag(id=101, name='纪录片')>",
    ),
    (
        # 字段叫 target_format，标签写的是 format——两头的名字都在这条串里钉住。
        "TranscodeOutput",
        lambda: TranscodeOutput(id=111, video_id=112, target_format="mkv"),
        "<TranscodeOutput(id=111, video_id=112, format='mkv')>",
    ),
    (
        "User",
        lambda: User(id=121, username="admin", role="owner"),
        "<User(id=121, username='admin', role='owner')>",
    ),
    (
        "UserSession",
        lambda: UserSession(user_id=131, expires_at=SESSION_EXPIRES),
        "<UserSession(user_id=131, expires_at=2026-10-10 12:30:00+00:00)>",
    ),
    (
        "Video",
        lambda: Video(id=141, title="某部影片", filepath="nas/media/movie.mkv"),
        "<Video(id=141, title='某部影片', filepath='nas/media/movie.mkv')>",
    ),
    (
        "WatchEvent",
        lambda: WatchEvent(user_id=151, video_id=152, seconds=153),
        "<WatchEvent(user_id=151, video_id=152, seconds=153)>",
    ),
    (
        "Watchlist",
        lambda: Watchlist(id=161, name="周末看"),
        "<Watchlist(id=161, name='周末看')>",
    ),
    (
        "WatchlistItem",
        lambda: WatchlistItem(id=171, watchlist_id=172, video_id=173),
        "<WatchlistItem(id=171, watchlist_id=172, video_id=173)>",
    ),
    (
        # 主键是字符串那一列，所以这一条里两个字段都带引号——它是本文件里唯一
        # 「第一个字段不是整数 id」的那条，写成 `key=` 而不是 `id=` 才有对应。
        "Setting",
        lambda: Setting(key="auto_scan_interval", value="3600"),
        "<Setting(key='auto_scan_interval', value='3600')>",
    ),
]


@pytest.mark.parametrize(
    "name, build, expected",
    CASES,
    ids=[name for name, _, _ in CASES],
)
def test_each_model_repr_reads_its_own_fields(name, build, expected):
    """18 个 repr 各钉一次：18 条独立签名，不共享、不总括。"""
    assert repr(build()) == expected


def test_the_preference_repr_is_the_one_that_needs_a_dict_already_present():
    """prefs 从没赋过值的实例（列的 default 到 INSERT 才生效）repr 当场炸。

    钉的是今天量到的行为，不是应该的行为：全仓唯一构造点显式传 prefs，所以线上
    走不到这一格；改不改是交给用户的选择，源码留原样。
    """
    unsaved = UserPreference(user_id=51)

    with pytest.raises(TypeError) as excinfo:
        repr(unsaved)

    assert str(excinfo.value) == "'NoneType' object is not iterable"
