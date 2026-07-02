from gi.repository import GdkPixbuf


class ImageOps:
    @staticmethod
    def rotate(pixbuf, rotation):
        if pixbuf is None:
            return None

        if rotation == 90:
            return pixbuf.rotate_simple(GdkPixbuf.PixbufRotation.CLOCKWISE)

        if rotation == 180:
            return pixbuf.rotate_simple(GdkPixbuf.PixbufRotation.UPSIDEDOWN)

        if rotation == 270:
            return pixbuf.rotate_simple(GdkPixbuf.PixbufRotation.COUNTERCLOCKWISE)

        return pixbuf
