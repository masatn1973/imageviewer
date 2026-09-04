# test_gallerycontroller_search_focus.py
#
# 検索絞り込み中に発生していた以下2つのバグに対する回帰テスト:
#
#   1. 検索文字列を変更しても、選択(フォーカス)が検索結果の1枚目に
#      移動しない場合がある。
#   2. その状態で Space キーを押すと、検索結果にマッチしない
#      (=非表示になっている)画像が開いてしまう。
#
# 実機の GTK を必要とせず、gi.repository をまるごとモックに差し替えて
# GalleryController のロジックだけを検証する。
#
# 想定リポジトリ構成 (このファイルからの相対位置のみに依存し、
# 実行環境固有の絶対パスは一切含まない):
#
#   repo-root/
#     controllers/
#       __init__.py
#       gallerycontroller.py
#     tests/
#       test_gallerycontroller_search_focus.py   <- このファイル
#
# 実行方法:
#   pytest tests/test_gallerycontroller_search_focus.py

import sys
import types
from importlib import import_module
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

# tests/ の1つ上 = リポジトリルート。絶対パスをハードコードせず、
# このファイル自身の場所から相対的に解決する。
REPO_ROOT = Path(__file__).resolve().parent.parent

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# --- gi.repository をモックに差し替える ---------------------------------------
#
# gallerycontroller.py は先頭で
#   from gi.repository import Gdk, Gtk, Gio, GLib, GdkPixbuf
# をインポートしているため、GTK が入っていない環境(CI等)でも import
# できるよう、実行前に sys.modules へ偽物を差し込む。
#
# models.searchfilter は GTK 非依存の純粋関数 (matches_filename) なので、
# リポジトリに実物があればそのままインポートし、無い場合(このテスト
# ファイル単体で試す場合など)のみ簡易スタブにフォールバックする。
#
# Gdk.KEY_space のような定数は MagicMock の属性アクセスとして扱う。
# MagicMock は同じ属性に何度アクセスしても同一オブジェクトを返す
# ("mock.KEY_space is mock.KEY_space" は常に True) ため、
# `keyval in (Gdk.KEY_space, Gdk.KEY_Return, ...)` のような
# 同一性(is)ベースの比較がそのまま成立する。
@pytest.fixture(scope="module")
def gallerycontroller_module():
    fake_gdk = MagicMock(name="Gdk")
    fake_gi = types.ModuleType("gi")
    fake_gi_repository = types.ModuleType("gi.repository")
    fake_gi_repository.Gdk = fake_gdk
    fake_gi_repository.Gtk = MagicMock(name="Gtk")
    fake_gi_repository.Gio = MagicMock(name="Gio")
    fake_gi_repository.GLib = MagicMock(name="GLib")
    fake_gi_repository.GLib.timeout_add.side_effect = lambda _ms, cb, *a: cb(*a)
    fake_gi_repository.GdkPixbuf = MagicMock(name="GdkPixbuf")
    fake_gi.repository = fake_gi_repository

    injected = {"gi": fake_gi, "gi.repository": fake_gi_repository}

    try:
        import_module("models.searchfilter")
    except ImportError:
        fake_models = types.ModuleType("models")
        fake_searchfilter = types.ModuleType("models.searchfilter")

        def fake_matches_filename(filename, search_text):
            # models.searchfilter が無い環境向けの簡易フォールバック実装
            return search_text.lower() in filename.lower()

        fake_searchfilter.matches_filename = fake_matches_filename
        injected["models"] = fake_models
        injected["models.searchfilter"] = fake_searchfilter

    saved = {name: sys.modules.get(name) for name in injected}
    sys.modules.update(injected)

    # controllers.gallerycontroller が(このテスト以外の経路で)
    # 本物の gi 込みで先にインポート済みだと、上のモック差し替えが
    # 効かないまま古いモジュールがキャッシュから返ってしまう。
    # 必ずモック適用後の状態で読み直すため、一旦キャッシュを外す。
    saved["controllers"] = sys.modules.get("controllers")
    saved["controllers.gallerycontroller"] = sys.modules.get(
        "controllers.gallerycontroller"
    )
    sys.modules.pop("controllers.gallerycontroller", None)

    try:
        module = import_module("controllers.gallerycontroller")
        module.Gdk = fake_gdk  # テスト側から Gdk.KEY_* を参照するため保持
        yield module

    finally:
        for name, original in saved.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


# --- テスト用の簡易 FlowBox / FlowBoxChild -----------------------------------
#
# 本物の Gtk.FlowBox は使わず、_visible_children() が依存している
# get_first_child() / get_next_sibling() / get_child_visible() だけを
# 持つ最小限の偽オブジェクトで代用する。
class FakeChild:
    def __init__(self, image_file, visible=True):
        self.image_file = image_file
        self._visible = visible
        self._next = None

    def get_child_visible(self):
        return self._visible

    def get_next_sibling(self):
        return self._next


