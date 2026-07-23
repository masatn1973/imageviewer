"""
ImageCanvas (Gtk.DrawingArea を継承したクラス) のテスト。

ポイント:
- ImageCanvas は `class ImageCanvas(Gtk.DrawingArea):` のように GTK の
  クラスを「継承」しているため、conftest.py で Gtk.DrawingArea だけ
  MagicMock ではなく本物のPythonクラス(_FakeGtkWidget)に差し替えてある
  (詳しくは conftest.py のコメント参照)。
- scrolled_window(実際は Gtk.ScrolledWindow)は継承ではなく「所有」
  している(self.scrolled_window = scrolled_window)だけなので、
  こちらは今まで通り MagicMock で問題ない。
- hadjustment / vadjustment(スクロール位置を表すオブジェクト)は、
  値の読み書きが絡む(configure() した値を後で get_value() で
  読み直す、など)ため、ただのMagicMockだと「呼ばれたかどうか」しか
  検証できない。ここでは簡易的な「本物らしく振る舞う」FakeAdjustment
  クラスを使い、実際の計算結果まで確認できるようにしている。
"""

import math
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from gi.repository import Gdk, GLib, Gtk

from imagecanvas import ImageCanvas
from models.imagestate import ImageState


# ---------------------------------------------------------------------------
# 共有のGTKモック(Gtk/Gdk/GLib)は全テストで使い回されるオブジェクトなので、
# 各テストの前に呼び出し履歴だけリセットしておく
# (Gtk.DrawingArea への差し替えなど、属性の設定自体は消えない)。
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _reset_shared_gtk_mocks():
    Gtk.reset_mock()
    Gdk.reset_mock()
    GLib.reset_mock()
    yield


class FakeAdjustment:
    """Gtk.Adjustment の簡易的な代役。

    本物と同じように、configure() で設定した値を get_value() / get_upper()
    / get_page_size() で読み直せるようにしてある。
    """

    def __init__(self, value=0.0, upper=100.0, page_size=50.0):
        self.value = value
        self.upper = upper
        self.page_size = page_size
        self._step_increment = 1.0
        self._page_increment = 1.0

    def get_value(self):
        return self.value

    def set_value(self, value):
        self.value = value

    def get_page_size(self):
        return self.page_size

    def get_upper(self):
        return self.upper

    def get_step_increment(self):
        return self._step_increment

    def get_page_increment(self):
        return self._page_increment

    def configure(self, value, lower, upper, step_increment, page_increment, page_size):
        self.value = value
        self.upper = upper
        self.page_size = page_size


def make_pixbuf(width=200, height=100):
    pixbuf = MagicMock(name="pixbuf")
    pixbuf.get_width.return_value = width
    pixbuf.get_height.return_value = height
    return pixbuf


@pytest.fixture
def make_canvas():
    """scrolled_window(MagicMock)・hadj/vadj(FakeAdjustment)を組み合わせた
    ImageCanvas を作るファクトリ。
    """

    def _make(view_width=800, view_height=600, on_zoom_changed=None):
        scrolled_window = MagicMock(name="scrolled_window")
        scrolled_window.get_allocation.return_value = SimpleNamespace(
            width=view_width, height=view_height
        )

        hadj = FakeAdjustment()
        vadj = FakeAdjustment()
        scrolled_window.get_hadjustment.return_value = hadj
        scrolled_window.get_vadjustment.return_value = vadj

        canvas = ImageCanvas(scrolled_window, on_zoom_changed)

        return canvas, scrolled_window, hadj, vadj

    return _make


