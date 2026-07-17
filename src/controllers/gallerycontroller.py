# gallery_controller.py
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

from gi.repository import Gdk, Gtk, Gio, GLib, GdkPixbuf

THUMB = 128


class GalleryController:
    """window.py (ImageViewerWindow) のイベントハンドラを集約する Controller。

    View (ImageViewerWindow) からのシグナルを受けて GalleryModel を更新し、
    GalleryModel の変化を View に反映する橋渡し役。
    """

    def __init__(self, model, view):
        self.model = model
        self.view = view

        self.slideshow_id = None
        self.pending_files = []
        self.loaded_count = 0
        self.thumbnail_idle_id = None

        # Model -> Controller
        self.model.connect("files-loaded", self.on_files_loaded)

        # View -> Controller
        view.flowbox.connect("child-activated", self.on_child_activated)
        view.flowbox.connect("selected-children-changed", self.on_selection_changed)

        drop_target = Gtk.DropTarget.new(Gdk.FileList, Gdk.DragAction.COPY)
        drop_target.connect("drop", self.on_drop)
        view.add_controller(drop_target)

        key_controller = Gtk.EventControllerKey()
        key_controller.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        key_controller.connect("key-pressed", self.on_key_pressed)
        view.add_controller(key_controller)

    # --- Model -> View ---------------------------------------------------------
    def on_files_loaded(self, model):
        if self.thumbnail_idle_id is not None:
            GLib.source_remove(self.thumbnail_idle_id)
            self.thumbnail_idle_id = None

        self.view.clear_thumbnails()

        self.pending_files = list(model.image_files)
        self.loaded_count = 0
        self.thumbnail_idle_id = GLib.idle_add(self._load_next_thumbnail)

        self.view.reload_action.set_enabled(True)
        self.view.slideshow_action.set_enabled(len(model.image_files) > 0)

    def _load_next_thumbnail(self):
        if not self.pending_files:
            self.thumbnail_idle_id = None
            return False

        gfile = self.pending_files.pop(0)

        try:
            stream = gfile.read(None)

            try:
                pixbuf = GdkPixbuf.Pixbuf.new_from_stream_at_scale(
                    stream, THUMB, THUMB, True, None
                )
                pixbuf = pixbuf.apply_embedded_orientation()
            finally:
                stream.close(None)

            self.view.add_thumbnail(
                gfile,
                pixbuf,
                select=(self.loaded_count == 0),
                on_drag_prepare=self._on_thumbnail_drag_prepare,
            )

            self.loaded_count += 1
            self.view.set_status(f"{self.loaded_count} " + _("image(s) read."))

        except Exception:
            print("FAILED:", gfile.get_basename())

        if not self.pending_files:
            self.thumbnail_idle_id = None
            return False

        return True

    def _on_thumbnail_drag_prepare(self, source, x, y, gfile):
        file_list = Gdk.FileList.new_from_array([gfile])
        return Gdk.ContentProvider.new_for_value(file_list)

    # --- View -> Model: フォルダ操作 ----------------------------------------
    def on_open(self, action, param):
        dialog = Gtk.FileDialog()
        dialog.select_folder(self.view, None, self._on_folder_selected)

    def _on_folder_selected(self, dialog, result):
        try:
            folder = dialog.select_folder_finish(result)
        except Exception as e:
            print("select_folder_finish:", e)
            return

        if folder:
            self.model.load_folder(folder)

    def on_drop(self, target, value, x, y):
        files = value.get_files()

        for file in files:
            if (
                file.query_file_type(Gio.FileQueryInfoFlags.NONE, None)
                == Gio.FileType.DIRECTORY
            ):
                GLib.idle_add(self._open_dropped_folder, file)
                return True

        return False

    def _open_dropped_folder(self, folder):
        self.model.load_folder(folder)
        return False

    def reload_folder(self):
        self.model.load_folder(self.model.current_folder)

        if self.view.viewer:
            self.view.viewer.set_image_files(self.model.image_files)

    # --- View -> Model: ソート ---------------------------------------------
    def on_sort_changed(self, action, value):
        mode = value.get_string()
        action.set_state(value)

        if mode == "name":
            self.model.set_sort_mode("name", reverse=False)
        elif mode == "name-desc":
            self.model.set_sort_mode("name", reverse=True)
        elif mode == "date":
            self.model.set_sort_mode("date", reverse=False)
        elif mode == "date-desc":
            self.model.set_sort_mode("date", reverse=True)

    def set_sort_mode(self, mode, reverse=False):
        self.model.set_sort_mode(mode, reverse)

    # --- サムネイル選択 / ビューアー起動 ---------------------------------------
    def on_child_activated(self, flowbox, child):
        gfile = getattr(child, "image_file", None)

        if not gfile:
            return

        self.view.open_viewer(gfile, self.model.image_files)

    def on_selection_changed(self, flowbox):
        self.view.update_status(flowbox, self.model.image_files)

    # --- スライドショー ---------------------------------------------------------
    def on_slideshow(self, action, param):
        if self.slideshow_id is None:
            self._start_slideshow()
        else:
            self._stop_slideshow()

    def _start_slideshow(self):
        if self.view.viewer is None:
            self.view.open_selected_image(self.model.image_files)

        if self.view.viewer is None:
            return

        interval = self.view.settings.get_uint("slideshow-interval")
        self.slideshow_id = GLib.timeout_add(interval * 1000, self._slideshow_next)

    def _slideshow_next(self):
        if not self.model.image_files:
            self._stop_slideshow()
            return False

        if self.view.viewer is None:
            self._stop_slideshow()
            return False

        self.view.viewer.show_next_image()
        return True

    def stop_slideshow(self):
        self._stop_slideshow()

    def _stop_slideshow(self):
        if self.slideshow_id is not None:
            GLib.source_remove(self.slideshow_id)
            self.slideshow_id = None

    # --- キーボードナビゲーション -------------------------------------------------
    # NOTE: 元の window.py の on_key_pressed のロジックをそのまま移設したもの。
    #       参照先を self.flowbox -> flowbox / self.image_files -> image_files
    #       に置き換えただけで、判定ロジック自体は変更していない。
    def on_key_pressed(self, controller, keyval, keycode, state):
        flowbox = self.view.flowbox
        image_files = self.model.image_files

        selected = flowbox.get_selected_children()

        if not selected:
            return False

        child = selected[0]

        if keyval in (Gdk.KEY_space, Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            self.on_child_activated(flowbox, selected[0])
            return True

        index = child.get_index()
        new_index = index
        first_child = flowbox.get_child_at_index(0)

        if first_child is None:
            return False

        item_width = (
            first_child.get_allocated_width() + flowbox.get_column_spacing()
        )
        columns = max(1, flowbox.get_allocated_width() // item_width)

        if keyval == Gdk.KEY_F5:
            self.reload_folder()
            return True

        if keyval in (Gdk.KEY_h, Gdk.KEY_Left, Gdk.KEY_ISO_Left_Tab):
            if new_index > 0:
                new_index -= 1

        elif keyval in (Gdk.KEY_j, Gdk.KEY_Down):
            if (new_index + columns) < len(image_files):
                new_index += columns

        elif keyval in (Gdk.KEY_k, Gdk.KEY_Up):
            if (new_index - columns) >= 0:
                new_index -= columns

        elif keyval in (Gdk.KEY_l, Gdk.KEY_Right, Gdk.KEY_Tab):
            if (new_index + 1) < len(image_files):
                new_index += 1

        elif keyval == Gdk.KEY_Home:
            new_index = 0

        elif keyval == Gdk.KEY_End:
            new_index = len(image_files) - 1

        elif keyval == Gdk.KEY_Page_Up:
            vadj = self.view.scrolled_window.get_vadjustment()
            page_height = vadj.get_page_size()
            row_height = (
                first_child.get_allocated_height() + flowbox.get_row_spacing()
            )
            visible_rows = max(1, int(page_height // row_height))
            page_size = visible_rows * columns

            if (new_index - page_size) > 0:
                new_index -= page_size
            else:
                new_index = 0

            target = flowbox.get_child_at_index(new_index)
            if target:
                flowbox.select_child(target)

        elif keyval == Gdk.KEY_Page_Down:
            vadj = self.view.scrolled_window.get_vadjustment()
            page_height = vadj.get_page_size()
            row_height = (
                first_child.get_allocated_height() + flowbox.get_row_spacing()
            )
            visible_rows = max(1, int(page_height // row_height))
            page_size = visible_rows * columns

            if (new_index + page_size) <= len(image_files):
                new_index += page_size
            else:
                new_index = len(image_files) - 1

            target = flowbox.get_child_at_index(new_index)
            if target:
                flowbox.select_child(target)

        else:
            return False

        new_index = max(0, min(new_index, len(image_files) - 1))
        target = flowbox.get_child_at_index(new_index)

        if target:
            flowbox.unselect_all()
            flowbox.select_child(target)
            target.grab_focus()

        return True
