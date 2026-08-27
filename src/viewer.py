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

from gettext import gettext as _
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gio, Gtk

from controllers.viewercontroller import ViewerController
from imagecanvas import ImageCanvas
from models.exifinfo import ExifData
from models.imagestate import ImageState


@Gtk.Template(resource_path="/io/github/masatn2026/ImageViewer/viewer.ui")
class ImageViewerDialog(Adw.Window):
    """画像1枚表示ダイアログ (View)。

    見た目の構築と更新だけを担当する。ズーム・回転・EXIF表示・
    キー操作などのロジックは ViewerController が持つ。
    """

    __gtype_name__ = "ImageViewerDialog"

    scrolled_window: Gtk.ScrolledWindow = Gtk.Template.Child()

    image_container:Gtk.Box = Gtk.Template.Child()

    prev_button: Gtk.Button = Gtk.Template.Child()
    next_button: Gtk.Button = Gtk.Template.Child()

    headerbar: Adw.HeaderBar = Gtk.Template.Child()
    media_stack: Gtk.Stack = Gtk.Template.Child()
    toast_overlay: Adw.ToastOverlay = Gtk.Template.Child()

    info_box: Gtk.Box = Gtk.Template.Child()
    camera_label: Gtk.Label = Gtk.Template.Child()
    date_label: Gtk.Label = Gtk.Template.Child()
    pixel_size: Gtk.Label = Gtk.Template.Child()
    orientation: Gtk.Label = Gtk.Template.Child()
    shutter_speed: Gtk.Label = Gtk.Template.Child()
    f_number: Gtk.Label = Gtk.Template.Child()
    iso: Gtk.Label = Gtk.Template.Child()
    focal_length: Gtk.Label = Gtk.Template.Child()

    def __init__(
        self,
        parent: Gtk.Window,
        image_files: list[Gio.File] | None = None,
        current_index: int = 0
    ) -> None:
        super().__init__()

        self.parent = parent
        self.set_transient_for(parent)

        self.settings = Gio.Settings.new("io.github.masatn2026.ImageViewer")

        self.state = ImageState()
        self.state.set_files(image_files or [], current_index)

        self.imagecanvas = ImageCanvas(
            self.scrolled_window, self._on_canvas_zoom_changed
        )
        self.imagecanvas.set_state(self.state)
        self.image_container.append(self.imagecanvas)

        self.key_controller = Gtk.EventControllerKey()
        self.add_controller(self.key_controller)

        self.controller = ViewerController(self.state, self)

        self.set_focusable(True)
        self.grab_focus()

        self.set_default_size(
            self.settings.get_int("viewer-width"),
            self.settings.get_int("viewer-height"),
        )

        if self.settings.get_boolean("viewer-maximized"):
            self.maximize()

    def _on_canvas_zoom_changed(self) -> None:
        self.controller.on_canvas_zoom_changed()

    def set_slideshow_mode(self, enabled: bool) -> None:
        self.controller.set_slideshow_mode(enabled)

    # --- View: 見た目の更新だけ ------------------------------------------------
    def show_image_container(self) -> None:
        self.media_stack.set_visible_child(self.image_container)

    def get_canvas_view_size(self) -> tuple[int, int]:
        alloc = self.scrolled_window.get_allocation()
        return max(1, alloc.width), max(1, alloc.height)

    def update_exif_labels(self, info: ExifData) -> None:
        fields = (
            (self.camera_label, _("Camera: "), info.camera),
            (self.date_label, _("Shooting Datetime: "), info.date_str),
            (self.pixel_size, _("Pixel Size: "), info.pixel_size),
            (self.orientation, _("Orientation: "), str(info.orientation) if info.orientation is not None else None),
            (self.shutter_speed, _("Shutter Speed: "), info.shutter_speed_text),
            (self.f_number, _("FNumber: "), info.fnumber_text),
            (self.iso, _("ISO: "), str(info.iso) if info.iso is not None else None),
            (self.focal_length, _("Focal Length: "), info.focal_length_text),
        )

        for label, title, value in fields:
            label.set_text(f"{title}{value}")

    def save_window_geometry(self, width: int | None = None, height: int | None = None) -> None:
        self.settings.set_int(
            "viewer-width", width if width is not None else self.get_width()
        )
        self.settings.set_int(
            "viewer-height", height if height is not None else self.get_height()
        )
        self.settings.set_boolean("viewer-maximized", self.is_maximized())

    # --- window.py から呼ばれる公開API ------------------------------------------
    def set_image_files(self, files: list[Gio.File], preserve_current: bool = True) -> None:
        self.controller.set_image_files(files, preserve_current=preserve_current)

    def show_next_image(self) -> None:
        self.controller.show_next_image()

    def show_previous_image(self) -> None:
        self.controller.show_previous_image()

    def show_error(self, message: str) -> None:
        toast = Adw.Toast.new(message)
        toast.set_timeout(4)
        self.toast_overlay.add_toast(toast)