# ---------------------------------------------------------------------------
# サイズ計算 (_get_view_size / _get_image_size)
# ---------------------------------------------------------------------------
class TestSizeHelpers:
    def test_get_view_size_uses_allocation(self, make_canvas):
        canvas, scrolled_window, hadj, vadj = make_canvas(
            view_width=800, view_height=600
        )

        assert canvas._get_view_size() == (800, 600)

    def test_get_view_size_never_returns_zero(self, make_canvas):
        """ウィンドウがまだ実現されておらず割り当てサイズが0のときでも、
        0除算などを避けるため最低1を返すこと。
        """
        canvas, scrolled_window, hadj, vadj = make_canvas(
            view_width=0, view_height=0
        )

        assert canvas._get_view_size() == (1, 1)

    def test_get_image_size_no_rotation(self, make_canvas):
        canvas, *_ = make_canvas()
        canvas.state = ImageState()
        canvas.state.pixbuf = make_pixbuf(width=200, height=100)
        canvas.state.rotation = 0

        assert canvas._get_image_size() == (200, 100)

    @pytest.mark.parametrize("rotation", [90, 270])
    def test_get_image_size_swaps_on_side_rotation(self, make_canvas, rotation):
        """90度・270度回転しているときは、幅と高さが入れ替わって
        見えるはずなので、それが反映されること。
        """
        canvas, *_ = make_canvas()
        canvas.state = ImageState()
        canvas.state.pixbuf = make_pixbuf(width=200, height=100)
        canvas.state.rotation = rotation

        assert canvas._get_image_size() == (100, 200)

    def test_get_image_size_no_swap_on_180(self, make_canvas):
        canvas, *_ = make_canvas()
        canvas.state = ImageState()
        canvas.state.pixbuf = make_pixbuf(width=200, height=100)
        canvas.state.rotation = 180

        assert canvas._get_image_size() == (200, 100)


# ---------------------------------------------------------------------------
# ズーム (zoom_at_point 系)
# ---------------------------------------------------------------------------
class TestZoomAtPoint:
    def test_does_nothing_without_state(self, make_canvas):
        canvas, scrolled_window, hadj, vadj = make_canvas()
        canvas.state = None

        canvas.zoom_at_point(100, 100, zoom_in=True)

        # 何も起きない = hadjustment の値も変わらない
        assert hadj.value == 0.0

    def test_does_nothing_without_pixbuf(self, make_canvas):
        canvas, scrolled_window, hadj, vadj = make_canvas()
        canvas.state = ImageState()
        canvas.state.pixbuf = None

        canvas.zoom_at_point(100, 100, zoom_in=True)

        assert hadj.value == 0.0

    def test_zoom_in_increases_zoom_ratio(self, make_canvas):
        canvas, scrolled_window, hadj, vadj = make_canvas()
        canvas.state = ImageState()
        canvas.state.pixbuf = make_pixbuf()
        canvas.state.fit_mode = False
        canvas.state.zoom = 1.0

        canvas.zoom_at_point(100, 100, zoom_in=True)

        assert canvas.state.zoom == pytest.approx(1.0 * ImageState.ZOOM_RATIO)
        assert canvas.state.fit_mode is False

    def test_zoom_out_decreases_zoom_ratio(self, make_canvas):
        canvas, scrolled_window, hadj, vadj = make_canvas()
        canvas.state = ImageState()
        canvas.state.pixbuf = make_pixbuf()
        canvas.state.fit_mode = False
        canvas.state.zoom = 1.0

        canvas.zoom_at_point(100, 100, zoom_in=False)

        assert canvas.state.zoom == pytest.approx(1.0 / ImageState.ZOOM_RATIO)

    def test_zoom_in_is_capped_at_max_zoom(self, make_canvas):
        """すでに最大ズームのとき、それ以上ズームインしても変化しない
        (上限でクランプされる)こと。
        """
        canvas, scrolled_window, hadj, vadj = make_canvas()
        canvas.state = ImageState()
        canvas.state.pixbuf = make_pixbuf()
        canvas.state.fit_mode = False
        canvas.state.zoom = ImageState.MAX_ZOOM

        canvas.zoom_at_point(100, 100, zoom_in=True)

        assert canvas.state.zoom == ImageState.MAX_ZOOM
        # 変化なし = 早期リターンしている = hadjustmentも操作されない
        assert hadj.value == 0.0

    def test_zoom_out_is_capped_at_min_zoom(self, make_canvas):
        canvas, scrolled_window, hadj, vadj = make_canvas()
        canvas.state = ImageState()
        canvas.state.pixbuf = make_pixbuf()
        canvas.state.fit_mode = False
        canvas.state.zoom = ImageState.MIN_ZOOM

        canvas.zoom_at_point(100, 100, zoom_in=False)

        assert canvas.state.zoom == ImageState.MIN_ZOOM

    def test_fit_mode_uses_current_zoom_as_base(self, make_canvas):
        """fit_mode中は state.zoom ではなく、実際に画面に表示されている
        current_zoom を基準にズームすること。
        """
        canvas, scrolled_window, hadj, vadj = make_canvas()
        canvas.state = ImageState()
        canvas.state.pixbuf = make_pixbuf()
        canvas.state.fit_mode = True
        canvas.current_zoom = 0.5  # フィット表示で実際に出ている倍率

        canvas.zoom_at_point(100, 100, zoom_in=True)

        assert canvas.state.zoom == pytest.approx(0.5 * ImageState.ZOOM_RATIO)
        assert canvas.state.fit_mode is False  # ズーム操作でフィット解除


