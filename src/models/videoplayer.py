# videoplayer.py
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
"""
ffmpeg を子プロセスとして使う、ごく簡易な動画プレーヤー。

Gtk.Video (内部はGStreamer) は、このアプリの動作環境(古いIntel内蔵GPU +
GTK4のVulkan/GLレンダラー)との相性問題で、クラッシュやメモリ肥大化を
繰り返し起こした。そのため、動画のフレームを ffmpeg で1枚ずつ生画像として
取り出し、自前で Gtk.Picture に貼り付けていく方式に切り替えている。

制約(意図的な割り切り):
- 音声は再生しない(無音)。
- シーク・巻き戻しは無い。「再生」「停止(次に再生したら先頭から)」のみ。
- 表示中フレームは常に1枚だけ保持し、古いフレームは即座に手放すことで
  メモリ使用量を抑えている。
"""

from __future__ import annotations

import queue
import shutil
import subprocess
import signal
import threading

from gi.repository import Gdk, GdkPixbuf, GLib

_FFMPEG_PATH = shutil.which("ffmpeg")
_FFPROBE_PATH = shutil.which("ffprobe")

DEFAULT_FPS = 30.0

# 音声プロセスは「映像の最初の1コマが画面に表示された瞬間」に起動して
# いるが、そこから実際に音が鳴り始めるまでのわずかな起動時間
# (プロセス起動・PulseAudio接続など)がどうしても残る。それでもまだ
# 音声が早く聞こえる/遅く聞こえる場合は、この値で微調整してください。
# 単位は秒。0.0 が「追加の調整なし」。
# - 音声が早く聞こえる → 値を大きくする(例: 0.05, 0.1)
# - 音声が遅く聞こえる → 値を小さくする、またはマイナスにする
AUDIO_FINE_TUNE_SEC = 0.0

# 再生時の最大幅/高さ。大きすぎるとメモリ・CPU負荷が高くなるため、
# ビューアーの表示領域より大きなサイズでは絶対にデコードさせない。
MAX_DIMENSION = 960


