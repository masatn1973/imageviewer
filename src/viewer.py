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

from gi.repository import Gdk, Gtk, Adw, GdkPixbuf, Gio, GLib

from exifinfo import ExifData, get_exif_info
from imagestate import ImageState
from imagecanvas import ImageCanvas


@Gtk.Template(resource_path="/io/github/masatn1973/ImageViewer/viewer.ui")
class ImageViewerDialog(Adw.Window):
    __gtype_name__ = "ImageViewerDialog"

    scrolled_window = Gtk.Template.Child()

    image_container = Gtk.Template.Child()

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

        self.image_container.append(self.imagecanvas)

        self.parent = parent

        self.settings = Gio.Settings.new("io.github.masatn1973.ImageViewer")

        self.info_box.add_css_class("exif-overlay")

        self.file_path = None

        self.connect("notify::default-width", self.on_window_resize)
        self.connect("notify::default-height", self.on_window_resize)
        self.connect("notify::maximized", self.on_window_resize)

        scroll = Gtk.EventControllerScroll.new(Gtk.EventControllerScrollFlags.VERTICAL)
        scroll.connect("scroll", self.on_scroll)
        self.imagecanvas.add_controller(scroll)

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

    @property
    def current_file(self):
        if not self.image_files:
            return None

        return self.image_files[self.current_index]

    def open_image(self, gfile):
        self.imagestate.initialize_view()
        self.media_stack.set_visible_child(self.image_container)

        path = gfile.get_path()

        try:
            self.imagestate.rotation = 0

            stream = gfile.read(None)

            pixbuf = GdkPixbuf.Pixbuf.new_from_stream(stream, None)
            pixbuf = pixbuf.apply_embedded_orientation()
            self.imagestate.pixbuf = pixbuf

            self.update_fit_zoom()

            self.redraw_image()
            self.update_title()

        except Exception as e:
            print(f"Failed to open image: {path}")
            print(e)

    def show_current_image(self):
        if not self.image_files:
            return

        self.imagestate.initialize_view()

        self.media_stack.set_visible_child(self.image_container)

        self.open_media(self.current_file)

        if self.is_show_exif_data:
            self.show_exif_data()

        self.imagecanvas.queue_draw()

    def redraw_image(self):
        self.imagecanvas.update_canvas_size()
        self.imagecanvas.queue_draw()

    # --- Event handler --------------------------------------------------------
    def on_key_pressed(self, controller, keyval, keycode, state):
        if keyval in (Gdk.KEY_plus, Gdk.KEY_KP_Add):
            self.imagestate.zoom_in()
            self.redraw_image()
            self.update_title()
            return True

        if keyval in (Gdk.KEY_minus, Gdk.KEY_KP_Subtract):
            self.imagestate.zoom_out()
            self.redraw_image()
            self.update_title()
            return True

        if keyval in (Gdk.KEY_Right, Gdk.KEY_l):
            self.show_next_image()
            return True

        if keyval in (Gdk.KEY_Left, Gdk.KEY_h):
            self.show_previous_image()
            return True

        if keyval == Gdk.KEY_r:
            self.imagestate.rotate_right()
            self.redraw_image()
            self.update_title()
            return True

        elif keyval == Gdk.KEY_R:
            self.imagestate.rotate_left()
            self.redraw_image()
            self.update_title()
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
            self.imagestate.zoom_reset()
            self.update_fit_zoom()
            return True

        if keyval == Gdk.KEY_1:
            self.imagestate.zoom_actual_size()
            self.redraw_image()
            self.update_title()
            return True

        return False

    def on_scroll(self, controller, dx, dy):
        state = controller.get_current_event_state()

        if state & Gdk.ModifierType.CONTROL_MASK:
            if dy < 0:
                self.imagestate.zoom_in()
            else:
                self.imagestate.zoom_out()

            self.redraw_image()
            self.update_title()
            return True

        return False

    def on_window_resize(self, *args):
        if self.imagestate.fit_mode:
            GLib.idle_add(self.update_fit_zoom)

    def on_close_request(self, *args):
        self.settings.set_int("viewer-width", self.get_width())
        self.settings.set_int("viewer-height", self.get_height())
        self.settings.set_boolean("viewer-maximized", self.is_maximized())

        self.parent.viewer = None

        return False

    # --- Zoom -----------------------------------------------------------------
    def update_fit_zoom(self):
        self.imagestate.set_fit_zoom(self.calculate_fit_zoom())
        self.redraw_image()
        self.update_title()

    def calculate_fit_zoom(self):
        if self.imagestate.pixbuf is None:
            return self.imagestate.zoom_actual_size()

        img_w = self.imagestate.pixbuf.get_width()
        img_h = self.imagestate.pixbuf.get_height()

        alloc = self.scrolled_window.get_allocation()

        win_w = max(1, alloc.width)
        win_h = max(1, alloc.height)

        return min(win_w / img_w, win_h / img_h)

    def get_window_title(self):
        if self.current_file is None:
            return ""

        filename = self.current_file.get_basename()
        percent = int(self.imagestate.get_display_zoom() * 100)

        return f"{filename} ({percent}%)"

    def update_title(self):
        self.set_title(self.get_window_title())

    # --- EXIF -------------------------------------------------------------
    def set_label(self, label, title, value):
        if value:
            label.set_text(title + value)

        else:
            label.set_text(title)

    def show_exif_data(self):
        info = get_exif_info(self.current_file)

        EXIF_FILEDS = (
            (self.Camera_label, _("Camera: "), info.camera),
            (self.Date_label, _("Shooting Datetime: "), info.date_str),
            (self.Pixel_size, _("Pixel Size: "), info.pixel_size),
            (self.Orientation, _("Orientation: "), f"{info.orientation}"),
            (self.ShutterSpeed, _("Shutter Speed: "), f"{info.shutter_speed_text}"),
            (self.FNumber, _("FNumber: "), f"{info.fnumber_text}"),
            (self.ISO, _("ISO: "), f"{info.iso}"),
            (self.FocalLength, _("Focal Length: "), f"{info.focal_length_text}"),
        )

        for label, title, value in EXIF_FILEDS:
            self.set_label(label, title, value)

    # --- Image display -------------------------------------------------------------
    def open_media(self, gfile):
        self.open_image(gfile)

    def show_next_image(self):
        self.change_image(1)

    def change_image(self, offset):
        if not self.image_files:
            return

        self.current_index = (self.current_index + offset) % len(self.image_files)
        self.show_current_image()

    def show_previous_image(self):
        self.change_image(-1)
