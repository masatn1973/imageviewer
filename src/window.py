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
import gi

from gettext import gettext as _

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Gdk, Gtk, Adw, Gio
from gi.repository import GLib

from viewer import ImageViewerDialog
from models.gallerymodel import GalleryModel
from controllers.gallerycontroller import GalleryController


@Gtk.Template(resource_path="/io/github/masatn1973/ImageViewer/window.ui")
class ImageViewerWindow(Adw.ApplicationWindow):
    """メインウィンドウ (View)。

    サムネイル一覧の表示・見た目の更新だけを担当する。
    フォルダ読込・ソート・スライドショー・キー操作などのロジックは
    GalleryModel / GalleryController が持つ。
    """

    __gtype_name__ = "ImageViewerWindow"

    flowbox = Gtk.Template.Child()
    status_label = Gtk.Template.Child()
    scrolled_window = Gtk.Template.Child()
    toast_overlay = Gtk.Template.Child()
    search_button = Gtk.Template.Child()
    search_bar = Gtk.Template.Child()
    search_entry = Gtk.Template.Child()
    thumbnail_size_scale = Gtk.Template.Child()
    thumbnail_size_adjustment = Gtk.Template.Child()

    def __init__(self, app):
        super().__init__(application=app)

        self.viewer = None
        self.settings = Gio.Settings.new("io.github.masatn1973.ImageViewer")

        self.thumbnail_size = self.settings.get_int("thumbnail-size")
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

    def _setup_actions(self, app):
        self.sort_action = Gio.SimpleAction.new_stateful(
            "sort", GLib.VariantType.new("s"), GLib.Variant.new_string("date")
        )
        self.sort_action.connect("change-state", self.controller.on_sort_changed)
        self.add_action(self.sort_action)

        action = Gio.SimpleAction.new("sort-name", None)
        action.connect("activate", lambda a, p: self.controller.set_sort_mode("name"))
        self.add_action(action)
        app.set_accels_for_action("win.sort('name')", ["<primary>n"])

        action = Gio.SimpleAction.new("sort-name-desc", None)
        action.connect(
            "activate",
            lambda a, p: self.controller.set_sort_mode("name", reverse=True),
        )
        self.add_action(action)
        app.set_accels_for_action("win.sort('name-desc')", ["<primary><shift>n"])

        action = Gio.SimpleAction.new("sort-date", None)
        action.connect("activate", lambda a, p: self.controller.set_sort_mode("date"))
        self.add_action(action)
        app.set_accels_for_action("win.sort('date')", ["<primary>d"])

        action = Gio.SimpleAction.new("sort-date-desc", None)
        action.connect(
            "activate",
            lambda a, p: self.controller.set_sort_mode("date", reverse=True),
        )
        self.add_action(action)
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
    def on_open(self, action, param):
        self.controller.on_open(action, param)

    def on_slideshow(self, action, param):
        self.controller.on_slideshow(action, param)

    def toggle_search_bar(self):
        is_active = self.search_bar.get_search_mode()
        self.search_bar.set_search_mode(not is_active)

        if not is_active:
            self.search_entry.grab_focus()

        else:
            self.flowbox.grab_focus()

    # --- View: サムネイル一覧の更新だけ -------------------------------------------
    def clear_thumbnails(self):
        child = self.flowbox.get_first_child()

        while child:
            next_child = child.get_next_sibling()
            self.flowbox.remove(child)
            child = next_child

    def add_thumbnail(
        self, gfile, paintable, select=False, on_drag_prepare=None, broken=False
    ):
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

    def set_status(self, text):
        self.status_label.set_text(text)

    def update_status(self, flowbox, image_files):
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

        if gfile in image_files:
            index = image_files.index(gfile)
            self.status_label.set_text(f"{index + 1}/{len(image_files)} : {filename}")

        else:
            self.status_label.set_text(filename)

    # --- View: ビューアーダイアログの開閉 -----------------------------------------
    def open_viewer(self, gfile, image_files):
        if self.viewer is not None:
            self.viewer.close()
            self.viewer = None

        viewer = ImageViewerDialog(
            self,
            image_files,
            image_files.index(gfile) if gfile in image_files else 0,
        )
        viewer.connect("close-request", self.on_viewer_close)
        viewer.present()

        self.viewer = viewer

    def open_selected_image(self, image_files):
        selected = self.flowbox.get_selected_children()

        if not selected:
            return

        gfile = getattr(selected[0], "image_file", None)

        if gfile:
            self.open_viewer(gfile, image_files)

    def on_viewer_close(self, win):
        self.controller.stop_slideshow()
        self.viewer = None
        return False

    # --- ウィンドウ終了時の後始末 ------------------------------------------------
    def on_close_request(self, *args):
        self.settings.set_int("window-width", self.get_width())
        self.settings.set_int("window-height", self.get_height())
        self.settings.set_boolean("window-maximized", self.is_maximized())

        self.model.stop_monitor()

        return False

    def open_path(self, gfile):
        self.controller.open_path(gfile)

    def show_toast(self, message):
        toast = Adw.Toast.new(message)
        toast.set_timeout(4)
        self.toast_overlay.add_toast(toast)

    def show_error(self, message):
        self.show_toast(message)
