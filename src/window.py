# window.py
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
import os
import gettext
import locale
import gi
import hashlib


APP_ID = "/io/github/masatn1973/ImageViewer"

locale.bindtextdomain(APP_ID, "/app/share/locale")
locale.textdomain(APP_ID)

gettext.bindtextdomain(APP_ID, "/app/share/locale")
gettext.textdomain(APP_ID)


from gettext import gettext as _


gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

gi.require_version("GExiv2", "0.16")
gi.require_version("Gst", "1.0")
gi.require_version("GstPbutils", "1.0")

from datetime import datetime
from collections import deque

from gi.repository import GExiv2
from gi.repository import Gdk, Gtk, Adw, Gio
from gi.repository import GObject, GdkPixbuf, GLib, Gst, GstPbutils

from preferences import PreferencesWindow
from shortcuts import ImageviewerShortcuts
from viewer import ImageViewerDialog

IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp", ".tiff")
VIDEO_EXTS = (".mp4", ".mkv", ".webm", ".avi", ".mov")

THUMB = 128


@Gtk.Template(resource_path="/io/github/masatn1973/ImageViewer/window.ui")
class ImageViewerWindow(Adw.ApplicationWindow):
    __gtype_name__ = "ImageViewerWindow"

    flowbox = Gtk.Template.Child()
    status_label = Gtk.Template.Child()
    scrolled_window = Gtk.Template.Child()

    def __init__(self, app):
        super().__init__(application=app)

        Gst.init(None)

        self.viewer = None
        self.image_files = []

        self.thumbnail_idle_id = None

        self.slideshow_id = None

        self.settings = Gio.Settings.new("io.github.masatn1973.ImageViewer")

        interval3_action = Gio.SimpleAction.new("slideshow3", None)
        interval3_action.connect("activate", lambda *_: self.set_slideshow_interval(3))
        self.add_action(interval3_action)

        interval5_action = Gio.SimpleAction.new("slideshow5", None)
        interval5_action.connect("activate", lambda *_: self.set_slideshow_interval(5))
        self.add_action(interval5_action)

        interval10_action = Gio.SimpleAction.new("slideshow10", None)
        interval10_action.connect(
            "activate", lambda *_: self.set_slideshow_interval(10)
        )
        self.add_action(interval10_action)

        self.flowbox.set_selection_mode(Gtk.SelectionMode.SINGLE)

        self.flowbox.connect("child-activated", self.on_child_activated)

        self.connect("close-request", self.on_close_request)

        # Action
        shortcuts_action = Gio.SimpleAction.new("shortcuts", None)
        shortcuts_action.connect("activate", self.on_shortcuts)
        self.add_action(shortcuts_action)
        app.set_accels_for_action("win.shortcuts", ["<primary>question"])

        slideshow_action = Gio.SimpleAction.new("slideshow", None)
        slideshow_action.connect("activate", self.on_slideshow)
        slideshow_action.set_enabled(False)
        self.add_action(slideshow_action)

        self.slideshow_action = slideshow_action
        app.set_accels_for_action("win.slideshow", ["<Ctrl>S"])

        about_action = Gio.SimpleAction.new("about", None)
        about_action.connect("activate", self.on_about)
        self.add_action(about_action)
        app.set_accels_for_action("win.about", ["<primary>a"])

        self.connect("close-request", self.on_close_request)

        controller = Gtk.EventControllerKey()
        controller.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        controller.connect("key-pressed", self.on_key_pressed)
        self.add_controller(controller)

        prefs_action = Gio.SimpleAction.new("preferences", None)
        prefs_action.connect("activate", self.on_preferences)
        self.add_action(prefs_action)
        app.set_accels_for_action("win.preferences", ["<primary>p"])

    def on_preferences(self, action, param):
        prefs = PreferencesWindow(self)
        prefs.present()

    def set_slideshow_interval(self, seconds):
        self.slideshow_interval = seconds * 1000

    def on_slideshow(self, action, param):
        if self.slideshow_id is None:
            self.start_slideshow()

        else:
            self.stop_slideshow()

    def stop_slideshow(self):
        if self.slideshow_id is not None:
            GLib.source_remove(self.slideshow_id)
            self.slideshow_id = None

    def slideshow_next(self):
        if not self.image_files:
            self.stop_slideshow()
            return False

        if self.viewer is None:
            self.stop_slideshow()
            return False

        self.viewer.show_next_image()

        return True

    def start_slideshow(self):
        if self.slideshow_id is not None:
            return

        if self.viewer is None:
            self.open_selected_image()

        if self.viewer is None:
            return

        interval = self.settings.get_uint("slideshow-interval")
        self.slideshow_id = GLib.timeout_add(
            interval * 1000,
            self.slideshow_next,
        )

    def craete_video_thumbnail(self, gfile):
        uri = gfile.get_uri()

        thumb = (
            os.path.expanduser("~/.cache/thumbnails/normal/")
            + hashlib.md5(uri.encode("utf-8")).hexdigest()
            + ".png"
        )

        try:
            playbin = Gst.ElementFactory.make("playbin")
            playbin.set_properties("uri", gfile.get_uri())

            playbin.set_state(Gst.State.PAUSED)

            playbin.set_state(Gst.CLOCK_TIME_NONE)

            sample = playbin.emit("convert-sample", None)

            if not sample:
                return None

            buffer = sample.get_buffer()
            caps = sample.get_caps()

            s = caps.get_structure(0)

            width = s.get_value("width")
            height = s.get_value("height")

            success, mapinfo = buffer.map(Gst.MapFlags.READ)

            if not success:
                return None

            try:
                pixbuf = GdkPixbuf.Pixbuf.new_from_data(
                    mapinfo.data,
                    GdkPixbuf.Colorspace.RGB,
                    False,
                    8,
                    width,
                    height,
                    width * 3,
                )

            finally:
                buffer.unmap(mapinfo)

            playbin.set_state(Gst.State.NULL)

            return pixbuf

        except Exception as e:
            print("thumbnail:", e)
            return None

    def open_video(self, gfile):
        self.set_title(gfile.get_basename())

        video = Gtk.Video.new_for_file(gfile)
        video.set_autoplay(True)

        self.set_content(video)

    def get_image_date(self, gfile):
        path = gfile.get_path()
        try:
            meta = GExiv2.Metadata(path)

            if meta.has_tag("Exif.Photo.DateTimeOriginal"):
                date_str = meta.get_tag_string("Exif.Photo.DateTimeOriginal")

                return datetime.strptime(date_str, "%Y:%m:%d %H:%M:%S")

        except Exception:
            pass

        return datetime.fromtimestamp(os.path.getmtime(path))

    def on_key_pressed(self, controller, keyval, keycode, state):
        selected = self.flowbox.get_selected_children()

        if not selected:
            return False

        child = selected[0]

        if keyval in (Gdk.KEY_space, Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            self.on_child_activated(self.flowbox, selected[0])
            return True

        index = child.get_index()
        new_index = index
        first_child = self.flowbox.get_child_at_index(0)

        if first_child is None:
            return False

        item_width = (
            first_child.get_allocated_width() + self.flowbox.get_column_spacing()
        )

        columns = max(
            1,
            self.flowbox.get_allocated_width() // item_width,
        )

        if keyval in (Gdk.KEY_h, Gdk.KEY_Left, Gdk.KEY_ISO_Left_Tab):
            if new_index > 0:
                new_index -= 1

        elif keyval in (Gdk.KEY_j, Gdk.KEY_Down):
            if (new_index + columns) < len(self.image_files):
                new_index += columns

        elif keyval in (Gdk.KEY_k, Gdk.KEY_Up):
            if (new_index - columns) >= 0:
                new_index -= columns

        elif keyval in (Gdk.KEY_l, Gdk.KEY_Right, Gdk.KEY_Tab):
            if (new_index + 1) < len(self.image_files):
                new_index += 1

        elif keyval == Gdk.KEY_Home:
            new_index = 0

        elif keyval == Gdk.KEY_End:
            new_index = len(self.image_files) - 1

        elif keyval == Gdk.KEY_Page_Up:
            vadj = self.scrolled_window.get_vadjustment()
            page_height = vadj.get_page_size()

            row_height = (
                first_child.get_allocated_height() + self.flowbox.get_row_spacing()
            )

            visible_rows = max(1, int(page_height // row_height))
            page_size = visible_rows * columns

            if (new_index - page_size) > 0:
                new_index -= page_size
            else:
                new_index = 0

            target = self.flowbox.get_child_at_index(new_index)
            if target:
                self.flowbox.select_child(target)

        elif keyval == Gdk.KEY_Page_Down:
            vadj = self.scrolled_window.get_vadjustment()
            page_height = vadj.get_page_size()

            row_height = (
                first_child.get_allocated_height() + self.flowbox.get_row_spacing()
            )

            visible_rows = max(1, int(page_height // row_height))
            page_size = visible_rows * columns

            if (new_index + page_size) <= len(self.image_files):
                new_index += page_size
            else:
                new_index = len(self.image_files) - 1

            target = self.flowbox.get_child_at_index(new_index)
            if target:
                self.flowbox.select_child(target)

        else:
            return False

        filename = os.path.basename(self.image_files[new_index])
        self.status_label.set_text(
            f"{new_index + 1}/{len(self.image_files)} : {filename}"
        )

        new_index = max(0, min(new_index, len(self.image_files) - 1))

        target = self.flowbox.get_child_at_index(new_index)

        if target:
            self.flowbox.unselect_all()
            self.flowbox.select_child(target)
            target.grab_focus()

        return True

    def open_selected_image(self):
        selected = self.flowbox.get_selected_children()

        if not selected:
            return

        child = selected[0]

        image_path = getattr(child, "image_path", None)

        if not image_path:
            return

        if self.viewer is not None:
            self.viewer.close()
            self.viewer = None

        viewer = ImageViewerDialog(
            self, self.image_files, self.image_files.index(image_path)
        )
        viewer.connect("close-request", self.on_viewer_close)
        viewer.present()

        self.viewer = viewer

    def on_open(self, action, param):
        dialog = Gtk.FileDialog()

        dialog.select_folder(self, None, self.on_folder_selected)

    def on_folder_selected(self, dialog, result):
        try:
            folder = dialog.select_folder_finish(result)

        except Exception as e:
            print("select_folder_finish:", e)
            return

        if folder:
            self.load_folder(folder)

    def on_about(self, action, param):
        builder = Gtk.Builder.new_from_resource(
            "/io/github/masatn1973/ImageViewer/about.ui"
        )
        builder.set_translation_domain("/io/github/masatn1973/ImageViewer")

        about = builder.get_object("about")
        about.present(self)

    def on_shortcuts(self, action, param):
        win = ImageviewerShortcuts(self)
        win.present()

    def load_folder(self, folder):
        # delete old thumbnails
        child = self.flowbox.get_first_child()
        count = 0

        while child:
            next_child = child.get_next_sibling()
            self.flowbox.remove(child)
            child = next_child
            count += 1

        self.pending_files = []
        self.image_files = []

        files = []

        enumerator = folder.enumerate_children(
            "standard::*", Gio.FileQueryInfoFlags.NONE, None
        )

        while True:
            info = enumerator.next_file(None)

            if info is None:
                break

            name = info.get_name()

            if name.lower().endswith(IMAGE_EXTS) or name.lower().endswith(VIDEO_EXTS):
                files.append(folder.get_child(name))

        enumerator.close(None)

        files.sort(key=lambda f: os.path.getmtime(f.get_path()))

        self.image_files = files
        self.pending_files = deque(files)

        self.loaded_count = 0

        self.thumbnail_idle_id = GLib.idle_add(self.load_next_thumbnail)

        child = self.flowbox.get_child_at_index(0)

        if child:
            self.flowbox.select_child(child)

        self.slideshow_action.set_enabled(len(self.image_files) > 0)

    def create_video_thumbnail(self, gfile):
        try:
            discoverer = GstPbutils.Discoverer.new(5 * Gst.SECOND)
            info = discoverer.discover_uri(gfile.get_uri())

            orientation = 0

            tags = info.get_tags()
            if tags:
                ok, orientation = tags.get_string("image-orientation")

            playbin = Gst.ElementFactory.make("playbin")
            sink = Gst.ElementFactory.make("gdkpixbufsink")

            playbin.set_property("video-sink", sink)
            playbin.set_property("uri", gfile.get_uri())

            playbin.set_state(Gst.State.PAUSED)
            playbin.get_state(5 * Gst.SECOND)

            pixbuf = sink.get_property("last-pixbuf")

            playbin.set_state(Gst.State.NULL)

            if pixbuf and orientation:
                if orientation == "rotate-90":
                    pixbuf = pixbuf.rotate_simple(GdkPixbuf.PixbufRotation.CLOCKWISE)
                elif orientation == "rotate-180":
                    pixbuf = pixbuf.rotate_simple(GdkPixbuf.PixbufRotation.UPSIDEDOWN)
                elif orientation == "rotate-270":
                    pixbuf = pixbuf.rotate_simple(
                        GdkPixbuf.PixbufRotation.COUNTERCLOCKWISE
                    )

            return pixbuf

        except Exception as e:
            print("thumbnail error:", e)
            return None

    def load_next_thumbnail(self):
        if not self.pending_files:
            self.thumbnail_idle_id = None
            return False

        if not self.pending_files:
            return False

        gfile = self.pending_files.popleft()

        ext = os.path.splitext(gfile.get_basename())[1].lower()

        try:
            if ext in IMAGE_EXTS:
                stream = gfile.read(None)

                try:
                    pixbuf = GdkPixbuf.Pixbuf.new_from_stream_at_scale(
                        stream, THUMB, THUMB, True, None
                    )
                    pixbuf = pixbuf.apply_embedded_orientation()

                    texture = Gdk.Texture.new_for_pixbuf(pixbuf)

                    widget = Gtk.Picture.new_for_paintable(texture)
                    widget.set_can_shrink(True)
                    widget.set_content_fit(Gtk.ContentFit.CONTAIN)

                finally:
                    stream.close(None)

            elif ext in VIDEO_EXTS:
                pixbuf = self.create_video_thumbnail(gfile)

                if pixbuf is None:
                    widget = Gtk.Image.new_from_icon_name("video-x-generic-symbolic")
                    widget.set_pixel_size(96)

                else:
                    w = pixbuf.get_width()
                    h = pixbuf.get_height()

                    scale = min(THUMB / w, THUMB / h)

                    new_w = int(w * scale)
                    new_h = int(h * scale)

                    pixbuf = pixbuf.scale_simple(
                        new_w, new_h, GdkPixbuf.InterpType.BILINEAR
                    )

                    texture = Gdk.Texture.new_for_pixbuf(pixbuf)

                    picture = Gtk.Picture.new_for_paintable(texture)
                    picture.set_size_request(THUMB, THUMB)
                    picture.set_can_shrink(True)
                    picture.set_content_fit(Gtk.ContentFit.CONTAIN)

                    overlay = Gtk.Overlay()
                    overlay.set_child(picture)

                    circle = Gtk.Box()
                    circle.add_css_class("video-play-circle")

                    play_icon = Gtk.Image.new_from_icon_name(
                        "media-playback-start-symbolic"
                    )
                    play_icon.add_css_class("video-play-icon")
                    play_icon.set_pixel_size(48)

                    circle.append(play_icon)

                    circle.set_halign(Gtk.Align.CENTER)
                    circle.set_valign(Gtk.Align.CENTER)

                    overlay.add_overlay(circle)

                    overlay.set_size_request(THUMB, THUMB)
                    widget = overlay

                    # else:
                    # widget = Gtk.Image.new_from_icon_name("video-x-generic-symbolic")
                    # widget.set_pixel_size(96)

            else:
                return len(self.pending_files) > 0

            child = Gtk.FlowBoxChild()
            child.set_size_request(THUMB, THUMB)
            child.set_child(widget)

            child.image_path = gfile
            child.is_video = ext in VIDEO_EXTS

            self.flowbox.append(child)

            if self.loaded_count == 0:
                self.flowbox.select_child(child)

            self.loaded_count += 1

            self.status_label.set_text(f"{self.loaded_count} " + _("image(s) loaded."))

        except Exception as e:
            print("FAILED:", gfile.get_basename())

        return len(self.pending_files) > 0

    def on_child_activated(self, flowbox, child):
        gfile = getattr(child, "image_path", None)

        if not gfile:
            return

        if self.viewer is not None:
            self.viewer.close()
            self.viewer = None

        viewer = ImageViewerDialog(
            self,
            self.image_files,
            self.image_files.index(gfile) if gfile in self.image_files else 0,
        )

        viewer.connect("close-request", self.on_viewer_close)
        viewer.present()

        self.viewer = viewer

        index = self.image_files.index(gfile)
        filename = os.path.basename(gfile)

        self.status_label.set_text(f"{index + 1}/{len(self.image_files)} : {filename}")

    def on_viewer_close(self, win):
        self.stop_slideshow()
        self.viewer = None
        return False

    def on_close_request(self, *args):
        while child := self.flowbox.get_first_child():
            self.flowbox.remove(child)

        return False
