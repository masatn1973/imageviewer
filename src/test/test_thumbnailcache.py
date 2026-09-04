# test_thumbnailcache.py
#
# models/thumbnailcache.py の単体テスト。
#
# conftest.py が gi.repository を丸ごと MagicMock に差し替えているため、
# GdkPixbuf.Pixbuf.new_from_stream_at_scale などは実際には画像を
# デコードせず、テストごとに戻り値(return_value)を仕込んで動かす。
# ディスクキャッシュ部分だけは実際の一時ディレクトリ(tmp_path)を使い、
# 本物のファイル操作(mkdir/exists/glob/unlink)で検証する。

from unittest.mock import MagicMock

from gi.repository import Gdk, GdkPixbuf

from models.thumbnailcache import ThumbnailCache, format_size


# ---------------------------------------------------------------------------
# テスト用ヘルパー
# ---------------------------------------------------------------------------
def make_gfile(uri="file:///tmp/photo.jpg", mtime_str="2026-01-01T00:00:00+00:00"):
    """Gio.File の代わりに使うダミー。

    ThumbnailCache が実際に呼び出すメソッド (get_uri / query_info / read)
    だけを持たせる。
    """
    gfile = MagicMock(name="gfile")
    gfile.get_uri.return_value = uri

    info = MagicMock(name="file_info")
    mtime = MagicMock(name="mtime")
    mtime.format_iso8601.return_value = mtime_str
    info.get_modification_date_time.return_value = mtime
    gfile.query_info.return_value = info

    stream = MagicMock(name="stream")
    gfile.read.return_value = stream

    return gfile


def stub_pixbuf_generation():
    """GdkPixbuf / Gdk 側のモックの戻り値を「生成成功」の状態に仕込み、
    最終的にできあがる Gdk.Texture (final_texture) を返す。
    """
    pixbuf_raw = MagicMock(name="pixbuf_raw")
    pixbuf_final = MagicMock(name="pixbuf_final")
    pixbuf_raw.apply_embedded_orientation.return_value = pixbuf_final

    GdkPixbuf.Pixbuf.new_from_stream_at_scale.return_value = pixbuf_raw

    final_texture = MagicMock(name="final_texture")
    Gdk.Texture.new_for_pixbuf.return_value = final_texture

    return pixbuf_final, final_texture


# ---------------------------------------------------------------------------
# format_size (GTKに依存しない純粋関数)
# ---------------------------------------------------------------------------
class TestFormatSize:
    def test_zero_bytes(self):
        assert format_size(0) == "0 B"

    def test_bytes_under_1kb(self):
        assert format_size(512) == "512 B"

    def test_exactly_1kb(self):
        assert format_size(1024) == "1.0 KB"

    def test_kilobytes_with_fraction(self):
        assert format_size(1536) == "1.5 KB"

    def test_megabytes(self):
        assert format_size(5 * 1024 * 1024) == "5.0 MB"

    def test_gigabytes(self):
        assert format_size(2 * 1024 ** 3) == "2.0 GB"


# ---------------------------------------------------------------------------
# キャッシュキーの生成
# ---------------------------------------------------------------------------
class TestCacheKey:
    def test_same_input_produces_same_key(self, tmp_path):
        cache = ThumbnailCache(cache_dir=tmp_path)
        gfile = make_gfile()

        key1 = cache._cache_key(gfile, 128)
        key2 = cache._cache_key(gfile, 128)

        assert key1 == key2

    def test_different_size_produces_different_key(self, tmp_path):
        cache = ThumbnailCache(cache_dir=tmp_path)
        gfile = make_gfile()

        assert cache._cache_key(gfile, 128) != cache._cache_key(gfile, 256)

    def test_different_uri_produces_different_key(self, tmp_path):
        cache = ThumbnailCache(cache_dir=tmp_path)

        key_a = cache._cache_key(make_gfile(uri="file:///a.jpg"), 128)
        key_b = cache._cache_key(make_gfile(uri="file:///b.jpg"), 128)

        assert key_a != key_b

    def test_different_mtime_produces_different_key(self, tmp_path):
        """画像を上書き保存(=更新日時が変わる)すると、別のキーになること。"""
        cache = ThumbnailCache(cache_dir=tmp_path)

        old = make_gfile(mtime_str="2026-01-01T00:00:00+00:00")
        new = make_gfile(mtime_str="2026-02-01T00:00:00+00:00")

        assert cache._cache_key(old, 128) != cache._cache_key(new, 128)


