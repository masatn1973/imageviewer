"""
ViewerController (GTKに依存するクラス) を unittest.mock でテストする例。

GalleryController のときと同じ考え方:
- ViewerController自体はGtk.Widgetを継承していないので、
  view(本来はImageViewerDialog)を MagicMock() に差し替えれば
  本物のGTK画面なしでロジックだけをテストできる。
- state(ImageState)は元々GTKに依存しない普通のクラスなので、モックせず
  本物をそのまま使う。「本物にできるものは本物を使い、GTKなど外部に
  依存する部分だけをモックに差し替える」のが基本方針。
"""

from unittest.mock import MagicMock

import pytest

from gi.repository import Gdk

from models.imagestate import ImageState
from controllers.viewercontroller import ViewerController

# on_scroll のテストで Ctrl キー判定に実際の整数演算(&)を使うため、
# このビットだけは MagicMock ではなく本物の整数に差し替えておく。
# (MagicMock同士の `&` 演算はいつも真扱いになってしまい、
#  「Ctrlが押されていない」ケースを再現できないため)
Gdk.ModifierType.CONTROL_MASK = 0b0100
NO_CTRL_STATE = 0b0000
WITH_CTRL_STATE = 0b0100


def make_gfile(name="photo.jpg", path="/tmp/photo.jpg"):
    """テスト用のダミー画像ファイル(Gio.File の代わり)を作る。"""
    gfile = MagicMock()
    gfile.get_basename.return_value = name
    gfile.get_path.return_value = path
    return gfile


@pytest.fixture
def make_controller():
    """state(本物)・view(MagicMock)を組み合わせた ViewerController を作る。

    呼び出し側で画像ファイルを指定できるようにファクトリ関数として提供する。
    """

    def _make(image_files=None, current_index=0):
        state = ImageState()

        if image_files:
            state.set_files(image_files, current_index)

        view = MagicMock()
        view.is_fullscreen.return_value = False
        view.imagecanvas.current_zoom = 1.0
        view.get_canvas_view_size.return_value = (400, 300)

        controller = ViewerController(state, view)

        # __init__ 内で show_current_image() 等が自動的に呼ばれ、
        # view側のメソッドがすでに何度か呼ばれた状態になっているので、
        # ここでリセットして「テストの操作による呼び出し」だけを
        # まっさらな状態から数えられるようにする。
        view.reset_mock()

        return controller, state, view

    return _make


# ---------------------------------------------------------------------------
# タイトル表示 (_window_title) のテスト
# ---------------------------------------------------------------------------
class TestWindowTitle:
    def test_empty_when_no_current_file(self, make_controller):
        controller, state, view = make_controller(image_files=None)

        assert controller._window_title() == ""

    def test_shows_filename_and_zoom_percent(self, make_controller):
        gfile = make_gfile("photo.jpg")
        controller, state, view = make_controller(image_files=[gfile])

        view.imagecanvas.current_zoom = 1.5  # 150%
        controller.slideshow_mode = False

        assert controller._window_title() == "photo.jpg (150%)"

    def test_slideshow_mode_hides_zoom_percent(self, make_controller):
        """スライドショー中はズーム%を表示せず、ファイル名だけにすること。"""
        gfile = make_gfile("photo.jpg")
        controller, state, view = make_controller(image_files=[gfile])

        controller.slideshow_mode = True

        assert controller._window_title() == "photo.jpg"


# ---------------------------------------------------------------------------
# フィットズーム計算 (_calculate_fit_zoom) のテスト
# ---------------------------------------------------------------------------
class TestCalculateFitZoom:
    def test_returns_default_when_no_pixbuf(self, make_controller):
        controller, state, view = make_controller()

        assert controller._calculate_fit_zoom() == ImageState.DEFAULT_ZOOM_RATIO

    def test_returns_smaller_ratio_to_fit_inside_view(self, make_controller):
        """画像がビューより大きいとき、縦横どちらか小さい方の縮小率に
        合わせること(画像全体が見えるように)。
        """
        controller, state, view = make_controller()

        pixbuf = MagicMock()
        pixbuf.get_width.return_value = 200
        pixbuf.get_height.return_value = 100
        state.pixbuf = pixbuf

        view.get_canvas_view_size.return_value = (100, 100)

        # 幅方向: 100/200 = 0.5, 高さ方向: 100/100 = 1.0 -> 小さい方の0.5
        assert controller._calculate_fit_zoom() == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# スライドショーモード
