# test_searchfilter.py
#
# models/searchfilter.py の単体テスト。
# GTK に一切依存しないため、通常の pytest だけで実行できる。
#
# 実行例:
#   pytest tests/test_searchfilter.py -v

import pytest

from models.searchfilter import matches_filename


class TestEmptyQuery:
    """検索クエリが空のときは常に全件マッチ(絞り込みなし)になること。"""

    def test_empty_string_matches_anything(self):
        assert matches_filename("photo.jpg", "") is True

    def test_whitespace_only_matches_anything(self):
        assert matches_filename("photo.jpg", "   ") is True


class TestSubstringMatch:
    """部分一致で判定されること。"""

    def test_match_at_start(self):
        assert matches_filename("summer_beach.jpg", "summer") is True

    def test_match_in_middle(self):
        assert matches_filename("summer_beach_trip.jpg", "beach") is True

    def test_match_at_end_including_extension(self):
        assert matches_filename("summer_beach.jpg", ".jpg") is True

    def test_extension_only(self):
        assert matches_filename("photo.png", "png") is True

    def test_no_match(self):
        assert matches_filename("summer_beach.jpg", "mountain") is False

    def test_full_filename_match(self):
        assert matches_filename("IMG_0001.jpg", "IMG_0001.jpg") is True


class TestCaseInsensitive:
    """大文字小文字を区別しないこと。"""

    def test_query_uppercase_filename_lowercase(self):
        assert matches_filename("summer_beach.jpg", "BEACH") is True

    def test_query_lowercase_filename_uppercase(self):
        assert matches_filename("SUMMER_BEACH.JPG", "beach") is True

    def test_mixed_case(self):
        assert matches_filename("IMG_0001.JPG", "img_0001") is True


class TestQueryTrimming:
    """クエリ前後の空白は無視されること。"""

    def test_leading_and_trailing_whitespace_is_trimmed(self):
        assert matches_filename("summer_beach.jpg", "  beach  ") is True

    def test_trimmed_query_that_does_not_match(self):
        assert matches_filename("summer_beach.jpg", "  mountain  ") is False


class TestNonAsciiFilenames:
    """日本語ファイル名でも部分一致で判定できること。"""

    def test_japanese_filename_match(self):
        assert matches_filename("旅行_沖縄_2026.jpg", "沖縄") is True

    def test_japanese_filename_no_match(self):
        assert matches_filename("旅行_沖縄_2026.jpg", "北海道") is False


@pytest.mark.parametrize(
    "filename,query,expected",
    [
        ("a.jpg", "a", True),
        ("a.jpg", "b", False),
        ("", "", True),
        ("", "x", False),
        ("photo (1).jpg", "(1)", True),
    ],
)
def test_matches_filename_parametrized(filename, query, expected):
    assert matches_filename(filename, query) is expected
