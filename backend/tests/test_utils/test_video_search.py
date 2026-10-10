"""搜索框解析的用例：一个文本框就是这个产品全部的筛选面。

#178 补的是这个文件最后五条没执行过的语句（`129-130, 170, 187, 212`），现在 126 条语句
全覆盖。三条的形状从地址栏真敲得出来：光杆一个引号、`标签:` 后面只剩一个引号、比较式跨过
一段不像数字的尾巴。第四条（`212`）从 `parse_video_search` 走不到——`require_key=True` 只在
`_consume_comparison` 里出现，而能进那个函数的 token 必然整颗匹配过
`_STANDALONE_COMPARISON`，也就是它本身就是一颗比较键，`buffer` 又从它开头只往后续，所以匹配
到的键永远在 `COMPARISON_KEYS` 里。这一行按 #165 / #172 的先例处理：用例直接敲那一层，钉住
"要键却没键"这道闸门，并声明它是防御分支。

变异电池逐格量过的结果，写在这里免得下一轮再猜：
- 删掉「空 token 跳过」那三行 → 红两条；`标签:` 后面是空串也照样登记 → 红一条；去掉 187 的
  break → **只有** `评分 >=4` 红。`评分 abc` 拆不出它：一次被拒绝的比较式会把 `buffer` 整个
  丢掉，外层循环重新吐出**原 token** 并只前进一格，所以中途吞掉的垃圾不留任何痕迹。
- 两处是**等价变异**，别以为已经钉住了：`_looks_like_comparison_tail` 里"缓冲里已经有这个
  运算符就不许再吞"那半句（改成永远放行，20 条全绿），以及尾巴"认小数点开头"那半句（只认
  数字开头，也全绿）——理由同上一条，被拒绝的比较式从不留下 `position`，这两颗闸门在结果上
  看不见。
"""
from src.utils import video_search as search_module
from src.utils.video_search import parse_video_search


def test_empty_input_is_not_a_filter():
    assert parse_video_search(None).has_conditions is False
    assert parse_video_search("   ").has_conditions is False


def test_plain_words_become_terms():
    query = parse_video_search("  暗涌  第一季 ")
    assert query.terms == ("暗涌", "第一季")
    assert query.rating is None


def test_quoted_phrase_stays_one_term():
    assert parse_video_search('"dark hero" 收藏').terms == ("dark hero", "收藏")


def test_name_filters_accept_both_colons_and_a_space_after_them():
    assert parse_video_search("标签:悬疑").tag_name == "悬疑"
    assert parse_video_search("标签：悬疑").tag_name == "悬疑"
    assert parse_video_search("源: 剧集").source_name == "剧集"
    assert parse_video_search("tag:noir").tag_name == "noir"
    assert parse_video_search("视频源:电影").source_name == "电影"


def test_a_key_without_a_value_stays_a_keyword():
    assert parse_video_search("标签:").terms == ("标签:",)
    assert parse_video_search("源:").terms == ("源:",)


def test_rating_comparison_forms():
    assert parse_video_search("评分>=4").rating == (">=", 4)
    assert parse_video_search("评分 > 4").rating == (">", 4)
    assert parse_video_search("评分≥4").rating == (">=", 4)
    assert parse_video_search("评分=0").rating == ("=", 0)


def test_rating_needs_its_key_and_a_whole_number():
    assert parse_video_search(">=4").terms == (">=4",)
    assert parse_video_search("评分=high").terms == ("评分=high",)


def test_duration_comparison_forms_are_seconds():
    assert parse_video_search("时长>40分钟").duration == (">", 2400)
    assert parse_video_search("时长>=90").duration == (">=", 5400)
    assert parse_video_search(">1.5小时").duration == (">", 5400)
    assert parse_video_search("时长 <= 30秒").duration == ("<=", 30)
    assert parse_video_search("duration<2h").duration == ("<", 7200)


def test_an_unknown_unit_is_a_keyword():
    assert parse_video_search("时长>40天").terms == ("时长>40天",)


def test_watch_states():
    assert parse_video_search("没看过").watch_state == "never"
    assert parse_video_search("未看完").watch_state == "unfinished"
    assert parse_video_search("已看完").watch_state == "finished"


def test_missing_files_are_a_state_of_their_own():
    assert parse_video_search("丢失").missing is True
    assert parse_video_search("已丢失").missing is True
    assert parse_video_search("missing").missing is True
    # the word alone must not also be searched as a keyword
    assert parse_video_search("丢失").terms == ()
    # but only when it is the whole token
    assert parse_video_search("丢失的胶片").missing is None
    assert parse_video_search("丢失的胶片").terms == ("丢失的胶片",)


def test_missing_combines_with_the_rest():
    query = parse_video_search("暗涌 丢失 评分>=3")
    assert query.terms == ("暗涌",)
    assert query.missing is True
    assert query.rating == (">=", 3)


def test_values_that_look_like_operators_stay_keywords():
    query = parse_video_search("16:9 http://x")
    assert query.terms == ("16:9", "http://x")
    assert query.source_name is None


def test_operators_and_keywords_combine():
    query = parse_video_search("暗涌 标签:悬疑 评分>=4 未看完")
    assert query.terms == ("暗涌",)
    assert query.tag_name == "悬疑"
    assert query.rating == (">=", 4)
    assert query.watch_state == "unfinished"


def test_the_last_writing_of_a_key_wins():
    assert parse_video_search("标签:悬疑 标签:科幻").tag_name == "科幻"


def test_a_stray_quote_is_dropped_without_eating_its_neighbours():
    # 129-130：一个孤立的 `"` 本身就是合法的 `\S+`，剥掉引号之后是空串。
    assert parse_video_search('暗涌 " 第一季').terms == ("暗涌", "第一季")
    assert parse_video_search('"').has_conditions is False


def test_a_key_followed_only_by_a_stray_quote_stays_a_keyword():
    # 170：`标签:` 后面只剩一个孤立引号时不许登记一个空标签。
    query = parse_video_search('标签: "')
    assert query.terms == ("标签:",)
    assert query.tag_name is None


def test_a_comparison_stops_absorbing_at_a_tail_that_is_not_a_number():
    # 187：跨过非数字的尾巴不许拼成比较式，否则 `评分 abc` 会变成一个谁也查不到的词。
    query = parse_video_search("评分 abc")
    assert query.terms == ("评分", "abc")
    assert query.rating is None


def test_a_keyless_comparison_is_refused_even_when_the_value_is_a_duration():
    # 212 是防御分支（见文件头）：>= 配上一颗合法时长值时，不许因为"值认得"就登记一个键。
    fields: dict[str, object] = {}
    assert search_module._assign_comparison(">=1.5小时", 7, fields, require_key=True) == 0
    assert fields == {}

    fields_with_key: dict[str, object] = {}
    given = search_module._assign_comparison("时长>=1.5小时", 7, fields_with_key, require_key=True)
    assert given == 7
    assert fields_with_key == {"duration": (">=", 5400)}


def test_a_space_before_the_operator_still_drops_the_filter():
    # 187 的 break 只有这颗输入钉得住：尾巴本身不像数字，但拼上去恰好是一条合法比较式。
    # 这条用例钉的是**今天量出来的行为**，不是它应有的行为——`评分 >=4` 是真敲得出来的写法，
    # 今天的答案是整个筛选静默失效。它属于本轮记下的「空格位置」那一族缺陷（见
    # backend/CLAUDE.md），哪天真要认这个写法，这条要连着源码一起翻，别只改源码留着它绿。
    query = parse_video_search("评分 >=4")
    assert query.terms == ("评分", ">=4")
    assert query.rating is None
