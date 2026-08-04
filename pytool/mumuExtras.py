"""mumu 模拟器专线截图（参考 MaaFramework MuMuPlayerExtras）

加载 mumu 安装目录的 external_renderer_ipc.dll（nx_main/sdk/ 或 shell/sdk/），
经 nemu_connect / nemu_capture_display 内存级直读屏幕，不经 adb（最快通道）。

- 只做截图，不做输入（AFS 输入统一走 minitouch）
- 像素为 RGBA 且上下颠倒（bottom-up）：需 cvtColor RGBA→BGR 后 flip(0)（对齐 Maa）
- Windows 专属：dll 缺失 / 连接失败时 init() 返回 False，调用方剔除该通道
"""
import ctypes
import os

import numpy as np
from cv2 import cvtColor, COLOR_RGBA2BGR, flip

_DLL_REL_PATHS = [  # 安装目录下 dll 相对路径（Maa 同款查找顺序）
    os.path.join('nx_main', 'sdk', 'external_renderer_ipc.dll'),
    os.path.join('shell', 'sdk', 'external_renderer_ipc.dll'),
]
_AUTO_PATHS = [     # 配置为空时自动探测的安装目录
    r'D:\mumu\MuMuPlayer',
    r'D:\Program Files\Netease\MuMuPlayer-12.0',
    r'C:\Program Files\Netease\MuMuPlayer-12.0',
    r'D:\Program Files\Netease\MuMuPlayer',
    r'C:\Program Files\Netease\MuMuPlayer',
]


class MuMuScreencap:
    """mumu 专线截图器：加载 dll → 连接实例 → 内存直读屏幕"""

    def __init__(self, path: str = '', index: int = 0):
        self.path = path          # 模拟器安装目录（空=自动探测）
        self.index = index        # 多开实例索引（0=第一个实例）
        self._dll = None
        self._handle = 0
        self._w = 0
        self._h = 0
        self._buf = None          # ctypes 像素缓冲
        self._did = -1            # display id 缓存（-1=未探测；keep-alive 下会话内不变）
        self._last_err = ''

    # ------------------------------------------------------------------ 初始化

    def init(self) -> bool:
        """加载 dll + 连接实例 + 探测宽高；任一失败返回 False"""
        dll_path = self._find_dll()
        if not dll_path:
            self._last_err = 'external_renderer_ipc.dll not found'
            return False
        try:
            dll_dir = os.path.dirname(dll_path)
            if hasattr(os, 'add_dll_directory'):
                os.add_dll_directory(dll_dir)  # 依赖 dll 同在 sdk 目录，帮助加载
            self._dll = ctypes.WinDLL(dll_path)
        except Exception as e:
            self._last_err = f'load dll failed: {type(e).__name__}: {e}'
            return False
        try:
            self._set_protos(self._dll)
            self._handle = self._dll.nemu_connect(self.path, self.index)
        except Exception as e:
            self._last_err = f'connect failed: {type(e).__name__}: {e}'
            return False
        if self._handle <= 0:
            self._last_err = f'nemu_connect returned {self._handle}'
            self._handle = 0
            return False
        if not self._probe_size():
            return False
        return True

    def _find_dll(self) -> str:
        """定位 dll 路径；同时把 self.path 确定为安装目录（nemu_connect 需要）"""
        installs = [self.path] if self.path else _AUTO_PATHS
        for install in installs:
            if not os.path.isdir(install):
                continue
            for rel in _DLL_REL_PATHS:
                p = os.path.join(install, rel)
                if os.path.exists(p):
                    self.path = install
                    return p
        return ''

    def _set_protos(self, dll):
        """按 external_renderer_ipc.h 声明 ctypes 签名"""
        dll.nemu_connect.argtypes = [ctypes.c_wchar_p, ctypes.c_int]
        dll.nemu_connect.restype = ctypes.c_int
        dll.nemu_disconnect.argtypes = [ctypes.c_int]
        dll.nemu_disconnect.restype = None
        dll.nemu_get_display_id.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
        dll.nemu_get_display_id.restype = ctypes.c_int
        dll.nemu_capture_display.argtypes = [ctypes.c_int, ctypes.c_uint, ctypes.c_int,
                                             ctypes.POINTER(ctypes.c_int),
                                             ctypes.POINTER(ctypes.c_int),
                                             ctypes.POINTER(ctypes.c_ubyte)]
        dll.nemu_capture_display.restype = ctypes.c_int

    def _display_id(self) -> int:
        """keep-alive 开启时 display id 随包变化；AFS 不管理应用，用 'default' 探测，失败退回 0

        会话内 display id 不变 → 首次探测后缓存（避免每帧 DLL 跨边界调用）。
        """
        if self._did >= 0:
            return self._did
        try:
            did = self._dll.nemu_get_display_id(self._handle, b'default', 0)
        except Exception:
            did = -1
        self._did = did if did >= 0 else 0
        return self._did

    def _probe_size(self) -> bool:
        """首次 size=0 调用拿宽高（对齐 Maa init_screencap）"""
        w = ctypes.c_int()
        h = ctypes.c_int()
        ret = self._dll.nemu_capture_display(self._handle, self._display_id(), 0,
                                             ctypes.byref(w), ctypes.byref(h), None)
        if ret != 0 or w.value <= 0 or h.value <= 0:
            self._last_err = f'probe size failed ret={ret} w={w.value} h={h.value}'
            return False
        self._w, self._h = w.value, h.value
        self._buf = (ctypes.c_ubyte * (self._w * self._h * 4))()
        return True

    # ------------------------------------------------------------------ 抓取

    def grab(self) -> np.ndarray:
        """取一帧 BGR（设备原分辨率）；失败返回 None"""
        if not self._dll or not self._handle:
            return None
        w = ctypes.c_int(self._w)
        h = ctypes.c_int(self._h)
        size = self._w * self._h * 4
        try:
            ret = self._dll.nemu_capture_display(self._handle, self._display_id(), size,
                                                 ctypes.byref(w), ctypes.byref(h), self._buf)
        except Exception as e:
            self._last_err = f'capture failed: {type(e).__name__}: {e}'
            return None
        if ret != 0:
            self._last_err = f'capture failed ret={ret}'
            return None
        if w.value != self._w or h.value != self._h:
            # 分辨率变化（横竖屏切换等）：重建缓冲再抓一次
            self._w, self._h = w.value, h.value
            self._buf = (ctypes.c_ubyte * (self._w * self._h * 4))()
            try:
                ret = self._dll.nemu_capture_display(self._handle, self._display_id(),
                                                     len(self._buf), ctypes.byref(w),
                                                     ctypes.byref(h), self._buf)
            except Exception:
                return None
            if ret != 0:
                self._last_err = f'capture retry failed ret={ret}'
                return None
        arr = np.frombuffer(self._buf, np.uint8).reshape(self._h, self._w, 4)
        bgr = cvtColor(arr, COLOR_RGBA2BGR)
        return flip(bgr, 0)  # mumu 像素 bottom-up，必须翻转（对齐 Maa）

    # ------------------------------------------------------------------ 清理

    def stop(self):
        if self._dll and self._handle:
            try:
                self._dll.nemu_disconnect(self._handle)
            except Exception:
                pass
            self._handle = 0
        self._dll = None

    def lastErr(self) -> str:
        return self._last_err
