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

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Gtk, Gio, Adw


@Gtk.Template(resource_path="/io/github/masatn1973/ImageViewer/preferences.ui")
class PreferencesWindow(Adw.PreferencesWindow):
    __gtype_name__ = "PreferencesWindow"

    interval_row = Gtk.Template.Child()

    def __init__(self, parent):
        super().__init__()

        self.set_transient_for(parent)

        self.settings = Gio.Settings.new("io.github.masatn1973.ImageViewer")

        adjustment = Gtk.Adjustment(
            value=self.settings.get_uint("slideshow-interval"),
            lower=1,
            upper=60,
            step_increment=1,
        )

        self.interval_row.set_adjustment(adjustment)

        adjustment.connect("value-changed", self.on_interval_changed)

    def on_interval_changed(self, adjustment):
        self.settings.set_uint("slideshow-interval", int(adjustment.get_value()))
