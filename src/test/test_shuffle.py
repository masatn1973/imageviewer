# test_shuffle.py
#
# ランダム再生(shuffle-enabled)機能のテスト。
#
# ViewerController / GalleryController は GTK ウィジェットを前提に
# __init__ でシグナル接続などを行うため、そのままインスタンス化する
# と実際の GTK 環境が必要になってしまう。
# ここでは __new__() でインスタンスを作り、テストに必要な属性だけを
# 手動でセットすることで、GTK に依存せずロジックだけを検証する。

import random
from unittest.mock import MagicMock, patch

import pytest

from controllers.viewercontroller import ViewerController
from controllers.gallerycontroller import GalleryController
from models.imagestate import ImageState


# --- ヘルパー: __init__ を経由せずにインスタンスを作る -------------------------

def make_viewer_controller(state):
    controller = ViewerController.__new__(ViewerController)
    controller.state = state
    return controller


def make_gallery_controller(model, view):
    controller = GalleryController.__new__(GalleryController)
    controller.model = model
    controller.view = view
    controller.slideshow_id = None
    return controller


# --- ViewerController.set_image_files ---------------------------------------

class TestViewerControllerSetImageFiles:
    def test_preserve_current_true_keeps_showing_same_file(self):
        """preserve_current=True (デフォルト) なら、リストの順番が変わっても
        現在表示中のファイルを表示し続ける。"""
        state = ImageState()
        state.set_files(["a.jpg", "b.jpg", "c.jpg"], index=1)  # 現在 b.jpg

        controller = make_viewer_controller(state)
        controller.set_image_files(["c.jpg", "b.jpg", "a.jpg"])

        assert state.current_file == "b.jpg"
        assert state.current_index == 1

    def test_preserve_current_false_resets_to_first_of_new_list(self):
        """preserve_current=False なら、現在の表示位置を維持せず
        新しいリストの先頭(index=0)を指すようになる。
        シャッフル時に「選択中の画像が必ず最初になる」問題への対処。"""
        state = ImageState()
        state.set_files(["a.jpg", "b.jpg", "c.jpg"], index=1)  # 現在 b.jpg

        controller = make_viewer_controller(state)
        controller.set_image_files(
            ["c.jpg", "a.jpg", "b.jpg"], preserve_current=False
        )

        assert state.current_index == 0
        assert state.current_file == "c.jpg"

    def test_current_file_not_in_new_list_falls_back_to_first(self):
        """現在のファイルが新リストに存在しない場合(削除された等)は
        先頭にフォールバックする。"""
        state = ImageState()
        state.set_files(["a.jpg", "b.jpg"], index=1)  # 現在 b.jpg

        controller = make_viewer_controller(state)
        controller.set_image_files(["x.jpg", "y.jpg"])  # b.jpg は含まれない

        assert state.current_index == 0

    def test_empty_new_list_does_not_raise(self):
        """空リストを渡してもエラーにならないこと。"""
        state = ImageState()
        state.set_files(["a.jpg"], index=0)

        controller = make_viewer_controller(state)
        controller.set_image_files([])

        assert state.current_index == 0
        assert state.current_file is None


# --- GalleryController._apply_shuffle ----------------------------------------

class TestApplyShuffle:
    def test_does_not_mutate_model_image_files(self, monkeypatch):
        """model.image_files (ギャラリー本体の並び順) 自体は
        シャッフルの影響を受けない。"""
        model = MagicMock()
        model.image_files = ["1.jpg", "2.jpg", "3.jpg", "4.jpg"]
        original_order = list(model.image_files)

        view = MagicMock()
        controller = make_gallery_controller(model, view)

        monkeypatch.setattr(random, "shuffle", lambda lst: lst.reverse())

        controller._apply_shuffle()

        assert model.image_files == original_order

    def test_passes_shuffled_copy_with_preserve_current_false(self, monkeypatch):
        """viewer.set_image_files() には shuffle 済みのコピーが
        preserve_current=False で渡される。"""
        model = MagicMock()
        model.image_files = ["1.jpg", "2.jpg", "3.jpg", "4.jpg"]

        view = MagicMock()
        controller = make_gallery_controller(model, view)

        monkeypatch.setattr(random, "shuffle", lambda lst: lst.reverse())

        controller._apply_shuffle()

        view.viewer.set_image_files.assert_called_once()
        args, kwargs = view.viewer.set_image_files.call_args

        assert args[0] == ["4.jpg", "3.jpg", "2.jpg", "1.jpg"]
        assert kwargs.get("preserve_current") is False

    def test_updates_display_after_shuffle(self, monkeypatch):
        """シャッフル後、先頭画像を実際に画面へ反映するために
        show_current_image() が呼ばれる。"""
        model = MagicMock()
        model.image_files = ["1.jpg", "2.jpg"]

        view = MagicMock()
        controller = make_gallery_controller(model, view)

        monkeypatch.setattr(random, "shuffle", lambda lst: None)

        controller._apply_shuffle()

        view.viewer.controller.show_current_image.assert_called_once()


# --- GalleryController._start_slideshow: shuffle-enabled の反映 ----------------

class TestStartSlideshowShuffleSetting:
    def _make_controller_with_open_viewer(self):
        model = MagicMock()
        model.image_files = ["1.jpg", "2.jpg"]

        view = MagicMock()
        view.viewer = MagicMock()  # すでにビューアーが開いている状態

        controller = make_gallery_controller(model, view)
        controller._apply_shuffle = MagicMock()

        return controller, view

    def test_shuffle_enabled_calls_apply_shuffle(self):
        controller, view = self._make_controller_with_open_viewer()
        view.settings.get_boolean.return_value = True
        view.settings.get_uint.return_value = 3

        with patch("controllers.gallerycontroller.GLib.timeout_add", return_value=1):
            controller._start_slideshow()

        view.settings.get_boolean.assert_called_with("shuffle-enabled")
        controller._apply_shuffle.assert_called_once()

    def test_shuffle_disabled_does_not_call_apply_shuffle(self):
        controller, view = self._make_controller_with_open_viewer()
        view.settings.get_boolean.return_value = False
        view.settings.get_uint.return_value = 3

        with patch("controllers.gallerycontroller.GLib.timeout_add", return_value=1):
            controller._start_slideshow()

        controller._apply_shuffle.assert_not_called()
