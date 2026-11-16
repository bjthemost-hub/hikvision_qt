# -*- coding: utf-8 -*-
"""主界面：连接 / 预览 / 云台 / 图像参数 / 录像 / 抓图。"""

from __future__ import annotations

import datetime
import os
import re
import time

import cv2
import numpy as np
from PySide6 import QtCore, QtGui, QtWidgets

from . import sdk as hk
from .image import ImageParams
from .preview import CameraPreview
from .recorder import Recorder


APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SDK_DIR = os.path.join(APP_DIR, "sdk")


def _now_stamp():
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")


class PtzButton(QtWidgets.QToolButton):
    """按住发命令、松开发停止 —— 云台转动必须成对，松手不能还在转。"""

    def __init__(self, text, command, pad):
        super(PtzButton, self).__init__()
        self.command = command
        self.pad = pad
        self.setText(text)
        self.setMinimumSize(56, 44)
        self.setAutoRaise(False)

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self.pad.ptz_start(self.command)
        super(PtzButton, self).mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self.pad.ptz_stop(self.command)
        super(PtzButton, self).mouseReleaseEvent(event)


class PtzPad(QtWidgets.QWidget):
    """九宫格云台盘。"""

    def __init__(self, window):
        super(PtzPad, self).__init__()
        self.window = window
        grid = QtWidgets.QGridLayout(self)
        grid.setSpacing(4)
        layout = [(0, 0, "左上", hk.UP_LEFT), (0, 1, "上", hk.TILT_UP), (0, 2, "右上", hk.UP_RIGHT),
                  (1, 0, "左", hk.PAN_LEFT), (1, 2, "右", hk.PAN_RIGHT),
                  (2, 0, "左下", hk.DOWN_LEFT), (2, 1, "下", hk.TILT_DOWN),
                  (2, 2, "右下", hk.DOWN_RIGHT)]
        for row, col, text, cmd in layout:
            grid.addWidget(PtzButton(text, cmd, self), row, col)
        center = QtWidgets.QPushButton("停")
        center.setMinimumSize(56, 44)
        center.clicked.connect(self.window.ptz_stop_all)
        grid.addWidget(center, 1, 1)

    def ptz_start(self, command):
        self.window.ptz_move(command, stop=False)

    def ptz_stop(self, command):
        self.window.ptz_move(command, stop=True)


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super(MainWindow, self).__init__()
        self.setWindowTitle("海康摄像机控制台 (HCNetSDK)")
        self.resize(1180, 760)

        self.settings = QtCore.QSettings("CodexTools", "HikvisionQt")
        self.api = None
        self.preview = None
        self.params = None
        self.recorder = None
        self._frame = None
        self._last_seq = 0
        self._fps_count = 0
        self._fps_time = time.time()
        self._fps_value = 0.0
        self._loading = False
        self._record_fps = 25.0
        self._connected = False

        self._build_ui()
        self._load_settings()

        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(30)
        self.timer.timeout.connect(self._tick)
        self.timer.start()

    # ------------------------------------------------------------ 界面
    def _build_ui(self):
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        root = QtWidgets.QVBoxLayout(central)

        # 顶部：连接栏
        conn_box = QtWidgets.QGroupBox("设备连接")
        conn = QtWidgets.QHBoxLayout(conn_box)
        self.ip_edit = QtWidgets.QLineEdit("192.168.6.70")
        self.ip_edit.setFixedWidth(130)
        self.port_edit = QtWidgets.QLineEdit("8000")
        self.port_edit.setFixedWidth(60)
        self.user_edit = QtWidgets.QLineEdit("admin")
        self.user_edit.setFixedWidth(90)
        self.pwd_edit = QtWidgets.QLineEdit()
        self.pwd_edit.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
        self.pwd_edit.setFixedWidth(120)
        self.channel_spin = QtWidgets.QSpinBox()
        self.channel_spin.setRange(1, 64)
        self.channel_spin.setFixedWidth(60)
        self.stream_combo = QtWidgets.QComboBox()
        self.stream_combo.addItems(["主码流", "子码流"])
        self.btn_connect = QtWidgets.QPushButton("连接")
        self.btn_connect.clicked.connect(self.toggle_connect)
        self.btn_preview = QtWidgets.QPushButton("停止预览")
        self.btn_preview.clicked.connect(self.toggle_preview)
        self.btn_preview.setEnabled(False)

        for label, w in (("IP", self.ip_edit), ("端口", self.port_edit), ("用户", self.user_edit),
                         ("密码", self.pwd_edit), ("通道", self.channel_spin)):
            conn.addWidget(QtWidgets.QLabel(label))
            conn.addWidget(w)
        conn.addWidget(self.stream_combo)
        conn.addWidget(self.btn_connect)
        conn.addWidget(self.btn_preview)
        conn.addStretch(1)
        self.device_label = QtWidgets.QLabel("未连接")
        self.device_label.setStyleSheet("color:#555")
        conn.addWidget(self.device_label)
        root.addWidget(conn_box)

        # 主体：左视频 右功能页
        splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        self.video = QtWidgets.QLabel("未连接")
        self.video.setMinimumSize(640, 360)
        self.video.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.video.setStyleSheet("background:#111;color:#888;font-size:16px")
        splitter.addWidget(self.video)
        self.tabs = QtWidgets.QTabWidget()
        self.tabs.addTab(self._build_ptz_tab(), "云台")
        self.tabs.addTab(self._build_image_tab(), "图像参数")
        self.tabs.addTab(self._build_record_tab(), "录像")
        splitter.addWidget(self.tabs)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        root.addWidget(splitter, 1)

        self.status = self.statusBar()
        self.lbl_res = QtWidgets.QLabel("--")
        self.lbl_fps = QtWidgets.QLabel("--")
        self.lbl_rec = QtWidgets.QLabel("未录像")
        for w in (self.lbl_res, self.lbl_fps, self.lbl_rec):
            self.status.addPermanentWidget(w)

    def _build_ptz_tab(self):
        w = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(w)

        pad_row = QtWidgets.QHBoxLayout()
        self.ptz_pad = PtzPad(self)
        pad_row.addWidget(self.ptz_pad)
        pad_row.addStretch(1)
        lay.addLayout(pad_row)

        speed_row = QtWidgets.QHBoxLayout()
        speed_row.addWidget(QtWidgets.QLabel("速度"))
        self.speed_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.speed_slider.setRange(1, 7)
        self.speed_slider.setValue(4)
        self.speed_slider.setTickInterval(1)
        self.speed_slider.setTickPosition(QtWidgets.QSlider.TickPosition.TicksBelow)
        speed_row.addWidget(self.speed_slider, 1)
        lay.addLayout(speed_row)

        lens_row = QtWidgets.QHBoxLayout()
        for text, cmd in (("变倍 +", hk.ZOOM_IN), ("变倍 -", hk.ZOOM_OUT),
                          ("聚焦 +", hk.FOCUS_NEAR), ("聚焦 -", hk.FOCUS_FAR),
                          ("光圈 +", hk.IRIS_OPEN), ("光圈 -", hk.IRIS_CLOSE)):
            lens_row.addWidget(PtzButton(text, cmd, self.ptz_pad))
        lay.addLayout(lens_row)

        aux_row = QtWidgets.QHBoxLayout()
        aux_row.addWidget(QtWidgets.QPushButton("灯光", clicked=lambda _=False: self._ptz_once(hk.LIGHT_PWRON)))
        aux_row.addWidget(QtWidgets.QPushButton("雨刷", clicked=lambda _=False: self._ptz_once(hk.WIPER_PWRON)))
        aux_row.addStretch(1)
        lay.addLayout(aux_row)

        preset_box = QtWidgets.QGroupBox("预置点")
        pl = QtWidgets.QHBoxLayout(preset_box)
        pl.addWidget(QtWidgets.QLabel("编号"))
        self.preset_spin = QtWidgets.QSpinBox()
        self.preset_spin.setRange(1, 255)
        pl.addWidget(self.preset_spin)
        pl.addWidget(QtWidgets.QPushButton("设置", clicked=lambda: self._preset(hk.SET_PRESET)))
        pl.addWidget(QtWidgets.QPushButton("调用", clicked=lambda: self._preset(hk.GOTO_PRESET)))
        pl.addWidget(QtWidgets.QPushButton("删除", clicked=lambda: self._preset(hk.CLEAR_PRESET)))
        pl.addStretch(1)
        lay.addWidget(preset_box)
        lay.addStretch(1)
        return w

    def _build_image_tab(self):
        w = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(w)
        form = QtWidgets.QFormLayout()

        self.sliders = {}
        for key, text in (("brightness", "亮度"), ("contrast", "对比度"),
                          ("saturation", "饱和度"), ("sharpness", "锐度")):
            s = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
            s.setRange(0, 100)
            s.setEnabled(False)
            s.sliderReleased.connect(lambda k=key: self._apply_slider(k))
            form.addRow(text, s)
            self.sliders[key] = s

        self.combo_ircut = QtWidgets.QComboBox()
        for v, t in (("auto", "自动"), ("day", "彩色(白天)"), ("night", "黑白(夜间)")):
            self.combo_ircut.addItem(t, v)
        self.combo_wdr = QtWidgets.QComboBox()
        self.combo_wdr.addItem("关闭", "close")
        self.combo_wdr.addItem("开启", "open")
        self.combo_blc = QtWidgets.QComboBox()
        self.combo_blc.addItem("关闭", "false")
        self.combo_blc.addItem("开启", "true")
        self.combo_hlc = QtWidgets.QComboBox()
        self.combo_hlc.addItem("关闭", "false")
        self.combo_hlc.addItem("开启", "true")
        for label, combo in (("日夜模式", self.combo_ircut), ("宽动态", self.combo_wdr),
                             ("背光补偿", self.combo_blc), ("强光抑制", self.combo_hlc)):
            combo.setEnabled(False)
            combo.currentIndexChanged.connect(self._apply_combo)
            form.addRow(label, combo)
        lay.addLayout(form)

        row = QtWidgets.QHBoxLayout()
        self.btn_img_refresh = QtWidgets.QPushButton("读取当前参数", clicked=self.refresh_image_params)
        self.btn_img_refresh.setEnabled(False)
        row.addWidget(self.btn_img_refresh)
        row.addStretch(1)
        lay.addLayout(row)
        hint = QtWidgets.QLabel("滑块松开后立即下发；组合框选中即下发。")
        hint.setStyleSheet("color:#666")
        lay.addWidget(hint)
        lay.addStretch(1)
        return w

    def _build_record_tab(self):
        w = QtWidgets.QWidget()
        lay = QtWidgets.QVBoxLayout(w)
        dir_row = QtWidgets.QHBoxLayout()
        self.dir_edit = QtWidgets.QLineEdit()
        dir_row.addWidget(QtWidgets.QLabel("保存目录"))
        dir_row.addWidget(self.dir_edit, 1)
        dir_row.addWidget(QtWidgets.QPushButton("选择", clicked=self._choose_dir))
        lay.addLayout(dir_row)

        row = QtWidgets.QHBoxLayout()
        self.btn_record = QtWidgets.QPushButton("开始录像")
        self.btn_record.setCheckable(True)
        self.btn_record.clicked.connect(self.toggle_record)
        self.btn_snapshot = QtWidgets.QPushButton("抓图", clicked=self.snapshot)
        row.addWidget(self.btn_record)
        row.addWidget(self.btn_snapshot)
        row.addStretch(1)
        lay.addLayout(row)

        self.record_info = QtWidgets.QLabel("未录像")
        self.record_info.setStyleSheet("color:#555")
        self.record_info.setWordWrap(True)
        lay.addWidget(self.record_info)
        lay.addWidget(QtWidgets.QLabel("提示：录像为重新编码的 MP4(video/mp4v)，"
                                       "帧率取实测的预览帧率。"))
        lay.addStretch(1)
        return w

    # ------------------------------------------------------------ 设置持久化
    def _load_settings(self):
        s = self.settings
        self.ip_edit.setText(s.value("ip", "192.168.6.70"))
        self.port_edit.setText(s.value("port", "8000"))
        self.user_edit.setText(s.value("user", "admin"))
        self.pwd_edit.setText(s.value("pwd", ""))
        default_dir = os.path.join(QtCore.QStandardPaths.writableLocation(
            QtCore.QStandardPaths.StandardLocation.MoviesLocation) or APP_DIR, "HikvisionRec")
        self.dir_edit.setText(s.value("dir", default_dir))

    def _save_settings(self):
        s = self.settings
        s.setValue("ip", self.ip_edit.text().strip())
        s.setValue("port", self.port_edit.text().strip())
        s.setValue("user", self.user_edit.text().strip())
        s.setValue("pwd", self.pwd_edit.text())
        s.setValue("dir", self.dir_edit.text().strip())

    def closeEvent(self, event):
        self._save_settings()
        self.stop_record()
        self.disconnect_all()
        super(MainWindow, self).closeEvent(event)

    # ------------------------------------------------------------ 连接
    def toggle_connect(self):
        if self._connected:
            self.disconnect_all()
        else:
            self.connect_device()

    def connect_device(self):
        ip = self.ip_edit.text().strip()
        try:
            port = int(self.port_edit.text().strip() or "8000")
        except ValueError:
            QtWidgets.QMessageBox.warning(self, "参数错误", "端口必须是数字")
            return
        if not ip:
            return
        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.CursorShape.WaitCursor)
        try:
            if self.api is None:
                self.api = hk.HikSdk(SDK_DIR)
            self.api.login(ip, port, self.user_edit.text().strip(), self.pwd_edit.text())
            self.params = ImageParams(self.api, self.channel_spin.value())
            self._connected = True
            self.btn_connect.setText("断开")
            self.device_label.setText(self._device_summary())
            self.btn_preview.setEnabled(True)
            self.btn_img_refresh.setEnabled(True)
            for s in self.sliders.values():
                s.setEnabled(True)
            for c in (self.combo_ircut, self.combo_wdr, self.combo_blc, self.combo_hlc):
                c.setEnabled(True)
            self.start_preview()
            self.refresh_image_params()
            self.status.showMessage("已登录 %s" % ip, 5000)
        except hk.HikError as exc:
            QtWidgets.QMessageBox.warning(self, "连接失败", str(exc))
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, "错误", str(exc))
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()

    def _device_summary(self):
        info = ""
        try:
            xml, _ = self.api.isapi("/ISAPI/System/deviceInfo")
            model = re.search(r"<model>(.*?)</model>", xml)
            fw = re.search(r"<firmwareVersion>(.*?)</firmwareVersion>", xml)
            info = "%s / %s" % (model.group(1) if model else "?",
                                fw.group(1) if fw else "?")
        except hk.HikError:
            info = "型号未知"
        return "已连接：%s  序列号 %s" % (info, self.api.serial)

    def disconnect_all(self):
        self.stop_record()
        self.stop_preview()
        if self.api is not None:
            try:
                self.api.logout()
            except Exception:
                pass
        self._connected = False
        self.btn_connect.setText("连接")
        self.btn_preview.setEnabled(False)
        self.btn_img_refresh.setEnabled(False)
        for s in self.sliders.values():
            s.setEnabled(False)
        for c in (self.combo_ircut, self.combo_wdr, self.combo_blc, self.combo_hlc):
            c.setEnabled(False)
        self.device_label.setText("未连接")
        self.video.setPixmap(QtGui.QPixmap())
        self.video.setText("未连接")
        self.lbl_res.setText("--")
        self.lbl_fps.setText("--")

    # ------------------------------------------------------------ 预览
    def start_preview(self):
        if not self._connected:
            return
        self.stop_preview()
        channel = self.channel_spin.value()
        stream = self.stream_combo.currentIndex()
        self.preview = CameraPreview(self.api, channel=channel, stream_type=stream)
        self.preview.streamInfo.connect(lambda t: self.status.showMessage(t, 4000))
        self.preview.decodeError.connect(lambda t: self.status.showMessage(t, 6000))
        try:
            self.preview.start()
        except hk.HikError as exc:
            QtWidgets.QMessageBox.warning(self, "取流失败", str(exc))
            self.preview = None
            return
        self.btn_preview.setText("停止预览")

    def stop_preview(self):
        if self.preview is not None:
            try:
                self.preview.stop()
            except Exception:
                pass
            self.preview = None
        self.btn_preview.setText("开始预览")

    def toggle_preview(self):
        if self.preview is None:
            self.start_preview()
        else:
            self.stop_preview()

    def _tick(self):
        if self.preview is None:
            return
        frame, seq = self.preview.latest()
        if frame is None or seq == self._last_seq:
            return
        self._last_seq = seq
        self._frame = frame
        self._fps_count += 1
        now = time.time()
        if now - self._fps_time >= 1.0:
            self._fps_value = self._fps_count / (now - self._fps_time)
            self._fps_count = 0
            self._fps_time = now
            h, w = frame.shape[:2]
            self.lbl_res.setText("%d x %d" % (w, h))
            self.lbl_fps.setText("%.1f fps" % self._fps_value)
        if self.recorder is not None:
            self.recorder.push(frame)
            # 2026-11-16 录像时预览降到约 8 帧/秒，把 CPU 让给编码（预览照样是动的）
            now2 = time.time()
            if now2 - getattr(self, "_prev_show_t", 0.0) < 0.12:
                return
            self._prev_show_t = now2
        self._show_frame(frame)

    def _show_frame(self, frame):
        h, w = frame.shape[:2]
        img = QtGui.QImage(frame.data, w, h, 3 * w, QtGui.QImage.Format.Format_BGR888)
        pix = QtGui.QPixmap.fromImage(img.copy())
        area = self.video.size()
        # 2026-11-16 原实现用平滑缩放，1080p 每帧都要吃掉不少 CPU，改快速缩放
        # self.video.setPixmap(pix.scaled(area, QtCore.Qt.AspectRatioMode.KeepAspectRatio,
        #                                 QtCore.Qt.TransformationMode.SmoothTransformation))
        self.video.setPixmap(pix.scaled(area, QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                                        QtCore.Qt.TransformationMode.FastTransformation))

    # ------------------------------------------------------------ 云台
    def ptz_move(self, command, stop):
        if not self._connected:
            return
        try:
            self.api.ptz(self.channel_spin.value(), command,
                         self.speed_slider.value(), stop)
        except hk.HikError as exc:
            self.status.showMessage(str(exc), 5000)

    def ptz_stop_all(self):
        for cmd in (hk.TILT_UP, hk.TILT_DOWN, hk.PAN_LEFT, hk.PAN_RIGHT,
                    hk.UP_LEFT, hk.UP_RIGHT, hk.DOWN_LEFT, hk.DOWN_RIGHT,
                    hk.ZOOM_IN, hk.ZOOM_OUT, hk.FOCUS_NEAR, hk.FOCUS_FAR,
                    hk.IRIS_OPEN, hk.IRIS_CLOSE):
            self.ptz_move(cmd, True)

    def _ptz_once(self, command):
        if not self._connected:
            return
        try:
            self.api.ptz(self.channel_spin.value(), command, self.speed_slider.value(), False)
            QtCore.QTimer.singleShot(300, lambda: self.ptz_move(command, True))
        except hk.HikError as exc:
            self.status.showMessage(str(exc), 5000)

    def _preset(self, command):
        if not self._connected:
            return
        try:
            self.api.ptz_preset(self.channel_spin.value(), command, self.preset_spin.value())
            self.status.showMessage("预置点 %d 操作完成" % self.preset_spin.value(), 3000)
        except hk.HikError as exc:
            self.status.showMessage(str(exc), 5000)

    # ------------------------------------------------------------ 图像参数
    def refresh_image_params(self):
        if not self._connected:
            return
        self._loading = True
        try:
            values = self.params.read_all()
        except hk.HikError as exc:
            self.status.showMessage(str(exc), 5000)
            return
        finally:
            self._loading = False
        for key, slider in self.sliders.items():
            if key in values:
                slider.setValue(int(values[key]))
        if "ircut" in values:
            idx = self.combo_ircut.findData(values["ircut"])
            if idx >= 0:
                self.combo_ircut.setCurrentIndex(idx)
        if "wdr" in values:
            idx = self.combo_wdr.findData(values["wdr"])
            if idx >= 0:
                self.combo_wdr.setCurrentIndex(idx)
        if "blc" in values:
            self.combo_blc.setCurrentIndex(1 if values["blc"] else 0)
        if "hlc" in values:
            self.combo_hlc.setCurrentIndex(1 if values["hlc"] else 0)

    def _apply_slider(self, key):
        if not self._connected or self._loading:
            return
        value = self.sliders[key].value()
        if key in ("brightness", "contrast", "saturation"):
            tag = {"brightness": "brightnessLevel", "contrast": "contrastLevel",
                   "saturation": "saturationLevel"}[key]
            res = ImageParams.RES_COLOR
        else:
            tag = "SharpnessLevel"
            res = ImageParams.RES_SHARP
        try:
            self.params.set_tag(res, tag, value)
            self.status.showMessage("%s = %d" % (key, value), 2000)
        except hk.HikError as exc:
            self.status.showMessage(str(exc), 6000)

    def _apply_combo(self):
        if not self._connected or self._loading:
            return
        sender = self.sender()
        try:
            if sender is self.combo_ircut:
                self.params.set_tag(ImageParams.RES_IR, "IrcutFilterType",
                                    self.combo_ircut.currentData())
            elif sender is self.combo_wdr:
                self.params.set_tag(ImageParams.RES_WDR, "mode", self.combo_wdr.currentData())
            elif sender is self.combo_blc:
                self.params.set_tag(ImageParams.RES_BLC, "enabled", self.combo_blc.currentData())
            elif sender is self.combo_hlc:
                self.params.set_tag(ImageParams.RES_HLC, "enabled", self.combo_hlc.currentData())
            self.status.showMessage("已下发", 2000)
        except hk.HikError as exc:
            self.status.showMessage(str(exc), 6000)

    # ------------------------------------------------------------ 录像 / 抓图
    def _choose_dir(self):
        d = QtWidgets.QFileDialog.getExistingDirectory(self, "选择保存目录", self.dir_edit.text())
        if d:
            self.dir_edit.setText(d)

    def toggle_record(self):
        if self.recorder is not None:
            self.stop_record()
        else:
            self.start_record()

    def start_record(self):
        if self._frame is None:
            QtWidgets.QMessageBox.information(self, "提示", "还没有视频画面，先连接并预览")
            self.btn_record.setChecked(False)
            return
        out_dir = self.dir_edit.text().strip() or APP_DIR
        name = "CH%d_%s.mp4" % (self.channel_spin.value(), _now_stamp())
        path = os.path.join(out_dir, name)
        fps = self._fps_value if self._fps_value > 5 else 25.0
        h, w = self._frame.shape[:2]
        try:
            rec = Recorder(path, fps=fps)
            # 2026-11-16 原调用保留：直接用预览帧率开录像
            # rec.start(w, h)
            # 起录像前先试编码校准帧率，避免成片时长比实际短一截
            rec.start(w, h, sample=self._frame)
        except Exception as exc:
            QtWidgets.QMessageBox.warning(self, "录像失败", str(exc))
            self.btn_record.setChecked(False)
            return
        self.recorder = rec
        self.btn_record.setText("停止录像")
        self.btn_record.setChecked(True)
        self.lbl_rec.setText("录像中")
        # 2026-11-16 原文本：帧率直接显示预览帧率
        # self.record_info.setText("正在写入：%s\n帧率 %.1f，分辨率 %d x %d" % (path, fps, w, h))
        self.record_info.setText("正在写入：%s\n帧率 自动（按本机编码能力），分辨率 %d x %d" % (path, w, h))

    def stop_record(self):
        if self.recorder is None:
            return
        written, dropped = self.recorder.stop()
        rec_fps = self.recorder.fps            # 收尾时已按实际写盘速度校正
        path = self.recorder.path
        self.recorder = None
        self.btn_record.setText("开始录像")
        self.btn_record.setChecked(False)
        self.lbl_rec.setText("未录像")
        # 2026-11-16 原文本：
        # self.record_info.setText("已保存 %s\n写入 %d 帧，丢弃 %d 帧" % (path, written, dropped))
        self.record_info.setText("已保存 %s\n写入 %d 帧，丢弃 %d 帧，帧率 %.1f" % (path, written, dropped, rec_fps))

    def snapshot(self):
        if self._frame is None:
            return
        out_dir = self.dir_edit.text().strip() or APP_DIR
        os.makedirs(out_dir, exist_ok=True)
        path = os.path.join(out_dir, "CH%d_%s.jpg" % (self.channel_spin.value(), _now_stamp()))
        h, w = self._frame.shape[:2]
        img = QtGui.QImage(self._frame.data, w, h, 3 * w, QtGui.QImage.Format.Format_BGR888)
        if img.copy().save(path, "JPEG", 95):
            self.status.showMessage("抓图已保存：%s" % path, 6000)
        else:
            self.status.showMessage("抓图保存失败：%s" % path, 6000)