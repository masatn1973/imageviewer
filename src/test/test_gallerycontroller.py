"""
GalleryController (GTKに依存するクラス) を unittest.mock でテストする例。

ポイント:
- GalleryController 自身は Gtk.Widget を継承していない「普通のPythonクラス」
  なので、コンストラクタに渡す model / view を MagicMock() に差し替えれば、
  本物のGTKウィンドウを一切表示せずにロジックだけをテストできる。
- conftest.py で gi.repository (GTK本体) をまるごと MagicMock に
  差し替えてあるので、このファイルの import 時点でも本物のGTKは不要。
"""

from unittest.mock import MagicMock

import pytest

# conftest.py が sys.modules を書き換えた「後」に import されるので、
# ここで得られる Gdk / GLib は本物ではなく MagicMock。
# ただし同じ属性(例: Gdk.KEY_Right)には常に同じオブジェクトが返るため、
# テストコード側とプロダクトコード側で「同じ偽物のキー定数」を
# 参照でき、比較(==)が成立する。
from gi.repository import Gdk, Gtk

from controllers.gallerycontroller import GalleryController


@pytest.fixture
def controller():
    """model・view を MagicMock に差し替えた GalleryController を用意する。"""
    model = MagicMock()
    view = MagicMock()

    return GalleryController(model, view)


def _make_flowbox_with_children(view, model, count, selected_index, columns=3):
    """flowbox.get_child_at_index(i) が呼ばれたら、対応する MagicMock を
    返すように仕込むヘルパー。

    on_key_pressed は「選択中の子(child)」「表示中の子一覧
    (_visible_children が get_first_child/get_next_sibling で辿る)」
    「移動先の子(target)」を flowbox から取得するため、事前にこれらを
    ちゃんと用意しておく必要がある。
    """
    model.image_files = [f"img{i}.jpg" for i in range(count)]

    children = {}
    for i in range(count):
        child = MagicMock(name=f"child{i}")
        child.get_index.return_value = i
        # デフォルトでは検索フィルタによる絞り込みは行われていない
        # (=すべて表示中)ものとして扱う
        child.get_child_visible.return_value = True
        children[i] = child

    # _visible_children() が get_first_child() -> get_next_sibling() の
    # 単方向リンクリストとして辿れるように仕込む
    for i in range(count):
        children[i].get_next_sibling.return_value = children.get(i + 1)

    # _compute_columns() は各子の get_allocation().y を比較して列数を
    # 数える実装(幅の割り算ではない)。そのため、同じ行に属する子は
    # 同じ y を、次の行の子は違う y を返すようにモックする。
    # 例: columns=3 なら [0,1,2]が y=0(1行目)、[3,4,5]が y=1(2行目)...
    for i in range(count):
        row = i // columns
        allocation = MagicMock(name=f"allocation{i}")
        allocation.y = row
        children[i].get_allocation.return_value = allocation

    flowbox = view.flowbox
    flowbox.get_first_child.return_value = children.get(0)
    flowbox.get_child_at_index.side_effect = lambda i: children.get(i)
    flowbox.get_selected_children.return_value = [children[selected_index]]

    # Page_Up/Page_Down のテストで使う想定の付随的なモック
    # (幅ベースの列数計算は使われなくなったが、他の処理で
    # get_allocated_width 等を参照する場合に備えて残している)
    children[0].get_allocated_width.return_value = 100
    flowbox.get_column_spacing.return_value = 0
    flowbox.get_allocated_width.return_value = 100 * columns

    return children


