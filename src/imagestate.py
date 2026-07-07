MAX_ZOOM = 16.0
MIN_ZOOM = 0.1

DEFAULT_ZOOM_RATIO = 1.0
ZOOM_RATIO = 1.25


class ImageState:
    def __init__(self):
        self.pixbuf = None
        self.zoom = DEFAULT_ZOOM_RATIO
        self.fit_zoom = DEFAULT_ZOOM_RATIO
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

        self.zoom = min(self.zoom * ZOOM_RATIO, MAX_ZOOM)

    def zoom_out(self):
        if self.fit_mode:
            self.zoom = self.fit_zoom
            self.fit_mode = False

        self.zoom = max(self.zoom / ZOOM_RATIO, MIN_ZOOM)

    def zoom_reset(self):
        self.zoom = self.fit_zoom
        self.fit_mode = True
