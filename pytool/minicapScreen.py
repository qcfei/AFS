"""minicap 流式截图模块

替代每帧 adb screencap+pull（约 200ms）的截图方式：设备端运行 minicap 虚拟
显示，通过 adb forward 的本地 socket 持续推送 JPEG 帧，本模块后台线程解码
缓存最新帧，getFrame() 零等待取用。

参考实现：MaaFramework MinicapStream（ref/maaframe）。

- 坐标系：minicap 输出真实分辨率帧（如 1080×1920 竖屏），由调用方统一
  imgResize2512 降采样到 512×288，与现有识别体系完全兼容
- 回退策略：connect() 失败或拉流中断时返回 None，调用方回退 screencap+pull
- 二进制：minicap/{arch}/bin/minicap + minicap/{arch}/lib/android-{sdk}/minicap.so
  （x86 32 位套件实测可在 x86_64 模拟器上运行；x86_64 的 android-31/32 so
  为官方构建错误产物(实为32位)，故架构优先选 x86）
"""
import os
import re
import socket
import struct
import subprocess
import threading
import time

import numpy as np
from cv2 import imdecode, IMREAD_COLOR, cvtColor, COLOR_BGR2RGB

from pytool.basicFunction import appRootGet, sysInput, myGetoutput

_LOCAL_SOCKET = 'minicap'
_FORWARD_PORT = 1313
_BIN_NAME = 'afs_minicap'          # 设备端二进制名（固定名，重复 push 覆盖）
_SO_NAME = 'minicap.so'            # 设备端 so 名（minicap dlopen 固定查找名）
_ARCH_PRIORITY = ['x86', 'x86_64', 'arm64-v8a', 'armeabi-v7a']
_SDK_LIST = [34, 33, 32, 31, 30, 29, 28, 27, 26, 25, 24, 23, 22, 21,
             19, 18, 17, 16, 15, 14, 10, 9]
_WAIT_ALLOCATING_TIMEOUT = 10.0   # 等待 minicap 启动输出超时（秒）
_RECV_TIMEOUT = 5.0               # socket 收帧超时（秒）
_PUSH_RATE = 4                    # minicap 推帧率上限（fps）：实际使用取 4fps 平衡模拟器负载；
                                  # 34fps 曾致模拟器卡顿白屏，20fps 与 4fps 均可用，以实测为准


# ---------------------------------------------------------------------------
# 模块级公共工具：minicap 二进制选择 / 推送 / 方向探测
# （MinicapScreen 流式与 MinicapDirectScreencap 单帧模式共用）
# ---------------------------------------------------------------------------

def minicapSelectBinary(ip: str):
    """按设备 abilist 与优先级挑选架构，SDK 选 ≤ 设备版本的最大 android-N

    成功返回 (arch, sdk)，失败返回 (None, 错误描述)。
    """
    abilist = myGetoutput(f'adb -s {ip} shell getprop ro.product.cpu.abilist').strip()
    sdk_out = myGetoutput(f'adb -s {ip} shell getprop ro.build.version.sdk').strip()
    if 'not found' in abilist or 'error' in abilist.lower() or 'not found' in sdk_out:
        return None, 'device not reachable'
    sdk_nums = re.findall(r'\d+', sdk_out)
    if not sdk_nums:
        return None, 'getprop sdk failed'
    dev_sdk = int(sdk_nums[0])
    abi_set = set(a.strip() for a in abilist.split(','))

    root = os.path.join(appRootGet(), 'minicap')
    for arch in _ARCH_PRIORITY:
        if arch not in abi_set:
            continue
        arch_dir = os.path.join(root, arch)
        lib_root = os.path.join(arch_dir, 'lib')
        if not os.path.exists(os.path.join(arch_dir, 'bin', 'minicap')):
            continue
        for sdk in _SDK_LIST:
            if sdk <= dev_sdk and os.path.exists(os.path.join(lib_root, f'android-{sdk}', 'minicap.so')):
                return arch, sdk
    return None, f'no prebuilt for abi={abi_set} sdk={dev_sdk}'


