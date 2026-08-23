# geometry.py
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
"""
imagecanvas.py のズーム/描画位置計算を GTK 非依存の純粋関数として
切り出したモジュール。Gtk.DrawingArea や Gtk.Adjustment を一切参照しない
ため、pytest だけで単体テストできる。
"""


def compute_geometry(
    image_w: int | float,
    image_h: int | float,
    view_w: int,
    view_h: int,
    zoom: float,
) -> tuple[int, int, float, float]:
    """指定ズーム率での描画領域サイズとオフセットを計算する。

    元は ImageCanvas._compute_geometry のロジック。
    """
    draw_w = image_w * zoom
    draw_h = image_h * zoom

    content_w = max(int(draw_w), view_w)
    content_h = max(int(draw_h), view_h)

    offset_x = max((content_w - draw_w) / 2, 0)
    offset_y = max((content_h - draw_h) / 2, 0)

    return content_w, content_h, offset_x, offset_y


def compute_zoom_anchor(
    x: float,
    y: float,
    old_zoom: float,
    new_zoom: float,
    offset_x_old: float,
    offset_y_old: float,
    offset_x_new: float,
    offset_y_new: float
) -> tuple[float, float]:
    """ズーム前後で「同じ画像上の点」がカーソル/中心の下に留まるように、
    新しいズーム率でのキャンバス座標を計算する。

    元は ImageCanvas.zoom_at_point 内のインライン計算。
    """
    anchor_x = (x - offset_x_old) / old_zoom
    anchor_y = (y - offset_y_old) / old_zoom

    canvas_x_new = offset_x_new + anchor_x * new_zoom
    canvas_y_new = offset_y_new + anchor_y * new_zoom

    return canvas_x_new, canvas_y_new
