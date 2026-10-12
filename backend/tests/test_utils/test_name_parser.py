"""文件名解析的用例：扫描循环里只看文件名，从不看文件内容。

#193 补的是这个文件最后五条没执行过的语句（`57, 108, 112, 138-139`），四条的形状都是真文件名敲得
出来的：没有集数的片子被问要角标、方括号里只剩数字、组名长过上限、`_number` 被问到一个模式里根本没有
的组名。**语句数和上限的单位都已被 #207 改过**：这一格现在 72 句全覆盖，多出的三句是
`import unicodedata`、`def _display_width` 和它的 `return`；而「长过上限」量的是显示列宽，
不再是字符数。上面那四个行号是 #193 当天的量，这一单在它们前面插了三句，于是 108、112、
138-139 今天分别落在 113、119、145-146（57 在插入点之前，没动）。

变异电池逐格量过的结果，写在这里免得下一轮再猜：
- 删掉 57（`episode is None` 那句早退）→ 红一条：角标会拼成「第None集」。
- 删掉 108（空候选与纯数字候选那条 `continue`）→ **等价变异**，而且不等实测就能证：任何让
  这条 `continue` 成立的候选串，必然过不了循环末尾那道「必须含一个拉丁字母或汉字」的检验——
  空串里没有，`isdigit()` 为真的串里也没有（全角数字与带圈数字都算 `isdigit()`，却都不在那道
  检验的字符类里）。留着它只是把意图写在前面，别读成它挡过什么。
- 删掉 112（长度上限那条 `continue`）→ 当时红一条，#207 之后同一格红三条（见下）。
  #193 那轮把它改成按 UTF-8 字节数算 → **只有**那条中文
  长组名红，因为当时上限数的是字符。这一格在 #207 之后**翻过来了**：面板 ⑥ 定甲（按显示宽度封顶），
  于是 27 个汉字（54 列）不再当组名，而 37 个字母（37 列）那一条断言一字未动。
- 删掉 `_number` 的 try（138-139）→ 红一条（`IndexError` 逃出来）；只把 `except` 那三个名字里的
  `IndexError` 拿掉 → 同样只红这一条。

#207 的电池八格，逐格只动一个变量（锚点先断言恰好命中一次，跑完按原字节还原并复核 md5）：
八格全红、零格等价。
- 上限整句删掉 → 红三条（ASCII 那格 + 两条中文）；单位改回 `len(candidate)` → 红两条，
  那一格就是改前的源码；`> 30` 写成 `>= 30` → 红一条（15 个汉字正好 30 列那格被误杀）。
- 宽度助手里的 `("W", "F")` 少掉 `F` → 红一条（全角字母占两格那格）；少掉 `W` → 红三条；加上
  `A` → 红一条（歧义宽度的希腊字母按一列算，那是这一条选的口径）。
  系数 2 改成 1、或整个 `return` 退回 `len(text)` → 各红三条：宽度这一层每个变量都被钉着。

本单顺带量到、源码一行没动的一件事：`episode_label` 这个属性在 `src/` 里**一个调用方都没有**——
扫描只读 `series` / `season` / `episode` 三个字段和 `auto_tags`（`scan_service.py:164-171`），
而前端那枚角标是把同一条三分支规则**自己写了两遍**（`VideoCard.vue:50-54`、`Home.vue:90-93`）。
删掉它、还是把它接进接口让前端只算一遍，是产品形状的选择：按 #189 的先例（零调用方的
`get_video_info` 是用户点头才删的）留给下一块面板，#193 本单只把 census 写在这里。**面板 ⑤ 已定甲
（接进接口、前端只算一遍），落在 #209**——这一单仍然没动那个属性。
"""
import pytest

from src.utils import name_parser as parser_module
from src.utils.name_parser import auto_tags, parse_video_filename


def test_scene_and_episode_form():
    parsed = parse_video_filename("Severance.S01E02.1080p.WEB-DL.x264-NTb.mkv")

    assert parsed.series == "Severance"
    assert parsed.season == 1
    assert parsed.episode == 2
    assert parsed.title == "Severance S01E02"
    assert parsed.episode_label == "S01E02"


def test_chinese_episode_form_keeps_the_group_tag():
    parsed = parse_video_filename("[NC-Raws] 海边的日子 第12集 [WEB-DL 1080p].mkv")

    assert parsed.series == "海边的日子"
    assert parsed.season is None
    assert parsed.episode == 12
    assert parsed.title == "海边的日子 第12集"
    assert parsed.episode_label == "第12集"
    assert parsed.group == "NC-Raws"
    assert auto_tags(parsed) == ("海边的日子", "NC-Raws")


def test_long_form_season_cross_episode():
    parsed = parse_video_filename("Friends.10x03.720p.HDTV.mkv")

    assert (parsed.series, parsed.season, parsed.episode) == ("Friends", 10, 3)
    assert parsed.title == "Friends S10E03"


@pytest.mark.parametrize(
    "filename",
    ["夜空列车.mp4", "100% 胶片.mkv", "72小时营救.mkv", "暗涌.2019.mp4"],
)
def test_titles_without_an_episode_marker_survive_untouched(filename):
    parsed = parse_video_filename(filename)

    assert parsed.episode is None
    assert parsed.series is None
    assert parsed.title in {"夜空列车", "100% 胶片", "72小时营救", "暗涌 2019"}


