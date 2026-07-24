# gallerycontroller.py
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

from gettext import gettext as _, ngettext

from gi.repository import Gdk, Gtk, Gio, GLib, GdkPixbuf

from models.searchfilter import matches_filename

THUMB = 128


class GalleryController:
    """window.py (ImageViewerWindow) のイベントハンドラを集約する Controller。

    View (ImageViewerWindow) からのシグナルを受けて GalleryModel を更新し、
    GalleryModel の変化を View に反映する橋渡し役。
    """

    def __init__(self, model, view):
        self.model = model
        self.view = view

        self.slideshow_id = None
        self.pending_files = []
        self.loaded_count = 0
        self.thumbnail_idle_id = None
        self.select_target = None

        self.failed_files = []
        self._broken_paintable = None

        self.search_text = ""

        # Model -> Controller
        self.model.connect("files-loaded", self.on_files_loaded)

        # View -> Controller
        view.flowbox.connect("child-activated", self.on_child_activated)
        view.flowbox.connect("selected-children-changed", self.on_selection_changed)

        # ファイル名によるフィルタリング (ギャラリー内の絞り込み検索)
        view.flowbox.set_filter_func(self.filter_thumbnail)
        view.search_entry.connect("search-changed", self.on_search_changed)

        drop_target = Gtk.DropTarget.new(Gdk.FileList, Gdk.DragAction.COPY)
        drop_target.connect("drop", self.on_drop)
        view.add_controller(drop_target)

        key_controller = Gtk.EventControllerKey()
        key_controller.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        key_controller.connect("key-pressed", self.on_key_pressed)
        view.add_controller(key_controller)

    # --- Model -> View ---------------------------------------------------------
    def on_files_loaded(self, model):
        if self.thumbnail_idle_id is not None:
            GLib.source_remove(self.thumbnail_idle_id)
            self.thumbnail_idle_id = None

        self.view.clear_thumbnails()

        self.pending_files = list(model.image_files)
        self.loaded_count = 0
        self.thumbnail_idle_id = GLib.idle_add(self._load_next_thumbnail)

        self.view.reload_action.set_enabled(True)
        self.view.slideshow_action.set_enabled(len(model.image_files) > 0)

    # --- 絞り込み検索 (ファイル名) ----------------------------------------------
    def on_search_changed(self, entry):
        self.search_text = entry.get_text()
        flowbox = self.view.flowbox
        flowbox.invalidate_filter()

        # invalidate_filter() は表示/非表示を切り替えるだけで、選択状態は
        # 変わらない。検索前に選択していたサムネイルが絞り込みで非表示に
        # なった場合、選択が「見えていないアイテム」を指したままになり、
        # 続けて Space/Enter を押すと検索結果に含まれない画像が開いて
        # しまう。フィルタ変更のたびに、選択中の子が表示中かどうかを
        # 確認し、非表示になっていれば表示中の先頭アイテムへ選択を
        # 移し替える。
        selected = flowbox.get_selected_children()
        visible_children = self._visible_children(flowbox)

        if not visible_children:
            return

        if not selected or selected[0] not in visible_children:
            target = visible_children[0]
            flowbox.unselect_all()
            flowbox.select_child(target)

    def filter_thumbnail(self, child):
        """GtkFlowBox.set_filter_func に渡すコールバック。

        True を返したサムネイルだけが表示される。
        マッチ判定そのものは models.searchfilter.matches_filename
        (GTK非依存の純粋関数) に委譲している。
        """
        gfile = getattr(child, "image_file", None)

        if gfile is None:
            return True

        return matches_filename(gfile.get_basename(), self.search_text)

    def open_path(self, gfile):
        folder = gfile.get_parent()

        if folder is None:
            print("open_path: Failed to get parent folder:", gfile.get_path())
            return

        self.select_target = gfile
        self.model.load_folder(folder)

    def _load_next_thumbnail(self):
        if not self.pending_files:
            self.thumbnail_idle_id = None
            self._report_failures()
            return False

        gfile = self.pending_files.pop(0)
        broken = False

        try:
            stream = gfile.read(None)

            try:
                pixbuf = GdkPixbuf.Pixbuf.new_from_stream_at_scale(
                    stream, THUMB, THUMB, True, None
                )
                pixbuf = pixbuf.apply_embedded_orientation()

            finally:
                stream.close(None)

            paintable = Gdk.Texture.new_for_pixbuf(pixbuf)

        except Exception:
            self.failed_files.append(gfile.get_basename())
            paintable = self._broken_image_pixbuf()
            broken = True

        if self.select_target is not None:
            select = gfile.equal(self.select_target)

        else:
            select = self.loaded_count == 0

        self.view.add_thumbnail(
            gfile,
            paintable,
            select=select,
            on_drag_prepare=self._on_thumbnail_drag_prepare,
            broken=broken,
        )

        self.loaded_count += 1
        self.view.set_status(f"{self.loaded_count} " + _("image(s) read."))

        if not self.pending_files:
            self.thumbnail_idle_id = None
            self.select_target = None
            self._report_failures()

            return False

        return True

    def _on_thumbnail_drag_prepare(self, source, x, y, gfile):
        file_list = Gdk.FileList.new_from_array([gfile])

        return Gdk.ContentProvider.new_for_value(file_list)

    def _report_failures(self):
        if not self.failed_files:
            return

        count = len(self.failed_files)
        self.view.show_error(
            ngettext(
                "Failed to load {count} image.",
                "Failed to load {count} images.",
                count,
            ).format(count=count)
        )
        self.failed_files = []

    def _broken_image_pixbuf(self):
        if self._broken_paintable is not None:
            return self._broken_paintable

        icon_theme = Gtk.IconTheme.get_for_display(self.view.get_display())
        self._broken_paintable = icon_theme.lookup_icon(
            "image-missing", None, THUMB, 1, Gtk.TextDirection.NONE, 0
        )

        return self._broken_paintable

    # --- View -> Model: フォルダ操作 ----------------------------------------
    def on_open(self, action, param):
        dialog = Gtk.FileDialog()
        dialog.select_folder(self.view, None, self._on_folder_selected)

    def _on_folder_selected(self, dialog, result):
        try:
            folder = dialog.select_folder_finish(result)

        except GLib.Error as e:
            if not e.matches(Gtk.DialogError.quark(), Gtk.DialogError.DISMISSED):
                self.view.show_error(_("Failed to open folder."))

            return

        if folder:
            self.model.load_folder(folder)

    def on_drop(self, target, value, x, y):
        files = value.get_files()

        for file in files:
            if (
                file.query_file_type(Gio.FileQueryInfoFlags.NONE, None)
                == Gio.FileType.DIRECTORY
            ):
                GLib.idle_add(self._open_dropped_folder, file)
                return True

        return False

    def _open_dropped_folder(self, folder):
        self.model.load_folder(folder)
        return False

    def reload_folder(self):
        self.model.load_folder(self.model.current_folder)

        if self.view.viewer:
            self.view.viewer.set_image_files(self.model.image_files)

    # --- View -> Model: ソート ---------------------------------------------
    def on_sort_changed(self, action, value):
        mode = value.get_string()
        action.set_state(value)

        if mode == "name":
            self.model.set_sort_mode("name", reverse=False)
        elif mode == "name-desc":
            self.model.set_sort_mode("name", reverse=True)
        elif mode == "date":
            self.model.set_sort_mode("date", reverse=False)
        elif mode == "date-desc":
            self.model.set_sort_mode("date", reverse=True)

    def set_sort_mode(self, mode, reverse=False):
        self.model.set_sort_mode(mode, reverse)

    # --- サムネイル選択 / ビューアー起動 ---------------------------------------
    def on_child_activated(self, flowbox, child):
        gfile = getattr(child, "image_file", None)

        if not gfile:
            return

        self.view.open_viewer(gfile, self.model.image_files)

    def on_selection_changed(self, flowbox):
        self.view.update_status(flowbox, self.model.image_files)

    # --- スライドショー ---------------------------------------------------------
    def on_slideshow(self, action, param):
        if self.slideshow_id is None:
            self._start_slideshow()
        else:
            self._stop_slideshow()

    def _start_slideshow(self):
        if self.view.viewer is None:
            self.view.open_selected_image(self.model.image_files)

        if self.view.viewer is None:
            return

        self.view.viewer.set_slideshow_mode(True)
        self.view.viewer.controller.enter_fullscreen()

        interval = self.view.settings.get_uint("slideshow-interval")
        self.slideshow_id = GLib.timeout_add(interval * 1000, self._slideshow_next)

    def _slideshow_next(self):
        if not self.model.image_files:
            self._stop_slideshow()
            return False

        if self.view.viewer is None:
            self._stop_slideshow()
            return False

        self.view.viewer.show_next_image()
        return True

    def is_slideshow_active(self):
        return self.slideshow_id is not None

    def stop_slideshow(self):
        self._stop_slideshow()

    def _stop_slideshow(self):
        if self.slideshow_id is not None:
            GLib.source_remove(self.slideshow_id)
            self.slideshow_id = None

        if self.view.viewer is not None:
            self.view.viewer.controller.exit_fullscreen()
            self.view.viewer.set_slideshow_mode(False)
            self.view.viewer.controller.show_current_image()

    # --- キーボードナビゲーション -------------------------------------------------
    def _visible_children(self, flowbox):
        """検索フィルタを通過して現在表示されている FlowBoxChild だけを、
        表示順のリストとして返す。

        GtkFlowBox の filter_func は非該当の子を「非表示(visible=False)」
        にするだけで、flowbox から取り除くわけではない。そのため
        get_child_at_index() や get_index() は非表示の子も含めた
        インデックスを返してしまう。キーボード移動は必ずこのメソッドが
        返す「見えているものだけのリスト」を基準に行うこと。
        """
        children = []
        child = flowbox.get_first_child()

        while child is not None:
            # GtkFlowBox はフィルタで除外した子を「visible」プロパティ
            # ではなく「child-visible」プロパティで隠す。そのため
            # get_visible() は常に True を返してしまい、フィルタ状態の
            # 判定には使えない。get_child_visible() を使うこと。
            if child.get_child_visible():
                children.append(child)

            child = child.get_next_sibling()

        return children

    # NOTE: 元の window.py の on_key_pressed のロジックをそのまま移設したもの。
    #       参照先を self.flowbox -> flowbox / self.image_files -> image_files
    #       に置き換えただけで、判定ロジック自体は変更していない。
    def on_key_pressed(self, controller, keyval, keycode, state):
        # 検索欄 (search_entry) にフォーカスがある間は、h/j/k/l 等を
        # サムネイル移動として横取りせず、そのまま入力させる。
        # このハンドラは CAPTURE フェーズで動いているため、ここで False
        # を返すと通常通りイベントが検索欄まで届く。
        #
        # isinstance(focus_widget, Gtk.Editable) のような型ベースの判定は
        # 「gi.repository をまるごとモックに差し替える」テスト環境
        # (Gtk.Editable が本物の型ではなくなる)と相性が悪いため使わず、
        # 「フォーカスが検索欄そのものかどうか」を同一性 (is) で判定する。
        focus_widget = self.view.get_focus()

        if focus_widget is self.view.search_entry:
            return False

        # GtkSearchEntry (GtkEditable) は合成ウィジェットで、実際に
        # フォーカスを受け取るのは search_entry 自身ではなく、内部の
        # delegate (Gtk.Text) であることが多い。そのため上の比較だけでは
        # 検索欄にフォーカスがあるのに False 判定になり、h/j/k/l が
        # サムネイル移動として横取りされてしまう。delegate 経由でも
        # 判定できるようにする。
        get_delegate = getattr(self.view.search_entry, "get_delegate", None)

        if get_delegate is not None and focus_widget is get_delegate():
            return False

        if keyval == Gdk.KEY_F5:
            self.reload_folder()
            return True

        flowbox = self.view.flowbox
        selected = flowbox.get_selected_children()

        if not selected:
            return False

        child = selected[0]

        # 検索フィルタで絞り込まれた「表示中のアイテム」だけを対象に扱う。
        # 以前はこの可視判定が Space/Enter の分岐より後ろにあったため、
        # 検索で非表示になったサムネイルが選択されたままの状態で
        # Space/Enter を押すと、検索結果に含まれない画像がそのまま
        # 開いてしまっていた。移動キーだけでなく画像を開く操作の前にも
        # 必ず可視判定を通す。
        visible_children = self._visible_children(flowbox)

        if not visible_children:
            return False

        if child not in visible_children:
            child = visible_children[0]
            flowbox.unselect_all()
            flowbox.select_child(child)

        if keyval in (Gdk.KEY_space, Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            self.on_child_activated(flowbox, child)
            return True

        index = visible_children.index(child)
        new_index = index
        first_child = visible_children[0]

        item_width = first_child.get_allocated_width() + flowbox.get_column_spacing()
        columns = max(1, flowbox.get_allocated_width() // item_width)

        if keyval in (Gdk.KEY_h, Gdk.KEY_Left, Gdk.KEY_ISO_Left_Tab):
            if new_index > 0:
                new_index -= 1

        elif keyval in (Gdk.KEY_j, Gdk.KEY_Down):
            if (new_index + columns) < len(visible_children):
                new_index += columns

        elif keyval in (Gdk.KEY_k, Gdk.KEY_Up):
            if (new_index - columns) >= 0:
                new_index -= columns

        elif keyval in (Gdk.KEY_l, Gdk.KEY_Right, Gdk.KEY_Tab):
            if (new_index + 1) < len(visible_children):
                new_index += 1

        elif keyval == Gdk.KEY_Home:
            new_index = 0

        elif keyval == Gdk.KEY_End:
            new_index = len(visible_children) - 1

        elif keyval == Gdk.KEY_Page_Up:
            vadj = self.view.scrolled_window.get_vadjustment()
            page_height = vadj.get_page_size()
            row_height = first_child.get_allocated_height() + flowbox.get_row_spacing()
            visible_rows = max(1, int(page_height // row_height))
            page_size = visible_rows * columns

            if (new_index - page_size) > 0:
                new_index -= page_size
            else:
                new_index = 0

        elif keyval == Gdk.KEY_Page_Down:
            vadj = self.view.scrolled_window.get_vadjustment()
            page_height = vadj.get_page_size()
            row_height = first_child.get_allocated_height() + flowbox.get_row_spacing()
            visible_rows = max(1, int(page_height // row_height))
            page_size = visible_rows * columns

            if (new_index + page_size) <= len(visible_children):
                new_index += page_size
            else:
                new_index = len(visible_children) - 1

        else:
            return False

        new_index = max(0, min(new_index, len(visible_children) - 1))
        target = visible_children[new_index]

        flowbox.unselect_all()
        flowbox.select_child(target)
        target.grab_focus()

        return True
