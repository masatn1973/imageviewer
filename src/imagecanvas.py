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

from gi.repository import Gtk, Gdk, GLib


class ImageCanvas(Gtk.DrawingArea):
    __gtype_name__ = "ImageCanvas"

    def __init__(self, on_zoom_changed=None):
        super().__init__()

        self.state = None
        self.current_zoom = 1.0
        self.on_zoom_changed = on_zoom_changed

        self.set_draw_func(self.draw_image)

        self.set_hexpand(True)
        self.set_vexpand(True)

    def redraw(self):
        self.queue_draw()

    def draw_image(self, area, cr, width, height):
        print("DRAW SIZE", width, height)

        if self.state is None or self.state.pixbuf is None:
            return

        pixbuf = self.state.pixbuf

        image_w = pixbuf.get_width()
        image_h = pixbuf.get_height()

        rotation = self.state.rotation

        if rotation in (90, 270):
            image_w, image_h = image_h, image_w

        if self.state.fit_mode:
            zoom = min(width / image_w, height / image_h)

        else:
            zoom = self.state.zoom

        old_zoom = self.current_zoom
        self.current_zoom = zoom

        if abs(old_zoom - zoom) > 0.001:
            if self.on_zoom_changed:
                GLib.idle_add(self.on_zoom_changed)

        if zoom <= 0:
            return

        draw_w = image_w * zoom
        draw_h = image_h * zoom

        offset_x = (width - draw_w) / 2
        offset_y = (height - draw_h) / 2

        cr.save()

        cr.translate(offset_x, offset_y)
        cr.scale(zoom, zoom)

        if rotation == 90:
            cr.translate(pixbuf.get_height(), 0)
            cr.rotate(math.radians(90))

        elif rotation == 180:
            cr.translate(pixbuf.get_width(), pixbuf.get_height())
            cr.rotate(math.radians(180))

        elif rotation == 270:
            cr.translate(0, pixbuf.get_width())
            cr.rotate(math.radians(270))

        Gdk.cairo_set_source_pixbuf(cr, pixbuf, 0, 0)
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
        self.queue_draw()
