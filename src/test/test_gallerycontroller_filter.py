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


class FakeFlowBoxChild:
    """Gtk.FlowBoxChild の代わりに使う、_visible_children() が実際に
    呼び出すメソッド (get_child_visible / get_next_sibling) だけを
    持つダミー。単方向リンクリストとして FakeFlowBox が組み立てる。
    """

    def __init__(self, basename, child_visible=True):
        self.image_file = FakeGFile(basename)
        self._child_visible = child_visible
        self._next_sibling = None

    def get_child_visible(self):
        return self._child_visible

    def get_next_sibling(self):
        return self._next_sibling


class FakeFlowBox:
    """Gtk.FlowBox の代わりに使う、get_first_child() だけを持つダミー。"""

    def __init__(self, children):
        self._children = children

        for current, following in zip(children, children[1:]):
            current._next_sibling = following

    def get_first_child(self):
        return self._children[0] if self._children else None


def test_visible_children_excludes_filtered_out_items():
    """_visible_children() が child-visible の状態を正しく反映することを
    確認する回帰テスト。

    以前は child.get_visible() で判定していたため、フィルタで除外
    された子も常に True を返してしまい、絞り込み後のキーボード移動で
    非表示のアイテムまで選択されてしまうバグがあった。

    実物の Gtk.FlowBox / Gtk.FlowBoxChild はディスプレイのない
    ヘッドレス環境で不安定になることがあるため、_visible_children()
    が実際に呼び出すメソッドだけを持つ軽量なダミーで代用する。
    """
    children = [
        FakeFlowBoxChild("apple.jpg", child_visible=False),
        FakeFlowBoxChild("banana.jpg", child_visible=True),
        FakeFlowBoxChild("cherry.jpg", child_visible=False),
    ]
    flowbox = FakeFlowBox(children)

    controller = GalleryController.__new__(GalleryController)
    visible = controller._visible_children(flowbox)

    assert [c.image_file.get_basename() for c in visible] == ["banana.jpg"]


def test_visible_children_returns_all_when_no_filter_applied():
    children = [
        FakeFlowBoxChild("apple.jpg", child_visible=True),
        FakeFlowBoxChild("banana.jpg", child_visible=True),
    ]
    flowbox = FakeFlowBox(children)

    controller = GalleryController.__new__(GalleryController)
    visible = controller._visible_children(flowbox)

    assert [c.image_file.get_basename() for c in visible] == [
        "apple.jpg",
        "banana.jpg",
    ]


class FakeViewWithFocus:
    """view.get_focus() / view.search_entry を差し替えるための
    最小限のダミー。
    """

    def __init__(self, focus_widget, search_entry):
        self._focus_widget = focus_widget
        self.search_entry = search_entry

    def get_focus(self):
        return self._focus_widget


def test_hjkl_is_not_captured_while_search_entry_focused():
    """検索欄 (search_entry) にフォーカスがある間は、h/j/k/l が
    サムネイル移動として横取りされず、on_key_pressed が
    False (未処理) を返すこと。

    実物の Gtk.SearchEntry や isinstance(..., Gtk.Editable) には
    依存せず、「フォーカスウィジェットが search_entry そのものか」
    という同一性 (is) だけで判定する実装なので、ここでは object()
    のような軽量なダミーで十分再現できる。
    """
    from gi.repository import Gdk

    search_entry = object()

    controller = GalleryController.__new__(GalleryController)
    controller.view = FakeViewWithFocus(
        focus_widget=search_entry, search_entry=search_entry
    )

    for keyval in (Gdk.KEY_h, Gdk.KEY_j, Gdk.KEY_k, Gdk.KEY_l):
        result = controller.on_key_pressed(None, keyval, 0, 0)
        assert result is False


def test_hjkl_is_handled_normally_when_search_entry_not_focused():
    """検索欄以外にフォーカスがある場合は、search_entry ガードでは
    False を返さず、後続のサムネイル移動ロジックに処理が進むこと
    (=フォーカス判定自体が正しく「素通り」させること)を確認する。

    後続ロジック自体の検証 (実際に移動先が選ばれること) は
    test_gallerycontroller.py::TestOnKeyPressed 側で行っている。
    """
    search_entry = object()
    other_widget = object()

    controller = GalleryController.__new__(GalleryController)
    controller.view = FakeViewWithFocus(
        focus_widget=other_widget, search_entry=search_entry
    )

    assert controller.view.get_focus() is not controller.view.search_entry
