# imagestate.py
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


class ImageState:
    DEFAULT_ZOOM_RATIO = 1.0

    MAX_ZOOM = 16.0
    MIN_ZOOM = 0.1

    ZOOM_RATIO = 1.25

    def __init__(self):
        self.pixbuf = None
        self.zoom = self.DEFAULT_ZOOM_RATIO
        self.fit_zoom = self.DEFAULT_ZOOM_RATIO
        self.fit_mode = True
        self.rotation = 0

    def get_display_zoom(self):
        if self.fit_mode:
            return self.fit_zoom

        return self.zoom

    def zoom_in(self):
        if self.fit_mode:
            self.zoom = self.fit_zoom
            self.fit_mode = False

        self.zoom = min(self.zoom * self.ZOOM_RATIO, self.MAX_ZOOM)

    def zoom_out(self):
        if self.fit_mode:
            self.zoom = self.fit_zoom
            self.fit_mode = False

        self.zoom = max(self.zoom / self.ZOOM_RATIO, self.MIN_ZOOM)

    def zoom_reset(self):
        self.zoom = self.fit_zoom
        self.fit_mode = True

    def zoom_actual_size(self):
        self.fit_mode = False
        self.zoom = self.DEFAULT_ZOOM_RATIO

    def set_fit_zoom(self, zoom):
        self.fit_zoom = zoom

    def initialize_view(self):
        self.zoom = self.DEFAULT_ZOOM_RATIO
        self.fit_mode = True
        self.rotation = 0

    def rotate_right(self):
        self.rotation = (self.rotation + 90) % 360

    def rotate_left(self):
        self.rotation = (self.rotation - 90) % 360