# ---------------------------------------------------------------------------
# redraw()
# ---------------------------------------------------------------------------
class TestRedraw:
    def test_does_nothing_without_state(self, make_canvas):
        canvas, *_ = make_canvas()
        canvas.state = None

        canvas.redraw()

        canvas.queue_draw.assert_not_called()

    def test_fit_mode_uses_auto_sizing(self, make_canvas):
        canvas, *_ = make_canvas()
        canvas.state = ImageState()
        canvas.state.pixbuf = make_pixbuf()
        canvas.state.fit_mode = True

        canvas.redraw()

        canvas.set_content_width.assert_called_once_with(0)
        canvas.set_content_height.assert_called_once_with(0)
        canvas.set_hexpand.assert_called_once_with(True)
        canvas.set_vexpand.assert_called_once_with(True)
        canvas.queue_resize.assert_called_once()
        canvas.queue_draw.assert_called_once()

    def test_actual_size_mode_sizes_to_zoomed_image(self, make_canvas):
        """フィットしていないとき、コンテンツサイズは
        「画像の実サイズ×ズーム」と「ビューサイズ」の大きい方になること
        (画像が小さくてもビュー全体を埋めるため)。
        """
        canvas, scrolled_window, hadj, vadj = make_canvas(
            view_width=100, view_height=100
        )
        canvas.state = ImageState()
        canvas.state.pixbuf = make_pixbuf(width=200, height=200)
        canvas.state.fit_mode = False
        canvas.state.zoom = 2.0  # 200 * 2.0 = 400 > ビュー100

        canvas.redraw()

        canvas.set_content_width.assert_called_once_with(400)
        canvas.set_content_height.assert_called_once_with(400)

    def test_schedules_cursor_update(self, make_canvas):
        """redraw() の最後に update_cursor が(次のフレームで)
        呼ばれるようスケジュールされること。
        """
        canvas, *_ = make_canvas()
        canvas.state = ImageState()
        canvas.state.pixbuf = make_pixbuf()

        canvas.redraw()

        GLib.idle_add.assert_called_once_with(canvas.update_cursor)


# ---------------------------------------------------------------------------
# update_cursor()
# ---------------------------------------------------------------------------
class TestUpdateCursor:
    def test_no_state_means_not_pannable(self, make_canvas):
        canvas, *_ = make_canvas()
        canvas.state = None

        result = canvas.update_cursor()

        assert canvas.is_pannable is False
        # 初期化時にも set_cursor(None) が1回呼ばれているため、
        # 回数(assert_called_once_with)ではなく、最後の呼び出し内容
        # (assert_called_with)だけを確認する
        canvas.set_cursor.assert_called_with(None)
        assert result is False

    def test_fit_mode_is_never_pannable(self, make_canvas):
        canvas, scrolled_window, hadj, vadj = make_canvas()
        canvas.state = ImageState()
        canvas.state.pixbuf = make_pixbuf()
        canvas.state.fit_mode = True

        canvas.update_cursor()

        assert canvas.is_pannable is False
        canvas.set_cursor_from_name.assert_called_once_with("default")

    def test_pannable_when_content_larger_than_view(self, make_canvas):
        canvas, scrolled_window, hadj, vadj = make_canvas()
        canvas.state = ImageState()
        canvas.state.pixbuf = make_pixbuf()
        canvas.state.fit_mode = False

        hadj.upper = 2000
        hadj.page_size = 800  # upper > page_size -> はみ出している

        canvas.update_cursor()

        assert canvas.is_pannable is True
        canvas.set_cursor_from_name.assert_called_once_with("all-scroll")

    def test_not_pannable_when_content_fits_in_view(self, make_canvas):
        canvas, scrolled_window, hadj, vadj = make_canvas()
        canvas.state = ImageState()
        canvas.state.pixbuf = make_pixbuf()
        canvas.state.fit_mode = False

        hadj.upper = 800
        hadj.page_size = 800
        vadj.upper = 600
        vadj.page_size = 600

        canvas.update_cursor()

        assert canvas.is_pannable is False
        canvas.set_cursor_from_name.assert_called_once_with("default")


