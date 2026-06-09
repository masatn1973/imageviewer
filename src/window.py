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
from gi.repository import GExiv2

from gi.repository import Gdk, Gtk, Adw, Gio, GObject, GdkPixbuf, GLib
from shortcuts import ImageviewerShortcuts
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

        self.flowbox.set_selection_mode(Gtk.SelectionMode.SINGLE)

        self.flowbox.connect("child-activated", self.on_child_activated)

        self.connect("close-request", self.on_close_request)

        # Action
        shortcuts_action = Gio.SimpleAction.new("shortcuts", None)
        shortcuts_action.connect("activate", self.on_shortcuts)
        self.add_action(shortcuts_action)
        app.set_accels_for_action("win.shortcuts", ["<primary>question"])

        about_action = Gio.SimpleAction.new("about", None)
        about_action.connect("activate", self.on_about)
        self.add_action(about_action)
        app.set_accels_for_action("win.about", ["<primary>a"])

        self.connect("close-request", self.on_close_request)

        controller = Gtk.EventControllerKey()
        controller.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        controller.connect("key-pressed", self.on_key_pressed)
        self.add_controller(controller)

    def get_image_date(self, gfile):
        try:
            meta = GExiv2.Metadata(gfile.get_path())

            date_str = meta.get_tag_string("Exif.Photo.DateTimeOriginal")

            if date_str:
                return datetime.strptime(date_str, "%Y:%m:%d %H:%M:%S")

        except Exception:
            pass

        return datetime.fromtimestamp(os.path.getmtime(gfile.get_path()))

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

        image_path = getattr(child, "image_path", None)

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

    def on_about(self, action, param):
        builder = Gtk.Builder.new_from_resource(
            "/io/github/masatn1973/ImageViewer/about.ui"
        )
        builder.set_translation_domain("/io/github/masatn1973/ImageViewer")

        about = builder.get_object("about")
        about.present(self)

    def on_shortcuts(self, action, param):
        win = ImageviewerShortcuts(self)
        win.present()

    def load_folder(self, folder):
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
                gfile = folder.get_child(name)
                files.append(gfile)

        files.sort(key=self.get_image_date)

        while True:
            info = enumerator.next_file(None)

            if info is None:
                break

            name = info.get_name()

            if name.lower().endswith(IMAGE_EXTS):
                gfile = folder.get_child(name)
                files.append(gfile)

        files.sort(key=self.get_image_date)

        self.image_files = files
        self.pending_files = files.copy()

        self.loaded_count = 0

        GLib.idle_add(self.load_next_thumbnail)

    def load_next_thumbnail(self):
        if not self.pending_files:
            return False

        gfile = self.pending_files.pop(0)

        try:
            stream = gfile.read(None)
            pixbuf = GdkPixbuf.Pixbuf.new_from_stream_at_scale(
                stream, THUMB, THUMB, True, None
            )

            texture = Gdk.Texture.new_for_pixbuf(pixbuf)
            pic = Gtk.Picture.new_for_paintable(texture)
            pic.set_size_request(THUMB, THUMB)
            pic.set_content_fit(Gtk.ContentFit.COVER)

            child = Gtk.FlowBoxChild()
            child.set_child(pic)
            child.image_path = gfile

            self.flowbox.append(child)

            self.loaded_count += 1

            self.status_label.set_text(f"{self.loaded_count} " + _("image(s) loaded."))

        except Exception as e:
            print("Failed to Read files:", e)

        return len(self.pending_files) > 0

    def on_child_activated(self, flowbox, child):
        gfile = getattr(child, "image_path", None)

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
        filename = os.path.basename(gfile)

        self.status_label.set_text(f"{index + 1}/{len(self.image_files)} : {filename}")

    def on_viewer_close(self, win):
        self.viewer = None
        return False

    def on_close_request(self, *args):
        self.get_application().quit()
        return False
