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
import os
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Gdk, Gtk, Adw


@Gtk.Template(resource_path="/io/github/masatn1973/ImageViewer/viewer.ui")
class ImageViewerDialog(Adw.Window):
    __gtype_name__ = "ImageViewerDialog"

    picture = Gtk.Template.Child()
    headerbar = Gtk.Template.Child()

    def __init__(self, parent, image_files=None, current_index=0):
        super().__init__(transient_for=parent)

        prev_button = Gtk.Button(icon_name="show_previous-symbolic")
        prev_button.connect("clicked", lambda *_: self.show_previous_image())

        lext_button = Gtk.Button(icon_name="go-next-symbolic")
        lext_button.connect("clicked", lambda *_: self.show_next_image())

        self.headerbar.pack_start(prev_button)
        self.headerbar.pack_start(lext_button)

        self.image_files = image_files or []
        self.current_index = current_index

        self.add_shortcut(
            Gtk.Shortcut.new(
                Gtk.ShortcutTrigger.parse_string("Right"),
                Gtk.NamedAction.new("next-image"),
            )
        )

        shortcut = Gtk.Shortcut.new(
            Gtk.ShortcutTrigger.parse_string("Escape"),
            Gtk.NamedAction.new("window.close"),
        )

        self.add_shortcut(shortcut)

        controller = Gtk.EventControllerKey()
        controller.connect("key-pressed", self.on_key_pressed)
        self.add_controller(controller)

        self.set_focusable(True)
        self.grab_focus()

        if self.image_files:
            self.show_current_image()

        controller = Gtk.EventControllerKey()
        controller.connect("key-pressed", self.on_key_pressed)
        self.add_controller(controller)

    def on_key_pressed(self, controller, keyval, keycode, state):
        if keyval == Gdk.KEY_Right:
            self.show_next_image()
            return True

        if keyval == Gdk.KEY_Left:
            self.show_previous_image()
            return True

        return False

    def show_current_image(self):
        if not self.image_files:
            return

        path = self.image_files[self.current_index]

        print("SHOW:", self.current_index, path)

        self.set_title(os.path.basename(path))
        self.picture.set_filename(path)

    def show_next_image(self):
        if not self.image_files:
            return

        self.current_index += 1

        if self.current_index >= len(self.image_files):
            self.current_index = 0

        self.show_current_image()

    def show_previous_image(self):
        if not self.image_files:
            return

        self.current_index -= 1

        if self.current_index < 0:
            self.current_index = len(self.image_files) - 1

        self.show_current_image()

    def open_image(self, path):
        self.set_title(os.path.basename(path))
        self.picture.set_filename(path)
