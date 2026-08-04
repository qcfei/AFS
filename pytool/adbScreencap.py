"""adb 截图通道（参考 MaaFramework ScreencapAgent 思路）

Maa 的做法：不依赖单一截图方式，注册多个通道（RawWithGzip/Encode/EncodeToFileAndPull/
Minicap...），启动时逐一实测耗时选最快者，运行期失败自动降级。

本模块实现截图通道体系（纯 stateless 为主：无守护进程、无 socket、无虚拟显示，
每帧独立执行，不存在 minicap 式"掉线 lost"问题——失败立即自动降级）：

    Tier0 MuMu     : external_renderer_ipc.dll 内存直读（mumu 模拟器专线，最快）
    Tier0 Netcat   : exec-out "screencap | nc -w 3 设备IP 宿主端口" → raw 经 TCP 直传
    Tier0 Raw      : adb exec-out screencap           → 8B 头 + RGBA 裸数据
    Tier1 RawGzip  : exec-out "screencap | gzip -1"   → gzip 流（设备 gzip 可用时启用）
    Tier2 Encode   : adb exec-out screencap -p        → PNG 字节（imdecode）
    Tier2 Minicap  : minicap -s 单帧模式（每次启动进程拍一帧 JPEG）
    Tier3 Pull     : shell screencap -p + pull        → 原实现，最后兜底

- 启动 init() 对各通道采样 2 次按耗时排序（模拟 Maa speed_test）；Netcat 首帧慢，
  min(2 次采样) 天然覆盖 Maa 的"丢首帧"处理
- 连续失败 >=3 次的通道本会话禁用（模拟 Maa 通道剔除）
- raw 解码（对齐 Maa ScreencapHelper::decode_raw）：前 8 字节为宽高（uint32 LE），
  随后为 RGBA 像素（4B/px），转 BGR；部分设备头部有额外填充字节
- adb 命令带超时 + 进程树杀（对齐 basicFunction._runCmd 防挂起）
- mumu 专线仅 Windows；mumuPath/mumuIndex 读 changable 配置（缺失字段容错跳过）
"""
import os
import platform
import re
import socket
import struct
import subprocess
import time
import zlib

import numpy as np
from cv2 import imdecode, imread, IMREAD_COLOR, cvtColor, COLOR_RGBA2BGR

from pytool.basicFunction import PLATFORM_TOOLS_DIR, settingRead
from pytool.minicapScreen import (_BIN_NAME, displayOrientationGet,
                                  minicapPushBinary, minicapSelectBinary)
from pytool.mumuExtras import MuMuScreencap

_CMD_TIMEOUT = 10.0        # 单条 adb 命令超时（秒）
_DISABLE_THRESHOLD = 3     # 连续失败次数达到该值后禁用该通道（本会话）
_INIT_SAMPLE = 2           # 启动测速采样次数


