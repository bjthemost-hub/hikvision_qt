# -*- coding: utf-8 -*-
"""海康摄像机控制台 —— 程序入口。

用法：  python main.py
依赖：  PySide6(界面) / opencv-python(解码与录像) / numpy，SDK DLL 放在 sdk 目录。
"""

import ctypes
import os
import sys

APP_DIR = os.path.dirname(os.path.abspath(__file__))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)


def main():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    from PySide6 import QtWidgets
    from hk.ui import MainWindow

    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName("HikvisionQt")
    app.setStyle("Fusion")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()