def _probe_fps(path: str) -> float:
    """ffprobe で動画のフレームレートを調べる。失敗したら既定値を返す。"""
    if _FFPROBE_PATH is None:
        return DEFAULT_FPS

    try:
        result = subprocess.run(
            [
                _FFPROBE_PATH,
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=r_frame_rate",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                path,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=5,
        )
    except (subprocess.TimeoutExpired, OSError):
        return DEFAULT_FPS

    text = result.stdout.decode("utf-8", "ignore").strip()

    if "/" in text:
        try:
            num_str, den_str = text.split("/")
            den = float(den_str)
            return float(num_str) / den if den else DEFAULT_FPS
        except ValueError:
            return DEFAULT_FPS

    try:
        value = float(text)
        return value if value > 0 else DEFAULT_FPS
    except ValueError:
        return DEFAULT_FPS


def _probe_dimensions(path: str) -> tuple[int, int] | None:
    """ffprobe で動画の元の幅・高さを調べる。失敗したら None を返す。"""
    if _FFPROBE_PATH is None:
        print("[videoplayer] ffprobe が見つからないため、解像度を取得できません")
        return None

    try:
        result = subprocess.run(
            [
                _FFPROBE_PATH,
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height",
                "-of",
                "csv=s=x:p=0",
                path,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=5,
        )
    except (subprocess.TimeoutExpired, OSError) as e:
        print(f"[videoplayer] ffprobe(解像度)の実行に失敗しました: {e}")
        return None

    if result.returncode != 0:
        stderr_text = result.stderr.decode("utf-8", "ignore").strip()
        print(
            f"[videoplayer] ffprobe(解像度)が異常終了しました "
            f"(code={result.returncode}): {stderr_text}"
        )
        return None

    text = result.stdout.decode("utf-8", "ignore").strip()
    parts = text.split("x")

    if len(parts) < 2:
        print(f"[videoplayer] ffprobe(解像度)の出力を解析できませんでした: {text!r}")
        return None

    try:
        # "1024x768" が基本形だが、環境によっては "1024x768x"(末尾に
        # 空の項目が付く)ことがあるため、先頭2つだけを使う。
        width = int(parts[0])
        height = int(parts[1])
    except ValueError:
        print(f"[videoplayer] ffprobe(解像度)の出力を解析できませんでした: {text!r}")
        return None

    if width <= 0 or height <= 0:
        print(f"[videoplayer] ffprobe(解像度)が不正な値を返しました: {width}x{height}")
        return None

    return width, height


def _probe_has_audio(path: str) -> bool:
    """動画に音声トラックがあるかどうかを調べる。

    音声トラックが無いファイルに対して音声出力を要求すると ffmpeg が
    エラー終了してしまう(結果として映像も出なくなる)ため、事前に
    確認しておく。
    """
    if _FFPROBE_PATH is None:
        return False

    try:
        result = subprocess.run(
            [
                _FFPROBE_PATH,
                "-v",
                "error",
                "-select_streams",
                "a:0",
                "-show_entries",
                "stream=index",
                "-of",
                "csv=p=0",
                path,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=5,
        )
    except (subprocess.TimeoutExpired, OSError) as e:
        print(f"[videoplayer] ffprobe(音声トラック確認)の実行に失敗しました: {e}")
        return False

    return bool(result.stdout.decode("utf-8", "ignore").strip())


def _probe_rotation(path: str) -> int:
    """動画に埋め込まれた回転情報(度)を調べる。無ければ 0 を返す。

    スマホの縦撮り動画などでは、実際の映像データは横向きのまま格納され、
    「表示するときに何度回すべきか」という情報だけが別途メタデータとして
    埋め込まれていることが多い。これを無視すると、縦動画が横に間延び
    して表示されてしまう。
    """
    if _FFPROBE_PATH is None:
        return 0

    try:
        result = subprocess.run(
            [
                _FFPROBE_PATH,
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream_side_data=rotation",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                path,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=5,
        )
    except (subprocess.TimeoutExpired, OSError) as e:
        print(f"[videoplayer] ffprobe(回転情報)の実行に失敗しました: {e}")
        return 0

    text = result.stdout.decode("utf-8", "ignore").strip().splitlines()

    if not text:
        return 0

    try:
        rotation = int(float(text[0]))
    except ValueError:
        print(f"[videoplayer] ffprobe(回転情報)の出力を解析できませんでした: {text!r}")
        return 0

    print(f"[videoplayer] 検出した回転情報: {rotation}度")

    return rotation % 360


def _fit_size(
    src_width: int | None,
    src_height: int | None,
    view_width: int,
    view_height: int,
) -> tuple[int, int]:
    """表示領域(view_width x view_height)に収まる、アスペクト比を保った
    サイズを計算する。奇数だと一部のスケーラで問題になることがあるため、
    偶数に丸める。
    """
    view_width = min(max(view_width, 2), MAX_DIMENSION)
    view_height = min(max(view_height, 2), MAX_DIMENSION)

    if not src_width or not src_height:
        width, height = view_width, view_height
    else:
        scale = min(view_width / src_width, view_height / src_height, 1.0)
        width = max(2, int(src_width * scale))
        height = max(2, int(src_height * scale))

    width -= width % 2
    height -= height % 2

    return max(width, 2), max(height, 2)


class FfmpegVideoPlayer:
    """Gtk.Picture に、ffmpegで取り出した動画フレームを流し込むだけの
    簡易プレーヤー。1つのウィジェットに対して1つ作って使う想定。
    """

    def __init__(self, picture, play_icon=None):
        self._picture = picture
        # 停止中(静止画プレビュー表示時・再生終了後)に表示する、
        # ○に▶マークのウィジェット。無くても動作する(None可)。
        self._play_icon = play_icon
        self._proc: subprocess.Popen | None = None
        # 音声は映像とは別プロセスで再生する(理由は play() 参照)。
        self._audio_proc: subprocess.Popen | None = None
        # 音声プロセスは play() の時点ですでに起動済みだが、
        # SIGSTOPで凍結された状態になっている。映像の最初の1コマが
        # 実際に画面に表示された瞬間に SIGCONT で解凍する。
        # この間に「True」なら、まだ解凍待ち。
        self._audio_sync_pending = False
        self._audio_sync_generation: int | None = None
        self._paused = False
        self._stop_event = threading.Event()
        # デコードしたフレームを一時的に貯めておく小さなキュー。
        # 読み込みスレッドはここに詰め込むだけ、表示は別途タイマーで
        # 一定間隔で取り出す(pump_frame)。こうすることで、動画の
        # デコードが一瞬重くなる(キーフレームなど)瞬間があっても、
        # このキューが吸収してくれるので、体感上の引っかかりが減る。
        self._frame_queue: queue.Queue | None = None
        self._pump_timeout_id: int | None = None
        # フォルダ切り替えや連続した再生/停止で、古いスレッドからの
        # 更新が新しい再生に紛れ込まないようにするための世代カウンタ。
        self._generation = 0

    def is_playing(self) -> bool:
        """実際に再生(映像が進行)している状態かどうか。
        一時停止中は False になる。
        """
        return self._proc is not None and self._proc.poll() is None and not self._paused

    def is_paused(self) -> bool:
        return self._paused and self._proc is not None and self._proc.poll() is None

    def _set_play_icon_visible(self, visible: bool) -> None:
        if self._play_icon is not None:
            self._play_icon.set_visible(visible)

    def play(self, path: str, view_width: int, view_height: int) -> None:
        """指定した動画の再生を開始する(すでに再生中なら止めてから)。"""
        self.stop()

        if _FFMPEG_PATH is None:
            return

        self._stop_event.clear()
        self._generation += 1
        generation = self._generation

        src_size = _probe_dimensions(path)
        rotation = _probe_rotation(path)

        # ffmpeg は動画の回転メタデータをすでに自動で反映して復号する
        # (=自前で transpose フィルタを掛ける必要はない)。ただし
        # ffprobe の width/height は「回転前の生データのサイズ」の
        # ままなので、表示サイズの計算(アスペクト比の判定)だけは
        # 90度/270度回転の場合に幅と高さを入れ替える必要がある。
        needs_swap = rotation in (90, 270)

        if needs_swap and src_size:
            fit_src_size = (src_size[1], src_size[0])
        else:
            fit_src_size = src_size

        width, height = _fit_size(
            fit_src_size[0] if fit_src_size else None,
            fit_src_size[1] if fit_src_size else None,
            view_width,
            view_height,
        )

        fps = _probe_fps(path)
        has_audio = _probe_has_audio(path)

        # 映像はこちら(Python側)へパイプで渡す。
        #
        # ここでは -re(実時間ペースでの読み込み)を付けていない。
        # ffmpegにはできるだけ速くデコードさせ、代わりに読み込んだ
        # フレームを _frame_queue に貯めておいて、_pump_frame() が
        # 一定間隔で1枚ずつ取り出して表示する。動画のキーフレーム等で
        # デコードが一瞬重くなっても、このキューが吸収してくれるので、
        # -re に任せていたときのような「詰まって止まる」感じが出にくい。
        video_cmd = [
            _FFMPEG_PATH,
            "-v",
            "error",
            "-i",
            path,
            # 一部の動画(Googleカメラの「モーションフォト」等)は、
            # 動画ストリームを複数本(本編+短いおまけ映像など)持って
            # いることがある。-map を指定しないと ffmpeg の自動選択に
            # 委ねられ、意図しない方(フレーム数が極端に少ない方など)が
            # 選ばれることがあるため、常に「最初の動画ストリーム」を
            # 明示的に指定する。
            "-map",
            "0:v:0",
            "-an",
            "-vf",
            f"scale={width}:{height}",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgb24",
            "pipe:1",
        ]

        try:
            self._proc = subprocess.Popen(
                video_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
            )
        except OSError as e:
            print(f"[videoplayer] ffmpeg(再生・映像)の起動に失敗しました: {e}")
            self._proc = None
            return

        self._audio_proc = None
        self._audio_sync_pending = False
        self._audio_sync_generation = None

        if has_audio:
            # 音声は、映像とは別の ffmpeg プロセスとしてPulseAudioへ
            # 直接出す。映像フレームは1枚1MBを超えることもあり、
            # こちら側の読み込みが少しでも追いつかないと ffmpeg 内部の
            # パイプ書き込みがブロックされる。もし映像と音声を同じ
            # プロセスの中で扱っていると、そのブロックにつられて
            # 音声まで一緒に途切れてしまう(実際に発生した)。
            # プロセスを分けることで、映像側が多少詰まっても音声には
            # 影響しないようにしている。厳密なフレーム単位の同期は
            # 無くなるが、体感上の途切れを防ぐことを優先している。
            #
            # ここで音声プロセスをすぐに起動し、直後に SIGSTOP で
            # 凍結する。プロセスの起動やPulseAudioへの接続といった
            # 「時間がかかる部分」は、この凍結している間(=映像の
            # 最初の1コマが表示されるまでの間)に済ませてしまう。
            # 映像の最初の1コマが実際に画面に表示された瞬間
            # (_show_frame)に SIGCONT で解凍することで、
            # 「解凍→実際に音が鳴るまで」の遅延だけが残ることになり、
            # これはプロセス起動そのものより短く、マシンの速さに
            # よる差も出にくい。
            audio_cmd = [
                _FFMPEG_PATH,
                "-v",
                "error",
            ]

            if AUDIO_FINE_TUNE_SEC != 0.0:
                audio_cmd += ["-itsoffset", str(AUDIO_FINE_TUNE_SEC)]

            audio_cmd += [
                "-re",
                "-i",
                path,
                "-map",
                "0:a:0",
                "-vn",
                "-f",
                "pulse",
                "default",
            ]

            try:
                self._audio_proc = subprocess.Popen(
                    audio_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
                )
                try:
                    self._audio_proc.send_signal(signal.SIGSTOP)
                except OSError:
                    pass
                self._audio_sync_pending = True
                self._audio_sync_generation = generation
            except OSError as e:
                print(f"[videoplayer] ffmpeg(再生・音声)の起動に失敗しました: {e}")
                self._audio_proc = None

        self._set_play_icon_visible(False)

        # キューのサイズは大きくしすぎない(貯めすぎるとメモリを
        # 圧迫するし、一時停止からの再開時などに古いフレームが
        # 溜まったまま出てくると違和感があるため)。数枚分あれば、
        # 短いデコードの引っかかりを吸収するには十分。
        self._frame_queue = queue.Queue(maxsize=6)

        threading.Thread(
            target=self._read_loop,
            args=(self._proc, width, height, generation, self._frame_queue),
            daemon=True,
        ).start()

        frame_interval_ms = max(1, round(1000 / fps)) if fps > 0 else 33
        self._pump_timeout_id = GLib.timeout_add(
            frame_interval_ms, self._pump_frame, generation
        )

    def _pump_frame(self, generation):
        """一定間隔で呼ばれ、キューに溜まったフレームを1枚だけ表示する。

        メインスレッドから GLib.timeout_add 経由で呼ばれる。
        """
        if generation != self._generation:
            self._pump_timeout_id = None
            return False  # このタイマーは役目を終えたので解除する

        if self._frame_queue is not None:
            try:
                data, width, height = self._frame_queue.get_nowait()
                self._show_frame(data, width, height, generation)
            except queue.Empty:
                # まだ次のフレームが来ていない。今回は何もせず、
                # 次のタイミングでまた試す(デコードの一時的な遅れを
                # ここで吸収している)。
                pass

        return True  # タイマーは継続する

    def _read_loop(self, proc, width, height, generation, frame_queue):
        """バックグラウンドスレッドで、ffmpegの標準出力から1フレームずつ
        生の画素データを読み取り、キューに積んでいく。表示のタイミング
        自体は _pump_frame() が別途一定間隔で行う。
        """
        frame_size = width * height * 3
        frame_count = 0

        try:
            while not self._stop_event.is_set() and generation == self._generation:
                data = proc.stdout.read(frame_size)

                if not data or len(data) < frame_size:
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        pass

                    stderr_text = ""

                    if proc.stderr is not None:
                        try:
                            stderr_text = (
                                proc.stderr.read().decode("utf-8", "ignore").strip()
                            )
                        except OSError:
                            pass

                    if stderr_text:
                        print(f"[videoplayer] ffmpeg(再生)のエラー出力: {stderr_text}")

                    break

                frame_count += 1

                # キューが満杯の間はここでブロックする。ブロックしている
                # 間は proc.stdout.read() を呼ばないので、ffmpeg 側の
                # パイプへの書き込みも詰まり、結果としてデコードの
                # 先読みしすぎを自然に抑える形になる。stop() されたか
                # 世代が変わった場合は、待ち続けずに抜けられるように
                # タイムアウト付きでリトライする。
                while not self._stop_event.is_set() and generation == self._generation:
                    try:
                        frame_queue.put((data, width, height), timeout=0.5)
                        break
                    except queue.Full:
                        continue

        finally:
            try:
                proc.stdout.close()
            except OSError:
                pass

            if proc.poll() is None:
                proc.terminate()

            if generation == self._generation:
                # 再生が最後まで終わった(=ユーザーがまだ別の操作をして
                # いない)場合は、再生マークを出し直しておく。
                GLib.idle_add(self._set_play_icon_visible, True)

    def _show_frame(self, data, width, height, generation):
        """メインスレッドで、受け取ったフレームを Gtk.Picture に反映する。"""
        if generation != self._generation:
            # すでに次の動画/画像に切り替わっている場合は捨てる
            return False

        try:
            pixbuf = GdkPixbuf.Pixbuf.new_from_bytes(
                GLib.Bytes.new(data),
                GdkPixbuf.Colorspace.RGB,
                False,
                8,
                width,
                height,
                width * 3,
            )
            texture = Gdk.Texture.new_for_pixbuf(pixbuf)
            # 直前のテクスチャへの参照は set_paintable() の呼び出しで
            # 自然に手放される(明示的な解放は不要)。
            self._picture.set_paintable(texture)
        except GLib.Error:
            pass

        self._release_pending_audio(generation)

        return False  # GLib.idle_add: 一度実行したら解除する

    def _release_pending_audio(self, generation: int) -> None:
        """凍結中の音声プロセスがあれば、ここで SIGCONT して再生を始める。

        「映像の最初の1コマが実際に画面に表示された瞬間」に呼ばれる
        ことを想定している。プロセスの起動やPulseAudioへの接続は
        すでに済んでいるはずなので、ここでの遅延はごくわずかで済み、
        マシンの速さによる差も出にくい。
        """
        if not self._audio_sync_pending:
            return

        if self._audio_sync_generation != generation:
            # すでに次の動画/画像に切り替わっている
            self._audio_sync_pending = False
            self._audio_sync_generation = None
            return

        if self._paused:
            # まだ一時停止中なら、ここでは解凍せず先送りする
            # (再開後、次にフレームが表示されたときに再度試みる)。
            # ここで pending フラグを消してしまうと、二度と解凍
            # されなくなってしまうので消さない。
            return

        self._audio_sync_pending = False
        self._audio_sync_generation = None

        if self._audio_proc is None or self._audio_proc.poll() is not None:
            return

        try:
            self._audio_proc.send_signal(signal.SIGCONT)
        except OSError:
            pass

    def show_preview_frame(self, path: str) -> None:
        """再生はせず、動画の代表フレームを1枚だけ静止画として表示する。

        ユーザーが手動で動画を開いたとき(スライドショー中でないとき)に
        使う。ffmpegを1回だけ動かすだけなので軽く、バックグラウンド
        スレッドで実行してメインスレッドをブロックしない。
        """
        self.stop()

        if _FFMPEG_PATH is None:
            return

        self._generation += 1
        generation = self._generation

        threading.Thread(
            target=self._preview_worker,
            args=(path, generation),
            daemon=True,
        ).start()

    def _preview_worker(self, path, generation):
        png_bytes = self._run_ffmpeg_still(path, seek_seconds=1)

        if png_bytes is None:
            # 1秒でシークできない(動画が短い等)場合は先頭から取り直す
            png_bytes = self._run_ffmpeg_still(path, seek_seconds=0)

        if png_bytes is None:
            return

        GLib.idle_add(self._show_preview_png, png_bytes, generation)

    @staticmethod
    def _run_ffmpeg_still(path, seek_seconds):
        # ffmpeg は動画の回転メタデータをすでに自動で反映して復号する
        # ため、ここで自前の回転フィルタを掛ける必要はない。
        cmd = [
            _FFMPEG_PATH,
            "-v",
            "error",
            "-ss",
            str(seek_seconds),
            "-i",
            path,
            "-map",
            "0:v:0",
            "-frames:v",
            "1",
            "-f",
            "image2pipe",
            "-vcodec",
            "png",
            "-",
        ]

        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=10,
            )
        except (subprocess.TimeoutExpired, OSError):
            return None

        if result.returncode != 0 or not result.stdout:
            return None

        return result.stdout

    def _show_preview_png(self, png_bytes, generation):
        if generation != self._generation:
            return False

        try:
            loader = GdkPixbuf.PixbufLoader()
            loader.write(png_bytes)
            loader.close()
            pixbuf = loader.get_pixbuf()

            if pixbuf is not None:
                texture = Gdk.Texture.new_for_pixbuf(pixbuf)
                self._picture.set_paintable(texture)

        except GLib.Error:
            pass

        return False  # GLib.idle_add: 一度実行したら解除する

    def _signal_all(self, sig) -> None:
        """映像・音声、両方のプロセスに同じシグナルを送る。

        音声プロセスが存在しない(音声トラックが無い)場合や、すでに
        終了している場合は無視する。
        """
        for proc in (self._proc, self._audio_proc):
            if proc is not None and proc.poll() is None:
                try:
                    proc.send_signal(sig)
                except OSError:
                    pass

    def pause(self) -> None:
        """再生中の動画を一時停止する(SIGSTOPでffmpegプロセスごと凍結する)。

        位置を自前で覚えておく必要がないシンプルな方法。読み込み中の
        バックグラウンドスレッドは、データが来なくなるだけで自然に
        待機状態になる。映像・音声のプロセスを両方同時に止める。
        """
        if self._proc is None or self._proc.poll() is not None:
            return

        if self._paused:
            return

        try:
            self._proc.send_signal(signal.SIGSTOP)
        except OSError:
            return

        if self._audio_proc is not None and self._audio_proc.poll() is None:
            try:
                self._audio_proc.send_signal(signal.SIGSTOP)
            except OSError:
                pass

        self._paused = True
        self._set_play_icon_visible(True)

    def resume(self) -> None:
        """一時停止中の動画を再開する(SIGCONTでffmpegプロセスを再開する)。"""
        if self._proc is None or self._proc.poll() is not None:
            return

        if not self._paused:
            return

        try:
            self._proc.send_signal(signal.SIGCONT)
        except OSError:
            return

        if (
            self._audio_proc is not None
            and self._audio_proc.poll() is None
            and not self._audio_sync_pending
        ):
            # まだ「映像の最初の1コマ待ち」で凍結している音声は、
            # ここでは解凍しない。_release_pending_audio() の役目。
            try:
                self._audio_proc.send_signal(signal.SIGCONT)
            except OSError:
                pass

        self._paused = False
        self._set_play_icon_visible(False)

    def stop(self) -> None:
        """再生を止める。ウィジェットの表示はそのまま(最後のフレームが残る)。"""
        self._stop_event.set()
        self._generation += 1  # 実行中のスレッドからの遅延更新を無効化する

        if self._paused:
            # 一時停止中(SIGSTOPで止めている)のプロセスは、
            # SIGTERMをすぐには処理できないことがあるため、
            # 先に再開させてから終了させる。
            self._signal_all(signal.SIGCONT)

        if self._proc is not None and self._proc.poll() is None:
            self._proc.terminate()

        if self._audio_proc is not None and self._audio_proc.poll() is None:
            self._audio_proc.terminate()

        self._proc = None
        self._audio_proc = None
        self._paused = False
        self._audio_sync_pending = False
        self._audio_sync_generation = None

        if self._pump_timeout_id is not None:
            GLib.source_remove(self._pump_timeout_id)
            self._pump_timeout_id = None

        self._frame_queue = None

        self._set_play_icon_visible(True)
