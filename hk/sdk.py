# -*- coding: utf-8 -*-
"""海康 HCNetSDK(设备网络 SDK) 的 ctypes 封装。

结构体与常量都对照 SDK 头文件抄写，出处标在注释里：
  HCNetSDK.h   : NET_DVR_USER_LOGIN_INFO / NET_DVR_DEVICEINFO_V30 / _V40 /
                 NET_DVR_PREVIEWINFO / NET_DVR_LOCAL_SDK_PATH /
                 NET_DVR_XML_CONFIG_INPUT / _OUTPUT
  plaympeg4.h  : FRAME_INFO / PlayM4_* 系列函数

SDK 为 64 位版本，DLL 放在程序目录下的 sdk 子目录里。
"""

from __future__ import annotations

import ctypes
import os
from ctypes import (CFUNCTYPE, POINTER, Structure, byref, c_char, c_int, c_long,
                    c_ubyte, c_uint32, c_ushort, c_void_p)

# ---------------------------------------------------------------- 常量
NET_SDK_INIT_CFG_SDK_PATH = 2            # HCNetSDK.h:43918

NET_DVR_GET_PICCFG_V30 = 1002            # HCNetSDK.h:1824
NET_DVR_SET_PICCFG_V30 = 1003            # HCNetSDK.h:1825

# 实时数据回调的数据类型
NET_DVR_SYSHEAD = 1
NET_DVR_STREAMDATA = 2

# 云台命令（HCNetSDK.h:1432-1467）
LIGHT_PWRON = 2
WIPER_PWRON = 3
SET_PRESET = 8
CLEAR_PRESET = 9
ZOOM_IN = 11
ZOOM_OUT = 12
FOCUS_NEAR = 13
FOCUS_FAR = 14
IRIS_OPEN = 15
IRIS_CLOSE = 16
TILT_UP = 21
TILT_DOWN = 22
PAN_LEFT = 23
PAN_RIGHT = 24
UP_LEFT = 25
UP_RIGHT = 26
DOWN_LEFT = 27
DOWN_RIGHT = 28
GOTO_PRESET = 39

# 播放库（plaympeg4.h:108-115）
STREAME_REALTIME = 0
T_YV12 = 3

# 常见错误码（HCNetSDK.h:502 起）
_ERROR_TEXT = {
    1: "用户名或密码错误",
    2: "权限不足",
    3: "SDK 未初始化",
    4: "通道号错误",
    5: "资源不足",
    7: "连接设备失败(网络不通 / IP 或端口不对)",
    8: "向设备发送失败",
    9: "从设备接收失败",
    10: "从设备接收数据超时",
    12: "调用次序错误",
    17: "参数错误",
    29: "设备不在线",
    41: "预览通道号错误",
    72: "云台不支持该功能",
    73: "云台协议不支持该功能",
}


def error_text(code):
    return _ERROR_TEXT.get(code, "SDK 错误码 %d" % code)


class HikError(RuntimeError):
    """SDK 调用失败。"""

    def __init__(self, what, code=None):
        self.code = code
        if code is None:
            super(HikError, self).__init__(what)
        else:
            super(HikError, self).__init__("%s：%s(错误码 %d)" % (what, error_text(code), code))


