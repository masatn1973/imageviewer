# viewer.py
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
import gettext
import locale
import gi

APP_ID = "io.github.masatn1973.ImageViewer"

locale.bindtextdomain(APP_ID, "/app/share/locale")
locale.textdomain(APP_ID)

gettext.bindtextdomain(APP_ID, "/app/share/locale")
gettext.textdomain(APP_ID)

from gettext import gettext as _

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("GExiv2", "0.16")

from gi.repository import Gdk, Gtk, Adw, GdkPixbuf, Gio, GLib
from gi.repository import GExiv2

from imagestate import ImageState
from imageops import ImageOps
from imagecanvas import ImageCanvas

DEFAULT_ZOOM_RATIO = 1.0
ZOOM_RATIO = 1.25


@Gtk.Template(resource_path="/io/github/masatn1973/ImageViewer/viewer.ui")
class ImageViewerDialog(Adw.Window):
    __gtype_name__ = "ImageViewerDialog"

    picture = Gtk.Template.Child()
    headerbar = Gtk.Template.Child()
    media_stack = Gtk.Template.Child()

    info_box = Gtk.Template.Child()
    Camera_label = Gtk.Template.Child()
    Date_label = Gtk.Template.Child()
    Pixel_size = Gtk.Template.Child()
    Orientation = Gtk.Template.Child()
    ShutterSpeed = Gtk.Template.Child()
    FNumber = Gtk.Template.Child()
    ISO = Gtk.Template.Child()
    FocalLength = Gtk.Template.Child()

    def __init__(self, parent, image_files=None, current_index=0):
        super().__init__()

        self.imagestate = ImageState()
        self.imagecanvas = ImageCanvas()

        self.imagecanvas.set_state(self.imagestate)

        self.parent = parent

        self.settings = Gio.Settings.new("io.github.masatn1973.ImageViewer")

        self.info_box.add_css_class("exif-overlay")

        self.imagestate.pixbuf = None
        self.imagestate.rotation = 0
        self.file_path = None

        self.imagestate.zoom = DEFAULT_ZOOM_RATIO
        self.imagestate.fit_mode = True

        self.connect("notify::default-width", self.on_window_resize)
        self.connect("notify::default-height", self.on_window_resize)
        self.connect("notify::maximized", self.on_window_resize)

        scroll = Gtk.EventControllerScroll.new(Gtk.EventControllerScrollFlags.VERTICAL)
        scroll.connect("scroll", self.on_scroll)
        self.picture.add_controller(scroll)

        prev_button = Gtk.Button(icon_name="go-previous-symbolic")
        prev_button.connect("clicked", lambda *_: self.show_previous_image())

        next_button = Gtk.Button(icon_name="go-next-symbolic")
        next_button.connect("clicked", lambda *_: self.show_next_image())

        self.headerbar.pack_start(prev_button)
        self.headerbar.pack_start(next_button)

        self.image_files = image_files or []
        self.current_index = current_index
        self.is_show_exif_data = False

        self.add_shortcut(
            Gtk.Shortcut.new(
                Gtk.ShortcutTrigger.parse_string("Right"),
                Gtk.NamedAction.new("next-image"),
            )
        )

        shortcut = Gtk.Shortcut.new(
            Gtk.ShortcutTrigger.parse_string("Escape"),
            Gtk.NamedAction.new("window.close"),
        )
        self.add_shortcut(shortcut)

        controller = Gtk.EventControllerKey()
        controller.connect("key-pressed", self.on_key_pressed)
        self.add_controller(controller)

        self.set_focusable(True)
        self.grab_focus()

        self.set_default_size(
            self.settings.get_int("viewer-width"),
            self.settings.get_int("viewer-height"),
        )

        if self.settings.get_boolean("viewer-maximized"):
            self.maximize()

        self.connect("close-request", self.on_close_request)

        if self.image_files:
            self.show_current_image()

    # --- Image list management -------------------------------------------------

    def set_image_files(self, image_files):
        current_file = self.current_file
        self.image_files = image_files

        if not self.image_files:
            self.close()
            return

        try:
            self.current_index = self.image_files.index(current_file)
        except ValueError:
            self.current_index = min(self.current_index, len(self.image_files) - 1)

        self.show_current_image()

    # --- Zoom -------------------------------------------------------------

    def update_fit_zoom(self):
        if self.imagestate.pixbuf is None:
            return False

        allocation = self.get_allocation()
        image_width = self.imagestate.pixbuf.get_width()
        image_height = self.imagestate.pixbuf.get_height()

        self.imagestate.fit_zoom = min(
            allocation.width / image_width, allocation.height / image_height
        )

        self.update_title()

        return False

    def get_display_zoom(self):
        if self.imagestate.fit_mode:
            return self.imagestate.fit_zoom

        return self.imagestate.zoom

    def calculate_fit_zoom(self):
        if self.imagestate.pixbuf is None:
            return DEFAULT_ZOOM_RATIO

        img_w = self.imagestate.pixbuf.get_width()
        img_h = self.imagestate.pixbuf.get_height()

        alloc = self.get_allocation()
        win_w = max(1, alloc.width)
        win_h = max(1, alloc.height)

        return min(win_w / img_w, win_h / img_h)

    def on_window_resize(self, *args):
        if self.imagestate.fit_mode:
            GLib.idle_add(self.update_fit_zoom)

    def get_scale_percent(self):
        if self.imagestate.pixbuf is None:
            return 0

        img_w = self.imagestate.pixbuf.get_width()
        img_h = self.imagestate.pixbuf.get_height()

        disp_w = self.picture.get_width()
        disp_h = self.picture.get_height()

        if disp_w == 0 or disp_h == 0:
            return 0

        scale = min(disp_w / img_w, disp_h / img_h)

        return round(scale * 100)

    def get_window_title(self):
        if self.current_file is None:
            return ""

        filename = self.current_file.get_basename()
        percent = int(self.get_display_zoom() * 100)

        return f"{filename} ({percent}%)"

    def update_title(self):
        self.set_title(self.get_window_title())

    def on_scroll(self, controller, dx, dy):
        state = controller.get_current_event_state()

        if state & Gdk.ModifierType.CONTROL_MASK:
            if dy < 0:
                self.zoom_in()
            else:
                self.zoom_out()

            return True

        return False

    def zoom_actual_size(self):
        self.imagestate.fit_mode = False
        self.imagestate.zoom = DEFAULT_ZOOM_RATIO
        self.update_image()
        self.update_title()

    def zoom_fit(self):
        self.imagestate.fit_mode = True
        self.imagestate.zoom = DEFAULT_ZOOM_RATIO
        self.update_image()

    def zoom_in(self):
        if self.imagestate.fit_mode:
            self.imagestate.zoom = self.imagestate.fit_zoom
            self.imagestate.fit_mode = False

        self.imagestate.zoom *= ZOOM_RATIO

        self.update_image()
        self.update_title()

    def zoom_out(self):
        if self.imagestate.fit_mode:
            self.imagestate.zoom = self.imagestate.fit_zoom
            self.imagestate.fit_mode = False

        self.imagestate.zoom /= ZOOM_RATIO

        self.update_image()
        self.update_title()

    def zoom_reset(self):
        self.imagestate.zoom = DEFAULT_ZOOM_RATIO
        self.update_image()
        self.update_title()

    # --- Keyboard shortcuts -------------------------------------------------------------

    def on_key_pressed(self, controller, keyval, keycode, state):
        if keyval in (Gdk.KEY_plus, Gdk.KEY_KP_Add):
            self.zoom_in()
            return True

        if keyval in (Gdk.KEY_minus, Gdk.KEY_KP_Subtract):
            self.zoom_out()
            return True

        if keyval in (Gdk.KEY_Right, Gdk.KEY_l):
            self.show_next_image()
            return True

        if keyval in (Gdk.KEY_Left, Gdk.KEY_h):
            self.show_previous_image()
            return True

        if keyval == Gdk.KEY_r:
            self.imagestate.rotation = (self.imagestate.rotation + 90) % 360
            self.update_image()
            return True

        elif keyval == Gdk.KEY_R:
            self.imagestate.rotation = (self.imagestate.rotation - 90) % 360
            self.update_image()
            return True

        if keyval == Gdk.KEY_e:
            if not self.is_show_exif_data:
                self.info_box.set_visible(True)
                self.show_exif_data()
                self.is_show_exif_data = True
            else:
                self.info_box.set_visible(False)
                self.is_show_exif_data = False

            return True

        if keyval == Gdk.KEY_0:
            self.zoom_fit()
            return True

        if keyval == Gdk.KEY_1:
            self.zoom_actual_size()
            return True

        return False

    # --- EXIF -------------------------------------------------------------

    def get_exif_info(self):
        info = {
            "Make": "",
            "Model": "",
            "Date": "",
            "PixelXDimension": None,
            "PixelYDimension": None,
            "Orientation": "",
            "ShutterSpeed": "",
            "FNumber": "",
            "ISO": "",
            "FocalLength": "",
        }

        try:
            meta = GExiv2.Metadata()
            path = self.current_file.get_path()
            meta.open_path(path)

            info["Make"] = meta.try_get_tag_string("Exif.Image.Make") or ""
            info["Model"] = meta.try_get_tag_string("Exif.Image.Model") or ""
            info["Date"] = (
                meta.try_get_tag_string("Exif.Photo.DateTimeOriginal")
                or meta.try_get_tag_string("Exif.Image.DateTime")
                or ""
            )
            info["PixelXDimension"] = (
                meta.try_get_tag_string("Exif.Photo.PixelXDimension")
                or meta.get_pixel_width()
            )
            info["PixelYDimension"] = (
                meta.try_get_tag_string("Exif.Photo.PixelYDimension")
                or meta.get_pixel_height()
            )
            info["Orientation"] = (
                meta.try_get_tag_string("Exif.Image.Orientation") or ""
            )
            info["ShutterSpeed"] = meta.try_get_exposure_time() or ""
            info["FNumber"] = meta.try_get_tag_string("Exif.Photo.FNumber") or ""
            info["ISO"] = meta.try_get_tag_string("Exif.Photo.ISOSpeedRatings") or ""
            info["FocalLength"] = meta.try_get_focal_length() or ""

        except Exception as e:
            print("EXIF:", e)

        return info

    def show_exif_data(self):
        info = self.get_exif_info()

        if info["Make"] == "":
            self.Camera_label.set_text(_("Camera: "))
        else:
            self.Camera_label.set_text(
                _("Camera: ") + f"{info['Make']} {info['Model']}".strip()
            )

        if info["Date"] == "":
            self.Date_label.set_text(_("Shooting Datetime: "))
        else:
            self.Date_label.set_text(_("Shooting Datetime: ") + info["Date"])

        if info["PixelXDimension"] == "" or info["PixelYDimension"] == "":
            self.Pixel_size.set_text(_("Pixel Size: "))
        else:
            self.Pixel_size.set_text(
                _("Pixel Size: ")
                + f"{info['PixelXDimension']} x {info['PixelYDimension']}"
            )

        if info["Orientation"] == "":
            self.Orientation.set_text(_("Orientation: "))
        else:
            self.Orientation.set_text(_("Orientation: ") + f"{info['Orientation']}")

        if info["ShutterSpeed"] == "":
            self.ShutterSpeed.set_text(_("Shutter Speed: "))
        elif (info["ShutterSpeed"][0] == 0) and (info["ShutterSpeed"][1] == 0):
            self.ShutterSpeed.set_text(_("Shutter Speed: "))
        else:
            nom = info["ShutterSpeed"][0]
            den = info["ShutterSpeed"][1]
            shutter_speed = int(den) / int(nom)

            self.ShutterSpeed.set_text(_("Shutter Speed: ") + f"1/{shutter_speed:.0f}")

        if info["FNumber"] == "":
            self.FNumber.set_text(_("FNumber: "))
        else:
            a, b = info["FNumber"].split("/")
            fnumber = f"f/{int(a) / int(b)}"
            self.FNumber.set_text(_("FNumber: ") + f"{fnumber}")

        if info["ISO"] == "":
            self.ISO.set_text(_("ISO: "))
        else:
            self.ISO.set_text(_("ISO: ") + f"{info['ISO']}")

        if info["FocalLength"] == "":
            self.FocalLength.set_text(_("Focal Length: "))
        else:
            self.FocalLength.set_text(_("Focal Length: ") + f"{info['FocalLength']}")

    # --- Image display -------------------------------------------------------------
    def update_picture(self, pixbuf):
        texture = Gdk.Texture.new_for_pixbuf(pixbuf)
        self.picture.set_paintable(texture)

    def update_picture_size(self, pixbuf):
        if self.imagestate.fit_mode:
            self.picture.set_size_request(-1, -1)
            GLib.idle_add(self.update_fit_zoom)

        else:
            width = int(pixbuf.get_width() * self.imagestate.zoom)
            height = int(pixbuf.get_height() * self.imagestate.zoom)

            self.picture.set_size_request(width, height)

    def update_image(self):
        pixbuf = ImageOps.rotate(self.imagestate.pixbuf, self.imagestate.rotation)

        if pixbuf is None:
            return

        self.update_picture(pixbuf)
        self.update_picture_size(pixbuf)

        self.current_file = self.image_files[self.current_index]

    def open_media(self, gfile):
        self.open_image(gfile)

    def reset_view_state(self):
        self.imagestate.zoon = DEFAULT_ZOOM_RATIO
        self.imagestate.fit_mode = True
        self.imagestate.fit_zoom = self.calculate_fit_zoom()

    def show_current_image(self):
        self.reset_view_state()

        self.media_stack.set_visible_child(self.picture)

        if not self.image_files:
            return

        gfile = self.image_files[self.current_index]
        self.current_file = gfile
        self.open_media(gfile)

        if self.is_show_exif_data:
            self.show_exif_data()

        self.imagecanvas.queue_draw()

    def show_next_image(self):
        self.change_image(1)

    def change_image(self, offset):
        if not self.image_files:
            return

        self.current_index = (self.current_index + offset) % len(self.image_files)
        self.show_current_image()

    def show_previous_image(self):
        self.change_image(-1)

    def open_image(self, gfile):
        self.imagestate.zoom = DEFAULT_ZOOM_RATIO
        self.media_stack.set_visible_child(self.picture)

        path = gfile.get_path()

        try:
            self.imagestate.rotation = 0

            stream = gfile.read(None)

            pixbuf = GdkPixbuf.Pixbuf.new_from_stream(stream, None)
            pixbuf = pixbuf.apply_embedded_orientation()
            self.imagestate.pixbuf = pixbuf

            self.update_image()

        except Exception as e:
            print(f"Failed to open image: {path}")
            print(e)

    def on_close_request(self, *args):
        self.settings.set_int("viewer-width", self.get_width())
        self.settings.set_int("viewer-height", self.get_height())
        self.settings.set_boolean("viewer-maximized", self.is_maximized())

        self.parent.viewer = None

        return False
