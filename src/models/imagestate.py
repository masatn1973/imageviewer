# imagestate.py
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

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gi.repository import GdkPixbuf, Gio


class ImageState:
    DEFAULT_ZOOM_RATIO = 1.0

    MAX_ZOOM = 16.0
    MIN_ZOOM = 0.1

    ZOOM_RATIO = 1.02

    def __init__(self) -> None:
        self.pixbuf: GdkPixbuf.Pixbuf | None = None
        self.pixbuf_animation: GdkPixbuf.PixbufAnimation | None = None  # GdkPixbuf.PixbufAnimation (GIF等の場合のみ)
        self.anim_iter: GdkPixbuf.PixbufAnimationIter | None = None  # GdkPixbuf.PixbufAnimationIter (現在の再生位置)
        self.zoom: float = self.DEFAULT_ZOOM_RATIO
        self.fit_zoom: float = self.DEFAULT_ZOOM_RATIO
        self.fit_mode: bool = True
        self.rotation: int = 0
        self.slideshow_mode: bool = False

        self.flip_horizontal: bool = False
        self.flip_vertical: bool = False

        # --- 画像一覧・現在位置 (旧: viewer.py / window.py に分散していたもの) ---
        self.image_files: list[Gio.File] = []
        self.current_index: int = 0

    @property
    def current_file(self) -> Gio.File | None:
        if not self.image_files or not (0 <= self.current_index < len(self.image_files)):
            return None

        return self.image_files[self.current_index]

    def set_files(self, files: list[Gio.File], index: int = 0) -> None:
        self.image_files = files
        if not files:
            self.current_index = 0
        else:
            self.current_index = max(0, min(index, len(files) - 1))

    def next_file(self) -> Gio.File | None:
        if not self.image_files:
            return None

        self.current_index = (self.current_index + 1) % len(self.image_files)
        return self.current_file

    def previous_file(self) -> Gio.File | None:
        if not self.image_files:
            return None

        self.current_index = (self.current_index - 1) % len(self.image_files)
        return self.current_file

    def zoom_reset(self) -> None:
        self.zoom = self.fit_zoom
        self.fit_mode = True

    def zoom_actual_size(self) -> None:
        self.fit_mode = False
        self.zoom = self.DEFAULT_ZOOM_RATIO

    def set_fit_zoom(self, zoom: float) -> None:
        self.fit_zoom = zoom

    def initialize_view(self) -> None:
        self.zoom = self.DEFAULT_ZOOM_RATIO
        self.fit_mode = True
        self.rotation = 0

        self.flip_horizontal = False
        self.flip_vertical = False

    def rotate_right(self) -> None:
        self.rotation = (self.rotation + 90) % 360

    def rotate_left(self) -> None:
        self.rotation = (self.rotation - 90) % 360

    def toggle_flip_horizontal(self) -> None:
        self.flip_horizontal = not self.flip_horizontal

    def toggle_flip_vertical(self) -> None:
        self.flip_vertical = not self.flip_vertical
