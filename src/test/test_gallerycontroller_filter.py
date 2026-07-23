# test_gallerycontroller_filter.py
#
# GalleryController.filter_thumbnail の単体テスト。
#
# GalleryController は Gtk / Gio に依存するモジュール(controllers/
# gallerycontroller.py)をインポートするため、実行には PyGObject
# (gi) と GTK4 のライブラリが必要。CI 等で gi が使えない環境では
# 自動的にスキップされる。
#
# 実物の GtkFlowBox や GalleryModel を組み立てるのは大掛かりなので、
# GalleryController.__init__ を経由せずインスタンスを作り、
# filter_thumbnail が参照する属性 (search_text) だけを直接セットして
# ロジック単体をテストする。
#
# 実行例:
#   pytest tests/test_gallerycontroller_filter.py -v

import types

import pytest

gi = pytest.importorskip("gi", reason="PyGObject (gi) がインストールされていません")

try:
    gi.require_version("Gtk", "4.0")
    from controllers.gallerycontroller import GalleryController  # noqa: E402
except (ValueError, ImportError) as e:
    pytest.skip(f"GTK4 が利用できないためスキップします: {e}", allow_module_level=True)


class FakeGFile:
    """Gio.File の代わりに使う、get_basename() だけを持つダミー。"""

    def __init__(self, basename):
        self._basename = basename

    def get_basename(self):
        return self._basename


class FakeChild:
    """Gtk.FlowBoxChild の代わりに使う、image_file 属性だけを持つダミー。"""

    def __init__(self, basename):
        self.image_file = FakeGFile(basename)


def make_controller(search_text=""):
    """Model/View を実際に組み立てずに GalleryController を作る。

    __init__ を呼ぶと本物の Gtk.FlowBox や GalleryModel との
    シグナル接続が必要になるため、__new__ でインスタンスだけ作り、
    filter_thumbnail が使う属性を直接設定する。
    """
    controller = GalleryController.__new__(GalleryController)
    controller.search_text = search_text
    return controller


def test_no_query_shows_everything():
    controller = make_controller("")
    assert controller.filter_thumbnail(FakeChild("photo.jpg")) is True


def test_matches_substring():
    controller = make_controller("beach")
    assert controller.filter_thumbnail(FakeChild("summer_beach_trip.jpg")) is True


def test_case_insensitive():
    controller = make_controller("BEACH")
    assert controller.filter_thumbnail(FakeChild("summer_beach_trip.jpg")) is True


def test_no_match_hides_child():
    controller = make_controller("mountain")
    assert controller.filter_thumbnail(FakeChild("summer_beach_trip.jpg")) is False


def test_child_without_image_file_defaults_to_visible():
    controller = make_controller("anything")
    child = types.SimpleNamespace()  # image_file 属性を持たない

    assert controller.filter_thumbnail(child) is True
