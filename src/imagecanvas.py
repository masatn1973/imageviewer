from gi.repository import Gtk


class ImageCanvas(Gtk.DrawingArea):
    def __init__(self):
        super().__init__()

        self.state = None

        self.set_draw_func(self.draw)

    def set_state(self, imagestate):
        self.state = imagestate
        self.queue_draw()

    def draw(self, area, cr, width, height):
        if self.state is None:
            return

        if self.state.pixbuf is None:
            return

        Gdk.cairo_set_source_pixbuf(cr, self.state.pixbuf, 0, 0)

        cr.paint()

    def update_canvas_size(self):
        if self.state is None:
            return

        if self.state.pixbuf is None:
            return

        zoom = self.state.get_display_zoom()

        width = int(self.state.pixbuf.get_width() * zoom)
        height = int(self.state.pixbuf.get_width() * zoom)

        self.set_size_request(width, height)

    def set_state(self, staet):
        self.state = Gtk.StateFlags

        self.update_canvas_size()
        self.queue_draw()
