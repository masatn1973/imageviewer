# imagecanvas.py
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

import math

from gi.repository import Gtk, Gdk


class ImageCanvas(Gtk.DrawingArea):
    __gtype_name__ = "ImageCanvas"

    def __init__(self):
        super().__init__()

        self.state = None

        self.set_draw_func(self.draw_image)

    def draw_image(self, area, cr, width, height):
        if self.state is None or self.state.pixbuf is None:
            return

        cr.save()

        zoom = self.state.get_display_zoom()

        cr.scale(zoom, zoom)
        cr.translate(0, 0)

        pixbuf = self.state.pixbuf

        image_w = pixbuf.get_width()
        image_h = pixbuf.get_height()

        rotation = self.state.rotation
        if rotation == 90:
            cr.translate(image_h, 0)
            cr.rotate(math.radians(90))

        elif rotation == 180:
            cr.translate(image_w, image_h)
            cr.rotate(math.radians(180))

        elif rotation == 270:
            cr.translate(0, image_w)
            cr.rotate(math.radians(270))

        Gdk.cairo_set_source_pixbuf(cr, self.state.pixbuf, 0, 0)
        cr.paint()

        cr.restore()

    def update_canvas_size(self):
        if self.state is None:
            return

        if self.state.pixbuf is None:
            return

        zoom = self.state.get_display_zoom()

        image_width = self.state.pixbuf.get_width()
        image_height = self.state.pixbuf.get_height()

        if self.state.rotation in (90, 270):
            image_width, image_height = image_height, image_width

        width = max(1, int(image_width * zoom))
        height = max(1, int(image_height * zoom))

        self.set_size_request(width, height)

    def set_state(self, state):
        self.state = state

        self.update_canvas_size()
        self.queue_draw()