def test_region_bracket_is_not_a_release_group():
    parsed = parse_video_filename("The Office (US) S03E01 2160p REMUX HEVC.mkv")

    assert parsed.series == "The Office"
    assert parsed.group is None
    assert parsed.title == "The Office S03E01"


def test_release_junk_never_becomes_a_group():
    parsed = parse_video_filename("[1080p] 深夜食堂 S02E05.mkv")

    assert parsed.group is None
    assert (parsed.series, parsed.episode) == ("深夜食堂", 5)


def test_a_marker_with_no_name_in_front_is_not_an_episode():
    parsed = parse_video_filename("EP07 公路旅行.mkv")

    assert parsed.episode is None
    assert parsed.title == "EP07 公路旅行"


def test_extension_is_only_stripped_at_the_end():
    parsed = parse_video_filename("3.14 圆.mp4")

    assert parsed.title == "3.14 圆"


def test_a_file_that_is_only_junk_falls_back_to_its_stem():
    parsed = parse_video_filename("1080p.mkv")

    assert parsed.title == "1080p"


def test_auto_tags_is_empty_for_a_plain_movie():
    parsed = parse_video_filename("前夜.mp4")

    assert auto_tags(parsed) == ()


def test_a_title_without_an_episode_has_no_label():
    # 57：没有集数时这个属性给 None，而不是拼出「第None集」。它今天在全仓零调用方，
    # 钉的是属性自身的形状——详见文件头那条 census。
    assert parse_video_filename("夜空列车.mp4").episode_label is None


def test_a_numeric_or_empty_bracket_is_skipped_when_looking_for_a_group():
    # 108：方括号里只剩数字或空格时跳过它，往后找那个真带字儿的；数字组名（【2024】）也一样。
    assert parse_video_filename("[2024][NCM] 暗涌 S01E01.mkv").group == "NCM"
    assert parse_video_filename("[00] 暗涌 S01E01.mkv").group is None
    assert parse_video_filename("[] 暗涌 S01E01.mkv").group is None
    assert parse_video_filename("【2024】暗涌 S01E01.mkv").group is None


def test_a_group_name_longer_than_the_cap_is_not_a_group():
    # 112：长过上限的候选串要跳过，让后面那个短的当组名。
    too_long = "SubtitleGroupThatIsFarTooLongToBeReal"
    assert len(too_long) == 37
    parsed = parse_video_filename(f"[{too_long}][NCM] 暗涌 S01E01.mkv")
    assert parsed.group == "NCM"


def test_the_group_name_cap_counts_display_width_not_characters():
    # 同一句 112 的另一半：上限的单位是**显示列宽**（#193 面板 ⑥ 甲）。27 个汉字占 54 列，长过
    # 30 列就跳过它，让后面那个短的当组名——#193 那轮它按字符数被收下，钉的是当时的实测行为。
    cjk_name = "字幕组名字长度超过三十个字所以才不会被当成组名哦哦哦哦"
    assert (len(cjk_name), parser_module._display_width(cjk_name)) == (27, 54)
    parsed = parse_video_filename(f"暗涌 [{cjk_name}] [NCM] S01E01.mkv")
    assert parsed.group == "NCM"


def test_the_width_cap_gives_a_cjk_name_the_same_visual_budget_as_an_ascii_one():
    # 上限那个数字没动（还是 30），动的是量法：15 个汉字正好 30 列，收下；16 个汉字 32 列，跳过。
    # 30 列正是 30 个 ASCII 字母占的宽度——换成显示宽度之后，两种名字在界面上一样长。
    fits = "虹彩字幕组名字长度超过十五个字"
    over = "虹彩字幕组名字长度超过十六个字哦"
    assert (len(fits), len(over)) == (15, 16)
    assert (parser_module._display_width(fits), parser_module._display_width(over)) == (30, 32)
    assert parse_video_filename(f"暗涌 [{fits}] S01E01.mkv").group == fits
    assert parse_video_filename(f"暗涌 [{over}] S01E01.mkv").group is None


def test_the_width_helper_counts_columns_and_what_a_terminal_shows():
    # 直接敲这一层（按本文件 _number 那条的先例）：单位是列数，不是字符数也不是字节数。
    # 「W」和「F」都算两列——全角字母、全角标点真占两格；「A」（歧义宽度，如希腊字母）算一列，
    # 那是这一条选的口径，钉在这里免得下一轮读成笔误。
    assert parser_module._display_width("NC-Raws") == 7
    assert parser_module._display_width("字幕组") == 6
    assert parser_module._display_width("ＡＢＣ") == 6
    assert parser_module._display_width("－") == 2
    assert parser_module._display_width("α") == 1
    assert parser_module._display_width("") == 0


def test_the_number_helper_says_none_for_a_group_the_pattern_does_not_have():
    # 138-139 是防御分支：`parse_video_filename` 走不到这里——它先算过 has_season，才敢问 season。
    # 按 #165 / #172 / #178 的先例直接敲那一层：拿一条根本没有 season 组的模式（第N集）问它，
    # `match.group('season')` 抛 IndexError，这一句把它换成 None。
    match = next(
        found
        for found in (pattern.search("暗涌 第12集") for pattern in parser_module._EPISODE_PATTERNS)
        if found is not None and "season" not in found.groupdict()
    )
    assert parser_module._number(match, "episode") == 12
    assert parser_module._number(match, "season") is None