# ---------------------------------------------------------------------------
# 遅延初期化: __init__ の時点では GLib/ファイルシステムに触らないこと
# ---------------------------------------------------------------------------
class TestLazyCacheDir:
    def test_init_does_not_touch_filesystem(self, tmp_path, monkeypatch):
        """cache_dir を指定しなくても、__init__ の時点では例外にならない
        こと(GLib がモックの場合でも安全)。実際にディスクへアクセス
        するのは cache_dir に初めてアクセスした時だけ。
        """
        # ThumbnailCache() 呼び出しの間にディレクトリが作られていない
        # ことを確認するため、GLib.get_user_cache_dir をあえて壊れた
        # 値のままにしておく(通常のモックはMagicMockを返すだけ)。
        cache = ThumbnailCache()  # cache_dir未指定でも例外にならない

        assert cache._resolved_cache_dir is None

    def test_explicit_cache_dir_is_created_on_first_use(self, tmp_path):
        cache_dir = tmp_path / "not_yet_created"
        cache = ThumbnailCache(cache_dir=cache_dir)

        assert not cache_dir.exists()

        _ = cache.cache_dir  # 初めてアクセス

        assert cache_dir.exists()


# ---------------------------------------------------------------------------
# get_texture: 新規生成・メモリキャッシュ
# ---------------------------------------------------------------------------
class TestGetTextureGeneration:
    def test_generates_and_returns_texture(self, tmp_path):
        cache = ThumbnailCache(cache_dir=tmp_path)
        gfile = make_gfile()
        _, final_texture = stub_pixbuf_generation()

        result = cache.get_texture(gfile, 128)

        assert result is final_texture
        gfile.read.assert_called_once_with(None)

    def test_stream_is_always_closed(self, tmp_path):
        cache = ThumbnailCache(cache_dir=tmp_path)
        gfile = make_gfile()
        stub_pixbuf_generation()

        cache.get_texture(gfile, 128)

        gfile.read.return_value.close.assert_called_once_with(None)

    def test_second_call_uses_memory_cache(self, tmp_path):
        """同じ画像・同じサイズを2回取得したら、2回目はメモリキャッシュから
        返され、gfile.read() が呼ばれ直さないこと。
        """
        cache = ThumbnailCache(cache_dir=tmp_path)
        gfile = make_gfile()
        _, final_texture = stub_pixbuf_generation()

        first = cache.get_texture(gfile, 128)
        second = cache.get_texture(gfile, 128)

        assert first is second
        gfile.read.assert_called_once()  # 1回しか読み込んでいない

    def test_different_size_is_not_memory_cache_hit(self, tmp_path):
        """同じ画像でもサイズが違えば、別物として再生成されること。"""
        cache = ThumbnailCache(cache_dir=tmp_path)
        gfile = make_gfile()
        stub_pixbuf_generation()

        cache.get_texture(gfile, 128)
        cache.get_texture(gfile, 256)

        assert gfile.read.call_count == 2

    def test_generation_error_propagates(self, tmp_path):
        """デコード失敗などの例外は握りつぶさず、呼び出し側(コントローラー)
        の「壊れた画像」処理に任せるためそのまま送出すること。
        """
        cache = ThumbnailCache(cache_dir=tmp_path)
        gfile = make_gfile()
        gfile.read.side_effect = Exception("読み込み失敗(テスト用)")

        try:
            cache.get_texture(gfile, 128)
            assert False, "例外が発生するはず"
        except Exception as e:
            assert "読み込み失敗" in str(e)


# ---------------------------------------------------------------------------
# get_texture: ディスクキャッシュ
# ---------------------------------------------------------------------------
class TestGetTextureDiskCache:
    def test_uses_disk_cache_after_memory_cleared(self, tmp_path):
        """アプリ再起動を模して clear_memory_cache() したあとでも、
        ディスクにファイルが残っていれば再デコードしないこと。
        """
        cache = ThumbnailCache(cache_dir=tmp_path)
        gfile = make_gfile()
        pixbuf_final, _ = stub_pixbuf_generation()

        # savev が実際にファイルを書き込むように仕込む
        # (本物のGdkPixbuf.savevの代わり)
        def fake_savev(path, fmt, opt_keys, opt_values):
            with open(path, "wb") as f:
                f.write(b"fake-png-bytes")

        pixbuf_final.savev.side_effect = fake_savev

        cache.get_texture(gfile, 128)  # 1回目: 新規生成 + ディスク保存
        cache.clear_memory_cache()  # メモリキャッシュだけクリア(再起動を模す)

        disk_texture = MagicMock(name="disk_texture")
        Gdk.Texture.new_from_filename.return_value = disk_texture

        result = cache.get_texture(gfile, 128)  # 2回目: ディスクキャッシュ

        assert result is disk_texture
        gfile.read.assert_called_once()  # 再デコードされていない

    def test_falls_back_to_generation_when_disk_file_missing(self, tmp_path):
        """savevが実際には書き込まなかった(=ディスクに何も残っていない)
        場合は、メモリキャッシュをクリアすると通常通り再生成されること。
        """
        cache = ThumbnailCache(cache_dir=tmp_path)
        gfile = make_gfile()
        stub_pixbuf_generation()  # savevは何もしない(デフォルトのMagicMock)

        cache.get_texture(gfile, 128)
        cache.clear_memory_cache()
        cache.get_texture(gfile, 128)

        assert gfile.read.call_count == 2


