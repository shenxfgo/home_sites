"""Tests for the filename → series/episode parser."""
import pytest

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
