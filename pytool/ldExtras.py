"""雷电模拟器专线截图（参考 MaaFramework LDPlayerExtras）

加载雷电安装目录的 ldopengl64（D3D 抓屏 dll），经 CreateScreenShotInstance
获取实例 → 虚函数表调用 cap() 直读屏幕（BGR），不经 adb。

- 像素 bottom-up：需 flip(0)（对齐 Maa）
- cap() 返回内部缓冲，下次 cap 会覆盖 → 必须立即复制
- ⚠️ 未实测（作者未安装雷电）：任何报错请连同 logs/innerLog.txt 反馈到
  GitHub issue（https://github.com/qcfei/AFS/issues）
- Windows 专属；dll 缺失 / 初始化失败时 init() 返回 False，调用方剔除该通道
"""
import ctypes
import os

import numpy as np
from cv2 import flip

_AUTO_PATHS = [     # 配置为空时自动探测的安装目录
    r'D:\leidian\LDPlayer9',
    r'C:\Program Files\LDPlayer9',
    r'D:\LDPlayer9',
    r'C:\Program Files\leidian\LDPlayer9',
    r'D:\Program Files\leidian\LDPlayer9',
]
_LD_NAMES = ('ldopengl64', 'ldopengl64.dll')  # 雷电目录内的抓屏库文件名（64 位）


class LDScreencap:
    """雷电专线截图器：加载 ldopengl64 → CreateScreenShotInstance → vtable cap 直读"""

    def __init__(self, path: str = '', index: int = 0):
        self.path = path          # 雷电安装目录（空=自动探测）
        self.index = index        # 多开实例索引（0=第一个实例）
        self._dll = None
        self._handle = None
        self._cap_fn = None       # vtable[1] cap()
        self._rel_fn = None       # vtable[2] release()
        self._w = 0
        self._h = 0
        self._last_err = ''

    # ------------------------------------------------------------------ 初始化

    def init(self) -> bool:
        """加载 dll + 创建实例 + 探测分辨率；任一失败返回 False"""
        dll_path = self._find_dll()
        if not dll_path:
            self._last_err = 'ldopengl64 not found (需配置雷电安装目录 changable.ldPath)'
            return False
        try:
            dll_dir = os.path.dirname(dll_path)
            if hasattr(os, 'add_dll_directory'):
                os.add_dll_directory(dll_dir)
            self._dll = ctypes.CDLL(dll_path)
        except Exception as e:
            self._last_err = f'load ldopengl64 failed: {type(e).__name__}: {e}'
            return False
        try:
            create = self._dll.CreateScreenShotInstance
            create.restype = ctypes.c_void_p
            create.argtypes = [ctypes.c_uint, ctypes.c_uint]
            # playerpid=0：让雷电按实例索引定位（Maa 亦支持显式 pid）
            self._handle = create(self.index, 0)
        except Exception as e:
            self._last_err = f'CreateScreenShotInstance failed: {type(e).__name__}: {e}'
            return False
        if not self._handle:
            self._last_err = f'CreateScreenShotInstance returned null (index={self.index})'
            return False
        try:
            # IScreenShotClass vtable: [0]=~dtor, [1]=cap(), [2]=release()
            vtbl = ctypes.cast(self._handle, ctypes.POINTER(ctypes.c_void_p)).contents
            self._cap_fn = ctypes.cast(vtbl[1], ctypes.CFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p))
            self._rel_fn = ctypes.cast(vtbl[2], ctypes.CFUNCTYPE(None, ctypes.c_void_p))
        except Exception as e:
            self._last_err = f'vtable resolve failed: {type(e).__name__}: {e}'
            return False
        # 探测一次 cap 数据长度 → 推导分辨率（对齐 Maa：分辨率来自设备 wm size，
        # 此处用 cap 返回的帧长校验，避免 wm size 与抓屏尺寸不一致）
        data = self._cap_fn(self._handle)
        if not data:
            self._last_err = 'cap probe returned null'
            return False
        # 尝试从 dll 侧读取？无法直接拿宽高 → 先 cap 一次得字节数，按常见分辨率匹配
        # 简化：由调用方提供分辨率（adb wm size），此处仅记录已就绪
        return True

    def setSize(self, w: int, h: int):
        """设置抓屏分辨率（来自 adb wm size；cap 数据 = w*h*3 字节 BGR）"""
        self._w, self._h = w, h

    def _find_dll(self) -> str:
        """定位 ldopengl64 路径（配置目录或自动探测目录，递归一层找 ldopengl* 文件）"""
        installs = [self.path] if self.path else _AUTO_PATHS
        for install in installs:
            if not os.path.isdir(install):
                continue
            for name in _LD_NAMES:
                p = os.path.join(install, name)
                if os.path.isfile(p):
                    self.path = install
                    return p
            # 递归一层（雷电目录结构各版本不同；受限目录跳过）
            try:
                subs = os.listdir(install)
            except OSError:
                continue
            for sub in subs:
                sub_path = os.path.join(install, sub)
                if os.path.isdir(sub_path):
                    for name in _LD_NAMES:
                        p = os.path.join(sub_path, name)
                        if os.path.isfile(p):
                            self.path = install
                            return p
        return ''

    # ------------------------------------------------------------------ 抓取

    def grab(self) -> np.ndarray:
        """取一帧 BGR（设备原分辨率）；失败返回 None"""
        if not self._cap_fn or not self._handle or self._w <= 0:
            return None
        try:
            data = self._cap_fn(self._handle)
        except Exception as e:
            self._last_err = f'cap failed: {type(e).__name__}: {e}'
            return None
        if not data:
            self._last_err = 'cap returned null'
            return None
        try:
            size = self._w * self._h * 3
            arr = np.ctypeslib.as_array(ctypes.cast(data, ctypes.POINTER(ctypes.c_ubyte)), shape=(size,))
            bgr = arr.reshape(self._h, self._w, 3).copy()  # 立即复制（内部缓冲会被下次 cap 覆盖）
            return flip(bgr, 0)  # 雷电像素 bottom-up（对齐 Maa）
        except Exception as e:
            self._last_err = f'cap data convert failed: {type(e).__name__}: {e}'
            return None

    # ------------------------------------------------------------------ 清理

    def stop(self):
        if self._rel_fn and self._handle:
            try:
                self._rel_fn(self._handle)
            except Exception:
                pass
        self._handle = None
        self._cap_fn = None
        self._rel_fn = None
        self._dll = None

    def lastErr(self) -> str:
        return self._last_err