# ---------------------------------------------------------------------------
# メモリキャッシュのLRU上限
# ---------------------------------------------------------------------------
class TestMemoryCacheLRU:
    def test_oldest_entry_is_evicted_when_limit_exceeded(self, tmp_path):
        cache = ThumbnailCache(cache_dir=tmp_path, memory_limit=2)
        stub_pixbuf_generation()

        gfile_a = make_gfile(uri="file:///a.jpg")
        gfile_b = make_gfile(uri="file:///b.jpg")
        gfile_c = make_gfile(uri="file:///c.jpg")

        cache.get_texture(gfile_a, 128)
        cache.get_texture(gfile_b, 128)
        cache.get_texture(gfile_c, 128)  # ここで上限(2枚)を超え、aが追い出される

        assert len(cache._memory_cache) == 2

        # a は追い出されている(ディスクにも実体が無い)ため再度読み込みが発生する
        cache.get_texture(gfile_a, 128)
        assert gfile_a.read.call_count == 2

    def test_accessing_entry_moves_it_to_most_recently_used(self, tmp_path):
        """アクセスしたエントリは「最近使った」扱いになり、
        LRU上限に達しても真っ先には追い出されないこと。
        """
        cache = ThumbnailCache(cache_dir=tmp_path, memory_limit=2)
        stub_pixbuf_generation()

        gfile_a = make_gfile(uri="file:///a.jpg")
        gfile_b = make_gfile(uri="file:///b.jpg")
        gfile_c = make_gfile(uri="file:///c.jpg")

        cache.get_texture(gfile_a, 128)
        cache.get_texture(gfile_b, 128)
        cache.get_texture(gfile_a, 128)  # a を再度使う -> 最近使った扱いに
        cache.get_texture(gfile_c, 128)  # 上限超過 -> 一番古い b が追い出される

        cache.get_texture(gfile_a, 128)
        assert gfile_a.read.call_count == 1  # a はまだメモリに残っている

        cache.get_texture(gfile_b, 128)
        assert gfile_b.read.call_count == 2  # b は追い出されて再読み込みされた


# ---------------------------------------------------------------------------
# clear_disk_cache / disk_cache_size_bytes
# ---------------------------------------------------------------------------
class TestDiskCacheMaintenance:
    def test_disk_cache_size_bytes_sums_png_files(self, tmp_path):
        cache = ThumbnailCache(cache_dir=tmp_path)

        (tmp_path / "aaa.png").write_bytes(b"1" * 100)
        (tmp_path / "bbb.png").write_bytes(b"2" * 250)
        (tmp_path / "not_a_thumbnail.txt").write_bytes(b"ignored")

        assert cache.disk_cache_size_bytes() == 350

    def test_disk_cache_size_bytes_is_zero_when_empty(self, tmp_path):
        cache = ThumbnailCache(cache_dir=tmp_path)
        assert cache.disk_cache_size_bytes() == 0

    def test_clear_disk_cache_removes_all_png_files(self, tmp_path):
        cache = ThumbnailCache(cache_dir=tmp_path)

        (tmp_path / "aaa.png").write_bytes(b"1")
        (tmp_path / "bbb.png").write_bytes(b"2")
        keep = tmp_path / "keep_me.txt"
        keep.write_bytes(b"not a thumbnail")

        cache.clear_disk_cache()

        assert list(tmp_path.glob("*.png")) == []
        assert keep.exists()  # png以外のファイルには触らない

    def test_clear_memory_cache_empties_memory(self, tmp_path):
        cache = ThumbnailCache(cache_dir=tmp_path)
        stub_pixbuf_generation()

        cache.get_texture(make_gfile(), 128)
        assert len(cache._memory_cache) == 1

        cache.clear_memory_cache()

        assert len(cache._memory_cache) == 0

    def test_prune_disk_cache_removes_oldest_files_when_exceeding_limit(self, tmp_path):
        cache = ThumbnailCache(cache_dir=tmp_path)

        file1 = tmp_path / "old.png"
        file2 = tmp_path / "mid.png"
        file3 = tmp_path / "new.png"

        file1.write_bytes(b"a" * 100)
        file2.write_bytes(b"b" * 100)
        file3.write_bytes(b"c" * 100)

        # タイムスタンプを設定 (old: 1000, mid: 2000, new: 3000)
        import os
        os.utime(file1, (1000, 1000))
        os.utime(file2, (2000, 2000))
        os.utime(file3, (3000, 3000))

        # 上限 150 バイトに指定してプルーニング
        freed = cache.prune_disk_cache(max_size_bytes=150)

        assert freed == 200  # old と mid が削除される (100 + 100 = 200バイト解放)
        assert not file1.exists()
        assert not file2.exists()
        assert file3.exists()
        assert cache.disk_cache_size_bytes() == 100

