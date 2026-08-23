# searchfilter.py
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
gallerycontroller.py のファイル名絞り込み検索のロジックを、GTK非依存の
純粋関数として切り出したモジュール。geometry.py と同様に、Gtk.Widget
などを一切参照しないため pytest だけで単体テストできる。
"""


def matches_filename(filename: str, query: str) -> bool:
    """ファイル名(filename)が検索クエリ(query)にマッチするかどうかを判定する。

    - 大文字小文字を区別しない部分一致で判定する
    - query が空文字列、または空白のみの場合は常に True を返す
      (検索欄が空 = 絞り込みなし = 全件表示、という挙動にするため)

    Args:
        filename: 判定対象のファイル名 (例: "IMG_0001.jpg")
        query: 検索クエリ文字列 (例: "img")

    Returns:
        bool: マッチする(=表示すべき)場合 True
    """
    query = query.strip().lower()

    if not query:
        return True

    return query in filename.lower()