# ---------------------------------------------------------------------------
# draw_image()
# ---------------------------------------------------------------------------
class TestDrawImage:
    def test_no_state_skips_drawing(self, make_canvas):
        canvas, *_ = make_canvas()
        canvas.state = None
        cr = MagicMock(name="cairo_context")

        canvas.draw_image(area=MagicMock(), cr=cr, width=800, height=600)

        assert canvas.draw_width == 800
        assert canvas.draw_height == 600
        cr.save.assert_not_called()

    def test_fit_mode_computes_zoom_to_fit(self, make_canvas):
        canvas, *_ = make_canvas()
        canvas.state = ImageState()
        canvas.state.pixbuf = make_pixbuf(width=1000, height=1000)
        canvas.state.fit_mode = True
        cr = MagicMock(name="cairo_context")

        canvas.draw_image(area=MagicMock(), cr=cr, width=500, height=250)

        # 幅方向: 500/1000=0.5, 高さ方向: 250/1000=0.25 -> 小さい方の0.25
        assert canvas.current_zoom == pytest.approx(0.25)
        cr.paint.assert_called_once()
        cr.restore.assert_called_once()

    def test_slideshow_mode_never_zooms_beyond_100_percent(self, make_canvas):
        """スライドショー中は、小さい画像を無理に拡大しないこと
        (画質が荒れるのを防ぐため)。
        """
        canvas, *_ = make_canvas()
        canvas.state = ImageState()
        canvas.state.pixbuf = make_pixbuf(width=100, height=100)
        canvas.state.fit_mode = True
        canvas.state.slideshow_mode = True
        cr = MagicMock(name="cairo_context")

        # ビューが画像よりずっと大きい(800x600)ので、
        # 通常のフィット計算なら zoom > 1.0 になってしまうケース
        canvas.draw_image(area=MagicMock(), cr=cr, width=800, height=600)

        assert canvas.current_zoom == pytest.approx(1.0)

    def test_actual_size_mode_uses_state_zoom(self, make_canvas):
        canvas, *_ = make_canvas()
        canvas.state = ImageState()
        canvas.state.pixbuf = make_pixbuf(width=100, height=100)
        canvas.state.fit_mode = False
        canvas.state.zoom = 2.5
        cr = MagicMock(name="cairo_context")

        canvas.draw_image(area=MagicMock(), cr=cr, width=800, height=600)

        assert canvas.current_zoom == pytest.approx(2.5)

    def test_notifies_zoom_change_callback(self, make_canvas):
        """ズーム率が(誤差レベルを超えて)変化したとき、
        on_zoom_changed コールバックが呼ばれること。
        """
        on_zoom_changed = MagicMock()
        canvas, *_ = make_canvas(on_zoom_changed=on_zoom_changed)
        canvas.current_zoom = 1.0
        canvas.state = ImageState()
        canvas.state.pixbuf = make_pixbuf(width=100, height=100)
        canvas.state.fit_mode = False
        canvas.state.zoom = 2.0  # 1.0 -> 2.0 に変化
        cr = MagicMock(name="cairo_context")

        canvas.draw_image(area=MagicMock(), cr=cr, width=800, height=600)

        GLib.idle_add.assert_called_once_with(on_zoom_changed)

    def test_does_not_notify_when_zoom_unchanged(self, make_canvas):
        on_zoom_changed = MagicMock()
        canvas, *_ = make_canvas(on_zoom_changed=on_zoom_changed)
        canvas.current_zoom = 2.0
        canvas.state = ImageState()
        canvas.state.pixbuf = make_pixbuf(width=100, height=100)
        canvas.state.fit_mode = False
        canvas.state.zoom = 2.0  # 変化なし

        canvas.draw_image(
            area=MagicMock(), cr=MagicMock(), width=800, height=600
        )

        GLib.idle_add.assert_not_called()

    def test_no_rotation_does_not_call_rotate(self, make_canvas):
        canvas, *_ = make_canvas()
        canvas.state = ImageState()
        canvas.state.pixbuf = make_pixbuf(width=100, height=100)
        canvas.state.fit_mode = False
        canvas.state.zoom = 1.0
        canvas.state.rotation = 0
        cr = MagicMock(name="cairo_context")

        canvas.draw_image(area=MagicMock(), cr=cr, width=800, height=600)

        cr.rotate.assert_not_called()

    def test_90_degree_rotation_translates_and_rotates(self, make_canvas):
        canvas, *_ = make_canvas()
        canvas.state = ImageState()
        canvas.state.pixbuf = make_pixbuf(width=100, height=50)
        canvas.state.fit_mode = False
        canvas.state.zoom = 1.0
        canvas.state.rotation = 90
        cr = MagicMock(name="cairo_context")

        canvas.draw_image(area=MagicMock(), cr=cr, width=800, height=600)

        # pixbuf.get_height() (= 50) の分だけ平行移動してから90度回転する
        cr.translate.assert_any_call(50, 0)
        cr.rotate.assert_called_once_with(math.radians(90))

    def test_draws_pixbuf_and_restores_context(self, make_canvas):
        canvas, *_ = make_canvas()
        canvas.state = ImageState()
        pixbuf = make_pixbuf(width=100, height=100)
        canvas.state.pixbuf = pixbuf
        canvas.state.fit_mode = False
        canvas.state.zoom = 1.0
        cr = MagicMock(name="cairo_context")

        canvas.draw_image(area=MagicMock(), cr=cr, width=800, height=600)

        Gdk.cairo_set_source_pixbuf.assert_called_once_with(cr, pixbuf, 0, 0)
        cr.paint.assert_called_once()
        cr.save.assert_called_once()
        cr.restore.assert_called_once()