# ---------------------------------------------------------------------------
class TestSlideshowMode:
    def test_enabling_updates_state_and_title(self, make_controller):
        controller, state, view = make_controller()

        controller.set_slideshow_mode(True)

        assert controller.slideshow_mode is True
        assert state.slideshow_mode is True
        view.set_title.assert_called_once()

    def test_disabling_updates_state(self, make_controller):
        controller, state, view = make_controller()

        controller.set_slideshow_mode(True)
        controller.set_slideshow_mode(False)

        assert controller.slideshow_mode is False
        assert state.slideshow_mode is False


# ---------------------------------------------------------------------------
# フルスクリーン
# ---------------------------------------------------------------------------
class TestFullscreen:
    def test_enter_fullscreen_saves_size_and_calls_view(self, make_controller):
        controller, state, view = make_controller()

        view.get_width.return_value = 800
        view.get_height.return_value = 600

        controller.enter_fullscreen()

        view.fullscreen.assert_called_once()
        assert controller._pre_fullscreen_size == (800, 600)

    def test_enter_fullscreen_does_nothing_if_already_fullscreen(
        self, make_controller
    ):
        controller, state, view = make_controller()
        view.is_fullscreen.return_value = True

        controller.enter_fullscreen()

        view.fullscreen.assert_not_called()

    def test_exit_fullscreen_calls_view(self, make_controller):
        controller, state, view = make_controller()
        view.is_fullscreen.return_value = True

        controller.exit_fullscreen()

        view.unfullscreen.assert_called_once()

    def test_exit_fullscreen_does_nothing_if_not_fullscreen(self, make_controller):
        controller, state, view = make_controller()
        view.is_fullscreen.return_value = False

        controller.exit_fullscreen()

        view.unfullscreen.assert_not_called()

    def test_get_current_window_size_uses_actual_size_when_available(
        self, make_controller
    ):
        controller, state, view = make_controller()
        view.get_width.return_value = 1024
        view.get_height.return_value = 768

        assert controller._get_current_window_size() == (1024, 768)

    def test_get_current_window_size_falls_back_to_settings(self, make_controller):
        """ウィンドウがまだ実サイズを持たない(1以下)ときは、
        GSettingsに保存された値を使うこと。
        """
        controller, state, view = make_controller()
        view.get_width.return_value = 1
        view.get_height.return_value = 1
        view.settings.get_int.side_effect = lambda key: {
            "viewer-width": 640,
            "viewer-height": 480,
        }[key]

        assert controller._get_current_window_size() == (640, 480)


# ---------------------------------------------------------------------------
# キー操作 (on_key_pressed) のテスト
# ---------------------------------------------------------------------------
class TestOnKeyPressed:
    def test_zoom_in_key(self, make_controller):
        controller, state, view = make_controller()

        result = controller.on_key_pressed(MagicMock(), Gdk.KEY_plus, 0, 0)

        assert result is True
        view.imagecanvas.zoom_at_viewport_center.assert_called_once_with(
            zoom_in=True
        )

    def test_zoom_out_key(self, make_controller):
        controller, state, view = make_controller()

        controller.on_key_pressed(MagicMock(), Gdk.KEY_minus, 0, 0)

        view.imagecanvas.zoom_at_viewport_center.assert_called_once_with(
            zoom_in=False
        )

    def test_right_key_shows_next_image(self, make_controller):
        gfiles = [make_gfile("a.jpg"), make_gfile("b.jpg")]
        controller, state, view = make_controller(image_files=gfiles, current_index=0)

        controller.on_key_pressed(MagicMock(), Gdk.KEY_Right, 0, 0)

        assert state.current_index == 1

    def test_left_key_shows_previous_image_with_wraparound(self, make_controller):
        gfiles = [make_gfile("a.jpg"), make_gfile("b.jpg")]
        controller, state, view = make_controller(image_files=gfiles, current_index=0)

        controller.on_key_pressed(MagicMock(), Gdk.KEY_Left, 0, 0)

        # 先頭で「前へ」なので末尾(index=1)に循環すること
        assert state.current_index == 1

    def test_rotate_right_key(self, make_controller):
        controller, state, view = make_controller()

        controller.on_key_pressed(MagicMock(), Gdk.KEY_r, 0, 0)

        assert state.rotation == 90
        view.imagecanvas.redraw.assert_called_once()

    def test_rotate_left_key(self, make_controller):
        controller, state, view = make_controller()

        controller.on_key_pressed(MagicMock(), Gdk.KEY_R, 0, 0)

        assert state.rotation == 270

    def test_zoom_reset_key(self, make_controller):
        controller, state, view = make_controller()
        state.zoom = 5.0
        state.fit_mode = False
        state.set_fit_zoom(0.5)

        controller.on_key_pressed(MagicMock(), Gdk.KEY_0, 0, 0)

        assert state.zoom == 0.5
        assert state.fit_mode is True

    def test_zoom_actual_size_key(self, make_controller):
        controller, state, view = make_controller()

        controller.on_key_pressed(MagicMock(), Gdk.KEY_1, 0, 0)

        assert state.zoom == ImageState.DEFAULT_ZOOM_RATIO
        assert state.fit_mode is False
        view.imagecanvas.redraw.assert_called_once()

    def test_toggle_exif_key_shows_exif_box(self, make_controller):
        """'e' キーでEXIF情報パネルの表示/非表示が切り替わること。

        EXIF自体の中身(exifinfo.pyの詳細)は別テストで扱うので、ここでは
        「表示状態が切り替わり、ラベル更新が呼ばれる」ことだけを確認する。
        対応していない拡張子(.jpg以外)のダミーファイルを使えば、
        実際のEXIF読み込み処理には入らず安全にテストできる。
        """
        gfile = make_gfile("photo.png", path="/tmp/photo.png")
        controller, state, view = make_controller(image_files=[gfile])

        controller.on_key_pressed(MagicMock(), Gdk.KEY_e, 0, 0)

        assert controller.is_show_exif_data is True
        view.info_box.set_visible.assert_called_once_with(True)
        view.update_exif_labels.assert_called_once()

        # もう一度押すと非表示に戻ること
        controller.on_key_pressed(MagicMock(), Gdk.KEY_e, 0, 0)
        assert controller.is_show_exif_data is False
        view.info_box.set_visible.assert_called_with(False)

    def test_fullscreen_toggle_key(self, make_controller):
        controller, state, view = make_controller()
        view.is_fullscreen.return_value = False
        view.get_width.return_value = 800
        view.get_height.return_value = 600

        controller.on_key_pressed(MagicMock(), Gdk.KEY_F11, 0, 0)

        view.fullscreen.assert_called_once()

    def test_unhandled_key_returns_false(self, make_controller):
        controller, state, view = make_controller()

        result = controller.on_key_pressed(MagicMock(), Gdk.KEY_z, 0, 0)

        assert result is False