# ---------------------------------------------------------------- 结构体
class NET_DVR_DEVICEINFO_V30(Structure):
    """HCNetSDK.h:10725"""
    _fields_ = [
        ("sSerialNumber", c_ubyte * 48),
        ("byAlarmInPortNum", c_ubyte),
        ("byAlarmOutPortNum", c_ubyte),
        ("byDiskNum", c_ubyte),
        ("byDVRType", c_ubyte),
        ("byChanNum", c_ubyte),
        ("byStartChan", c_ubyte),
        ("byAudioChanNum", c_ubyte),
        ("byIPChanNum", c_ubyte),
        ("byZeroChanNum", c_ubyte),
        ("byMainProto", c_ubyte),
        ("bySubProto", c_ubyte),
        ("bySupport", c_ubyte),
        ("bySupport1", c_ubyte),
        ("bySupport2", c_ubyte),
        ("wDevType", c_ushort),
        ("bySupport3", c_ubyte),
        ("byMultiStreamProto", c_ubyte),
        ("byStartDChan", c_ubyte),
        ("byStartDTalkChan", c_ubyte),
        ("byHighDChanNum", c_ubyte),
        ("bySupport4", c_ubyte),
        ("byLanguageType", c_ubyte),
        ("byVoiceInChanNum", c_ubyte),
        ("byStartVoiceInChanNo", c_ubyte),
        ("bySupport5", c_ubyte),
        ("bySupport6", c_ubyte),
        ("byMirrorChanNum", c_ubyte),
        ("wStartMirrorChanNo", c_ushort),
        ("bySupport7", c_ubyte),
        ("byRes2", c_ubyte),
    ]


class NET_DVR_DEVICEINFO_V40(Structure):
    """HCNetSDK.h:10814"""
    _fields_ = [
        ("struDeviceV30", NET_DVR_DEVICEINFO_V30),
        ("bySupportLock", c_ubyte),
        ("byRetryLoginTime", c_ubyte),
        ("byPasswordLevel", c_ubyte),
        ("byProxyType", c_ubyte),
        ("dwSurplusLockTime", c_uint32),
        ("byCharEncodeType", c_ubyte),
        ("bySupportDev5", c_ubyte),
        ("byRes2", c_ubyte * 254),
    ]


class NET_DVR_USER_LOGIN_INFO(Structure):
    """HCNetSDK.h:10827"""
    _fields_ = [
        ("sDeviceAddress", c_char * 129),
        ("byUseTransport", c_ubyte),
        ("wPort", c_ushort),
        ("sUserName", c_char * 64),
        ("sPassword", c_char * 64),
        ("cbLoginResult", c_void_p),
        ("pUser", c_void_p),
        ("bUseAsynLogin", c_int),
        ("byProxyType", c_ubyte),
        ("byUseUTCTime", c_ubyte),
        ("byRes2", c_ubyte * 2),
        ("iProxyID", c_long),
        ("byRes3", c_ubyte * 120),
    ]


class NET_DVR_PREVIEWINFO(Structure):
    """HCNetSDK.h:24620"""
    _fields_ = [
        ("lChannel", c_long),
        ("dwStreamType", c_uint32),
        ("dwLinkMode", c_uint32),
        ("hPlayWnd", c_void_p),
        ("bBlocked", c_uint32),
        ("bPassbackRecord", c_uint32),
        ("byPreviewMode", c_ubyte),
        ("byStreamID", c_ubyte * 32),
        ("byProtoType", c_ubyte),
        ("byRes1", c_ubyte),
        ("byVideoCodingType", c_ubyte),
        ("dwDisplayBufNum", c_uint32),
        ("byRes", c_ubyte * 216),
    ]


class NET_DVR_LOCAL_SDK_PATH(Structure):
    """HCNetSDK.h:43943"""
    _fields_ = [
        ("sPath", c_char * 256),
        ("byRes", c_ubyte * 128),
    ]


class NET_DVR_XML_CONFIG_INPUT(Structure):
    """HCNetSDK.h:36243"""
    _fields_ = [
        ("dwSize", c_uint32),
        ("lpRequestUrl", c_void_p),
        ("dwRequestUrlLen", c_uint32),
        ("lpInBuffer", c_void_p),
        ("dwInBufferSize", c_uint32),
        ("dwRecvTimeOut", c_uint32),
        ("byForceEncrpt", c_ubyte),
        ("byRes", c_ubyte * 31),
    ]


class NET_DVR_XML_CONFIG_OUTPUT(Structure):
    """HCNetSDK.h:36255"""
    _fields_ = [
        ("dwSize", c_uint32),
        ("lpOutBuffer", c_void_p),
        ("dwOutBufferSize", c_uint32),
        ("dwReturnedXMLSize", c_uint32),
        ("lpStatusBuffer", c_void_p),
        ("dwStatusSize", c_uint32),
        ("byRes", c_ubyte * 32),
    ]


