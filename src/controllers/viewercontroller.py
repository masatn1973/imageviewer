# viewercontroller.py
#
# Copyright 2026 masatn
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: GPL-3.0-or-later

from gettext import gettext as _
from gi.repository import Gdk, Gtk, GLib, GdkPixbuf, Gio

from controllers import gallerycontroller
from models.exifinfo import get_exif_info
from models.animation import is_gif_path, next_frame_delay
from models.gallerymodel import is_video_path


class ViewerController:
    """viewer.py (ImageViewerDialog) のイベントハンドラを集約する Controller。

    ImageState (Model) と ImageViewerDialog (View) を橋渡しする。
    """

    def __init__(self, state, view):
        self.state = state
        self.view = view
        self.is_show_exif_data = False
        self._load_cancellable = None
        self._anim_timeout_id = None
        self._pre_fullscreen_size = None
        self.slideshow_mode = False
        self._loading_slideshow_mode = False

        scroll = Gtk.EventControllerScroll.new(Gtk.EventControllerScrollFlags.VERTICAL)
        scroll.connect("scroll", self.on_scroll)
        view.imagecanvas.add_controller(scroll)

        view.key_controller.connect("key-pressed", self.on_key_pressed)
        view.prev_button.connect("clicked", lambda *_: self.show_previous_image())
        view.next_button.connect("clicked", lambda *_: self.show_next_image())

        view.connect("notify::default-width", self.on_window_resize)
        view.connect("notify::default-height", self.on_window_resize)
        view.connect("notify::maximized", self.on_window_resize)
        view.connect("close-request", self.on_close_request)

        if state.image_files:
            self.show_current_image()

    def set_slideshow_mode(self, enabled):
        self.slideshow_mode = enabled
        self.state.slideshow_mode = enabled
        self.update_title()

    # --- 画像切り替え -----------------------------------------------------------
    def show_current_image(self):
        if not self.state.image_files:
            return

        self.state.initialize_view()
        self.view.show_image_container()
        self._open_media(self.state.current_file)

        if self.is_show_exif_data:
            self.show_exif_data()

        self.view.imagecanvas.queue_draw()

    def show_next_image(self):
        self.state.next_file()
        self.show_current_image()

    def show_previous_image(self):
        self.state.previous_file()
        self.show_current_image()

    def set_image_files(self, files, preserve_current=True):
        current = self.state.current_file
        self.state.image_files = files

        if preserve_current and current is not None and current in files:
            self.state.current_index = files.index(current)
        else:
            self.state.current_index = 0

    # --- 画像読込 -------------------------------------------------------------
    def _open_media(self, gfile):
        self._stop_animation()
        self._stop_video()

        if self._load_cancellable is not None:
            self._load_cancellable.cancel()
            self._load_cancellable = None

        if is_video_path(gfile.get_path()):
            self._open_video(gfile)
            return

        self.view.show_image_container()

        self._load_cancellable = Gio.Cancellable()

        # 読み込み開始時点のモードを記憶しておく
        # （非同期処理の完了時には self.slideshow_mode が
        # 途中で変わっている可能性があるため）
        self._loading_slideshow_mode = self.slideshow_mode

        # # 新しい画像の準備ができるまでは、今の画像を表示したままにする
        # (state.pixbuf を先に None にすると、その間 画面が空白になりチラつく)
        gfile.read_async(
            GLib.PRIORITY_DEFAULT, self._load_cancellable, self._on_file_read, gfile
        )

    def _on_file_read(self, gfile, result, _gfile):
        try:
            stream = gfile.read_finish(result)

        except GLib.Error as e:
            if not e.matches(Gio.io_error_quark(), Gio.IOErrorEnum.CANCELLED):
                self._show_load_error(gfile)

            return

        path = gfile.get_path()

        if is_gif_path(path):
            # GIFはアニメーションの可能性があるため PixbufAnimation で読み込む。
            # (静止画用の GdkPixbuf.Pixbuf ではアニメーション情報を扱えない)
            GdkPixbuf.PixbufAnimation.new_from_stream_async(
                stream,
                self._load_cancellable,
                self._on_animation_ready,
                (gfile, stream),
            )
            return

        if self._loading_slideshow_mode:
            # スライドショー中は表示サイズ相当まで縮小してデコード（高速）
            win_w, win_h = self.view.get_canvas_view_size()
            target_w = max(win_w, 1) * 2
            target_h = max(win_h, 1) * 2

            # フォーマットによっては at_scale_async が「元画像より小さければ
            # 拡大しない」という仕様を守らず、意図せず引き伸ばしてしまうこと
            # がある(WebP/BMP等)。そのため、先にヘッダーだけ読んで本来の
            # サイズを確認し、すでに表示領域より小さい画像は拡大せず
            # そのままのサイズでデコードする。
            native_size = self._get_native_image_size(gfile)

            if (
                native_size is not None
                and native_size[0] <= target_w
                and native_size[1] <= target_h
            ):
                GdkPixbuf.Pixbuf.new_from_stream_async(
                    stream,
                    self._load_cancellable,
                    self._on_pixbuf_ready,
                    (gfile, stream),
                )
            else:
                GdkPixbuf.Pixbuf.new_from_stream_at_scale_async(
                    stream,
                    target_w,
                    target_h,
                    True,  # preserve_aspect_ratio
                    self._load_cancellable,
                    self._on_pixbuf_ready,
                    (gfile, stream),
                )

        else:
            # 通常時はフルサイズでデコード（実寸表示のため）
            GdkPixbuf.Pixbuf.new_from_stream_async(
                stream, self._load_cancellable, self._on_pixbuf_ready, (gfile, stream)
            )

    def _get_native_image_size(self, gfile):
        path = gfile.get_path()

        if path is None:
            return None

        try:
            info = GdkPixbuf.Pixbuf.get_file_info(path)

        except GLib.Error:
            return None

        if info is None:
            return None

        _format, width, height = info

        if not width or not height:
            return None

        return (width, height)

    def _on_pixbuf_ready(self, stream, result, data):
        gfile, stream = data

        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_stream_finish(result)
            pixbuf = pixbuf.apply_embedded_orientation()

            self.state.pixbuf = pixbuf
            self.update_fit_zoom()
            self.view.imagecanvas.redraw()
            self.update_title()

        except GLib.Error as e:
            if not e.matches(Gio.io_error_quark(), Gio.IOErrorEnum.CANCELLED):
                self._show_load_error(gfile)

        finally:
            stream.close(None)

    def _on_animation_ready(self, stream, result, data):
        gfile, stream = data

        try:
            animation = GdkPixbuf.PixbufAnimation.new_from_stream_finish(result)

            if animation.is_static_image():
                # 1フレームしかない(=実質静止画)場合は、通常の画像と
                # 同じように pixbuf をそのまま表示すればよい
                self.state.pixbuf = animation.get_static_image()
                self.state.pixbuf_animation = None
                self.state.anim_iter = None

            else:
                self.state.pixbuf_animation = animation
                self.state.anim_iter = animation.get_iter(None)
                self.state.pixbuf = self.state.anim_iter.get_pixbuf()
                self._schedule_next_frame()

            self.update_fit_zoom()
            self.view.imagecanvas.redraw()
            self.update_title()

        except GLib.Error as e:
            if not e.matches(Gio.io_error_quark(), Gio.IOErrorEnum.CANCELLED):
                self._show_load_error(gfile)

        finally:
            stream.close(None)

    def _schedule_next_frame(self):
        anim_iter = self.state.anim_iter

        if anim_iter is None:
            return

        delay_ms = next_frame_delay(anim_iter.get_delay_time())

        if delay_ms is None:
            # 負の値はこれ以上進むフレームがない(アニメーション終了)ことを示す
            return

        self._anim_timeout_id = GLib.timeout_add(delay_ms, self._advance_animation)

    def _advance_animation(self):
        self._anim_timeout_id = None

        anim_iter = self.state.anim_iter

        if anim_iter is None:
            return False

        anim_iter.advance(None)
        self.state.pixbuf = anim_iter.get_pixbuf()
        self.view.imagecanvas.queue_draw()

        self._schedule_next_frame()

        return False  # 自前で次のタイマーを登録するため、GLib側の自動再実行は不要

    def _stop_animation(self):
        if self._anim_timeout_id is not None:
            GLib.source_remove(self._anim_timeout_id)
            self._anim_timeout_id = None

        self.state.pixbuf_animation = None
        self.state.anim_iter = None

    # --- 動画再生 --------------------------------------------------------------
    def _open_video(self, gfile):
        self.view.show_video_container()

        if self.slideshow_mode:
            view_w, view_h = self.view.get_canvas_view_size()
            self.view.video_player.play(gfile.get_path(), view_w, view_h)
        else:
            # スライドショー中でなければ自動再生はせず、代表フレームを
            # 1枚だけ静止画として表示しておく(真っ白のままにしないため)。
            # 実際に再生したい場合はスペースキーで開始できる。
            self.view.video_player.show_preview_frame(gfile.get_path())

        self.update_title()

    def _stop_video(self):
        self.view.video_player.stop()

    def toggle_video_playback(self):
        """スペースキーや再生マークのクリックから呼ばれる、
        再生/一時停止/再開の切り替え。

        - 再生中 -> 一時停止
        - 一時停止中 -> 再開
        - 停止中(未再生・再生終了後) -> 先頭から再生

        動画以外を表示中の場合は何もせず False を返す。
        """
        player = self.view.video_player

        if player.is_playing():
            player.pause()
            return True

        if player.is_paused():
            player.resume()
            return True

        current_file = self.state.current_file

        if current_file is None or not is_video_path(current_file.get_path()):
            return False

        view_w, view_h = self.view.get_canvas_view_size()
        player.play(current_file.get_path(), view_w, view_h)

        return True

    def _show_load_error(self, gfile):
        self.state.pixbuf = None
        self.view.imagecanvas.redraw()

        self.view.show_error(
            _("Failed to open {filename}").format(filename=gfile.get_basename())
        )
        self.view.set_title(gfile.get_basename())

    # --- ズーム ----------------------------------------------------------------
    def update_fit_zoom(self):
        self.state.set_fit_zoom(self._calculate_fit_zoom())
        self.view.imagecanvas.redraw()
        self.update_title()

    def _calculate_fit_zoom(self):
        if self.state.pixbuf is None:
            return self.state.DEFAULT_ZOOM_RATIO

        img_w = self.state.pixbuf.get_width()
        img_h = self.state.pixbuf.get_height()

        win_w, win_h = self.view.get_canvas_view_size()

        return min(win_w / img_w, win_h / img_h)

    def update_title(self):
        self.view.set_title(self._window_title())

    def _window_title(self):
        if self.state.current_file is None:
            return ""

        filename = self.state.current_file.get_basename()

        if self.slideshow_mode:
            return filename

        percent = int(self.view.imagecanvas.current_zoom * 100)

        return f"{filename} ({percent}%)"

    def on_canvas_zoom_changed(self):
        self.update_title()

    def toggle_fullscreen(self):
        if self.view.is_fullscreen():
            self.exit_fullscreen()

        else:
            self.enter_fullscreen()

    def enter_fullscreen(self):
        if self.view.is_fullscreen():
            return

        self._pre_fullscreen_size = self._get_current_window_size()
        self.view.fullscreen()

    def _get_current_window_size(self):
        width = self.view.get_width()
        height = self.view.get_height()

        # ウィンドウがまだ実現(realize)されておらず、
        # 実サイズが確定していない場合は、GSettings に保存されている
        # 値にフォールバックする
        if width <= 1 or height <= 1:
            width = self.view.settings.get_int("viewer-width")
            height = self.view.settings.get_int("viewer-height")

        return (width, height)

    def exit_fullscreen(self):
        if not self.view.is_fullscreen():
            return

        self.view.unfullscreen()

        # unfullscreen() は非同期（ウィンドウマネージャー任せ）のため、
        # 直後に set_default_size しても効かないことがある。
        # 1 フレーム後に確実に反映させる。
        if self._pre_fullscreen_size is not None:
            w, h = self._pre_fullscreen_size
            GLib.idle_add(self._restore_pre_fullscreen_size, w, h)

    def _restore_pre_fullscreen_size(self, w, h):
        self.view.set_default_size(w, h)
        return False  # GLib.idle_add: 一度実行したら解除する

    # --- EXIF ------------------------------------------------------------------
    def show_exif_data(self):
        info = get_exif_info(self.state.current_file)
        self.view.update_exif_labels(info)

    def toggle_exif_data(self):
        if not self.is_show_exif_data:
            self.view.info_box.set_visible(True)
            self.show_exif_data()
            self.is_show_exif_data = True
        else:
            self.view.info_box.set_visible(False)
            self.is_show_exif_data = False

    # --- イベントハンドラ ---------------------------------------------------------
    # NOTE: 元の viewer.py の on_key_pressed のロジックをそのまま移設したもの。
    def on_key_pressed(self, controller, keyval, keycode, state):
        canvas = self.view.imagecanvas

        if keyval == Gdk.KEY_Escape and self.view.is_fullscreen():
            gallerycontroller = self.view.parent.controller

            if gallerycontroller.is_slideshow_active():
                gallerycontroller.stop_slideshow()

            else:
                self.exit_fullscreen()

            return True

        if keyval == Gdk.KEY_space:
            if self.toggle_video_playback():
                return True

        if keyval in (Gdk.KEY_plus, Gdk.KEY_KP_Add):
            canvas.zoom_at_viewport_center(zoom_in=True)
            self.update_title()
            return True

        if keyval in (Gdk.KEY_minus, Gdk.KEY_KP_Subtract):
            canvas.zoom_at_viewport_center(zoom_in=False)
            self.update_title()
            return True

        if keyval in (Gdk.KEY_Right, Gdk.KEY_l):
            self.show_next_image()
            return True

        if keyval in (Gdk.KEY_Left, Gdk.KEY_h):
            self.show_previous_image()
            return True

        if keyval == Gdk.KEY_r:
            self.state.rotate_right()
            canvas.redraw()
            self.update_title()
            return True

        elif keyval == Gdk.KEY_R:
            self.state.rotate_left()
            canvas.redraw()
            self.update_title()
            return True

        if keyval == Gdk.KEY_f:
            self.state.toggle_flip_horizontal()
            canvas.redraw()
            self.update_title()
            return True

        elif keyval == Gdk.KEY_F:
            self.state.toggle_flip_vertical()
            canvas.redraw()
            self.update_title()
            return True

        if keyval == Gdk.KEY_e:
            self.toggle_exif_data()
            return True

        if keyval == Gdk.KEY_F11:
            self.toggle_fullscreen()
            return True

        if keyval == Gdk.KEY_0:
            self.state.zoom_reset()
            self.update_fit_zoom()
            return True

        if keyval == Gdk.KEY_1:
            self.state.zoom_actual_size()
            canvas.redraw()
            self.update_title()
            return True

        return False

    def on_scroll(self, controller, dx, dy):
        event_state = controller.get_current_event_state()

        if not (event_state & Gdk.ModifierType.CONTROL_MASK):
            return False

        if dy < 0:
            self.view.imagecanvas.zoom_at_cursor(zoom_in=True)
        else:
            self.view.imagecanvas.zoom_at_cursor(zoom_in=False)

        self.update_title()
        return True

    def on_window_resize(self, *args):
        if self.state.fit_mode:
            GLib.idle_add(self.update_fit_zoom)

    def on_close_request(self, *args):
        self._stop_animation()
        self._stop_video()

        if self.view.is_fullscreen() and self._pre_fullscreen_size is not None:
            w, h = self._pre_fullscreen_size
            self.view.save_window_geometry(w, h)

        else:
            self.view.save_window_geometry()

        self.view.parent.viewer = None
        return False
