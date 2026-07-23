"""
geometry.py のテスト。

geometry.py は GTK に依存しない「純粋関数」だけで構成されているので、
実際の画面を表示しなくてもロジックだけをテストできる。
"""

import pytest

from models.geometry import compute_geometry, compute_zoom_anchor


# ---------------------------------------------------------------------------
# compute_geometry のテスト
# ---------------------------------------------------------------------------
class TestComputeGeometry:
    def test_image_smaller_than_view(self):
        """画像がビューより小さい場合、コンテンツサイズはビューサイズになる。

        画像 100x100 をズーム1.0で表示 -> 描画サイズは100x100。
        ビューが800x600なら、それより小さい画像はビューいっぱいに
        余白(オフセット)を持って中央寄せされるはず。
        """
        content_w, content_h, offset_x, offset_y = compute_geometry(
            image_w=100, image_h=100, view_w=800, view_h=600, zoom=1.0
        )

        assert content_w == 800
        assert content_h == 600

        # 中央に配置されるので、左右・上下の余白は均等になる
        assert offset_x == (800 - 100) / 2
        assert offset_y == (600 - 100) / 2

    def test_image_larger_than_view(self):
        """画像がビューより大きい場合、コンテンツサイズは画像の描画サイズに
        なり、オフセットは0(はみ出す=スクロールで見る)になる。
        """
        content_w, content_h, offset_x, offset_y = compute_geometry(
            image_w=1000, image_h=1000, view_w=400, view_h=300, zoom=1.0
        )

        assert content_w == 1000
        assert content_h == 1000
        assert offset_x == 0
        assert offset_y == 0

    def test_zoom_scales_draw_size(self):
        """ズーム率が描画サイズに正しく反映されること。"""
        content_w, content_h, offset_x, offset_y = compute_geometry(
            image_w=100, image_h=100, view_w=50, view_h=50, zoom=2.0
        )

        # 100 * 2.0 = 200 でビュー(50)より大きいので、コンテンツサイズは200
        assert content_w == 200
        assert content_h == 200
        assert offset_x == 0
        assert offset_y == 0

    def test_offset_is_never_negative(self):
        """画像がビューより大きいときにオフセットが負の値にならないこと。

        max(..., 0) のガードが効いているかの確認。
        """
        _, _, offset_x, offset_y = compute_geometry(
            image_w=2000, image_h=2000, view_w=100, view_h=100, zoom=1.0
        )

        assert offset_x >= 0
        assert offset_y >= 0


# ---------------------------------------------------------------------------
# compute_zoom_anchor のテスト
# ---------------------------------------------------------------------------
class TestComputeZoomAnchor:
    def test_same_zoom_returns_same_point(self):
        """ズーム率が変わらない場合、アンカー座標も変わらないこと。"""
        x, y = compute_zoom_anchor(
            x=100, y=100,
            old_zoom=1.0, new_zoom=1.0,
            offset_x_old=0, offset_y_old=0,
            offset_x_new=0, offset_y_new=0,
        )

        assert x == pytest.approx(100)
        assert y == pytest.approx(100)

    def test_zoom_in_doubles_distance_from_offset(self):
        """ズームを2倍にすると、オフセットからの距離も2倍になること。

        offset=0, カーソル位置=50, old_zoom=1.0 のとき、
        画像上のアンカー点は (50-0)/1.0 = 50。
        new_zoom=2.0 なら、新しい座標は 0 + 50*2.0 = 100 になるはず。
        """
        x, y = compute_zoom_anchor(
            x=50, y=50,
            old_zoom=1.0, new_zoom=2.0,
            offset_x_old=0, offset_y_old=0,
            offset_x_new=0, offset_y_new=0,
        )

        assert x == pytest.approx(100)
        assert y == pytest.approx(100)

    def test_zoom_out_halves_distance_from_offset(self):
        """ズームを半分にすると、オフセットからの距離も半分になること。"""
        x, y = compute_zoom_anchor(
            x=100, y=100,
            old_zoom=2.0, new_zoom=1.0,
            offset_x_old=0, offset_y_old=0,
            offset_x_new=0, offset_y_new=0,
        )

        assert x == pytest.approx(50)
        assert y == pytest.approx(50)

    def test_offset_change_is_reflected(self):
        """新しいオフセットがそのまま結果に加算されること。"""
        x, y = compute_zoom_anchor(
            x=50, y=50,
            old_zoom=1.0, new_zoom=1.0,
            offset_x_old=0, offset_y_old=0,
            offset_x_new=10, offset_y_new=20,
        )

        assert x == pytest.approx(60)  # 10 + 50
        assert y == pytest.approx(70)  # 20 + 50
