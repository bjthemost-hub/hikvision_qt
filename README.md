# 海康摄像机控制台(HCNetSDK + PySide6)

用海康私有 SDK(HCNetSDK) 连摄像机:实时预览、云台控制、图像参数调整、录像/抓图。

## 功能

- **连接**：IP / 端口(默认 8000) / 用户名 / 密码 / 通道 / 主或子码流
- **预览**：私有协议取流(NET_DVR_RealPlay_V40)，PlayCtrl 解码，Qt 显示，实测 1920x1080 约 24~25 fps
- **云台**：八方向 + 变倍 / 聚焦 / 光圈 + 速度(1~7) + 预置点(设置 / 调用 / 删除) + 灯光 / 雨刷
- **图像参数**：亮度、对比度、饱和度、锐度，日夜模式、宽动态、背光补偿、强光抑制
- **录像**：保存成本地 MP4(H.264 解码后重新编码，video/mp4v)，文件名 `CH<通道>_<年月日_时分秒>.mp4`
- **抓图**：保存 JPEG 到同一目录

## 目录

```
hikvision_qt\
  main.py            程序入口
  run.bat            双击启动(找 pythonw / pyw / python)
  hk\sdk.py          HCNetSDK 的 ctypes 封装(结构体、登录、云台、ISAPI)
  hk\preview.py      取流 + 解码成 BGR 帧
  hk\image.py        图像参数读写(走 SDK 的 ISAPI 通道)
  hk\recorder.py     录像线程(OpenCV VideoWriter)
  hk\ui.py           主界面
  sdk\               HCNetSDK 64 位 DLL + HCNetSDKCom 组件
  requirements.txt   PySide6-Essentials / opencv-python / numpy
```

## 运行

```
pip install -r requirements.txt
python main.py
```

或双击 `run.bat`。

## SDK

`sdk\` 里是海康设备网络 SDK 64 位版本(V5.3.1.22 build20170909)的 DLL 集合，
另补了两个它缺的依赖：`AudioRender.dll`(PlayCtrl 需要)、`msvcr90.dll`(VC2008 运行库)。

若换成新版 SDK，把 `sdk\` 整体替换成新版同名目录即可；`hk/sdk.py` 用到的接口都是老接口，
新旧版本都在(`NET_DVR_Login_V40` / `NET_DVR_RealPlay_V40` / `NET_DVR_PTZControlWithSpeed_Other` /
`NET_DVR_PTZPreset_Other` / `NET_DVR_STDXMLConfig`)。

## 已实测(2026-11-16)

| 设备 | 型号 | 固件 | 结果 |
|---|---|---|---|
| 192.168.6.70 | DS-2CD3T56FWDV2-I3 | V5.5.125 | 登录 / 预览 1920x1080 24~25 fps / 参数读写 / 录像 119 帧/5 秒 / 抓图 全部通过 |
| 192.168.6.71 | DS-2CD3T46DWD-I3 | V5.5.800 | 登录 / 预览 1920x1080 约 24 fps / 参数读取 通过 |

录像文件用 OpenCV 回读核过：119 帧、1920x1080、可正常解码。

## 已知限制与坑

1. **ISAPI 请求行必须带方法前缀**：`"GET /ISAPI/System/deviceInfo"` 能通，
   只写 `"/ISAPI/System/deviceInfo"` 返回错误码 17(参数错误)。`hk/sdk.py: isapi()` 已按此实现。
2. **图像参数不走 `NET_DVR_SET_PICCFG_V30`**：在 DS-2CD3T56FWDV2-I3 上该接口返回成功但读回仍是 0
   (设备不支持老的通道图像结构)。实际生效的是 ISAPI 的 `Image/channels/1/color|Sharpness|...`，
   代码走的就是这条。
3. **云台**：定焦枪机(如上面两台)在 `ImageChannel` 里是 `<PTZ><enabled>false</enabled></PTZ>`，
   调云台接口会返回成功但镜头不动 —— 这是设备不支持，不是程序问题。球机/云台机上才有实际动作。
4. **PlayCtrl 依赖**：只拷 `PlayCtrl.dll` 会加载失败(缺 `AudioRender.dll`、`MSVCR90.dll`)。
5. **录像为重新编码**：帧来自解码后的画面，不是原始码流，清晰度略低于设备直存的录像。
   要无损直存请用设备的 `NET_DVR_SaveRealData`(落 .ps 文件，需 ffmpeg 转 mp4)。

## 常见错误码(程序会直接显示中文)

- 1 用户名或密码错误 / 2 权限不足 / 7 连接设备失败 / 10 接收超时 / 17 参数错误 / 72、73 云台不支持

## 部署到 6.195(2026-11-16)

目标机 `192.168.6.195`(DESKTOP-BFJRENH，Win11，i5-5300U，原本没有 Python)。

- 便携 Python 3.12.10：`C:\Users\zgx390\HikvisionQt\python\`
- 程序本体：`C:\Users\zgx390\HikvisionQt\hikvision_qt\`
- 录像/抓图默认目录：`C:\Users\zgx390\HikvisionQt\rec\`
- 启动：桌面快捷方式「海康监控」，或双击 `C:\Users\zgx390\HikvisionQt\启动海康监控.bat`
  (批处理里写死 `pythonw.exe` 绝对路径，195 的 PATH 里没有 Python)

装过的依赖：numpy 2.3.5、opencv-python 5.0.0.93、PySide6-Essentials 6.12.0(+ shiboken6)，
以及 **VC++ 2015-2022 运行库(vc_redist.x64.exe)** —— 195 原本没装，缺它时 numpy 的
`_multiarray_umath` 会报 "DLL load failed"，光是往 python 目录拷 vcruntime 也不够。

### 录像帧率

`hk/recorder.py` 按墙钟挑帧写盘，收尾时把 MP4 头里的时间刻度改成"实际写出帧数 ÷ 实际耗时"。
所以目标机器编码能力不足时，成片帧率会自己降下来(195 上实测约 22 fps)，但**时长与真实录制时间一致**。
早期版本(直接按预览帧率开文件)在 195 上实测 4 秒录成 2.12 秒，已修掉。
