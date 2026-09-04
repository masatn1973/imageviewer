# test_security.py
from unittest.mock import MagicMock
import main


def test_do_open_with_empty_files_does_not_crash():
    app = MagicMock()
    win = MagicMock()
    app._get_or_create_window.return_value = win

    # do_open 実装を直接テスト
    main.ImageViewerApplication.do_open(app, [], 0, "")

    win.open_path.assert_not_called()
    win.present.assert_called_once()


def test_do_open_with_files_opens_first_file():
    app = MagicMock()
    win = MagicMock()
    app._get_or_create_window.return_value = win

    file1 = MagicMock()
    file2 = MagicMock()

    main.ImageViewerApplication.do_open(app, [file1, file2], 2, "")

    win.open_path.assert_called_once_with(file1)
    win.present.assert_called_once()