# ---------------------------------------------------------------------------
# マウス移動 (on_motion)
# ---------------------------------------------------------------------------
class TestOnMotion:
    def test_updates_mouse_position(self, make_canvas):
        canvas, *_ = make_canvas()

        canvas.on_motion(MagicMock(), 123, 456)

        assert canvas.mouse_x == 123
        assert canvas.mouse_y == 456


# ---------------------------------------------------------------------------
# ドラッグでのパン操作 (on_drag_begin / on_drag_update / on_drag_end)
# ---------------------------------------------------------------------------
class TestDragPan:
    def test_drag_begin_does_nothing_when_not_pannable(self, make_canvas):
        canvas, scrolled_window, hadj, vadj = make_canvas()
        canvas.state = ImageState()
        canvas.state.pixbuf = make_pixbuf()
        canvas.is_pannable = False
        hadj.value = 10.0

        canvas.on_drag_begin(MagicMock(), 0, 0)

        # パン不可のときは開始位置を記録しない(0.0のまま)
        assert canvas.drag_start_hadj == 0.0

    def test_drag_begin_records_start_position_when_pannable(self, make_canvas):
        canvas, scrolled_window, hadj, vadj = make_canvas()
        canvas.state = ImageState()
        canvas.state.pixbuf = make_pixbuf()
        canvas.is_pannable = True
        hadj.value = 30.0
        vadj.value = 40.0

        canvas.on_drag_begin(MagicMock(), 0, 0)

        assert canvas.drag_start_hadj == 30.0
        assert canvas.drag_start_vadj == 40.0

    def test_drag_update_moves_opposite_to_mouse_direction(self, make_canvas):
        """マウスを右/下に動かした分だけ、表示位置(スクロール量)は
        逆方向(左/上)にずれること。
        """
        canvas, scrolled_window, hadj, vadj = make_canvas()
        canvas.state = ImageState()
        canvas.state.pixbuf = make_pixbuf()
        canvas.is_pannable = True
        canvas.drag_start_hadj = 100.0
        canvas.drag_start_vadj = 200.0

        canvas.on_drag_update(MagicMock(), offset_x=20, offset_y=5)

        assert hadj.value == 80.0  # 100 - 20
        assert vadj.value == 195.0  # 200 - 5

    def test_drag_update_does_nothing_when_not_pannable(self, make_canvas):
        canvas, scrolled_window, hadj, vadj = make_canvas()
        canvas.state = ImageState()
        canvas.state.pixbuf = make_pixbuf()
        canvas.is_pannable = False
        hadj.value = 100.0

        canvas.on_drag_update(MagicMock(), offset_x=20, offset_y=5)

        assert hadj.value == 100.0  # 変化しない

    def test_drag_end_refreshes_cursor(self, make_canvas):
        canvas, *_ = make_canvas()
        canvas.state = ImageState()
        canvas.state.pixbuf = make_pixbuf()
        canvas.state.fit_mode = False

        canvas.on_drag_end(MagicMock(), 0, 0)

        # on_drag_end は update_cursor() を呼び、カーソルを再設定する
        canvas.set_cursor_from_name.assert_called_once()
