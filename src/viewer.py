# viewer.py
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

import gi

from gettext import gettext as _

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Gtk, Adw, Gio

from models.imagestate import ImageState
from imagecanvas import ImageCanvas
from models.videoplayer import FfmpegVideoPlayer
from controllers.viewercontroller import ViewerController


@Gtk.Template(resource_path="/io/github/masatn1973/ImageViewer/viewer.ui")
class ImageViewerDialog(Adw.Window):
    """画像1枚表示ダイアログ (View)。

    見た目の構築と更新だけを担当する。ズーム・回転・EXIF表示・
    キー操作などのロジックは ViewerController が持つ。
    """

    __gtype_name__ = "ImageViewerDialog"

    scrolled_window = Gtk.Template.Child()

    image_container = Gtk.Template.Child()

    prev_button = Gtk.Template.Child()
    next_button = Gtk.Template.Child()

    headerbar = Gtk.Template.Child()
    media_stack = Gtk.Template.Child()
    toast_overlay = Gtk.Template.Child()

    info_box = Gtk.Template.Child()
    Camera_label = Gtk.Template.Child()
    Date_label = Gtk.Template.Child()
    Pixel_size = Gtk.Template.Child()
    Orientation = Gtk.Template.Child()
    ShutterSpeed = Gtk.Template.Child()
    FNumber = Gtk.Template.Child()
    ISO = Gtk.Template.Child()
    FocalLength = Gtk.Template.Child()

    def __init__(self, parent, image_files=None, current_index=0):
        super().__init__()

        self.parent = parent
        self.settings = Gio.Settings.new("io.github.masatn1973.ImageViewer")

        self.state = ImageState()
        self.state.set_files(image_files or [], current_index)

        self.imagecanvas = ImageCanvas(
            self.scrolled_window, self._on_canvas_zoom_changed
        )
        self.imagecanvas.set_state(self.state)
        self.image_container.append(self.imagecanvas)

        # 動画再生用ウィジェット。Gtk.Video(GStreamer)はこの環境の
        # GPU/ドライバとの相性問題(クラッシュ・メモリ肥大化)が
        # 解決できなかったため、ffmpegを子プロセスとして使う自前の
        # 簡易プレーヤー(FfmpegVideoPlayer)に切り替えている。
        self.video_widget = Gtk.Picture()
        self.video_widget.set_can_shrink(True)
        self.video_widget.set_content_fit(Gtk.ContentFit.CONTAIN)

        # 停止中(静止画プレビュー表示時・再生終了後)に、ギャラリーの
        # サムネイルと同じ再生マーク(○に▶)を重ねて表示する。
        self.video_overlay = Gtk.Overlay()
        self.video_overlay.set_child(self.video_widget)
        self.video_overlay.set_cursor_from_name("pointer")

        # クリック判定は再生マークではなく、動画エリア全体に付ける。
        # 再生中はマーク自体が非表示(=クリックを受け付けない)になる
        # ため、マークだけに付けると「再生中にクリックして一時停止」が
        # できなくなってしまう。
        click = Gtk.GestureClick()
        click.connect("released", self._on_video_area_clicked)
        self.video_overlay.add_controller(click)

        self.video_play_icon = Gtk.Box()
        self.video_play_icon.add_css_class("video-play-circle")
        self.video_play_icon.set_halign(Gtk.Align.CENTER)
        self.video_play_icon.set_valign(Gtk.Align.CENTER)
        # クリックはあくまで動画エリア全体(video_overlay)側で受けるので、
        # マーク自身はクリック判定を持たせない(奪わないようにする)。
        self.video_play_icon.set_can_target(False)

        play_icon_image = Gtk.Image.new_from_icon_name(
            "media-playback-start-symbolic"
        )
        play_icon_image.add_css_class("video-play-icon")
        self.video_play_icon.append(play_icon_image)

        self.video_overlay.add_overlay(self.video_play_icon)

        self.media_stack.add_named(self.video_overlay, "video")

        self.video_player = FfmpegVideoPlayer(self.video_widget, self.video_play_icon)

        self.info_box.add_css_class("exif-overlay")

        self.key_controller = Gtk.EventControllerKey()
        self.add_controller(self.key_controller)

        self.add_shortcut(
            Gtk.Shortcut.new(
                Gtk.ShortcutTrigger.parse_string("Right"),
                Gtk.NamedAction.new("next-image"),
            )
        )

        self.add_shortcut(
            Gtk.Shortcut.new(
                Gtk.ShortcutTrigger.parse_string("Escape"),
                Gtk.NamedAction.new("window.close"),
            )
        )

        self.set_focusable(True)
        self.grab_focus()

        self.set_default_size(
            self.settings.get_int("viewer-width"),
            self.settings.get_int("viewer-height"),
        )

        if self.settings.get_boolean("viewer-maximized"):
            self.maximize()

        # View / Model の初期化が終わった最後に Controller を組み立てる
        self.controller = ViewerController(self.state, self)

    def _on_canvas_zoom_changed(self):
        self.controller.on_canvas_zoom_changed()

    def _on_video_area_clicked(self, gesture, n_press, x, y):
        self.controller.toggle_video_playback()

    def set_slideshow_mode(self, enabled):
        self.controller.set_slideshow_mode(enabled)

    # --- View: 見た目の更新だけ ------------------------------------------------
    def show_image_container(self):
        self.media_stack.set_visible_child(self.image_container)

    def show_video_container(self):
        self.media_stack.set_visible_child(self.video_overlay)

    def get_canvas_view_size(self):
        alloc = self.scrolled_window.get_allocation()
        return max(1, alloc.width), max(1, alloc.height)

    def update_exif_labels(self, info):
        fields = (
            (self.Camera_label, _("Camera: "), info.camera),
            (self.Date_label, _("Shooting Datetime: "), info.date_str),
            (self.Pixel_size, _("Pixel Size: "), info.pixel_size),
            (self.Orientation, _("Orientation: "), f"{info.orientation}"),
            (self.ShutterSpeed, _("Shutter Speed: "), f"{info.shutter_speed_text}"),
            (self.FNumber, _("FNumber: "), f"{info.fnumber_text}"),
            (self.ISO, _("ISO: "), f"{info.iso}"),
            (self.FocalLength, _("Focal Length: "), f"{info.focal_length_text}"),
        )

        for label, title, value in fields:
            label.set_text(title + value if value else title)

    def save_window_geometry(self, width=None, height=None):
        self.settings.set_int(
            "viewer-width", width if width is not None else self.get_width()
        )
        self.settings.set_int(
            "viewer-height", height if height is not None else self.get_height()
        )
        self.settings.set_boolean("viewer-maximized", self.is_maximized())

    # --- window.py から呼ばれる公開API ------------------------------------------
    def set_image_files(self, files, preserve_current=True):
        self.controller.set_image_files(files, preserve_current=preserve_current)

    def show_next_image(self):
        self.controller.show_next_image()

    def show_previous_image(self):
        self.controller.show_previous_image()

    def show_error(self, message):
        toast = Adw.Toast.new(message)
        toast.set_timeout(4)
        self.toast_overlay.add_toast(toast)
