from gi.repository import Gtk, Gdk


class ImageCanvas(Gtk.DrawingArea):
    __gtype_name__ = "ImageCanvas"

    def __init__(self):
        super().__init__()

        self.state = None

        self.set_draw_func(self.draw)

    def draw(self, area, cr, width, height):
        if self.state is None or self.state.pixbuf is None:
            return

        zoom = self.state.get_display_zoom()

        cr.save()

        cr.scale(zoom, zoom)

        Gdk.cairo_set_source_pixbuf(cr, self.state.pixbuf, 0, 0)
        cr.paint()

        cr.restore()

    def update_canvas_size(self):
        if self.state is None:
            return

        if self.state.pixbuf is None:
            return

        zoom = self.state.get_display_zoom()

        width = int(self.state.pixbuf.get_width() * zoom)
        height = int(self.state.pixbuf.get_height() * zoom)

        self.set_size_request(width, height)

    def set_state(self, state):
        self.state = state

        self.update_canvas_size()
        self.queue_draw()
