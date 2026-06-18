# main.py
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

import gettext
import locale
import sys
import gi


APP_ID = "io.github.masatn1973.ImageViewer"

locale.bindtextdomain(APP_ID, "/app/share/locale")
locale.textdomain(APP_ID)

gettext.bindtextdomain(APP_ID, "/app/share/locale")
gettext.textdomain(APP_ID)

from gettext import gettext as _

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Gtk, Gdk, Gio, Adw

resource = Gio.Resource.load("/app/share/imageviewer/imageviewer.gresource")
resource._register()

from window import ImageViewerWindow
from preferences import PreferencesWindow


class ImageviewerApplication(Adw.Application):
    """The main application singleton class."""

    def __init__(self):
        super().__init__(
            application_id=APP_ID,
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
            resource_base_path="/io/github/masatn1973/ImageViewer",
        )

        open_action = Gio.SimpleAction.new("open", None)
        open_action.connect("activate", self.on_open)
        self.add_action(open_action)
        self.set_accels_for_action("app.open", ["<Ctrl>O"])

        prefs_action = Gio.SimpleAction.new("preferences", None)
        prefs_action.connect("activate", self.on_preferences)
        self.add_action(prefs_action)
        self.set_accels_for_action("app.preferences", ["<primary>p"])

        shortcuts_action = Gio.SimpleAction.new("shortcuts", None)
        shortcuts_action.connect("activate", self.on_shortcuts)
        self.add_action(shortcuts_action)
        self.set_accels_for_action("app.shortcuts", ["<primary>question"])

        about_action = Gio.SimpleAction.new("about", None)
        about_action.connect("activate", self.on_about)
        self.add_action(about_action)
        self.set_accels_for_action("app.about", ["<primary>a"])

        quit_action = Gio.SimpleAction.new("quit", None)
        quit_action.connect("activate", lambda *_: self.quit())
        self.add_action(quit_action)
        self.set_accels_for_action("app.quit", ["<Ctrl>Q"])

    def on_about(self, action, param):
        builder = Gtk.Builder.new_from_resource(
            "/io/github/masatn1973/ImageViewer/about.ui"
        )

        about = builder.get_object("about")
        about.present(self.get_active_window())

    def on_preferences(self, action, param):
        prefs = PreferencesWindow(self.get_active_window())
        prefs.present()

    def on_shortcuts(self, action, param):
        builder = Gtk.Builder.new_from_resource(
            "/io/github/masatn1973/ImageViewer/shortcuts.ui"
        )
        shortcuts = builder.get_object("shortcuts")
        shortcuts.present(self.get_active_window())

    def on_open(self, action, param):
        win = self.props.active_window

        if win:
            win.on_open(action, param)

    def on_slideshow(self, action, param):
        win = self.props.active_window

        if win:
            win.on_slideshow(action, param)

    def do_activate(self):
        css = Gtk.CssProvider()
        css.load_from_resource("/io/github/masatn1973/ImageViewer/style.css")

        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        self.win = self.get_active_window()
        if not self.win:
            self.win = ImageViewerWindow(self)
        self.win.present()

    def create_action(self, name, callback, shortcuts=None):
        """Add an application action.

        Args:
            name: the name of the action
            callback: the function to be called when the action is
              activated
            shortcuts: an optional list of accelerators
        """
        action = Gio.SimpleAction.new(name, None)

        if callback is not None:
            action.connect("activate", callback)

        self.add_action(action)

        if shortcuts:
            self.set_accels_for_action(f"app.{name}", shortcuts)


def main(version):
    """The application's entry point."""
    app = ImageviewerApplication()
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main(None))
