# window.py
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
from __future__ import annotations

from collections.abc import Callable
from typing import Any

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gdk, Gio, GLib, Gtk

from controllers.gallerycontroller import GalleryController
from models.gallerymodel import GalleryModel
from viewer import ImageViewerDialog


@Gtk.Template(resource_path="/io/github/masatn1973/ImageViewer/window.ui")
class ImageViewerWindow(Adw.ApplicationWindow):
    """メインウィンドウ (View)。

    サムネイル一覧の表示・見た目の更新だけを担当する。
    フォルダ読込・ソート・スライドショー・キー操作などのロジックは
    GalleryModel / GalleryController が持つ。
    """

    __gtype_name__ = "ImageViewerWindow"

    flowbox: Gtk.FlowBox = Gtk.Template.Child()
    scrolled_window: Gtk.ScrolledWindow = Gtk.Template.Child()
    status_label: Gtk.Label = Gtk.Template.Child()
    toast_overlay: Adw.ToastOverlay = Gtk.Template.Child()
    search_bar: Gtk.SearchBar = Gtk.Template.Child()
    search_entry: Gtk.SearchEntry = Gtk.Template.Child()
    thumbnail_size_adjustment: Gtk.Adjustment = Gtk.Template.Child()

    def __init__(self, app: Adw.Application) -> None:
        super().__init__(application=app)

        self.viewer: ImageViewerDialog | None = None
        self.settings = Gio.Settings.new("io.github.masatn1973.ImageViewer")

        self.thumbnail_size: int = self.settings.get_int("thumbnail-size")
        self.thumbnail_size_adjustment.set_value(self.thumbnail_size)

        self.flowbox.set_selection_mode(Gtk.SelectionMode.SINGLE)

        # ウィンドウ内のどこにフォーカスがあっても、文字を入力すると
        # 自動的に検索バーが開いて入力が反映されるようにする
        self.search_bar.set_key_capture_widget(self)

        self.model = GalleryModel()
        self.controller = GalleryController(self.model, self)

        self._setup_actions(app)

        self.set_default_size(
            self.settings.get_int("window-width"),
            self.settings.get_int("window-height"),
        )

        if self.settings.get_boolean("window-maximized"):
            self.maximize()

        self.connect("close-request", self.on_close_request)

    def _setup_actions(self, app: Adw.Application) -> None:
        self.sort_action = Gio.SimpleAction.new_stateful(
            "sort", GLib.VariantType.new("s"), GLib.Variant.new_string("date")
        )
        self.sort_action.connect("change-state", self.controller.on_sort_changed)
        self.add_action(self.sort_action)

        app.set_accels_for_action("win.sort('name')", ["<primary>n"])

        app.set_accels_for_action("win.sort('name-desc')", ["<primary><shift>n"])

        app.set_accels_for_action("win.sort('date')", ["<primary>d"])

        app.set_accels_for_action("win.sort('date-desc')", ["<primary><shift>d"])

        self.reload_action = Gio.SimpleAction.new("reload", None)
        self.reload_action.connect(
            "activate", lambda a, p: self.controller.reload_folder()
        )
        self.reload_action.set_enabled(False)
        self.add_action(self.reload_action)
        app.set_accels_for_action("win.reload", ["F5"])

        self.slideshow_action = Gio.SimpleAction.new("slideshow", None)
        self.slideshow_action.connect("activate", self.controller.on_slideshow)
        self.slideshow_action.set_enabled(False)
        self.add_action(self.slideshow_action)
        app.set_accels_for_action("win.slideshow", ["<primary>s"])

        self.search_action = Gio.SimpleAction.new("toggle-search", None)
        self.search_action.connect("activate", lambda a, p: self.toggle_search_bar())
        self.add_action(self.search_action)
        app.set_accels_for_action("win.toggle-search", ["<primary>f"])

    # --- main.py から呼ばれる公開API ---------------------------------------------
    def on_open(self, action: Gio.SimpleAction, param: GLib.Variant | None) -> None:
        self.controller.on_open(action, param)

    def on_slideshow(self, action: Gio.SimpleAction, param: GLib.Variant | None) -> None:
        self.controller.on_slideshow(action, param)

    def open_path(self, gfile: Gio.File) -> None:
        self.controller.open_path(gfile)

    def toggle_search_bar(self) -> None:
        is_active = self.search_bar.get_search_mode()
        self.search_bar.set_search_mode(not is_active)

        if not is_active:
            self.search_entry.grab_focus()

        else:
            self.flowbox.grab_focus()

    # --- View: サムネイル一覧の更新だけ -------------------------------------------
    def clear_thumbnails(self) -> None:
        self.flowbox.remove_all()

    def add_thumbnail(
        self,
        gfile: Gio.File,
        paintable: Gdk.Paintable,
        select: bool = False,
        on_drag_prepare: Callable[
            [Gtk.DragSource, float, float, Gio.File],
            Gdk.ContentProvider | None
        ] | None = None,
        broken: bool = False
    ) -> None:
        widget = Gtk.Picture.new_for_paintable(paintable)
        widget.set_can_shrink(True)
        widget.set_content_fit(Gtk.ContentFit.CONTAIN)

        child = Gtk.FlowBoxChild()
        child.set_size_request(self.thumbnail_size, self.thumbnail_size)
        child.set_child(widget)
        child.image_file = gfile

        if broken:
            child.add_css_class("thumbnail-broken")

        self.flowbox.append(child)

        if on_drag_prepare is not None:
            drag = Gtk.DragSource.new()
            drag.set_actions(Gdk.DragAction.COPY)
            drag.connect("prepare", on_drag_prepare, gfile)
            child.add_controller(drag)

        if select:
            self.flowbox.select_child(child)

    def set_status(self, text: str) -> None:
        self.status_label.set_text(text)

    def update_status(self, flowbox: Gtk.FlowBox, image_files: list[Gio.File]) -> None:
        selected = flowbox.get_selected_children()

        if not selected:
            self.status_label.set_text("")
            return

        child = selected[0]
        gfile = getattr(child, "image_file", None)

        if gfile is None:
            self.status_label.set_text("")
            return

        filename = gfile.get_basename()

        try:
            index = image_files.index(gfile)
            self.status_label.set_text(f"{index + 1}/{len(image_files)} : {filename}")

        except ValueError:
            self.status_label.set_text(filename)

    # --- View: ビューアーダイアログの開閉 -----------------------------------------
    def open_viewer(self, gfile: Gio.File, image_files: list[Gio.File]) -> None:
        if self.viewer is not None:
            self.viewer.close()
            self.viewer = None

        try:
            start_index = image_files.index(gfile)
        except ValueError:
            start_index = 0

        viewer = ImageViewerDialog(
            self,
            image_files,
            start_index,
        )
        viewer.connect("close-request", self.on_viewer_close)
        viewer.present()

        self.viewer = viewer

    def open_selected_image(self, image_files: list[Gio.File]) -> None:
        selected = self.flowbox.get_selected_children()

        if not selected:
            return

        gfile = getattr(selected[0], "image_file", None)

        if gfile:
            self.open_viewer(gfile, image_files)

    def on_viewer_close(self, win: Gtk.Window) -> bool:
        self.controller.stop_slideshow()
        self.viewer = None
        return False

    # --- ウィンドウ終了時の後始末 ------------------------------------------------
    def on_close_request(self, *args: Any) -> bool:
        if not self.is_maximized():
            self.settings.set_int("window-width", self.get_width())
            self.settings.set_int("window-height", self.get_height())

        self.settings.set_boolean("window-maximized", self.is_maximized())

        if self.viewer is not None:
            self.viewer.close()
            self.viewer = None

        self.flowbox.remove_all()
        self.controller.cleanup()

        return False

    def show_toast(self, message: str) -> None:
        toast = Adw.Toast.new(message)
        toast.set_timeout(4)
        toast.set_priority(Adw.ToastPriority.HIGH)
        self.toast_overlay.add_toast(toast)

    def show_error(self, message: str) -> None:
        self.show_toast(message)
