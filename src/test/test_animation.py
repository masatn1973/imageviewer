# test_animation.py
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""
models/animation.py の単体テスト。
GTK に一切依存しないため、`pytest tests/test_animation.py` だけで実行できる。
"""

import pytest

from models.animation import is_gif_path, next_frame_delay


# --- is_gif_path -------------------------------------------------------------


class TestIsGifPath:
    def test_lowercase_gif_extension(self):
        assert is_gif_path("/home/user/pictures/cat.gif") is True

    def test_uppercase_gif_extension(self):
        assert is_gif_path("/home/user/pictures/CAT.GIF") is True

    def test_mixed_case_extension(self):
        assert is_gif_path("photo.Gif") is True

    def test_non_gif_extension(self):
        assert is_gif_path("/home/user/pictures/cat.png") is False

    def test_gif_substring_but_different_extension(self):
        # 拡張子ではなくファイル名の途中に "gif" が含まれるだけのケース
        assert is_gif_path("mygifcollection.png") is False

    def test_no_extension(self):
        assert is_gif_path("README") is False

    def test_none_path(self):
        # Gio.File.get_path() はリモートファイルの場合 None を返すため、
        # 例外を出さずに False になることを保証する
        assert is_gif_path(None) is False

    def test_empty_string_path(self):
        assert is_gif_path("") is False

    def test_windows_style_path(self):
        assert is_gif_path("C:\\Users\\me\\Pictures\\anim.gif") is True


# --- next_frame_delay ---------------------------------------------------------


class TestNextFrameDelay:
    def test_normal_delay_is_kept_as_is(self):
        assert next_frame_delay(100) == 100

    def test_negative_delay_means_animation_finished(self):
        # -1 は「これ以上フレームがない」ことを示す特別な値
        assert next_frame_delay(-1) is None

    def test_zero_delay_is_clamped_to_minimum(self):
        # GIFによっては 0ms 指定のことがあるため、最低値まで引き上げる
        assert next_frame_delay(0) == 20

    def test_delay_below_minimum_is_clamped(self):
        assert next_frame_delay(5) == 20

    def test_delay_above_minimum_is_untouched(self):
        assert next_frame_delay(500) == 500

    def test_custom_minimum(self):
        assert next_frame_delay(10, minimum=50) == 50
        assert next_frame_delay(100, minimum=50) == 100

    @pytest.mark.parametrize("delay_ms", [-1, -100, -9999])
    def test_any_negative_value_means_finished(self, delay_ms):
        assert next_frame_delay(delay_ms) is None
