# gallery_model.py
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
from datetime import datetime

from gi.repository import GObject, Gio, GLib

IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp", ".tiff")
VIDEO_EXTS = (".mp4", ".mov", ".webm", ".mkv", ".avi")
MEDIA_EXTS = IMAGE_EXTS + VIDEO_EXTS


def is_video_path(path):
    """ファイルパスが動画かどうかを拡張子で判定する。

    models/animation.py の is_gif_path と同じ考え方の、GTK非依存の純粋関数。
    """
    if not path:
        return False

    return path.lower().endswith(VIDEO_EXTS)


class GalleryModel(GObject.Object):
    """フォルダ内の画像一覧・ソート順・フォルダ監視を管理する Model。

    元は window.py の ImageViewerWindow に直接書かれていたロジック。
    GTK の Gio / GLib は使うが、Gtk.Widget には一切依存しない。
    """

    __gsignals__ = {
        # 画像一覧が (再)構築されたときに発火。
        # フォルダを開いた・ソート順を変えた・フォルダ監視で再読込した、
        # いずれの場合もこのシグナル1つで通知する。
        "files-loaded": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(self):
        super().__init__()

        self.current_folder = None
        self.image_files = []
        self.sort_mode = "date"
        self.sort_reverse = False

        self._folder_monitor = None
        self._reload_timeout = 0

    # --- ソート -------------------------------------------------------------
    def set_sort_mode(self, mode, reverse=False):
        self.sort_mode = mode
        self.sort_reverse = reverse

        if self.current_folder is not None:
            self.load_folder(self.current_folder)

    # --- フォルダ読込 ---------------------------------------------------------
    def load_folder(self, folder):
        if isinstance(folder, str):
            folder = Gio.File.new_for_path(folder)

        is_new_folder = (
            self.current_folder is None or not self.current_folder.equal(folder)
        )

        self.current_folder = folder

        if is_new_folder:
            self._start_monitor(folder)

        self.image_files = self._scan_folder(folder)
        self.emit("files-loaded")

    def _scan_folder(self, folder):
        files = []

        enumerator = folder.enumerate_children(
            "standard::*", Gio.FileQueryInfoFlags.NONE, None
        )

        while True:
            info = enumerator.next_file(None)

            if info is None:
                break

            name = info.get_name()

            if name.lower().endswith(MEDIA_EXTS):
                files.append(folder.get_child(name))

        enumerator.close(None)

        if self.sort_mode == "name":
            files.sort(
                key=lambda f: f.get_basename().lower(), reverse=self.sort_reverse
            )
        else:
            files.sort(key=self._get_image_date, reverse=self.sort_reverse)

        return files

    @staticmethod
    def _get_image_date(gfile):
        path = gfile.get_path()
        return datetime.fromtimestamp(os.path.getmtime(path))

    # --- フォルダ監視 ---------------------------------------------------------
    def _start_monitor(self, folder):
        if self._folder_monitor:
            self._folder_monitor.cancel()

        self._folder_monitor = folder.monitor_directory(
            Gio.FileMonitorFlags.NONE, None
        )
        self._folder_monitor.connect("changed", self._on_folder_changed)

    def _on_folder_changed(self, monitor, file, other_file, event_type):
        if self._reload_timeout:
            GLib.source_remove(self._reload_timeout)

        self._reload_timeout = GLib.timeout_add(300, self._on_reload_timeout)

    def _on_reload_timeout(self):
        self._reload_timeout = 0
        self.load_folder(self.current_folder)
        return False

    def stop_monitor(self):
        if self._folder_monitor:
            self._folder_monitor.cancel()
            self._folder_monitor = None
