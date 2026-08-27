# animation.py
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
viewercontroller.py のGIFアニメーション判定・フレーム送り間隔計算を
GTK非依存の純粋関数として切り出したモジュール。geometry.py /
searchfilter.py と同様に、Gtk.Widget や GLib を一切参照しないため
pytest だけで単体テストできる。
"""

GIF_EXTENSIONS = (".gif",)

# GIFによっては delay_time が 0ms 指定のことがあるため、
# CPUを無駄に使い切らないよう最低限保証する待機時間(ミリ秒)
MIN_FRAME_DELAY_MS = 20


def is_gif_path(path: str | None) -> bool:
    """ファイルパスがGIFかどうかを拡張子で判定する。

    Args:
        path: ファイルパス文字列。None や空文字列も許容する
            (Gio.File.get_path() はリモートファイルの場合 None を返すため)。

    Returns:
        bool: 拡張子が .gif (大文字小文字問わず) なら True。
    """
    if not path:
        return False

    return path.lower().endswith(GIF_EXTENSIONS)


def next_frame_delay(delay_ms: int, minimum: int = MIN_FRAME_DELAY_MS) -> int | None:
    """GdkPixbuf.PixbufAnimationIter.get_delay_time() の戻り値から、
    次のフレームまで待つべきミリ秒を計算する。

    Args:
        delay_ms: get_delay_time() の戻り値。
            負の値は「これ以上フレームがない(アニメーション終了)」を意味する。
        minimum: 保証する最小待機時間(ミリ秒)。

    Returns:
        int | None: 次フレームまでの待機ミリ秒。
            アニメーションが終了している場合は None。
    """
    if delay_ms < 0:
        return None

    return max(delay_ms, minimum)
