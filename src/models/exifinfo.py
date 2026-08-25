# exifinfo.py
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

import gi
import os

gi.require_version("GExiv2", "0.16")

from gi.repository import GExiv2, Gio

from dataclasses import dataclass
from typing import cast, Any

EXIF_EXTS = {
    ".jpg",
    ".jpeg",
    ".tif",
    ".tiff",
}


@dataclass
class ExifData:
    make: str = ""
    model: str = ""
    date: str = ""
    pixel_x: int | None = None
    pixel_y: int | None = None
    orientation: str = ""
    shutter_nom: int | None = None
    shutter_den: int | None = None
    fnumber: str = ""
    iso: str = ""
    focal_length: float | None = None

    @property
    def camera(self) -> str:
        return f"{self.make} {self.model}".strip()

    @property
    def date_str(self) -> str:
        return f"{self.date}"

    @property
    def pixel_size(self) -> str:
        if self.pixel_x is None or self.pixel_y is None:
            return ""

        return f"{self.pixel_x} x {self.pixel_y}"

    @property
    def shutter_speed_text(self) -> str:
        if self.shutter_nom is None or self.shutter_den is None:
            return ""

        if self.shutter_den == 0:
            return ""

        seconds = self.shutter_nom / self.shutter_den

        if seconds < 1:
            return f"1/{round(1 / seconds)}"

        return f"{seconds:g}s"

    @property
    def fnumber_text(self) -> str:
        if not self.fnumber:
            return ""

        try:
            a, b = self.fnumber.split("/")
            return f"f/{int(a) / int(b):g}"

        except (ValueError, ZeroDivisionError):
            return self.fnumber

    @property
    def focal_length_text(self) -> str:
        if self.focal_length is None:
            return ""

        return f"{self.focal_length:g} mm"


def get_exif_info(current_file: Gio.File | None) -> ExifData:
    info = ExifData()
    path = current_file.get_path()

    ext = os.path.splitext(path)[1].lower()

    if ext not in EXIF_EXTS:
        return info

    try:
        meta = GExiv2.Metadata()
        meta.open_path(path)

        info.make = meta.try_get_tag_string("Exif.Image.Make") or ""
        info.model = meta.try_get_tag_string("Exif.Image.Model") or ""

        info.date = (
            meta.try_get_tag_string("Exif.Photo.DateTimeOriginal")
            or meta.try_get_tag_string("Exif.Image.DateTime")
            or ""
        )

        width = meta.try_get_tag_string("Exif.Photo.PixelXDimension")

        if width:
            info.pixel_x = int(width)

        else:
            info.pixel_x = meta.get_pixel_width()

        height = meta.try_get_tag_string("Exif.Photo.PixelYDimension")

        if height:
            info.pixel_y = int(height)

        else:
            info.pixel_y = meta.get_pixel_height()

        info.orientation = meta.try_get_tag_string("Exif.Image.Orientation") or ""

        result = meta.try_get_exposure_time()

        if result:
            info.shutter_nom = result[0]
            info.shutter_den = result[1]

        info.fnumber = meta.try_get_tag_string("Exif.Photo.FNumber") or ""

        info.iso = meta.try_get_tag_string("Exif.Photo.ISOSpeedRatings") or ""
        info.focal_length = meta.try_get_focal_length()

    except Exception as e:
        print(f"EXIF ({path}): {e}")

    return info
