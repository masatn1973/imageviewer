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
    """imagecanvas.py の `class ImageCanvas(Gtk.DrawingArea):` が
    正しく継承できるように、Gtk.DrawingArea だけ本物のクラスに差し替える。
    """
    fake_repository.Gtk.DrawingArea = _FakeGtkWidget


_install_fake_gi()