# ---------------------------------------------------------------------------
# キーボードナビゲーション (on_key_pressed) のテスト
# ---------------------------------------------------------------------------
class TestOnKeyPressed:
    def test_right_arrow_moves_to_next_child(self, controller):
        children = _make_flowbox_with_children(
            controller.view, controller.model, count=10, selected_index=4
        )

        result = controller.on_key_pressed(
            MagicMock(), Gdk.KEY_Right, 0, 0
        )

        assert result is True
        controller.view.flowbox.select_child.assert_called_once_with(children[5])
        children[5].grab_focus.assert_called_once()

    def test_left_arrow_moves_to_previous_child(self, controller):
        children = _make_flowbox_with_children(
            controller.view, controller.model, count=10, selected_index=4
        )

        controller.on_key_pressed(MagicMock(), Gdk.KEY_Left, 0, 0)

        controller.view.flowbox.select_child.assert_called_once_with(children[3])

    def test_right_arrow_stops_at_last_child(self, controller):
        """一番最後の画像で右キーを押しても、それ以上進まないこと
        (循環しない・末尾を超えない)。
        """
        children = _make_flowbox_with_children(
            controller.view, controller.model, count=10, selected_index=9
        )

        controller.on_key_pressed(MagicMock(), Gdk.KEY_Right, 0, 0)

        # 9のまま = children[9] が選択され続ける
        controller.view.flowbox.select_child.assert_called_once_with(children[9])

    def test_left_arrow_stops_at_first_child(self, controller):
        """先頭で左キーを押しても、それ以上戻らないこと。"""
        children = _make_flowbox_with_children(
            controller.view, controller.model, count=10, selected_index=0
        )

        controller.on_key_pressed(MagicMock(), Gdk.KEY_Left, 0, 0)

        controller.view.flowbox.select_child.assert_called_once_with(children[0])

    def test_down_arrow_moves_by_column_count(self, controller):
        """下キーを押すと、列数(columns)ぶんインデックスが進むこと。

        columns=3 に設定しているので、index=1 から下へ移動すると
        1 + 3 = 4 になるはず。
        """
        children = _make_flowbox_with_children(
            controller.view, controller.model,
            count=10, selected_index=1, columns=3,
        )

        controller.on_key_pressed(MagicMock(), Gdk.KEY_Down, 0, 0)

        controller.view.flowbox.select_child.assert_called_once_with(children[4])

    def test_home_key_selects_first_child(self, controller):
        children = _make_flowbox_with_children(
            controller.view, controller.model, count=10, selected_index=5
        )

        controller.on_key_pressed(MagicMock(), Gdk.KEY_Home, 0, 0)

        controller.view.flowbox.select_child.assert_called_once_with(children[0])

    def test_end_key_selects_last_child(self, controller):
        children = _make_flowbox_with_children(
            controller.view, controller.model, count=10, selected_index=0
        )

        controller.on_key_pressed(MagicMock(), Gdk.KEY_End, 0, 0)

        controller.view.flowbox.select_child.assert_called_once_with(children[9])

    def test_no_selection_returns_false(self, controller):
        """何も選択されていない状態でキーを押しても、何もせず False を
        返すこと(GTK側にイベントを渡す = 未処理扱い)。
        """
        controller.view.flowbox.get_selected_children.return_value = []

        result = controller.on_key_pressed(MagicMock(), Gdk.KEY_Right, 0, 0)

        assert result is False

    def test_enter_key_opens_viewer(self, controller):
        """Enterキーで、選択中の画像がビューアーで開かれること。"""
        children = _make_flowbox_with_children(
            controller.view, controller.model, count=10, selected_index=2
        )

        controller.on_key_pressed(MagicMock(), Gdk.KEY_Return, 0, 0)

        controller.view.open_viewer.assert_called_once_with(
            children[2].image_file, controller.model.image_files
        )

    def test_f5_reloads_folder(self, controller):
        _make_flowbox_with_children(
            controller.view, controller.model, count=10, selected_index=0
        )
        controller.model.current_folder = "dummy_folder"

        controller.on_key_pressed(MagicMock(), Gdk.KEY_F5, 0, 0)

        controller.model.load_folder.assert_called_once_with("dummy_folder")

    def test_search_entry_focused_ignores_navigation_keys(self, controller):
        """検索欄 (view.search_entry) にフォーカスがある間は、
        h/j/k/l 等のナビゲーションキーがサムネイル移動として横取り
        されず、on_key_pressed が False (未処理) を返すこと。
        """
        _make_flowbox_with_children(
            controller.view, controller.model, count=10, selected_index=4
        )

        # view.get_focus() が view.search_entry と同じオブジェクトを
        # 返す = 検索欄にフォーカスがある状態を再現する
        controller.view.get_focus.return_value = controller.view.search_entry

        result = controller.on_key_pressed(MagicMock(), Gdk.KEY_Right, 0, 0)

        assert result is False
        controller.view.flowbox.select_child.assert_not_called()

    def test_focus_elsewhere_still_handles_navigation_keys(self, controller):
        """検索欄以外にフォーカスがある場合は、従来通りナビゲーション
        キーが処理されること。
        """
        children = _make_flowbox_with_children(
            controller.view, controller.model, count=10, selected_index=4
        )

        # get_focus() が search_entry とは別のオブジェクトを返す
        # (=検索欄にフォーカスがない)状態
        controller.view.get_focus.return_value = MagicMock(name="some_other_widget")

        result = controller.on_key_pressed(MagicMock(), Gdk.KEY_Right, 0, 0)

        assert result is True
        controller.view.flowbox.select_child.assert_called_once_with(children[5])


