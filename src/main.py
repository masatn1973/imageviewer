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
import os
import sys

import gi

APP_ID = "io.github.masatn1973.ImageViewer"

locale.bindtextdomain(APP_ID, "/app/share/locale")
locale.textdomain(APP_ID)

gettext.bindtextdomain(APP_ID, "/app/share/locale")
gettext.textdomain(APP_ID)


gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Gtk, Gdk, Gio, Adw


def _find_gresource_path():
    flatpak_path = "/app/share/imageviewer/imageviewer.gresource"
    if os.path.exists(flatpak_path):
        return flatpak_path

    here = os.path.dirname(os.path.abspath(__file__))
    local_path = os.path.join(here, "..", "build", "src", "imageviewer.gresource")
    local_path = os.path.normpath(local_path)
    if os.path.exists(local_path):
        return local_path

    raise FileNotFoundError(
        f"Not found imageviewer.gresource. "
        f"build using 'meson compile -C build' when run on local."
    )


resource = Gio.Resource.load(_find_gresource_path())
resource._register()

from window import ImageViewerWindow
from preferences import PreferencesDialog


class ImageViewerApplication(Adw.Application):
    """The main application singleton class."""

    def __init__(self):
        super().__init__(
            application_id=APP_ID,
            flags=Gio.ApplicationFlags.HANDLES_OPEN,
            resource_base_path="/io/github/masatn1973/ImageViewer",
        )

    def do_startup(self):
        Adw.Application.do_startup(self)

        self._add_action("open", self._on_open, ["<primary>o"])
        self._add_action("preferences", self._on_preferences,
            ["<primary>p"])
        self._add_action("shortcuts", self._on_shortcuts,
            ["<primary>question"])
        self._add_action("about", self._on_about, ["<primary>a"])
        self._add_action("quit", lambda *_: self.quit(),
            ["<primary>q"])

        css = Gtk.CssProvider()
        css.load_from_resource("/io/github/masatn1973/ImageViewer/style.css")
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

    def _add_action(self, name, callback, accels=None):
        action = Gio.SimpleAction.new(name, None)
        action.connect("activate", callback)
        self.add_action(action)
        if accels:
            self.set_accels_for_action(f"app.{name}", accels)

        return action

    def _on_about(self, action, param):
        builder = Gtk.Builder.new_from_resource(
            "/io/github/masatn1973/ImageViewer/about.ui"
        )

        about = builder.get_object("about")
        about.present(self.props.active_window)

    def _on_preferences(self, action, param):
        prefs = PreferencesDialog(self.props.active_window)
        prefs.present(self.props.active_window)

    def _on_shortcuts(self, action, param):
        builder = Gtk.Builder.new_from_resource(
            "/io/github/masatn1973/ImageViewer/shortcuts.ui"
        )
        shortcuts = builder.get_object("shortcuts")
        shortcuts.present(self.props.active_window)

    def _on_open(self, action, param):
        win = self.props.active_window

        if win:
            win.on_open(action, param)

    def on_slideshow(self, action, param):
        win = self.props.active_window

        if win:
            win.on_slideshow(action, param)

    def do_activate(self):
        win = self._get_or_create_window()
        win.present()

    def do_open(self, files, n_files, hint):
        win = self._get_or_create_window()

        gfile = files[0]
        win.open_path(gfile)
        win.present()

    def _get_or_create_window(self):
        win = self.props.active_window
        if not win:
            win = ImageViewerWindow(self)

        return win
def main():
    """The application's entry point."""
    app = ImageViewerApplication()
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
