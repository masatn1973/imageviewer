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