class FRAME_INFO(Structure):
    """plaympeg4.h:190"""
    _fields_ = [
        ("nWidth", c_long),
        ("nHeight", c_long),
        ("nStamp", c_long),
        ("nType", c_long),
        ("nFrameRate", c_long),
        ("dwFrameNum", c_uint32),
    ]


# BOOL(__stdcall)(LONG, DWORD, BYTE*, DWORD, void*)  —— 实时流数据回调
REALDATACALLBACK = CFUNCTYPE(c_int, c_long, c_uint32, c_void_p, c_uint32, c_void_p)
# void(CALLBACK)(long, char*, long, FRAME_INFO*, long, long) —— 解码回调(Mend 版)
DECCBFUN = CFUNCTYPE(None, c_long, c_void_p, c_long, POINTER(FRAME_INFO), c_long, c_long)


# ---------------------------------------------------------------- SDK
class HikSdk(object):
    """HCNetSDK 封装：初始化、登录、云台、ISAPI(XML) 配置。"""

    def __init__(self, sdk_dir):
        self.sdk_dir = os.path.abspath(sdk_dir)
        dll_path = os.path.join(self.sdk_dir, "HCNetSDK.dll")
        if not os.path.exists(dll_path):
            raise HikError("找不到 %s，请把海康 SDK 的 DLL 放到 sdk 目录" % dll_path)

        os.environ["PATH"] = self.sdk_dir + os.pathsep + os.environ.get("PATH", "")
        if hasattr(os, "add_dll_directory"):
            os.add_dll_directory(self.sdk_dir)

        self.dll = ctypes.WinDLL(dll_path)
        self.play = ctypes.WinDLL(os.path.join(self.sdk_dir, "PlayCtrl.dll"))
        self._bind()

        path = NET_DVR_LOCAL_SDK_PATH()
        path.sPath = self.sdk_dir.encode("gbk")
        if not self.dll.NET_DVR_SetSDKInitCfg(NET_SDK_INIT_CFG_SDK_PATH, byref(path)):
            raise HikError("NET_DVR_SetSDKInitCfg 失败", self.last_error)

        if not self.dll.NET_DVR_Init():
            raise HikError("NET_DVR_Init 失败", self.last_error)
        self.dll.NET_DVR_SetConnectTime(3000, 1)
        self.dll.NET_DVR_SetReconnect(10000, True)
        self._inited = True
        self._uid = -1
        self.serial = ""
        self.dev_type = 0
        self.ip_channels = 0
        self.analog_channels = 0
        self.start_channel = 1

    def _bind(self):
        d = self.dll
        d.NET_DVR_Init.restype = c_int
        d.NET_DVR_SetSDKInitCfg.restype = c_int
        d.NET_DVR_SetSDKInitCfg.argtypes = [c_int, c_void_p]
        d.NET_DVR_GetLastError.restype = c_uint32
        d.NET_DVR_SetConnectTime.restype = c_int
        d.NET_DVR_SetConnectTime.argtypes = [c_uint32, c_uint32]
        d.NET_DVR_SetReconnect.restype = c_int
        d.NET_DVR_SetReconnect.argtypes = [c_uint32, c_int]

        d.NET_DVR_Login_V40.restype = c_long
        d.NET_DVR_Login_V40.argtypes = [POINTER(NET_DVR_USER_LOGIN_INFO),
                                        POINTER(NET_DVR_DEVICEINFO_V40)]
        d.NET_DVR_Logout.restype = c_int
        d.NET_DVR_Logout.argtypes = [c_long]

        d.NET_DVR_RealPlay_V40.restype = c_long
        d.NET_DVR_RealPlay_V40.argtypes = [c_long, POINTER(NET_DVR_PREVIEWINFO),
                                           REALDATACALLBACK, c_void_p]
        d.NET_DVR_StopRealPlay.restype = c_int
        d.NET_DVR_StopRealPlay.argtypes = [c_long]

        d.NET_DVR_PTZControlWithSpeed_Other.restype = c_int
        d.NET_DVR_PTZControlWithSpeed_Other.argtypes = [c_long, c_long, c_uint32,
                                                        c_uint32, c_uint32]
        d.NET_DVR_PTZPreset_Other.restype = c_int
        d.NET_DVR_PTZPreset_Other.argtypes = [c_long, c_long, c_uint32, c_uint32]

        d.NET_DVR_GetDVRConfig.restype = c_int
        d.NET_DVR_GetDVRConfig.argtypes = [c_long, c_uint32, c_long, c_void_p,
                                           c_uint32, POINTER(c_uint32)]
        d.NET_DVR_SetDVRConfig.restype = c_int
        d.NET_DVR_SetDVRConfig.argtypes = [c_long, c_uint32, c_long, c_void_p, c_uint32]

        d.NET_DVR_STDXMLConfig.restype = c_int
        d.NET_DVR_STDXMLConfig.argtypes = [c_long, POINTER(NET_DVR_XML_CONFIG_INPUT),
                                           POINTER(NET_DVR_XML_CONFIG_OUTPUT)]

        p = self.play
        p.PlayM4_GetPort.restype = c_int
        p.PlayM4_GetPort.argtypes = [POINTER(c_long)]
        p.PlayM4_FreePort.restype = c_int
        p.PlayM4_FreePort.argtypes = [c_long]
        p.PlayM4_SetStreamOpenMode.restype = c_int
        p.PlayM4_SetStreamOpenMode.argtypes = [c_long, c_uint32]
        p.PlayM4_OpenStream.restype = c_int
        p.PlayM4_OpenStream.argtypes = [c_long, c_void_p, c_uint32, c_uint32]
        p.PlayM4_CloseStream.restype = c_int
        p.PlayM4_CloseStream.argtypes = [c_long]
        p.PlayM4_SetDecCallBackMend.restype = c_int
        p.PlayM4_SetDecCallBackMend.argtypes = [c_long, DECCBFUN, c_long]
        p.PlayM4_InputData.restype = c_int
        p.PlayM4_InputData.argtypes = [c_long, c_void_p, c_uint32]
        p.PlayM4_Play.restype = c_int
        p.PlayM4_Play.argtypes = [c_long, c_void_p]
        p.PlayM4_Stop.restype = c_int
        p.PlayM4_Stop.argtypes = [c_long]

    @property
    def last_error(self):
        return self.dll.NET_DVR_GetLastError()

    @property
    def user_id(self):
        return self._uid

    def cleanup(self):
        if getattr(self, "_inited", False):
            self.dll.NET_DVR_Cleanup()
            self._inited = False

    # ------------------------------------------------------------ 登录
    def login(self, ip, port, user, password):
        info = NET_DVR_USER_LOGIN_INFO()
        info.sDeviceAddress = ip.encode("utf-8")
        info.wPort = port
        info.sUserName = user.encode("utf-8")
        info.sPassword = password.encode("utf-8")
        info.bUseAsynLogin = 0
        dev = NET_DVR_DEVICEINFO_V40()
        uid = self.dll.NET_DVR_Login_V40(byref(info), byref(dev))
        if uid < 0:
            raise HikError("登录 %s 失败" % ip, self.last_error)
        v30 = dev.struDeviceV30
        raw = bytes(bytearray(v30.sSerialNumber))
        self.serial = raw.split(b"\x00")[0].decode("ascii", "ignore")
        self.dev_type = v30.wDevType
        self.ip_channels = v30.byIPChanNum + v30.byHighDChanNum * 256
        self.analog_channels = v30.byChanNum
        self.start_channel = v30.byStartChan or 1
        self._uid = uid
        return uid

    def logout(self):
        if self._uid >= 0:
            self.dll.NET_DVR_Logout(self._uid)
            self._uid = -1

    # ------------------------------------------------------------ 云台
    def ptz(self, channel, command, speed=4, stop=False):
        ok = self.dll.NET_DVR_PTZControlWithSpeed_Other(
            self.user_id, channel, command, 1 if stop else 0, max(1, min(7, speed)))
        if not ok:
            raise HikError("云台控制失败", self.last_error)

    def ptz_preset(self, channel, command, index):
        ok = self.dll.NET_DVR_PTZPreset_Other(self.user_id, channel, command, index)
        if not ok:
            raise HikError("预置点操作失败", self.last_error)

    # ------------------------------------------------------------ ISAPI over SDK
    def isapi(self, url, method="GET", body=None, timeout_ms=8000):
        """通过私有协议通道发 ISAPI 请求，返回 (XML, 状态 XML)。

        注意：请求行必须带方法前缀，实测 "GET /ISAPI/System/deviceInfo" 返回 OK，
        只写 "/ISAPI/System/deviceInfo" 会返回错误码 17（参数错误）。
        """
        url_bytes = ("%s %s" % (method, url)).encode("utf-8")
        url_buf = ctypes.create_string_buffer(url_bytes, len(url_bytes) + 1)
        in_buf = None
        body_bytes = b""
        if body is not None:
            body_bytes = body.encode("utf-8")
            in_buf = ctypes.create_string_buffer(body_bytes, len(body_bytes) + 1)

        inp = NET_DVR_XML_CONFIG_INPUT()
        inp.dwSize = ctypes.sizeof(NET_DVR_XML_CONFIG_INPUT)
        inp.lpRequestUrl = ctypes.cast(url_buf, c_void_p)
        inp.dwRequestUrlLen = len(url_bytes)
        inp.lpInBuffer = ctypes.cast(in_buf, c_void_p) if in_buf else None
        inp.dwInBufferSize = len(body_bytes)
        inp.dwRecvTimeOut = timeout_ms

        out_size = 256 * 1024
        out_buf = ctypes.create_string_buffer(out_size)
        st_size = 64 * 1024
        st_buf = ctypes.create_string_buffer(st_size)

        out = NET_DVR_XML_CONFIG_OUTPUT()
        out.dwSize = ctypes.sizeof(NET_DVR_XML_CONFIG_OUTPUT)
        out.lpOutBuffer = ctypes.cast(out_buf, c_void_p)
        out.dwOutBufferSize = out_size
        out.lpStatusBuffer = ctypes.cast(st_buf, c_void_p)
        out.dwStatusSize = st_size

        ok = self.dll.NET_DVR_STDXMLConfig(self.user_id, byref(inp), byref(out))
        xml = out_buf.raw[:out.dwReturnedXMLSize].decode("utf-8", "ignore")
        status = st_buf.raw[:out.dwStatusSize].decode("utf-8", "ignore")
        if not ok:
            raise HikError("ISAPI %s 失败" % url, self.last_error)
        return xml, status

    # ------------------------------------------------------------ 图像参数(结构体)
    def get_pic_cfg(self, channel):
        size = 64 * 1024
        buf = ctypes.create_string_buffer(size)
        ctypes.c_uint32.from_buffer(buf).value = size
        got = c_uint32(0)
        ok = self.dll.NET_DVR_GetDVRConfig(self.user_id, NET_DVR_GET_PICCFG_V30, channel,
                                           buf, size, byref(got))
        if not ok:
            raise HikError("读取图像参数失败", self.last_error)
        return buf.raw[:got.value]

    def set_pic_cfg(self, channel, raw):
        buf = ctypes.create_string_buffer(raw, len(raw))
        ok = self.dll.NET_DVR_SetDVRConfig(self.user_id, NET_DVR_SET_PICCFG_V30, channel,
                                           buf, len(raw))
        if not ok:
            raise HikError("设置图像参数失败", self.last_error)