def minicapPushBinary(ip: str, arch: str, sdk: int) -> bool:
    """推送 minicap 二进制与 so 到设备 /data/local/tmp（已存在且 size 一致则跳过）"""
    root = os.path.join(appRootGet(), 'minicap', arch)
    bin_local = os.path.join(root, 'bin', 'minicap')
    so_local = os.path.join(root, 'lib', f'android-{sdk}', 'minicap.so')
    tmp = '/data/local/tmp'
    # 已存在且 size 与本地一致 → 跳过推送（防残留旧版本被误判就绪）
    ls_out = myGetoutput(f'adb -s {ip} shell ls -l {tmp}/{_BIN_NAME} {tmp}/{_SO_NAME}')
    local_size = {_BIN_NAME: os.path.getsize(bin_local), _SO_NAME: os.path.getsize(so_local)}
    remote_size = {}
    for line in ls_out.splitlines():
        parts = line.split()
        if len(parts) >= 6 and parts[4].isdigit():
            remote_size[parts[-1].split('/')[-1]] = int(parts[4])
    if all(remote_size.get(name) == size for name, size in local_size.items()):
        return True
    sysInput(f'adb -s {ip} push "{bin_local}" {tmp}/{_BIN_NAME}')
    sysInput(f'adb -s {ip} push "{so_local}" {tmp}/{_SO_NAME}')
    out = myGetoutput(f'adb -s {ip} shell chmod 777 {tmp}/{_BIN_NAME} {tmp}/{_SO_NAME}')
    return 'notfound' not in out.lower()


def displayOrientationGet(ip: str) -> int:
    """读取当前显示方向（SurfaceOrientation 0-3 → 角度 0/90/180/270），供 -P 投影参数使用"""
    out = myGetoutput(f'adb -s {ip} shell dumpsys input')
    m = re.search(r'SurfaceOrientation:\s*(\d)', out)
    return int(m.group(1)) * 90 if m else 0


