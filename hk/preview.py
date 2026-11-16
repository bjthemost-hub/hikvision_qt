# -*- coding: utf-8 -*-
"""取流 + 解码：NET_DVR_RealPlay_V40 拉私有流，PlayCtrl 解码成 BGR 帧。"""

from __future__ import annotations

import ctypes
import threading

import numpy as np

from PySide6 import QtCore

from . import sdk as hk


YUV_CODEC = None      # 由视频画面颜色决定：YV12 与 I420 只差 U/V 顺序


class CameraPreview(QtCore.QObject):
    """一路预览。

    数据流向：SDK 回调(线程) -> PlayM4 -> 解码回调(线程) -> 最新帧 -> GUI 定时器取走。
    取帧不阻塞解码，掉帧只影响显示，不影响录像(录像也拿同一份最新帧)。
    """

    error = Signal = None  # 占位，下面用 QtCore.Signal 定义

    frameArrived = QtCore.Signal(int)          # 帧序号
    decodeError = QtCore.Signal(str)
    streamInfo = QtCore.Signal(str)

    def __init__(self, api, channel=1, stream_type=0, parent=None):
        super(CameraPreview, self).__init__(parent)
        self.api = api
        self.channel = channel
        self.stream_type = stream_type
        self._port = ctypes.c_long(-1)
        self._handle = -1
        self._lock = threading.Lock()
        self._frame = None
        self._seq = 0
        self._size = (0, 0)
        self._running = False
        self._got_head = False
        self._cb = hk.REALDATACALLBACK(self._on_real_data)
        self._dec_cb = hk.DECCBFUN(self._on_decoded)
        self._err_count = 0

    # ------------------------------------------------------------ 生命周期
    def start(self):
        if self._running:
            return
        port = ctypes.c_long(-1)
        if not self.api.play.PlayM4_GetPort(ctypes.byref(port)):
            raise hk.HikError("播放库取端口失败", self.api.last_error)
        self._port = port
        self.api.play.PlayM4_SetStreamOpenMode(port, hk.STREAME_REALTIME)
        if not self.api.play.PlayM4_SetDecCallBackMend(port, self._dec_cb, 0):
            raise hk.HikError("设置解码回调失败", self.api.last_error)

        info = hk.NET_DVR_PREVIEWINFO()
        info.lChannel = self.channel
        info.dwStreamType = self.stream_type
        info.dwLinkMode = 0                 # TCP
        info.hPlayWnd = None                # 自己解码，不交给 SDK 画
        info.bBlocked = 0
        info.dwDisplayBufNum = 1
        handle = self.api.dll.NET_DVR_RealPlay_V40(self.api.user_id, ctypes.byref(info),
                                                   self._cb, None)
        if handle < 0:
            self.api.play.PlayM4_FreePort(self._port)
            self._port = ctypes.c_long(-1)
            raise hk.HikError("取流失败", self.api.last_error)
        self._handle = handle
        self._running = True
        self.streamInfo.emit("取流中：通道 %d / %s" % (
            self.channel, "主码流" if self.stream_type == 0 else "子码流"))

    def stop(self):
        if not self._running:
            return
        self._running = False
        try:
            self.api.dll.NET_DVR_StopRealPlay(self._handle)
        except Exception:
            pass
        self._handle = -1
        try:
            self.api.play.PlayM4_Stop(self._port)
            self.api.play.PlayM4_CloseStream(self._port)
            self.api.play.PlayM4_FreePort(self._port)
        except Exception:
            pass
        self._port = ctypes.c_long(-1)
        self._got_head = False
        with self._lock:
            self._frame = None

    # ------------------------------------------------------------ 回调
    def _on_real_data(self, real_handle, data_type, buf, size, user):
        try:
            if not self._running:
                return 0
            if data_type == hk.NET_DVR_SYSHEAD:
                if not self.api.play.PlayM4_OpenStream(self._port, buf, size, 1024 * 1024):
                    raise hk.HikError("OpenStream 失败", self.api.last_error)
                self.api.play.PlayM4_Play(self._port, None)
                self._got_head = True
            elif data_type == hk.NET_DVR_STREAMDATA:
                # 缓冲满时 InputData 返回 0，丢这一包即可(实时流不补)
                self.api.play.PlayM4_InputData(self._port, buf, size)
        except Exception as exc:                     # 回调里绝不能抛出去
            self._err_count += 1
            if self._err_count in (1, 100, 1000):
                self.decodeError.emit("取流回调异常：%s" % exc)
        return 0

    def _on_decoded(self, port, pbuf, size, frame_info, user, reserved):
        try:
            if not self._running or not pbuf or not size:
                return
            fi = frame_info.contents
            if fi.nType != hk.T_YV12:
                return
            w, h = int(fi.nWidth), int(fi.nHeight)
            need = w * h * 3 // 2
            if w <= 0 or h <= 0 or size < need:
                return
            raw = ctypes.string_at(pbuf, need)
            yuv = np.frombuffer(raw, dtype=np.uint8).reshape((h * 3 // 2, w))
            bgr = _yuv_to_bgr(yuv, h)
            with self._lock:
                self._frame = bgr
                self._seq += 1
                if self._size != (w, h):
                    self._size = (w, h)
                    self.streamInfo.emit("画面 %d x %d" % (w, h))
        except Exception as exc:
            self._err_count += 1
            if self._err_count < 5:
                self.decodeError.emit("解码回调异常：%s" % exc)

    # ------------------------------------------------------------ 取帧
    def latest(self):
        with self._lock:
            return self._frame, self._seq

    @property
    def running(self):
        return self._running


def _yuv_to_bgr(yuv, height):
    """YV12 -> BGR。用 OpenCV，避免在 Python 里逐像素算。"""
    import cv2
    global YUV_CODEC
    if YUV_CODEC is None:
        YUV_CODEC = cv2.COLOR_YUV2BGR_YV12
    return cv2.cvtColor(yuv, YUV_CODEC)