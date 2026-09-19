"""Tests for the search box parser."""
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