class MinicapScreen:
    """minicap 流式截图器：连接/拉流/取帧/清理"""

    def __init__(self, ip: str):
        self.ip = ip
        self.arch = ''          # 选中的架构
        self.sdk = 0            # 选中的 android-N
        self._proc = None       # 设备端 minicap 进程（adb shell 管道）
        self._sock = None
        self._pull_thread = None
        self._quit = False
        self._alive = False
        self._lock = threading.Lock()
        self._latest = None     # 最新一帧 BGR ndarray
        self._last_error = ''
        self.frame_count = 0    # 已解码帧数（性能统计）
        self.decode_ms_total = 0.0  # 累计解码耗时 ms（性能统计）
        # 断线/恢复事件回调（拉流线程内触发；由调用方绑定，如经 Qt 信号转发到 GUI）
        self.on_lost = None         # on_lost(error_text)
        self.on_recovered = None    # on_recovered()

    # ------------------------------------------------------------------ 连接

    def connect(self) -> bool:
        """完整启动流程，成功返回 True。任一环节失败自动清理并返回 False

        模拟器 adb 服务不稳定（反复掉线）时会 push/启动失败——每轮失败后先 adb connect 重试。
        注意：_quit 必须复位（stop() 置 True 后本对象可再次 connect/reconnect）。
        """
        self._quit = False
        self._last_error = ''
        for attempt in range(3):
            try:
                if self._connect_steps():
                    self._alive = True
                    self.frame_count = 0
                    self.decode_ms_total = 0.0
                    self._pull_thread = threading.Thread(target=self._pulling, daemon=True)
                    self._pull_thread.start()
                    return True
            except Exception as e:
                self._last_error = f'{type(e).__name__}: {e}'
            self.stop()
            if attempt < 2:
                sysInput(f'adb connect {self.ip}')
                time.sleep(1.0)
        return False

    def _connect_steps(self) -> bool:
        """执行完整连接步骤：选二进制→push→启动→forward→socket 握手，成功返回 True"""
        for step in (self._select_binary, self._push_binary, self._start_minicap,
                     self._forward, self._connect_socket):
            if not step():
                return False
        return True

    def _select_binary(self) -> bool:
        """按设备 abilist 与优先级挑选架构；SDK 选 ≤ 设备版本的最大 android-N"""
        arch, sdk = minicapSelectBinary(self.ip)
        if arch is None:
            self._last_error = sdk or 'select minicap failed'
            return False
        self.arch, self.sdk = arch, sdk
        return True

    def _push_binary(self) -> bool:
        return minicapPushBinary(self.ip, self.arch, self.sdk)

    def _start_minicap(self) -> bool:
        """设备端启动 minicap（保持 adb shell 管道 = 进程保活），等待 Allocating 输出"""
        wm = myGetoutput(f'adb -s {self.ip} shell wm size')
        nums = re.findall(r'\d+', wm)
        if len(nums) < 2:
            self._last_error = f'wm size parse failed: {wm}'
            return False
        w, h = int(nums[0]), int(nums[1])
        orientation = self._display_orientation()
        tmp = '/data/local/tmp'
        self._proc = subprocess.Popen(
            ['adb', '-s', self.ip, 'shell',
             f'export LD_LIBRARY_PATH={tmp}/; {tmp}/{_BIN_NAME} -P {w}x{h}@{w}x{h}/{orientation} -r {_PUSH_RATE} 2>&1'],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        deadline = time.time() + _WAIT_ALLOCATING_TIMEOUT
        while time.time() < deadline:
            line = self._proc.stdout.readline()
            if not line:
                break
            if 'Allocating' in line:
                threading.Thread(target=self._drain, daemon=True).start()
                return True
        self._last_error = 'minicap no Allocating output'
        return False

    def _display_orientation(self) -> int:
        """读取当前显示方向（SurfaceOrientation 0-3 → 角度 0/90/180/270），供 -P 投影参数使用"""
        return displayOrientationGet(self.ip)

    def _drain(self):
        """丢弃 minicap 后续标准输出，防止管道缓冲区阻塞进程"""
        try:
            while self._proc and self._proc.poll() is None:
                if not self._proc.stdout.readline():
                    break
        except Exception:
            pass

    def _forward(self) -> bool:
        sysInput(f'adb -s {self.ip} forward --remove tcp:{_FORWARD_PORT}')
        out = myGetoutput(f'adb -s {self.ip} forward tcp:{_FORWARD_PORT} localabstract:{_LOCAL_SOCKET}')
        return str(_FORWARD_PORT) in out

    def _connect_socket(self) -> bool:
        host = self.ip.split(':')[0] if ':' in self.ip else '127.0.0.1'
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.settimeout(_RECV_TIMEOUT)
        self._sock.connect((host, _FORWARD_PORT))
        hdr = self._recv_exact(24)
        ver, size = struct.unpack('<BB', hdr[:2])
        if ver != 1 or size < 24:
            self._last_error = f'bad minicap header ver={ver} size={size}'
            return False
        if size > 24:
            self._recv_exact(size - 24)
        return True

    # ------------------------------------------------------------------ 拉流

    def _recv_exact(self, n: int) -> bytes:
        buf = b''
        while len(buf) < n:
            chunk = self._sock.recv(n - len(buf))
            if not chunk:
                raise ConnectionError('socket closed')
            buf += chunk
        return buf

    def _pulling(self):
        """后台线程：持续读帧解码，缓存最新一帧；断开时自动恢复重连

        minicap 协议在屏幕不变时不推帧——socket 读超时（静默期）**不算断开**，
        继续等待；仅连接真断开（recv 返回空/OSError）才进入自动恢复流程
        （adb connect → 清理设备残留 → 重跑连接步骤，指数退避重试）。
        恢复期间 getFrame() 返回 None，调用方自然回退 screencap+pull，无需阻塞主流程。
        """
        try:
            while not self._quit:
                try:
                    while not self._quit:
                        try:
                            size = struct.unpack('<I', self._recv_exact(4))[0]
                        except socket.timeout:
                            continue  # 静默期（屏幕静止无新帧），保持连接
                        try:
                            jpg = self._recv_exact(size)
                        except socket.timeout:
                            # 帧体超时：长度头已消费 → 帧边界失步，无法继续解析 → 视为断开走恢复
                            raise ConnectionError('frame body timeout (desync)')
                        t0 = time.time()
                        img = imdecode(np.frombuffer(jpg, np.uint8), IMREAD_COLOR)
                        dt_ms = (time.time() - t0) * 1000
                        if img is not None:
                            with self._lock:
                                self._latest = img
                                self.frame_count += 1
                                self.decode_ms_total += dt_ms
                except Exception as e:
                    # 主动停止（stop/reconnect 关闭 socket 唤醒 recv）不算断开
                    if self._quit:
                        break
                    self._mark_lost(f'{type(e).__name__}: {e}')
                    if not self._auto_recover():
                        return
        finally:
            self._alive = False
            with self._lock:
                self._latest = None

    def _mark_lost(self, err: str):
        """记录断开原因、清空帧缓存并触发 on_lost 回调（回调异常不向上抛）"""
        self._alive = False
        self._last_error = err
        with self._lock:
            self._latest = None
        if self.on_lost:
            try:
                self.on_lost(err)
            except Exception:
                pass

    def _auto_recover(self) -> bool:
        """断线自动恢复：循环尝试 _recover()，指数退避 1→10s，直到成功或主动停止"""
        delay = 1.0
        while not self._quit:
            time.sleep(delay)
            try:
                if self._recover():
                    self._alive = True
                    if self.on_recovered:
                        try:
                            self.on_recovered()
                        except Exception:
                            pass
                    return True
            except Exception as e:
                self._last_error = f'{type(e).__name__}: {e}'
            delay = min(delay * 2, 10.0)
        return False

    def _recover(self) -> bool:
        """单次恢复尝试：重连 adb → 清理设备端残留 minicap 进程（防抽象 socket 被占）→ 重跑连接步骤"""
        if self._quit:  # stop() 已发出：不再重建连接，避免与 stop 的清理竞态
            return False
        sysInput(f'adb connect {self.ip}')
        time.sleep(0.3)
        sysInput(f'adb -s {self.ip} shell "kill $(pidof {_BIN_NAME}) 2>/dev/null"')
        self._close_sock()
        self._kill_proc()
        return self._connect_steps()

    def _close_sock(self):
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None

    def _kill_proc(self):
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.kill()
            except Exception:
                pass
        self._proc = None

    def stats(self):
        """性能统计：累计解码帧数与解码总耗时(ms)"""
        with self._lock:
            return self.frame_count, self.decode_ms_total

    def getFrame(self):
        """返回最新一帧 BGR ndarray；未就绪/断开返回 None"""
        with self._lock:
            return self._latest

    # ------------------------------------------------------------------ 清理

    def reconnect(self) -> bool:
        """断开后重建连接：清理旧资源并重新 connect（模拟器 adb 不稳时的保活手段）

        注：正常运行时断线由拉流线程自动恢复，本方法仅供外部显式强制重连。
        """
        self.stop()
        time.sleep(0.5)
        return self.connect()

    def stop(self):
        self._quit = True
        self._close_sock()
        if self._pull_thread and self._pull_thread.is_alive():
            self._pull_thread.join(timeout=_RECV_TIMEOUT + 1)
        self._kill_proc()
        sysInput(f'adb -s {self.ip} shell rm /data/local/tmp/{_BIN_NAME} /data/local/tmp/{_SO_NAME}')
        sysInput(f'adb -s {self.ip} forward --remove tcp:{_FORWARD_PORT}')


def mat2QImage(mat: np.ndarray):
    """BGR ndarray → QImage（深拷贝，安全跨线程使用）"""
    from PyQt5.QtGui import QImage
    rgb = cvtColor(mat, COLOR_BGR2RGB)
    h, w = rgb.shape[:2]
    return QImage(rgb.data, w, h, rgb.strides[0], QImage.Format_RGB888).copy()
