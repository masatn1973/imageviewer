# preferences.py
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

from gi.repository import Gtk, Gio, Adw

from models.thumbnailcache import format_size


@Gtk.Template(resource_path="/io/github/masatn1973/ImageViewer/preferences.ui")
class PreferencesDialog(Adw.PreferencesDialog):
    __gtype_name__ = "PreferencesDialog"

    adjustment = Gtk.Template.Child()
    interval_row = Gtk.Template.Child()
    shuffle_row = Gtk.Template.Child()
    cache_row = Gtk.Template.Child()
    clear_cache_button = Gtk.Template.Child()

    def __init__(self, parent):
        super().__init__()

        self.parent_window = parent

        self.settings = Gio.Settings.new("io.github.masatn1973.ImageViewer")

        self.settings.bind(
            "slideshow-interval",
            self.adjustment,
            "value",
            Gio.SettingsBindFlags.DEFAULT,
        )

        self.settings.bind(
            "shuffle-enabled",
            self.shuffle_row,
            "active",
            Gio.SettingsBindFlags.DEFAULT,
        )

        self.clear_cache_button.connect("clicked", self.on_clear_cache_clicked)
        self._update_cache_subtitle()

    # --- サムネイルキャッシュ ---------------------------------------------------
    def _update_cache_subtitle(self):
        cache = self.parent_window.controller.thumbnail_cache
        size = cache.disk_cache_size_bytes()
        self.cache_row.set_subtitle(format_size(size))

    def on_clear_cache_clicked(self, button):
        cache = self.parent_window.controller.thumbnail_cache
        freed_bytes = cache.disk_cache_size_bytes()

        cache.clear_memory_cache()
        cache.clear_disk_cache()

        self._update_cache_subtitle()
        self.parent_window.show_toast(
            _("Thumbnail cache cleared ({size}).").format(size=format_size(freed_bytes))
        )
