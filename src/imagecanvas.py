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
