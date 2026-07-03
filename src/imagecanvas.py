from gi.repository import Gtk


class ImageCanvas(Gtk.DrawingArea):
    def __init__(self):
        super().__init__()

        self.state = None

    def set_state(self, state):
        self.state = state
        self.queue_draw()
