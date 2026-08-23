# thumbnailcache.py
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
サムネイル(Gdk.Texture)のキャッシュ。

- メモリキャッシュ (OrderedDictによる簡易LRU) : アプリ実行中だけ有効。一番速い。
- ディスクキャッシュ (PNGファイル)            : ~/.cache/<app_name>/thumbnails/
  次回起動時やフォルダ再読込(F5)のときも、同じ画像なら再デコードを省略できる。

キャッシュキーは「Gio.Fileの URI + 更新日時 + サムネイルサイズ」から作る。
画像を上書き保存すると更新日時が変わるので、古いサムネイルが誤って
使われることはない。サムネイルサイズもキーに含めているので、
サイズスライダーを動かしても正しいサイズの画像が使われる
(以前使ったサイズに戻せばディスクキャッシュがそのまま使える)。
"""

from __future__ import annotations

import hashlib
from collections import OrderedDict
from pathlib import Path

from gi.repository import Gdk, GdkPixbuf, Gio, GLib


def format_size(num_bytes: int) -> str:
    """バイト数を 'B' / 'KB' / 'MB' / 'GB' の見やすい文字列にする。

    設定ダイアログやトースト通知でキャッシュ容量を表示するのに使う。
    """
    size = float(num_bytes)

    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"

        size /= 1024

    return f"{size:.1f} GB"  # 実際にはここまで来ない(念のため)


class ThumbnailCache:
    """画像のサムネイルを生成・キャッシュするクラス。"""

    def __init__(
        self,
        memory_limit: int = 300,
        cache_dir: str | Path | None = None,
        app_name: str = "io.github.masatn1973.ImageViewer",
    ) -> None:
        """
        Args:
            memory_limit: メモリキャッシュに保持する枚数の上限(LRU)。
            cache_dir: ディスクキャッシュの保存先。省略時はOS標準の
                       キャッシュディレクトリ (Linuxなら ~/.cache/) を使う。
            app_name: cache_dir省略時に使うサブフォルダ名。
        """
        self.memory_limit = memory_limit
        self._memory_cache: OrderedDict[str, Gdk.Texture] = OrderedDict()

        self._app_name = app_name
        # cache_dir が指定されなかった場合、ここでは GLib.get_user_cache_dir()
        # を呼ばない。GalleryController.__init__ から作られるたびに
        # OS/GTKへ問い合わせが発生すると、GTKの無いテスト環境(gi.repository
        # をモックに差し替えている場合)で ThumbnailCache() を生成しただけで
        # 例外になってしまうため。実際にキャッシュを使うタイミング
        # (cache_dir プロパティに初めてアクセスした時)まで解決を遅らせる。
        self._explicit_cache_dir = Path(cache_dir) if cache_dir is not None else None
        self._resolved_cache_dir: Path | None = None

    @property
    def cache_dir(self) -> Path:
        """ディスクキャッシュの保存先ディレクトリ(初回アクセス時に解決)。"""
        if self._resolved_cache_dir is None:
            if self._explicit_cache_dir is not None:
                resolved = self._explicit_cache_dir
            else:
                resolved = (
                    Path(GLib.get_user_cache_dir()) / self._app_name / "thumbnails"
                )
            resolved.mkdir(parents=True, exist_ok=True)
            self._resolved_cache_dir = resolved

        return self._resolved_cache_dir

    # ------------------------------------------------------------------
    # 公開API
    # ------------------------------------------------------------------

    def get_texture(self, gfile: Gio.File, size: int) -> Gdk.Texture:
        """
        指定した画像ファイルのサムネイル(Gdk.Texture)を返す。

        メモリ → ディスク → 新規生成 の順で探し、見つかったものを返す。
        読み込み・デコードに失敗した場合は例外がそのまま送出されるので、
        呼び出し側で従来通り `except Exception:` として
        「壊れた画像」の扱いをしてください(このクラスは失敗を
        キャッシュしない)。
        """
        key = self._cache_key(gfile, size)

        texture = self._get_from_memory(key)
        if texture is not None:
            return texture

        disk_path = self._disk_path(key)
        if disk_path.exists():
            texture = self._try_load_disk_cache(disk_path)
            if texture is not None:
                self._store_in_memory(key, texture)
                return texture

        texture = self._generate_texture(gfile, size, disk_path)
        self._store_in_memory(key, texture)
        return texture

    def clear_memory_cache(self) -> None:
        self._memory_cache.clear()

    def clear_disk_cache(self) -> None:
        for f in self.cache_dir.glob("*.png"):
            f.unlink()

    def disk_cache_size_bytes(self) -> int:
        """現在のディスクキャッシュの合計サイズ(バイト)。設定画面などで使う用。"""
        return sum(f.stat().st_size for f in self.cache_dir.glob("*.png"))

    # ------------------------------------------------------------------
    # 内部処理
    # ------------------------------------------------------------------

    def _cache_key(self, gfile: Gio.File, size: int) -> str:
        """URI + 更新日時 + サイズ からキャッシュキー(ハッシュ)を作る。

        os.path.getmtime ではなく Gio 経由で更新日時を取るのは、
        ローカルファイル以外(ネットワーク越しのGFileなど)でも
        同じ方法で動かすため。
        """
        info = gfile.query_info(
            "time::modified", Gio.FileQueryInfoFlags.NONE, None
        )
        mtime = info.get_modification_date_time()
        mtime_str = mtime.format_iso8601() if mtime is not None else "0"

        raw = f"{gfile.get_uri()}:{mtime_str}:{size}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _disk_path(self, key: str) -> Path:
        return self.cache_dir / f"{key}.png"

    def _generate_texture(
        self, gfile: Gio.File, size: int, disk_path: Path
    ) -> Gdk.Texture:
        """元画像からサムネイルを生成し、ディスクキャッシュにも保存する。

        既存の GalleryController._load_next_thumbnail と同じ手順
        (ストリームから縮小読み込み → Exif回転を反映)。
        失敗時は例外をそのまま呼び出し元に投げる。
        """
        stream = gfile.read(None)

        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_stream_at_scale(
                stream, size, size, True, None
            )
            pixbuf = pixbuf.apply_embedded_orientation()
        finally:
            stream.close(None)

        try:
            pixbuf.savev(str(disk_path), "png", [], [])
        except GLib.Error as e:
            # ディスク保存に失敗してもメモリ上では使えるので致命的エラーにはしない
            print(f"[ThumbnailCache] ディスクキャッシュ保存に失敗: {e}")

        return Gdk.Texture.new_for_pixbuf(pixbuf)

    def _try_load_disk_cache(self, disk_path: Path) -> Gdk.Texture | None:
        try:
            return Gdk.Texture.new_from_filename(str(disk_path))
        except GLib.Error as e:
            print(f"[ThumbnailCache] ディスクキャッシュの読み込みに失敗: {e}")
            return None

    def _get_from_memory(self, key: str) -> Gdk.Texture | None:
        texture = self._memory_cache.get(key)
        if texture is not None:
            self._memory_cache.move_to_end(key)  # 使われたので「最近使った」扱いに
        return texture

    def _store_in_memory(self, key: str, texture: Gdk.Texture) -> None:
        self._memory_cache[key] = texture
        self._memory_cache.move_to_end(key)
        while len(self._memory_cache) > self.memory_limit:
            self._memory_cache.popitem(last=False)  # 一番古いものを削除
