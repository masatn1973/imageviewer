"""
imagestate.py のテスト。

ImageState は GTK に依存しない、状態(ズーム率・回転角・現在の画像位置
など)を保持するだけの純粋な Python クラス。GTK なしで単体テストできる。
"""

import pytest

from models.imagestate import ImageState


@pytest.fixture
def state():
    """各テストの最初にまっさらな ImageState を用意する。"""
    return ImageState()


# ---------------------------------------------------------------------------
# 初期状態
# ---------------------------------------------------------------------------
class TestInitialState:
    def test_default_values(self, state):
        assert state.pixbuf is None
        assert state.zoom == ImageState.DEFAULT_ZOOM_RATIO
        assert state.fit_mode is True
        assert state.rotation == 0
        assert state.image_files == []
        assert state.current_index == 0

    def test_current_file_is_none_when_no_files(self, state):
        """画像リストが空のとき、current_file は None を返すこと。"""
        assert state.current_file is None


# ---------------------------------------------------------------------------
# ファイル一覧・現在位置の移動
# ---------------------------------------------------------------------------
class TestFileNavigation:
    def test_set_files(self, state):
        files = ["a.jpg", "b.jpg", "c.jpg"]
        state.set_files(files, index=1)

        assert state.image_files == files
        assert state.current_index == 1
        assert state.current_file == "b.jpg"

    def test_next_file_moves_forward(self, state):
        state.set_files(["a.jpg", "b.jpg", "c.jpg"])

        result = state.next_file()

        assert result == "b.jpg"
        assert state.current_file == "b.jpg"

    def test_next_file_wraps_around_to_first(self, state):
        """最後の画像で次へ進むと、最初の画像に戻ること(循環)。"""
        state.set_files(["a.jpg", "b.jpg", "c.jpg"], index=2)

        result = state.next_file()

        assert result == "a.jpg"
        assert state.current_index == 0

    def test_previous_file_moves_backward(self, state):
        state.set_files(["a.jpg", "b.jpg", "c.jpg"], index=1)

        result = state.previous_file()

        assert result == "a.jpg"
        assert state.current_index == 0

    def test_previous_file_wraps_around_to_last(self, state):
        """最初の画像で前へ戻ると、最後の画像に移動すること(循環)。"""
        state.set_files(["a.jpg", "b.jpg", "c.jpg"], index=0)

        result = state.previous_file()

        assert result == "c.jpg"
        assert state.current_index == 2

    def test_next_file_with_empty_list_returns_none(self, state):
        """画像リストが空のときに next_file を呼んでもエラーにならず、
        None を返すこと。
        """
        assert state.next_file() is None

    def test_previous_file_with_empty_list_returns_none(self, state):
        assert state.previous_file() is None

    def test_next_file_with_single_file_stays_same(self, state):
        """画像が1枚だけのとき、次へ進んでも同じ画像のままであること。"""
        state.set_files(["only.jpg"])

        result = state.next_file()

        assert result == "only.jpg"
        assert state.current_index == 0


# ---------------------------------------------------------------------------
# ズーム操作
# ---------------------------------------------------------------------------
class TestZoom:
    def test_zoom_reset_uses_fit_zoom(self, state):
        """zoom_reset() は fit_zoom の値を採用し、fit_mode を有効にすること。"""
        state.set_fit_zoom(0.5)
        state.zoom = 3.0
        state.fit_mode = False

        state.zoom_reset()

        assert state.zoom == 0.5
        assert state.fit_mode is True

    def test_zoom_actual_size_sets_100_percent(self, state):
        """zoom_actual_size() はズーム100%(等倍)にし、fit_modeを解除すること。"""
        state.fit_mode = True

        state.zoom_actual_size()

        assert state.zoom == ImageState.DEFAULT_ZOOM_RATIO
        assert state.fit_mode is False

    def test_set_fit_zoom(self, state):
        state.set_fit_zoom(0.75)
        assert state.fit_zoom == 0.75


# ---------------------------------------------------------------------------
# 回転操作
# ---------------------------------------------------------------------------
class TestRotation:
    def test_rotate_right_increases_by_90(self, state):
        state.rotate_right()
        assert state.rotation == 90

    def test_rotate_right_wraps_at_360(self, state):
        """右回転を4回行うと、360度で0度に戻ること。"""
        for _ in range(4):
            state.rotate_right()

        assert state.rotation == 0

    def test_rotate_left_decreases_by_90(self, state):
        """左回転は0度からでも負の値にならず、270度になること
        (Pythonの % は負数でも0以上の値を返す)。
        """
        state.rotate_left()
        assert state.rotation == 270

    def test_rotate_left_then_right_returns_to_original(self, state):
        state.rotate_left()
        state.rotate_right()
        assert state.rotation == 0


# ---------------------------------------------------------------------------
# initialize_view
# ---------------------------------------------------------------------------
class TestInitializeView:
    def test_resets_zoom_fit_mode_and_rotation(self, state):
        """画像を切り替えたときに呼ばれる initialize_view() が、
        ズーム・フィットモード・回転をすべて初期状態に戻すこと。
        """
        state.zoom = 5.0
        state.fit_mode = False
        state.rotation = 180

        state.initialize_view()

        assert state.zoom == ImageState.DEFAULT_ZOOM_RATIO
        assert state.fit_mode is True
        assert state.rotation == 0
