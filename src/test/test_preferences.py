# test_preferences.py
#
# preferences.py (PreferencesWindow) のうち、サムネイルキャッシュの
# 容量表示・クリア処理 (_update_cache_subtitle / on_clear_cache_clicked)
# の単体テスト。
#
# PreferencesWindow は Adw.PreferencesWindow を継承し、
# @Gtk.Template(...) でUIファイルと結びつく「GTKウィジェット」だが、
# conftest.py が
#   - Adw.PreferencesWindow を本物のPythonクラス(_FakeGtkWidget)に、
#   - Gtk.Template を「クラスをそのまま返すだけ」の identity decorator に
# それぞれ差し替えているため、実際のUIファイルやディスプレイなしで
# クラス定義そのものをimportできる。
#
# GalleryController のテストと同じ方針で、__init__ (実際のGio.Settingsや
# シグナル接続が必要)を経由せず __new__ でインスタンスを作り、
# テストに必要な属性(cache_row, parent_window)だけを直接セットする。

from unittest.mock import MagicMock

import pytest

from preferences import PreferencesWindow


def make_preferences_window(thumbnail_cache):
    """cache_row・parent_window.controller.thumbnail_cache だけを
    差し替えた PreferencesWindow を用意する。
    """
    window = PreferencesWindow.__new__(PreferencesWindow)
    window.cache_row = MagicMock(name="cache_row")
    window.parent_window = MagicMock(name="parent_window")
    window.parent_window.controller.thumbnail_cache = thumbnail_cache
    return window


# ---------------------------------------------------------------------------
# _update_cache_subtitle
# ---------------------------------------------------------------------------
class TestUpdateCacheSubtitle:
    def test_shows_formatted_disk_cache_size(self):
        cache = MagicMock()
        cache.disk_cache_size_bytes.return_value = 5 * 1024 * 1024  # 5.0 MB

        window = make_preferences_window(cache)
        window._update_cache_subtitle()

        window.cache_row.set_subtitle.assert_called_once_with("5.0 MB")

    def test_shows_zero_bytes_when_cache_is_empty(self):
        cache = MagicMock()
        cache.disk_cache_size_bytes.return_value = 0

        window = make_preferences_window(cache)
        window._update_cache_subtitle()

        window.cache_row.set_subtitle.assert_called_once_with("0 B")


# ---------------------------------------------------------------------------
# on_clear_cache_clicked
# ---------------------------------------------------------------------------
class TestOnClearCacheClicked:
    def test_clears_both_memory_and_disk_cache(self):
        cache = MagicMock()
        cache.disk_cache_size_bytes.return_value = 1024

        window = make_preferences_window(cache)
        window.on_clear_cache_clicked(MagicMock())

        cache.clear_memory_cache.assert_called_once()
        cache.clear_disk_cache.assert_called_once()

    def test_shows_toast_with_freed_size(self):
        """トーストには「クリア前(削除した分)の容量」が表示されること。"""
        cache = MagicMock()
        cache.disk_cache_size_bytes.return_value = 3 * 1024 * 1024  # 3.0 MB

        window = make_preferences_window(cache)
        window.on_clear_cache_clicked(MagicMock())

        window.parent_window.show_toast.assert_called_once()
        (message,), _ = window.parent_window.show_toast.call_args
        assert "3.0 MB" in message

    def test_updates_subtitle_to_post_clear_size(self):
        """クリア後の表示(cache_row)は、削除前ではなく削除後(=0)の
        容量になっていること。
        """
        cache = MagicMock()
        # 1回目の呼び出し(クリア前の容量計算用)は5MB、
        # 2回目(クリア後、表示更新用)は0を返すようにする。
        cache.disk_cache_size_bytes.side_effect = [5 * 1024 * 1024, 0]

        window = make_preferences_window(cache)
        window.on_clear_cache_clicked(MagicMock())

        window.cache_row.set_subtitle.assert_called_once_with("0 B")

    def test_processing_order(self):
        """「クリア前の容量を覚えておく」→「実際にクリアする」→
        「クリア後の容量で表示を更新する」の順で処理されること。

        この順序が逆になっていると、トーストに"0 B"のような
        意味のない値が表示されてしまう(削除した分の容量を
        知りたいのに、既に空にした後で容量を測ってしまうため)。
        """
        cache = MagicMock()
        call_order = []

        size_sequence = iter(["size_before_clear", "size_after_clear"])
        cache.disk_cache_size_bytes.side_effect = (
            lambda: call_order.append(next(size_sequence)) or 0
        )
        cache.clear_memory_cache.side_effect = (
            lambda: call_order.append("clear_memory")
        )
        cache.clear_disk_cache.side_effect = lambda: call_order.append("clear_disk")

        window = make_preferences_window(cache)
        window.on_clear_cache_clicked(MagicMock())

        assert call_order == [
            "size_before_clear",
            "clear_memory",
            "clear_disk",
            "size_after_clear",
        ]

    def test_freed_size_reflects_size_before_clearing_even_if_large(self):
        """境界値的な確認: 削除前の容量が0でなければ、その値が
        (0ではなく)そのままトーストの文言に反映されること。
        """
        cache = MagicMock()
        cache.disk_cache_size_bytes.side_effect = [1536, 0]  # 1536B -> 1.5 KB

        window = make_preferences_window(cache)
        window.on_clear_cache_clicked(MagicMock())

        (message,), _ = window.parent_window.show_toast.call_args
        assert "1.5 KB" in message
