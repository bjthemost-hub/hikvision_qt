# -*- coding: utf-8 -*-
"""录像：把解码出来的 BGR 帧写成本地 MP4(OpenCV VideoWriter)。"""

from __future__ import annotations

import ctypes
import os
import queue
import struct
import time
import threading

import cv2


class Recorder(object):
    """独立线程写盘，主线程只负责 push，队列满就丢帧，不拖慢预览。"""

    def __init__(self, path, fps=25.0):
        self.path = path
        self.requested_fps = float(fps)
        self.fps = float(fps)
        self._q = queue.Queue(maxsize=90)
        self._stop = threading.Event()
        self._thread = None
        self._writer = None
        self._size = None
        self._fourcc = None
        self._timer = False
        self._t_first = 0.0
        self._t_last = 0.0
        self.written = 0
        self.dropped = 0
        self.error = None

    # ---- 2026-11-16 之前的老做法（保留不删，仅停用） ----
    # 老代码来一帧写一帧；编码跟不上取流时，成片时长会明显短于真实时长
    # （195 上实测 4 s 录成 2.12 s）。现在按墙钟挑帧，并在收尾时校正帧率。
    #
    # def _run(self):
    #     while not self._stop.is_set() or not self._q.empty():
    #         try:
    #             frame = self._q.get(timeout=0.2)
    #         except queue.Empty:
    #             continue
    #         try:
    #             self._writer.write(frame)
    #             self.written += 1
    #         except Exception as exc:                  # 写盘异常不致宕，记下来
    #             self.error = str(exc)
    #             break
    #     try:
    #         self._writer.release()
    #     except Exception:
    #         pass

    def start(self, width, height, sample=None):
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        self._fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        self._size = (int(width), int(height))
        if sample is not None:
            self._size = (int(sample.shape[1]), int(sample.shape[0]))
        self._writer = cv2.VideoWriter(self.path, self._fourcc, self.fps, self._size)
        if not self._writer.isOpened():
            raise RuntimeError("无法创建录像文件：%s" % self.path)
        # 2026-11-16 起把系统定时精度提到 1 ms：默认 15.6 ms 的 sleep 粒度会让
        # 每帧白等一格，实际写盘帧率只有目标的一半（195 上实测目标 16 fps 只写到 8.6 fps）
        try:
            ctypes.windll.winmm.timeBeginPeriod(1)
            self._timer = True
        except Exception:
            self._timer = False
        self._thread = threading.Thread(target=self._run, name="hik-recorder", daemon=True)
        self._thread.start()

    def push(self, frame):
        if self._stop.is_set():
            return
        try:
            self._q.put_nowait(frame)
        except queue.Full:
            self.dropped += 1

    def _run(self):
        """按墙钟节拍写盘：每 1/fps 秒写一帧当前最新的画面。

        取流比编码快就丢掉中间帧，取流比编码慢就重复上一帧，画面始终跟着真实时间走。
        """
        interval = 1.0 / self.fps if self.fps > 0 else 0.04
        next_t = time.time() + interval
        last = None
        while not self._stop.is_set() or not self._q.empty():
            try:
                frame = self._q.get(timeout=max(0.001, next_t - time.time()))
                while True:                       # 攒着的旧帧只留最新的那一个
                    try:
                        frame = self._q.get_nowait()
                    except queue.Empty:
                        break
            except queue.Empty:
                frame = None
            if frame is None:
                frame = last                       # 没有新帧就重复上一帧，保证时长
            if frame is None:
                continue
            delay = next_t - time.time()
            while delay > 0.0015:                  # 细睡 + 末段自旋，避免 sleep 粒度拖慢节拍
                time.sleep(min(delay - 0.001, 0.02))
                delay = next_t - time.time()
            while time.time() < next_t:
                pass
            try:
                self._writer.write(frame)
            except Exception as exc:
                self.error = str(exc)
                break
            now = time.time()
            if not self.written:
                self._t_first = now
            self._t_last = now
            self.written += 1
            last = frame
            next_t += interval
            if next_t < now:                       # 编码落后就别追帧，按墙钟重新对齐
                next_t = now
        try:
            self._writer.release()
        except Exception:
            pass
        if self._timer:
            try:
                ctypes.windll.winmm.timeEndPeriod(1)
            except Exception:
                pass
        self._fix_fps()

    def _fix_fps(self):
        """按"实际写出的帧数 / 实际耗时"校正 MP4 头里的帧率。

        VideoWriter 只能在开文件那一刻定帧率；本机编码跟不上取流时定高了，
        成片就会比真实时间短。这里直接改时间刻度，让时长回到真实值
        （画面本身已经是按墙钟挑的帧，改刻度不会造成跳帧）。
        """
        count = self.written
        span = self._t_last - self._t_first
        if count < 2 or span <= 0:
            return
        fps = (count - 1) / span
        if self.fps > 0 and abs(fps - self.fps) / self.fps < 0.02:
            return
        try:
            with open(self.path, "rb") as fh:
                data = bytearray(fh.read())
        except OSError:
            return

        def find(typ, start=0, end=None):
            end = len(data) if end is None else end
            off = start
            while off + 8 <= end:
                size = struct.unpack_from(">I", data, off)[0]
                name = bytes(data[off + 4:off + 8]).decode("latin1")
                head = 8
                if size == 1:
                    size = struct.unpack_from(">Q", data, off + 8)[0]
                    head = 16
                elif size == 0:
                    size = end - off
                if size < head:
                    return None
                if name == typ:
                    return off, size, head
                if name in ("moov", "trak", "mdia", "minf", "stbl", "edts"):
                    got = find(typ, off + head, off + size)
                    if got:
                        return got
                off += size
            return None

        mdhd = find("mdhd")
        if not mdhd:
            return
        off, _size, head = mdhd
        if data[off + head] != 0:                  # 只处理 version 0
            return
        struct.pack_into(">I", data, off + head + 12, max(1, int(round(fps * 1000))))
        total_ms = int(round(count * 1000.0 / fps))
        mvhd = find("mvhd")
        if mvhd and data[mvhd[0] + mvhd[2]] == 0:
            struct.pack_into(">I", data, mvhd[0] + mvhd[2] + 16, total_ms)
        elst = find("elst")
        if elst:
            entries = struct.unpack_from(">I", data, elst[0] + elst[2] + 4)[0]
            if entries >= 1:
                struct.pack_into(">I", data, elst[0] + elst[2] + 8, total_ms)
        try:
            with open(self.path, "wb") as fh:
                fh.write(bytes(data))
        except OSError:
            return
        self.fps = fps

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=10)
        return self.written, self.dropped