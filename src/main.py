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
import os
import resource

# その後、動画再生を Gtk.Video から ffmpeg 子プロセスを使う自前の
# プレーヤー(FfmpegVideoPlayer)に切り替えたため、Gtk.Video/GStreamerは
# もう使っていない。この対策自体が不要になっている可能性があるため、
# 一旦無効化して動作を確認している。GTK全体の描画までソフトウェアに
# 固定していたことが、動画のデコード/縮小と同時にCPUを圧迫し、
# カクつきの一因になっていた可能性があるため。
#
# もしこれを外したことで再びクラッシュ等が起きるようなら、
# 下の2行のコメントを外して元に戻してください。
# os.environ.setdefault("GDK_DISABLE", "gl")
# os.environ.setdefault("GSK_RENDERER", "cairo")

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
        f"Not found imageviewer.gresource"
        f"build using 'meson compile -C build' when run on local"
    )


resource = Gio.Resource.load(_find_gresource_path())
"""
resource = Gio.Resource.load("/app/share/imageviewer/imageviewer.gresource")
"""
resource._register()

from window import ImageViewerWindow
from preferences import PreferencesWindow


class ImageviewerApplication(Adw.Application):
    """The main application singleton class."""

    def __init__(self):
        super().__init__(
            application_id=APP_ID,
            flags=Gio.ApplicationFlags.HANDLES_OPEN,
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

    def _ensure_css_loaded(self):
        if getattr(self, "_css_loaded", False):
            return

        css = Gtk.CssProvider()
        css.load_from_resource("/io/github/masatn1973/ImageViewer/style.css")
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )
        self._css_loaded = True

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
        self._ensure_css_loaded()
        self.win = self.get_active_window()
        if not self.win:
            self.win = ImageViewerWindow(self)

        self.win.present()

    def do_open(self, files, n_files, hint):
        self._ensure_css_loaded()
        self.win = self.get_active_window()
        if not self.win:
            self.win = ImageViewerWindow(self)

        gfile = files[0]
        self.win.open_path(gfile)
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