# ---------------------------------------------------------------------------
# サムネイル読み込み (_load_next_thumbnail) のテスト
#
# 実際のサムネイル生成(GdkPixbufでのデコード等)は models/thumbnailcache.py
# の ThumbnailCache に委譲されている(そちら側の単体テストは
# tests/test_thumbnailcache.py で行う)。ここでは「コントローラーが
# thumbnail_cache を正しい引数で呼び、結果を正しく view に渡すか」
# だけを検証する。
# ---------------------------------------------------------------------------
class TestLoadNextThumbnail:
    def test_successful_load_adds_thumbnail(self, controller):
        """読み込みに成功したら、正常なサムネイルとして view.add_thumbnail
        が呼ばれること。
        """
        gfile = MagicMock()
        paintable = MagicMock()

        controller.thumbnail_cache = MagicMock()
        controller.thumbnail_cache.get_texture.return_value = paintable
        controller.view.thumbnail_size = 128

        controller.pending_files = [gfile]

        result = controller._load_next_thumbnail()

        controller.thumbnail_cache.get_texture.assert_called_once_with(gfile, 128)

        controller.view.add_thumbnail.assert_called_once_with(
            gfile,
            paintable,
            select=True,  # 1枚目なので選択状態になる
            on_drag_prepare=controller._on_thumbnail_drag_prepare,
            broken=False,
        )
        assert controller.loaded_count == 1
        assert controller.pending_files == []
        # まだ残りがない = キューが空になったので False (idle_addの停止)
        assert result is False

    def test_failed_load_marks_thumbnail_as_broken(self, controller):
        """サムネイル取得(thumbnail_cache.get_texture)が例外を投げても
        外に伝播させず、broken=True のサムネイルとして扱われること。

        なお _load_next_thumbnail は「キューが空になった瞬間」に自動で
        _report_failures() を呼んで failed_files をリセットする仕様
        なので(pending_filesが1件だけの場合はこの1回で空になる)、
        failed_files の中身ではなく view.show_error が呼ばれたことと、
        add_thumbnail が broken=True で呼ばれたことを確認する。
        """
        gfile = MagicMock()
        gfile.get_basename.return_value = "broken.jpg"

        controller.thumbnail_cache = MagicMock()
        controller.thumbnail_cache.get_texture.side_effect = Exception(
            "読み込み失敗(テスト用)"
        )

        controller.pending_files = [gfile]

        controller._load_next_thumbnail()

        _, kwargs = controller.view.add_thumbnail.call_args
        assert kwargs["broken"] is True

        # キューが空になったタイミングで失敗が通知されること
        controller.view.show_error.assert_called_once()

    def test_failed_load_keeps_failed_files_when_queue_not_empty(self, controller):
        """まだキューに他の画像が残っている場合は、failed_filesに
        溜められたままで、まだ通知(_report_failures)されないこと。
        """
        gfile = MagicMock()
        gfile.get_basename.return_value = "broken.jpg"

        controller.thumbnail_cache = MagicMock()
        controller.thumbnail_cache.get_texture.side_effect = Exception(
            "読み込み失敗(テスト用)"
        )

        another_gfile = MagicMock()  # まだ読み込まれていない残り1枚

        controller.pending_files = [gfile, another_gfile]

        controller._load_next_thumbnail()

        assert "broken.jpg" in controller.failed_files
        controller.view.show_error.assert_not_called()


# ---------------------------------------------------------------------------
# 失敗通知 (_report_failures) のテスト
# ---------------------------------------------------------------------------
class TestReportFailures:
    def test_no_failures_does_not_show_error(self, controller):
        controller.failed_files = []

        controller._report_failures()

        controller.view.show_error.assert_not_called()

    def test_failures_show_error_and_are_cleared(self, controller):
        controller.failed_files = ["a.jpg", "b.jpg"]

        controller._report_failures()

        controller.view.show_error.assert_called_once()
        # 通知したあとは、次回のためにリストが空に戻ること
        assert controller.failed_files == []


# ---------------------------------------------------------------------------
# ソート切り替え (on_sort_changed) のテスト
# ---------------------------------------------------------------------------
class TestOnSortChanged:
    @pytest.mark.parametrize(
        "mode_string, expected_mode, expected_reverse",
        [
            ("name", "name", False),
            ("name-desc", "name", True),
            ("date", "date", False),
            ("date-desc", "date", True),
        ],
    )
    def test_dispatches_correct_sort_mode(
        self, controller, mode_string, expected_mode, expected_reverse
    ):
        action = MagicMock()
        value = MagicMock()
        value.get_string.return_value = mode_string

        controller.on_sort_changed(action, value)

        controller.model.set_sort_mode.assert_called_once_with(
            expected_mode, reverse=expected_reverse
        )
        action.set_state.assert_called_once_with(value)