def _adb(argv: list, timeout: float = _CMD_TIMEOUT) -> bytes:
    """执行 adb 命令，返回 stdout 原始字节；超时杀进程树后返回 b''

    直接 subprocess 二进制管道（不用 shell=True 文本模式），保证 exec-out 字节无损。
    超时处理对齐 basicFunction._runCmd：Popen 对象在 try 前绑定（保证 except 内 pid 可用），
    taskkill /T 杀整棵进程树（shell 子进程残留会持有管道导致收尾卡死）。
    """
    adb = os.path.join(PLATFORM_TOOLS_DIR, 'adb.exe')
    proc = subprocess.Popen([adb] + argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    try:
        out, _ = proc.communicate(timeout=timeout)
        return out or b''
    except subprocess.TimeoutExpired:
        try:
            subprocess.run(['taskkill', '/F', '/T', '/PID', str(proc.pid)],
                           capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
        except Exception:
            pass
        try:
            out, _ = proc.communicate(timeout=5)
            return out or b''
        except Exception:
            return b''


class MinicapDirectScreencap:
    """minicap 单帧模式（-s，对齐 Maa MinicapDirect）：每次启动进程拍一帧 JPEG 退出

    无 socket/无 forward/无守护进程，不存在流式掉线问题；进程启动较慢，
    在 adb 多通道测速排序中自然靠后（聊胜于无的加速兜底层）。
    """

    def __init__(self, ip: str):
        self.ip = ip
        self.arch = ''
        self.sdk = 0
        self._w = 0
        self._h = 0
        self._orient = 0
        self._ready = False
        self._last_err = ''

    def init(self) -> bool:
        """选二进制 + 推送 + 探测 wm size/orientation；任一失败返回 False"""
        arch, sdk = minicapSelectBinary(self.ip)
        if arch is None:
            self._last_err = sdk or 'select minicap failed'
            return False
        if not minicapPushBinary(self.ip, arch, sdk):
            self._last_err = 'push minicap failed'
            return False
        self.arch, self.sdk = arch, sdk
        wm = _adb(['-s', self.ip, 'shell', 'wm size']).decode(errors='ignore')
        nums = re.findall(r'\d+', wm)
        if len(nums) < 2:
            self._last_err = f'wm size parse failed: {wm}'
            return False
        self._w, self._h = int(nums[0]), int(nums[1])
        self._orient = displayOrientationGet(self.ip)
        self._ready = True
        return True

    def grab(self) -> np.ndarray:
        """启动一次 minicap -s 拍单帧 JPEG；失败返回 None"""
        if not self._ready:
            return None
        tmp = '/data/local/tmp'
        cmd = (f'export LD_LIBRARY_PATH={tmp}/; {tmp}/{_BIN_NAME} '
               f'-P {self._w}x{self._h}@{self._w}x{self._h}/{self._orient} -s')
        adb = os.path.join(PLATFORM_TOOLS_DIR, 'adb.exe')
        proc = subprocess.Popen([adb, '-s', self.ip, 'shell', cmd],
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        try:
            data, _ = proc.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            try:
                subprocess.run(['taskkill', '/F', '/T', '/PID', str(proc.pid)],
                               capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
            except Exception:
                pass
            return None
        return imdecode(np.frombuffer(data, np.uint8), IMREAD_COLOR)

    def lastErr(self) -> str:
        return self._last_err


class AdbScreencap:
    """adb 多通道截图器：启动测速排序，运行期失败自动降级"""

    def __init__(self, ip: str, pullPath: str = 'screen.jpeg'):
        self.ip = ip
        self.pullPath = pullPath      # Pull 通道落地文件（由调用方传程序根路径）
        self.gzipOk = False           # 设备端 gzip 是否可用
        self.tiers = []             # [(名称, 抓取函数)]，按启动测速排序
        self._disabled = set()      # 本会话已禁用的通道名
        self._failCount = {}        # 通道名 -> 连续失败次数
        self.frame_count = 0        # 成功帧数（统计）
        self.ms_total = 0.0         # 累计耗时 ms（统计）
        self._last_err = ''
        self._nc_addr = ''          # RawByNetcat 目标地址（ARP 表第一个邻居 IP）
        self.mumu = None            # mumu 专线截图器（仅 Windows，dll 可用时）
        self.minicap = None         # minicap 单帧截图器（二进制就绪时）

    # ------------------------------------------------------------------ 初始化

    def init(self) -> bool:
        """探测各通道可用性 + 测速排序；任一无可用通道即返回 False"""
        # 设备 gzip 探测（toybox 自带，失败仅禁用 gzip 通道）
        out = _adb(['-s', self.ip, 'shell', 'which gzip']).decode(errors='ignore').strip()
        self.gzipOk = 'gzip' in out

        # 新通道就绪探测（各自失败自动剔除，不影响其他通道）
        self._nc_addr = self._netcat_address()
        self.mumu = self._mumu_init()
        self.minicap = self._minicap_init()

        raw_t = self._timeit('Raw')
        gzip_t = self._timeit('RawGzip') if self.gzipOk else None
        png_t = self._timeit('Encode')
        nc_t = self._timeit('Netcat') if self._nc_addr else None
        mumu_t = self._timeit('MuMu') if self.mumu else None
        mcd_t = self._timeit('Minicap') if self.minicap else None

        order = []
        if raw_t is not None:
            order.append(('Raw', self._grab_raw, raw_t))
        if gzip_t is not None:
            order.append(('RawGzip', self._grab_gzip, gzip_t))
        if png_t is not None:
            order.append(('Encode', self._grab_png, png_t))
        if nc_t is not None:
            order.append(('Netcat', self._grab_netcat, nc_t))
        if mumu_t is not None:
            order.append(('MuMu', self._grab_mumu, mumu_t))
        if mcd_t is not None:
            order.append(('Minicap', self._grab_minicap, mcd_t))
        order.append(('Pull', self._grab_pull, 9999.0))  # 兜底通道永远在最后
        order.sort(key=lambda x: x[2])
        self.tiers = [(name, fn) for name, fn, _ in order]
        return len(self.tiers) > 0

    def _netcat_address(self) -> str:
        """探测 RawByNetcat 目标地址：ARP 表第一个邻居 IP（对齐 Maa request_netcat_address）

        模拟器 NAT 下该地址即"设备可达宿主"的网关（如 10.0.2.2），
        设备 nc 直连它 → 宿主 NAT 栈转发到本机监听端口（不经 adb 传输层）。
        """
        out = _adb(['-s', self.ip, 'shell', 'cat /proc/net/arp | grep : ']).decode(errors='ignore')
        for line in out.splitlines():
            parts = line.split()
            if len(parts) >= 1 and re.match(r'^\d+\.\d+\.\d+\.\d+$', parts[0]):
                return parts[0]
        return ''

    def _mumu_init(self):
        """mumu 专线初始化（仅 Windows；配置缺失字段容错）"""
        if platform.system() != 'Windows':
            return None
        try:
            path = settingRead(['changable', 'mumuPath'])
        except Exception:
            path = ''
        try:
            index = settingRead(['changable', 'mumuIndex'])
        except Exception:
            index = 0
        mumu = MuMuScreencap(path, index)
        if mumu.init():
            print(f'mumu extras ready: path={mumu.path} index={mumu.index}')
            return mumu
        print(f'mumu extras unavailable: {mumu.lastErr()}')
        return None

    def _minicap_init(self):
        """minicap 单帧通道初始化（useMinicapDirect 配置开关，默认关闭）

        mumu12 实测 -s 单帧模式输出花屏（minicap 虚拟显示与模拟器渲染不兼容，
        官方本就声明模拟器不支持 minicap），且花屏帧无可靠自动检测 →
        默认禁用，启用需自行验证（与流式 minicap 的保守策略一致）。
        """
        try:
            use = settingRead(['changable', 'useMinicapDirect'])
        except Exception:
            use = False
        if not use:
            print('minicap direct disabled, use adb screencap')
            return None
        mc = MinicapDirectScreencap(self.ip)
        if mc.init():
            return mc
        print(f'minicap direct unavailable: {mc.lastErr()}')
        return None

    def _timeit(self, method: str):
        """单通道采样耗时（ms）；失败返回 None"""
        grab = {'Raw': self._grab_raw, 'RawGzip': self._grab_gzip,
                'Encode': self._grab_png, 'Netcat': self._grab_netcat,
                'MuMu': self._grab_mumu, 'Minicap': self._grab_minicap}[method]
        ts = []
        for _ in range(_INIT_SAMPLE):
            t0 = time.perf_counter()
            img = grab()
            if img is None:
                return None
            ts.append((time.perf_counter() - t0) * 1000)
        return min(ts)

    # ------------------------------------------------------------------ 抓取

    def grab(self) -> np.ndarray:
        """取一帧 BGR（1080×1920 原分辨率）；全部通道失败返回 None"""
        for name, fn in self.tiers:
            if name in self._disabled:
                continue
            t0 = time.perf_counter()
            try:
                img = fn()
            except Exception as e:
                img = None
                self._last_err = f'{name}: {type(e).__name__}: {e}'
            if img is not None:
                self._failCount[name] = 0
                self.frame_count += 1
                self.ms_total += (time.perf_counter() - t0) * 1000
                return img
            self._failCount[name] = self._failCount.get(name, 0) + 1
            if self._failCount[name] >= _DISABLE_THRESHOLD:
                self._disabled.add(name)
                print(f'adb screencap channel disabled: {name}')
        return None

    def _grab_raw(self) -> np.ndarray:
        return self._decode_raw(_adb(['-s', self.ip, 'exec-out', 'screencap']))

    def _grab_gzip(self) -> np.ndarray:
        data = _adb(['-s', self.ip, 'exec-out', 'screencap | gzip -1'])
        try:
            raw = zlib.decompress(data, 16 + zlib.MAX_WBITS)
        except Exception:
            return None
        return self._decode_raw(raw)

    def _grab_png(self) -> np.ndarray:
        data = _adb(['-s', self.ip, 'exec-out', 'screencap -p'])
        return imdecode(np.frombuffer(data, np.uint8), IMREAD_COLOR)

    def _grab_pull(self) -> np.ndarray:
        # 原实现：shell 落盘 + pull（最后兜底，行为与旧版本一致）
        _adb(['-s', self.ip, 'shell', 'screencap -p /sdcard/screenshot.jpeg'])
        _adb(['-s', self.ip, 'pull', '/sdcard/screenshot.jpeg', self.pullPath])
        return imread(self.pullPath)

    def _grab_netcat(self) -> np.ndarray:
        """exec-out "screencap | nc -w 3 {addr} {port}"：设备端 nc 把 raw 经 TCP 直传宿主

        本机临时监听端口 → 设备 nc 连 NAT 网关（ARP 第一个邻居）→ 宿主 NAT 栈转发到
        监听端口。raw 数据不走 adb 传输层（对齐 Maa RawByNetcat：accept 超时 5s，
        收流超时 1s；收尾等 adb 进程退出，超时杀进程树防挂起）。
        """
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.settimeout(5.0)  # nc 连不上时 accept 快速失败，不等 adb 超时
        try:
            srv.bind(('127.0.0.1', 0))
            srv.listen(1)
            port = srv.getsockname()[1]
        except Exception:
            srv.close()
            return None
        adb = os.path.join(PLATFORM_TOOLS_DIR, 'adb.exe')
        proc = subprocess.Popen([adb, '-s', self.ip, 'exec-out',
                                 f'screencap | nc -w 3 {self._nc_addr} {port}'],
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        try:
            conn, _ = srv.accept()
            try:
                conn.settimeout(1.0)  # 对齐 Maa：ios->expires_after(1s)
                data = b''
                try:
                    while True:
                        chunk = conn.recv(65536)
                        if not chunk:
                            break
                        data += chunk
                except socket.timeout:
                    pass  # 1s 无新数据即认为帧已收完
            finally:
                conn.close()
            return self._decode_raw(data)
        except socket.timeout:
            return None
        finally:
            srv.close()
            try:
                proc.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    subprocess.run(['taskkill', '/F', '/T', '/PID', str(proc.pid)],
                                   capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
                except Exception:
                    pass

    def _grab_mumu(self) -> np.ndarray:
        if self.mumu is None:
            return None
        return self.mumu.grab()

    def _grab_minicap(self) -> np.ndarray:
        if self.minicap is None:
            return None
        return self.minicap.grab()

    @staticmethod
    def _decode_raw(data: bytes) -> np.ndarray:
        """raw 截图解码：8B 宽高头 + RGBA 数据 → BGR（对齐 Maa decode_raw）"""
        if len(data) < 8:
            return None
        w, h = struct.unpack('<II', data[:8])
        size = 4 * w * h
        if size <= 0 or len(data) < size:
            return None
        header_size = len(data) - size  # 部分设备头部有多余字节，从尾部对齐像素起点
        arr = np.frombuffer(data, np.uint8, size, offset=header_size).reshape(h, w, 4)
        return cvtColor(arr, COLOR_RGBA2BGR)

    def stats(self):
        """性能统计：成功帧数与总耗时(ms)"""
        return self.frame_count, self.ms_total

    def stop(self):
        """释放长期连接（mumu nemu_disconnect）；由调用方在结束/停止时调用"""
        if self.mumu:
            self.mumu.stop()
            self.mumu = None

    def channelInfo(self) -> str:
        """当前通道排序说明（GUI 日志用）"""
        names = [n for n, _ in self.tiers if n not in self._disabled]
        return ' > '.join(names) + ('; gzip ' + ('on' if self.gzipOk else 'off'))
