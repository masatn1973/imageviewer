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

from models.geometry import compute_geometry, compute_zoom_anchor


class ImageCanvas(Gtk.DrawingArea):
    __gtype_name__ = "ImageCanvas"

    def __init__(self, scrolled_window, on_zoom_changed=None):
        super().__init__()

        self.state = None
        self.scrolled_window = scrolled_window
        self.on_zoom_changed = on_zoom_changed

        self.current_zoom = 1.0

        self.draw_width = 0
        self.draw_height = 0

        self.mouse_x = 0
        self.mouse_y = 0

        self.set_draw_func(self.draw_image)

        motion = Gtk.EventControllerMotion()
        motion.connect("motion", self.on_motion)
        self.add_controller(motion)

    def _get_view_size(self):
        alloc = self.scrolled_window.get_allocation()
        return max(1, alloc.width), max(1, alloc.height)

    def _get_image_size(self):
        pixbuf = self.state.pixbuf
        w = pixbuf.get_width()
        h = pixbuf.get_height()

        if self.state.rotation in (90, 270):
            w, h = h, w

        return w, h

    def _compute_geometry(self, zoom):
        image_w, image_h = self._get_image_size()
        view_w, view_h = self._get_view_size()

        return compute_geometry(image_w, image_h, view_w, view_h, zoom)

    def zoom_at_viewport_center(self, zoom_in):
        hadj = self.scrolled_window.get_hadjustment()
        vadj = self.scrolled_window.get_vadjustment()

        center_x = hadj.get_value() + hadj.get_page_size() / 2
        center_y = vadj.get_value() + vadj.get_page_size() / 2

        self.zoom_at_point(center_x, center_y, zoom_in)

    def zoom_at_cursor(self, zoom_in):
        self.zoom_at_point(self.mouse_x, self.mouse_y, zoom_in)

    def zoom_at_point(self, x, y, zoom_in):
        if self.state is None or self.state.pixbuf is None:
            return

        if self.state.fit_mode:
            old_zoom = self.current_zoom

        else:
            old_zoom = self.state.zoom

        if zoom_in:
            new_zoom = min(old_zoom * self.state.ZOOM_RATIO, self.state.MAX_ZOOM)

        else:
            new_zoom = max(old_zoom / self.state.ZOOM_RATIO, self.state.MIN_ZOOM)

        if new_zoom == old_zoom:
            return

        hadj = self.scrolled_window.get_hadjustment()
        vadj = self.scrolled_window.get_vadjustment()

        old_hadj_value = hadj.get_value()
        old_vadj_value = vadj.get_value()

        _, _, offset_x_old, offset_y_old = self._compute_geometry(old_zoom)

        content_w_new, content_h_new, offset_x_new, offset_y_new = (
            self._compute_geometry(new_zoom)
        )

        canvas_x_new, canvas_y_new = compute_zoom_anchor(
            x,
            y,
            old_zoom,
            new_zoom,
            offset_x_old,
            offset_y_old,
            offset_x_new,
            offset_y_new,
        )

        new_hadj_value = old_hadj_value + (canvas_x_new - x)
        new_vadj_value = old_vadj_value + (canvas_y_new - y)

        view_w, view_h = self._get_view_size()

        hadj.configure(
            new_hadj_value,
            0,
            content_w_new,
            hadj.get_step_increment(),
            hadj.get_page_increment(),
            view_w,
        )

        vadj.configure(
            new_vadj_value,
            0,
            content_h_new,
            vadj.get_step_increment(),
            vadj.get_page_increment(),
            view_h,
        )

        self.state.zoom = new_zoom
        self.state.fit_mode = False

        self.redraw()

        self.mouse_x = canvas_x_new
        self.mouse_y = canvas_y_new

    def redraw(self):
        if self.state is None or self.state.pixbuf is None:
            return

        width = self.state.pixbuf.get_width()
        height = self.state.pixbuf.get_height()

        if self.state.rotation in (90, 270):
            width, height = height, width

        if self.state.fit_mode:
            self.set_content_width(0)
            self.set_content_height(0)
            self.set_hexpand(True)
            self.set_vexpand(True)

        else:
            zoom = self.state.zoom

            display_width = int(width * zoom)
            display_height = int(height * zoom)

            alloc = self.scrolled_window.get_allocation()

            view_width = max(1, alloc.width)
            view_height = max(1, alloc.height)

            self.set_content_width(max(display_width, view_width))
            self.set_content_height(max(display_height, view_height))

        self.queue_resize()
        self.queue_draw()

    def draw_image(self, area, cr, width, height):
        self.draw_width = width
        self.draw_height = height

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

        offset_x = max((width - draw_w) / 2, 0)
        offset_y = max((height - draw_h) / 2, 0)

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

    def set_state(self, state):
        self.state = state
        self.queue_draw()

    def on_motion(self, controller, x, y):
        self.mouse_x = x
        self.mouse_y = y
