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
import os
import gettext
import locale
import gi


APP_ID = "/io/github/masatn1973/ImageViewer"

locale.bindtextdomain(APP_ID, "/app/share/locale")
locale.textdomain(APP_ID)

gettext.bindtextdomain(APP_ID, "/app/share/locale")
gettext.textdomain(APP_ID)


from gettext import gettext as _


gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

gi.require_version("GExiv2", "0.16")

from datetime import datetime
from collections import deque

from gi.repository import GExiv2
from gi.repository import Gdk, Gtk, Adw, Gio
from gi.repository import GObject, GdkPixbuf, GLib

from viewer import ImageViewerDialog

IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp", ".tiff")

THUMB = 128


@Gtk.Template(resource_path="/io/github/masatn1973/ImageViewer/window.ui")
class ImageViewerWindow(Adw.ApplicationWindow):
    __gtype_name__ = "ImageViewerWindow"

    flowbox = Gtk.Template.Child()
    status_label = Gtk.Template.Child()
    scrolled_window = Gtk.Template.Child()

    def __init__(self, app):
        super().__init__(application=app)

        self.viewer = None
        self.image_files = []

        self.thumbnail_idle_id = None

        self.current_folder = None

        self.slideshow_id = None

        self.settings = Gio.Settings.new("io.github.masatn1973.ImageViewer")

        self.flowbox.set_selection_mode(Gtk.SelectionMode.SINGLE)

        self.flowbox.connect("child-activated", self.on_child_activated)

        self.sort_mode = "date"
        self.sort_reverse = False

        self.folder_monitor = None
        self.reload_timeout = 0

        drop_target = Gtk.DropTarget.new(Gdk.FileList, Gdk.DragAction.COPY)
        drop_target.connect("drop", self.on_drop)

        self.add_controller(drop_target)

        # Action
        self.sort_action = Gio.SimpleAction.new_stateful(
            "sort", GLib.VariantType.new("s"), GLib.Variant.new_string("date")
        )
        self.sort_action.connect("change-state", self.on_sort_changed)
        self.add_action(self.sort_action)

        action = Gio.SimpleAction.new("sort-name", None)
        action.connect("activate", lambda a, p: self.set_sort_mode("name"))
        self.add_action(action)

        action = Gio.SimpleAction.new("sort-name-desc", None)
        action.connect(
            "activate", lambda a, p: self.set_sort_mode("name", reverse=True)
        )
        self.add_action(action)

        action = Gio.SimpleAction.new("sort-date", None)
        action.connect("activate", lambda a, p: self.set_sort_mode("date"))
        self.add_action(action)

        action = Gio.SimpleAction.new("sort-date-desc", None)
        action.connect(
            "activate", lambda a, p: self.set_sort_mode("date", reverse=True)
        )
        self.add_action(action)

        self.reload_action = Gio.SimpleAction.new("reload", None)
        self.reload_action.connect("activate", lambda a, p: self.reload_folder())
        self.reload_action.set_enabled(False)
        self.add_action(self.reload_action)
        app.set_accels_for_action("win.reload", ["F5"])

        slideshow_action = Gio.SimpleAction.new("slideshow", None)
        slideshow_action.connect("activate", self.on_slideshow)
        slideshow_action.set_enabled(False)
        self.add_action(slideshow_action)

        self.slideshow_action = slideshow_action
        app.set_accels_for_action("win.slideshow", ["<Ctrl>s"])

        controller = Gtk.EventControllerKey()
        controller.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        controller.connect("key-pressed", self.on_key_pressed)
        self.add_controller(controller)

        self.set_default_size(
            self.settings.get_int("window-width"),
            self.settings.get_int("window-height"),
        )

        if self.settings.get_boolean("window-maximized"):
            self.maximize()

        self.connect("close-request", self.on_close_request)

    def on_folder_changed(self, monitor, file, other_file, event_type):
        if self.reload_timeout:
            GLib.source_remove(self.reload_timeout)

        self.reload_timeout = GLib.timeout_add(300, self.reload_folder)

    def start_folder_monitor(self, folder):
        if self.folder_monitor:
            self.folder_monitor.cancel()

        self.folder_monitor = folder.monitor_directory(Gio.FileMonitorFlags.NONE, None)

        self.folder_monitor.connect("changed", self.on_folder_changed)

    def on_thumbnail_drag_prepare(self, source, x, y, gfile):
        file_list = Gdk.FileList.new_from_array([gfile])
        return Gdk.ContentProvider.new_for_value(file_list)

    def open_dropped_folder(self, folder):
        self.load_folder(folder)
        return False

    def on_drop(self, target, value, x, y):
        files = value.get_files()

        for file in files:
            if (
                file.query_file_type(Gio.FileQueryInfoFlags.NONE, None)
                == Gio.FileType.DIRECTORY
            ):
                GLib.idle_add(self.open_dropped_folder, file)
                return True

        return False

    def on_sort_changed(self, action, value):
        mode = value.get_string()

        action.set_state(value)

        if mode == "name":
            self.sort_mode = "name"
            self.sort_reverse = False

        elif mode == "name-desc":
            self.sort_mode = "name"
            self.sort_reverse = True

        elif mode == "date":
            self.sort_mode = "date"
            self.sort_reverse = False

        elif mode == "date-desc":
            self.sort_mode = "date"
            self.sort_reverse = True

        if self.current_folder:
            self.load_folder(self.current_folder)

    def set_sort_mode(self, mode, reverse=False):
        self.sort_mode = mode
        self.sort_reverse = reverse

        if self.current_folder is not None:
            self.load_folder(self.current_folder)

    def reload_folder(self):
        self.reload_timeout = 0

        self.load_folder(self.current_folder)

        if self.viewer:
            self.viewer.set_image_files(self.image_files)

        return False

    def set_slideshow_interval(self, seconds):
        self.slideshow_interval = seconds * 1000

    def on_slideshow(self, action, param):
        if self.slideshow_id is None:
            self.start_slideshow()

        else:
            self.stop_slideshow()

    def stop_slideshow(self):
        if self.slideshow_id is not None:
            GLib.source_remove(self.slideshow_id)
            self.slideshow_id = None

    def slideshow_next(self):
        if not self.image_files:
            self.stop_slideshow()
            return False

        if self.viewer is None:
            self.stop_slideshow()
            return False

        self.viewer.show_next_image()

        return True

    def start_slideshow(self):
        if self.slideshow_id is not None:
            return

        if self.viewer is None:
            self.open_selected_image()

        if self.viewer is None:
            return

        interval = self.settings.get_uint("slideshow-interval")
        self.slideshow_id = GLib.timeout_add(
            interval * 1000,
            self.slideshow_next,
        )

    def get_image_date(self, gfile):
        path = gfile.get_path()

        return datetime.fromtimestamp(os.path.getmtime(path))

    def on_key_pressed(self, controller, keyval, keycode, state):
        selected = self.flowbox.get_selected_children()

        if not selected:
            return False

        child = selected[0]

        if keyval in (Gdk.KEY_space, Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            self.on_child_activated(self.flowbox, selected[0])
            return True

        index = child.get_index()
        new_index = index
        first_child = self.flowbox.get_child_at_index(0)

        if first_child is None:
            return False

        item_width = (
            first_child.get_allocated_width() + self.flowbox.get_column_spacing()
        )

        columns = max(
            1,
            self.flowbox.get_allocated_width() // item_width,
        )

        if keyval == Gdk.KEY_F5:
            self.reload_folder()
            return True

        if keyval in (Gdk.KEY_h, Gdk.KEY_Left, Gdk.KEY_ISO_Left_Tab):
            if new_index > 0:
                new_index -= 1

        elif keyval in (Gdk.KEY_j, Gdk.KEY_Down):
            if (new_index + columns) < len(self.image_files):
                new_index += columns

        elif keyval in (Gdk.KEY_k, Gdk.KEY_Up):
            if (new_index - columns) >= 0:
                new_index -= columns

        elif keyval in (Gdk.KEY_l, Gdk.KEY_Right, Gdk.KEY_Tab):
            if (new_index + 1) < len(self.image_files):
                new_index += 1

        elif keyval == Gdk.KEY_Home:
            new_index = 0

        elif keyval == Gdk.KEY_End:
            new_index = len(self.image_files) - 1

        elif keyval == Gdk.KEY_Page_Up:
            vadj = self.scrolled_window.get_vadjustment()
            page_height = vadj.get_page_size()

            row_height = (
                first_child.get_allocated_height() + self.flowbox.get_row_spacing()
            )

            visible_rows = max(1, int(page_height // row_height))
            page_size = visible_rows * columns

            if (new_index - page_size) > 0:
                new_index -= page_size
            else:
                new_index = 0

            target = self.flowbox.get_child_at_index(new_index)
            if target:
                self.flowbox.select_child(target)

        elif keyval == Gdk.KEY_Page_Down:
            vadj = self.scrolled_window.get_vadjustment()
            page_height = vadj.get_page_size()

            row_height = (
                first_child.get_allocated_height() + self.flowbox.get_row_spacing()
            )

            visible_rows = max(1, int(page_height // row_height))
            page_size = visible_rows * columns

            if (new_index + page_size) <= len(self.image_files):
                new_index += page_size
            else:
                new_index = len(self.image_files) - 1

            target = self.flowbox.get_child_at_index(new_index)
            if target:
                self.flowbox.select_child(target)

        else:
            return False

        filename = os.path.basename(self.image_files[new_index])
        self.status_label.set_text(
            f"{new_index + 1}/{len(self.image_files)} : {filename}"
        )

        new_index = max(0, min(new_index, len(self.image_files) - 1))

        target = self.flowbox.get_child_at_index(new_index)

        if target:
            self.flowbox.unselect_all()
            self.flowbox.select_child(target)
            target.grab_focus()

        return True

    def open_selected_image(self):
        selected = self.flowbox.get_selected_children()

        if not selected:
            return

        child = selected[0]

        image_path = getattr(child, "image_file", None)

        if not image_path:
            return

        if self.viewer is not None:
            self.viewer.close()
            self.viewer = None

        viewer = ImageViewerDialog(
            self, self.image_files, self.image_files.index(image_path)
        )
        viewer.connect("close-request", self.on_viewer_close)
        viewer.present()

        self.viewer = viewer

    def on_open(self, action, param):
        dialog = Gtk.FileDialog()

        dialog.select_folder(self, None, self.on_folder_selected)

    def on_folder_selected(self, dialog, result):
        try:
            folder = dialog.select_folder_finish(result)

        except Exception as e:
            print("select_folder_finish:", e)
            return

        if folder:
            self.load_folder(folder)

    def load_folder(self, folder):
        if isinstance(folder, str):
            folder = Gio.File.new_for_path(folder)

        if self.current_folder is None:
            self.start_folder_monitor(folder)

        elif not self.current_folder.equal(folder):
            self.start_folder_monitor(folder)

        self.current_folder = folder

        if self.thumbnail_idle_id is not None:
            GLib.source_remove(self.thumbnail_idle_id)
            self.thumbnail_idle_id = None

        files = self.get_image_files(folder)

        self.clear_thumbnails()

        self.create_thumbnails(files)

    def get_image_files(self, folder):
        files = []

        enumerator = folder.enumerate_children(
            "standard::*", Gio.FileQueryInfoFlags.NONE, None
        )

        while True:
            info = enumerator.next_file(None)

            if info is None:
                break

            name = info.get_name()

            if name.lower().endswith(IMAGE_EXTS):
                files.append(folder.get_child(name))

        enumerator.close(None)

        if self.sort_mode == "name":
            files.sort(
                key=lambda f: f.get_basename().lower(), reverse=self.sort_reverse
            )

        else:
            files.sort(key=self.get_image_date, reverse=self.sort_reverse)

        return files

    def clear_thumbnails(self):
        child = self.flowbox.get_first_child()

        while child:
            next_child = child.get_next_sibling()
            self.flowbox.remove(child)
            child = next_child

    def create_thumbnails(self, files):
        self.image_files = files
        self.pending_files = deque(files)

        self.loaded_count = 0

        self.thumbnail_idle_id = GLib.idle_add(self.load_next_thumbnail)

        self.reload_action.set_enabled(True)
        self.slideshow_action.set_enabled(len(files) > 0)

    def load_next_thumbnail(self):
        if not self.pending_files:
            self.thumbnail_idle_id = None
            return False

        if not self.pending_files:
            return False

        gfile = self.pending_files.popleft()

        ext = os.path.splitext(gfile.get_basename())[1].lower()

        try:
            if ext in IMAGE_EXTS:
                stream = gfile.read(None)

                try:
                    pixbuf = GdkPixbuf.Pixbuf.new_from_stream_at_scale(
                        stream, THUMB, THUMB, True, None
                    )
                    pixbuf = pixbuf.apply_embedded_orientation()

                    texture = Gdk.Texture.new_for_pixbuf(pixbuf)

                    widget = Gtk.Picture.new_for_paintable(texture)
                    widget.set_can_shrink(True)
                    widget.set_content_fit(Gtk.ContentFit.CONTAIN)

                finally:
                    stream.close(None)

            else:
                return len(self.pending_files) > 0

            child = Gtk.FlowBoxChild()
            child.set_size_request(THUMB, THUMB)
            child.set_child(widget)

            child.image_file = gfile

            self.flowbox.append(child)

            drag = Gtk.DragSource.new()
            drag.set_actions(Gdk.DragAction.COPY)
            drag.connect("prepare", self.on_thumbnail_drag_prepare, gfile)

            child.add_controller(drag)

            if self.loaded_count == 0:
                self.flowbox.select_child(child)

            self.loaded_count += 1

            self.status_label.set_text(f"{self.loaded_count} " + _("image(s) read."))

        except Exception as e:
            print("FAILED:", gfile.get_basename())

        if not self.pending_files:
            self.thumbnail_idle_id = None
            return False

        return len(self.pending_files) > 0

    def on_child_activated(self, flowbox, child):
        gfile = getattr(child, "image_file", None)

        if not gfile:
            return

        if self.viewer is not None:
            self.viewer.close()
            self.viewer = None

        viewer = ImageViewerDialog(
            self,
            self.image_files,
            self.image_files.index(gfile) if gfile in self.image_files else 0,
        )

        viewer.connect("close-request", self.on_viewer_close)
        viewer.present()

        self.viewer = viewer

        index = self.image_files.index(gfile)
        filename = gfile.get_basename()

        self.status_label.set_text(f"{index + 1}/{len(self.image_files)} : {filename}")

    def on_viewer_close(self, win):
        self.stop_slideshow()
        self.viewer = None
        return False

    def on_close_request(self, *args):
        self.settings.set_int("window-width", self.get_width())
        self.settings.set_int("window-height", self.get_height())
        self.settings.set_boolean("window-maximized", self.is_maximized())

        while child := self.flowbox.get_first_child():
            self.flowbox.remove(child)

        if self.folder_monitor:
            self.folder_monitor.cancel()
            self.folder_monitor = None

        return False