# ---------------------------------------------------------------------------
# マウスホイールでのズーム (on_scroll) のテスト
# ---------------------------------------------------------------------------
class TestOnScroll:
    def test_scroll_without_ctrl_is_ignored(self, make_controller):
        """Ctrlキーを押していないホイール操作は無視され、ズームしないこと
        (通常のスクロールとして GTK 側に処理を譲る)。
        """
        controller, state, view = make_controller()
        gtk_controller = MagicMock()
        gtk_controller.get_current_event_state.return_value = NO_CTRL_STATE

        result = controller.on_scroll(gtk_controller, 0, -1)

        assert result is False
        view.imagecanvas.zoom_at_cursor.assert_not_called()

    def test_scroll_up_with_ctrl_zooms_in(self, make_controller):
        controller, state, view = make_controller()
        gtk_controller = MagicMock()
        gtk_controller.get_current_event_state.return_value = WITH_CTRL_STATE

        result = controller.on_scroll(gtk_controller, 0, -1)

        assert result is True
        view.imagecanvas.zoom_at_cursor.assert_called_once_with(zoom_in=True)

    def test_scroll_down_with_ctrl_zooms_out(self, make_controller):
        controller, state, view = make_controller()
        gtk_controller = MagicMock()
        gtk_controller.get_current_event_state.return_value = WITH_CTRL_STATE

        controller.on_scroll(gtk_controller, 0, 1)

        view.imagecanvas.zoom_at_cursor.assert_called_once_with(zoom_in=False)


# ---------------------------------------------------------------------------
# ウィンドウを閉じるとき (on_close_request) のテスト
# ---------------------------------------------------------------------------
class TestOnCloseRequest:
    def test_saves_geometry_normally(self, make_controller):
        controller, state, view = make_controller()
        view.is_fullscreen.return_value = False

        controller.on_close_request()

        view.save_window_geometry.assert_called_once_with()
        assert view.parent.viewer is None

    def test_saves_pre_fullscreen_size_when_fullscreen(self, make_controller):
        """フルスクリーン中に閉じた場合は、フルスクリーンになる前の
        ウィンドウサイズを保存すること(全画面サイズを保存してしまうと、
        次回起動時にウィンドウが画面いっぱいになってしまうため)。
        """
        controller, state, view = make_controller()
        view.is_fullscreen.return_value = True
        controller._pre_fullscreen_size = (800, 600)

        controller.on_close_request()

        view.save_window_geometry.assert_called_once_with(800, 600)
