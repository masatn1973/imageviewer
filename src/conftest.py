# このファイルがある場所(プロジェクトルート)を基準に、
# `from models.geometry import ...` のような import が
# 動くようにするための設定ファイル。pytest が自動的に読み込む。

import sys
import types
from unittest.mock import MagicMock


def _install_fake_gi():
    """gi.repository (GTK本体) を丸ごと偽物に差し替える。

    gallerycontroller.py などは先頭で
        from gi.repository import Gdk, Gtk, Gio, GLib, GdkPixbuf
    としているので、テスト対象のモジュールを import する【前】に、
    sys.modules に偽の 'gi.repository' を仕込んでおく必要がある。

    こうしておくと、実機にGTKが入っていない環境(CIサーバーなど)でも
    「ロジック部分」だけをテストできる。
    お使いのPCのようにGTKが実際に入っている環境では、本来この処理は
    必須ではない(本物のGTKを使ってもよい)が、どちらの環境でも同じ
    テストコードが動くようにするためにここで差し替えている。
    """
    fake_repository = types.ModuleType("gi.repository")

    for name in (
        "Gtk",
        "Gdk",
        "GLib",
        "Gio",
        "GdkPixbuf",
        "GObject",
        "Adw",
        "GExiv2",
    ):
        # MagicMock() は「何を呼んでも(メソッドを呼んでも属性を
        # 参照しても)エラーにならず、また別のMagicMockを返す」便利な偽物。
        setattr(fake_repository, name, MagicMock(name=name))

    fake_gi = MagicMock(name="gi")
    fake_gi.repository = fake_repository

    sys.modules["gi"] = fake_gi
    sys.modules["gi.repository"] = fake_repository

    _install_fake_drawing_area(fake_repository)
    _install_fake_gtk_template(fake_repository)


def _install_fake_gtk_template(fake_repository):
    """`@Gtk.Template(resource_path=...)` を「クラスをそのまま返すだけ」の
    identity decorator に差し替える。

    本物の Gtk.Template はクラスを .ui ファイルと結びつける処理をするが、
    そのままモック(MagicMock)にしておくと、デコレータ呼び出し
    (`Gtk.Template(resource_path=...)`)のたびに新しい MagicMock が
    返ってしまい、それをクラスに適用した結果(`decorator(cls)`)も
    別の MagicMock になってしまう。つまり

        @Gtk.Template(resource_path="...")
        class PreferencesWindow(Adw.PreferencesWindow):
            ...

    と書いても、モジュールに束縛される `PreferencesWindow` が
    「本物のクラスの中身(メソッドなど)を持たない別物」に化けてしまい、
    そのクラスの中身をテストできなくなる。

    テストでは実際に .ui リソースを読み込む必要はないので、単に
    元のクラスをそのまま返すようにしておく。`Gtk.Template.Child()`
    (テンプレート内のウィジェットへの参照を宣言する部分)は、
    クラス属性のプレースホルダーとして None を返すだけにしておき、
    各テスト側で必要なウィジェットを直接モックに差し替えて使う。
    """

    def fake_template(*args, **kwargs):
        def decorator(cls):
            return cls

        return decorator

    def fake_template_child(*args, **kwargs):
        return None

    fake_template.Child = fake_template_child
    fake_repository.Gtk.Template = fake_template


class _FakeGtkWidget:
    """Gtk.DrawingArea など「継承して使うGTKクラス」の代役。

    MagicMock() のインスタンスは class文で継承しても正しく動かない
    (独自の __init__ が呼ばれない)ため、継承が必要な相手だけは
    こうして「本物のPythonクラス」を用意する。

    呼ばれたメソッド・属性は自動的に MagicMock として振る舞う
    (= 何を呼んでもエラーにならない)ようにしつつ、同じ名前には
    毎回同じ MagicMock を返すことで、テスト側で
    `instance.queue_draw.assert_called()` のような検証もできるようにする。
    """

    def __getattr__(self, name):
        mock = MagicMock(name=name)
        object.__setattr__(self, name, mock)
        return mock


def _install_fake_drawing_area(fake_repository):
    """imagecanvas.py の `class ImageCanvas(Gtk.DrawingArea):` や
    preferences.py の `class PreferencesWindow(Adw.PreferencesWindow):`
    のように「継承して使うGTK/Adwaitaのクラス」が正しく継承できるように、
    それらのクラスだけ本物のPythonクラス(_FakeGtkWidget)に差し替える。

    MagicMock のインスタンスをそのまま基底クラスにすると、Pythonの
    クラス文が正しく動かない(__mro_entries__ 絡みで、定義したはずの
    クラスが別のMagicMockに化けてしまう)ため。
    """
    fake_repository.Gtk.DrawingArea = _FakeGtkWidget
    fake_repository.Adw.PreferencesWindow = _FakeGtkWidget


_install_fake_gi()