class FakeFlowBox:
    def __init__(self, children):
        self._children = children

        for a, b in zip(children, children[1:]):
            a._next = b

        self._selected = []

    def get_first_child(self):
        return self._children[0] if self._children else None

    def get_selected_children(self):
        return list(self._selected)

    def select_child(self, child):
        self._selected = [child]

    def unselect_all(self):
        self._selected = []

    def get_column_spacing(self):
        return 0

    def get_row_spacing(self):
        return 0

    def get_allocated_width(self):
        return 1000

    def invalidate_filter(self):
        # 本物の Gtk.FlowBox はここで filter_func を再適用して
        # child-visible を更新するが、このテストでは FakeChild の
        # visible フラグを事前にセットして代用しているため何もしない
        pass


def _make_controller(module, flowbox):
    """__init__ を経由せず(=シグナル接続などを一切行わず)、
    テストに必要な属性だけを持つ GalleryController を組み立てる。
    """
    controller = module.GalleryController.__new__(module.GalleryController)
    controller.search_text = ""
    controller.model = SimpleNamespace(image_files=["a.jpg", "b.jpg", "c.jpg"])

    view = MagicMock()
    view.flowbox = flowbox
    # 検索欄・delegate のどちらにもフォーカスが無い状態を模倣
    # (キー入力ガードを素通りさせるため)
    view.get_focus.return_value = MagicMock(name="unrelated_focus_widget")
    view.search_entry = MagicMock(name="search_entry")
    view.search_entry.get_delegate.return_value = MagicMock(name="search_entry_delegate")
    controller.view = view
    controller._search_debounce_id = None

    return controller


# --- バグ1: 検索変更後、選択が検索結果の1枚目に移動しない ---------------------
def test_search_changed_moves_selection_to_first_visible_child(gallerycontroller_module):
    module = gallerycontroller_module

    # "cat1.jpg" は検索前に選択されていたが、検索文字列 "dog" では
    # マッチしなくなり非表示(child_visible=False)になったとする
    hidden_selected = FakeChild("cat1.jpg", visible=False)
    first_match = FakeChild("dog1.jpg", visible=True)
    second_match = FakeChild("dog2.jpg", visible=True)

    flowbox = FakeFlowBox([hidden_selected, first_match, second_match])
    flowbox.select_child(hidden_selected)  # 検索前の選択状態を再現

    controller = _make_controller(module, flowbox)

    entry = MagicMock()
    entry.get_text.return_value = "dog"

    controller.on_search_changed(entry)

    selected = flowbox.get_selected_children()
    assert selected == [first_match], (
        "検索結果に含まれる先頭アイテムへ選択が移動していない: "
        f"selected={[c.image_file for c in selected]}"
    )


def test_search_changed_keeps_selection_if_still_visible(gallerycontroller_module):
    module = gallerycontroller_module

    match_a = FakeChild("dog1.jpg", visible=True)
    match_b = FakeChild("dog2.jpg", visible=True)

    flowbox = FakeFlowBox([match_a, match_b])
    flowbox.select_child(match_b)  # 2枚目を選択中

    controller = _make_controller(module, flowbox)

    entry = MagicMock()
    entry.get_text.return_value = "dog"

    controller.on_search_changed(entry)

    # 既に表示中のアイテムを選択している場合は、選択を変更しない
    assert flowbox.get_selected_children() == [match_b]


# --- バグ2: 非表示アイテムが選択されたまま Space を押すと、
#            検索結果にマッチしない画像が開いてしまう -----------------------
def test_space_key_opens_first_visible_child_not_hidden_selection(gallerycontroller_module):
    module = gallerycontroller_module
    Gdk = module.Gdk

    # 検索フィルタで非表示になった画像が、まだ「選択中」として
    # 残ってしまっている状況を再現する
    hidden_selected = FakeChild("cat1.jpg", visible=False)
    first_match = FakeChild("dog1.jpg", visible=True)
    second_match = FakeChild("dog2.jpg", visible=True)

    flowbox = FakeFlowBox([hidden_selected, first_match, second_match])
    flowbox.select_child(hidden_selected)

    controller = _make_controller(module, flowbox)

    controller.on_key_pressed(
        controller=None, keyval=Gdk.KEY_space, keycode=0, state=0
    )

    # 修正前は hidden_selected ("cat1.jpg") が開かれてしまっていた。
    # 修正後は、表示中(検索結果にマッチする)先頭アイテムが開かれるべき。
    controller.view.open_viewer.assert_called_once_with(
        "dog1.jpg", controller.model.image_files
    )


def test_space_key_opens_selected_child_when_already_visible(gallerycontroller_module):
    """回帰確認: 選択中のアイテムが表示されている通常時の動作は変えない。"""
    module = gallerycontroller_module
    Gdk = module.Gdk

    match_a = FakeChild("dog1.jpg", visible=True)
    match_b = FakeChild("dog2.jpg", visible=True)

    flowbox = FakeFlowBox([match_a, match_b])
    flowbox.select_child(match_b)

    controller = _make_controller(module, flowbox)

    controller.on_key_pressed(
        controller=None, keyval=Gdk.KEY_space, keycode=0, state=0
    )

    controller.view.open_viewer.assert_called_once_with(
        "dog2.jpg", controller.model.image_files
    )
