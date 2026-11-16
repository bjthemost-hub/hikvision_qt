# -*- coding: utf-8 -*-
"""图像参数：走 SDK 的 ISAPI 通道(NET_DVR_STDXMLConfig)，按资源逐个读写。

实测(DS-2CD3T56FWDV2-I3 / V5.5.125)：
  GET  /ISAPI/Image/channels/1/color        -> <Color><brightnessLevel>50</...>
  PUT  同样的 XML(改数值)                    -> statusCode 1，再 GET 读回已生效
"""

from __future__ import annotations

import re

from .sdk import HikError


class ImageParams(object):
    RES_COLOR = "color"
    RES_SHARP = "Sharpness"
    RES_IR = "IrcutFilter"
    RES_WDR = "WDR"
    RES_BLC = "BLC"
    RES_HLC = "HLC"

    def __init__(self, api, channel=1):
        self.api = api
        self.channel = channel

    def url(self, res):
        return "/ISAPI/Image/channels/%d/%s" % (self.channel, res)

    def get(self, res):
        xml, _ = self.api.isapi(self.url(res))
        return xml

    def tag(self, res, tag):
        xml = self.get(res)
        m = re.search(r"<%s>\s*(.*?)\s*</%s>" % (re.escape(tag), re.escape(tag)), xml, re.S)
        return m.group(1) if m else None

    def set_tag(self, res, tag, value):
        xml = self.get(res)
        pattern = r"<%s>.*?</%s>" % (re.escape(tag), re.escape(tag))
        new = re.sub(pattern, "<%s>%s</%s>" % (tag, value, tag), xml, count=1, flags=re.S)
        if new == xml:
            raise HikError("设备返回的 %s 里没有 %s 字段，改不了" % (res, tag))
        self.api.isapi(self.url(res), method="PUT", body=new)

    # ---- 组合接口 ----
    def read_all(self):
        out = {}
        try:
            for key, tag in (("brightness", "brightnessLevel"),
                             ("contrast", "contrastLevel"),
                             ("saturation", "saturationLevel")):
                v = self.tag(self.RES_COLOR, tag)
                if v is not None:
                    out[key] = int(float(v))
        except HikError:
            pass
        try:
            v = self.tag(self.RES_SHARP, "SharpnessLevel")
            if v is not None:
                out["sharpness"] = int(float(v))
        except HikError:
            pass
        try:
            v = self.tag(self.RES_IR, "IrcutFilterType")
            if v:
                out["ircut"] = v
        except HikError:
            pass
        try:
            v = self.tag(self.RES_WDR, "mode")
            if v:
                out["wdr"] = v
            lv = self.tag(self.RES_WDR, "WDRLevel")
            if lv is not None:
                out["wdr_level"] = int(float(lv))
        except HikError:
            pass
        try:
            v = self.tag(self.RES_BLC, "enabled")
            if v:
                out["blc"] = v.lower() == "true"
        except HikError:
            pass
        try:
            v = self.tag(self.RES_HLC, "enabled")
            if v:
                out["hlc"] = v.lower() == "true"
        except HikError:
            pass
        return out