# gallerymodel.py
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

from __future__ import annotations

import os
import re
from typing import List, Union

from gi.repository import GObject, Gio, GLib

IMAGE_EXTS = (
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".svg",
    ".bmp",
    ".tiff",
    ".tif",
)


def _natural_sort_key(gfile:Gio.File) -> list[Union[int, str]]:
    """ファイル名を自然順 (例: img1 -> img2 -> img10)
    で並べるためのソートキー。"""
    name = gfile.get_basename() or ""
    return [
        int(text) if text.isdigit() else text.lower()
        for text in re.split(r"(\d+)", name)
    ]


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

    def __init__(self) -> None:
        super().__init__()

        self.current_folder: Gio.File | None = None
        self.image_files: List[Gio.File] = []
        self.sort_mode: str = "date"
        self.sort_reverse: bool = False

        self._folder_monitor: Gio.FileMonitor | None = None
        self._reload_timeout: int = 0

    # --- ソート -------------------------------------------------------------
    def set_sort_mode(self, mode: str, reverse: bool = False) -> None:
        self.sort_mode = mode
        self.sort_reverse = reverse

        if self.image_files:
            self._sort_files(self.image_files)
            self.emit("files-loaded")

    def _sort_files(self, files: List[Gio.file]) -> None:
        """保持しているファイルリストを現在の設定でソートする。"""
        if self.sort_mode == "name":
            files.sort(key=_natural_sort_key, reverse=self.sort_reverse)

        else:
            files.sort(key=self._get_image_date, reverse=self.sort_reverse)

    # --- フォルダ読込 ---------------------------------------------------------
    def load_folder(self, folder: Union[Gio.File, str, None]) -> None:
        if folder is None:
            return

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

    def _scan_folder(self, folder: Union[Gio.File, str, None]) -> List[Gio.File]:
        files: List[Gio.File] = []

        try:
            enumerator = folder.enumerate_children(
                "standard::*", Gio.FileQueryInfoFlags.NONE, None
            )

        except GLib.Error as e:
            # 権限がないフォルダや削除されたパスなどの例外に対応
            print(f"GalleryModel._scan_folder error: { e.message}")
            return files

        try:
            while True:
                info = enumerator.next_file(None)

                if info is None:
                    break

                # ディレクトリを除外し、通常のファイルシンボリックリンクのみを対象にする
                file_type = info.get_file_type()
                if file_type not in (Gio.FileType.REGULAR, Gio.FileType.SYMBOLIC_LINK):
                    continue

                name = info.get_name()

                if name.lower().endswith(IMAGE_EXTS):
                    files.append(folder.get_child(name))

        finally:
            enumerator.close(None)

        self._sort_files(files)
        return files

    @staticmethod
    def _get_image_date(gfile: Gio.File) -> float:
        """更新日時 (mtime) を float で取得する。取得失敗時は 0.0 を返す。"""
        path = gfile.get_path()
        if not path:
            return 0.0

        try:
            return os.path.getmtime(path)

        except OSError:
            return 0.0

    # --- フォルダ監視 ---------------------------------------------------------
    def _start_monitor(self, folder: Gio.File) -> None:
        self.stop_monitor()

        try:
            self._folder_monitor = folder.monitor_directory(
                Gio.FileMonitorFlags.NONE, None
            )
            self._folder_monitor.connect("changed", self._on_folder_changed)

        except GLib.Error as e:
            print(f"GalleryModel._start_monitor error: {e.message}")
            self._folder_monitor = None

    def _on_folder_changed(
        self,
        monitor: Gio.FileMonitor,
        file: Gio.File,
        other_file: Gio.File,
        event_type: Gio.FileMonitorEvent,
    ) -> None:
        if self._reload_timeout:
            GLib.source_remove(self._reload_timeout)

        self._reload_timeout = GLib.timeout_add(300, self._on_reload_timeout)

    def _on_reload_timeout(self) -> bool:
        self._reload_timeout = 0
        if self.current_folder is not None:
            self.load_folder(self.current_folder)

        return False

    def stop_monitor(self) -> None:
        if self._reload_timeout:
            GLib.source_remove(self._reload_timeout)
            self._reload_timeout = 0

        if self._folder_monitor:
            self._folder_monitor.cancel()
            self._folder_monitor = None
