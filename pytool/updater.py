"""GitHub 增量更新模块（参考 MaaUpdater 思路）

协议（配合 make_release 生成的发布包）：
- 仓库根 `version.json`：{"version": "x.y.z"}
- 检查更新：GET https://raw.githubusercontent.com/{repo}/main/version.json
- 更新包随 GitHub Release 上传（v{version} tag）：
    AFS_update_{ver}.zip   增量包：仅含与上一版不同的文件 + update_manifest.json
    AFS_full_{ver}.zip     全量包（增量包不存在时回退下载）
  update_manifest.json: {"version": "x.y.z", "from_version": "a.b.c",
                         "files": {"相对路径": "md5", ...}}
- 应用策略（两阶段，避开运行中 exe/dll 占用）：
    1) check/download/校验/解压到 `update_pending/` + 生成 `apply_update.bat`
    2) 提示用户关闭程序 → bat 把新文件覆盖到程序根（跳过个人数据）→ 重新启动 AFS.exe
- 个人数据保护：setting.json / 助战素材 / 出战头像 / logs / screen.jpeg 一律不覆盖

网络与镜像（国内裸连 GitHub 可能失败）：
- 候选顺序：配置镜像（fixed.update.mirror，如 https://ghproxy.net/）→ 直连 → 内置镜像
- 任一候选成功即用；全部失败抛异常
- 更新仓库地址配置：settingFixed.json `fixed.update.repo`（格式 owner/name，空=禁用）
"""
import hashlib
import json
import os
import shutil
import tempfile
import urllib.request
import urllib.error
import zipfile

from pytool.basicFunction import appRootGet, fixedSettingRead

_TIMEOUT = 15           # 网络请求超时（秒）
_PERSONAL_FILENAMES = ('setting.json', 'screen.jpeg', 'screen copy.jpeg')
_PERSONAL_PREFIXES = ('fgoMaterial/assist', 'fgoMaterial/preServant', 'fgoMaterial/eyeServant', 'logs/')
_PENDING_DIR = 'update_pending'
_APPLY_BAT = 'apply_update.bat'
_DELETED_FLAG = 'DELETED'   # 增量清单中"旧版有、新版已删除"的标记（make_release 生成）
_DEFAULT_MIRRORS = (        # 内置镜像（整站代理，前缀拼完整 github URL）
    'https://ghproxy.net/',
    'https://gh-proxy.com/',
)


def compareVersion(a: str, b: str) -> int:
    """版本号比较：a>b 返回 1，a<b 返回 -1，相等返回 0（短版本补 0 后逐段比较）"""
    def _nums(v: str):
        return [int(x) for x in str(v).strip('v').split('.') if x.isdigit()] or [0]
    na, nb = _nums(a), _nums(b)
    length = max(len(na), len(nb))
    na += [0] * (length - len(na))
    nb += [0] * (length - len(nb))
    for x, y in zip(na, nb):
        if x != y:
            return 1 if x > y else -1
    return 0


def _md5(path: str) -> str:
    h = hashlib.md5()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


class Updater:
    """GitHub 更新器：检查/下载/校验/阶段式应用

    base：默认按 GitHub 规则拼 URL；测试时可传入本地 HTTP 服务地址。
    """

    def __init__(self, repo: str, base: str = None, check_base: str = None):
        self.repo = repo.strip('/')
        self.base = (base or 'https://github.com/' + self.repo).rstrip('/')
        self.check_base = (check_base or f'https://raw.githubusercontent.com/{self.repo}/main').rstrip('/')
        # 配置镜像（fixed.update.mirror，空=不用）；缺失字段容错
        try:
            self.mirror = (fixedSettingRead(['fixed', 'update', 'mirror']) or '').strip().rstrip('/')
        except Exception:
            self.mirror = ''

    def _candidate_urls(self, url: str) -> list:
        """候选下载地址：配置镜像 → 直连 → 内置镜像（任一成功即用）"""
        urls = [url]
        for m in _DEFAULT_MIRRORS:
            urls.append(self._join_mirror(m, url))
        if self.mirror:
            urls.insert(0, self._join_mirror(self.mirror, url))
        return urls

    @staticmethod
    def _join_mirror(mirror: str, url: str) -> str:
        """镜像前缀拼接：保证两者间恰好一个斜杠（mirror 可能配置为 ghproxy.net 无尾斜杠）"""
        return mirror.rstrip('/') + '/' + url.lstrip('/')

    # ------------------------------------------------------------------ 检查

    def check(self) -> dict:
        """查询仓库最新 version.json；全部候选失败抛最后异常"""
        url = f'{self.check_base}/version.json'
        last_err = None
        for u in self._candidate_urls(url):
            try:
                with urllib.request.urlopen(u, timeout=_TIMEOUT) as r:
                    data = json.loads(r.read().decode('utf-8'))
                if 'version' not in data:
                    raise ValueError(f'bad version.json: {data}')
                return data
            except Exception as e:
                last_err = e
        raise last_err or ValueError('check update failed')

    @staticmethod
    def localVersion() -> str:
        """本地版本（程序根 version.json）"""
        try:
            with open(os.path.join(appRootGet(), 'version.json'), 'r', encoding='utf-8') as f:
                return json.load(f).get('version', '0.0.0')
        except Exception:
            return '0.0.0'

    # ------------------------------------------------------------------ 下载

    def _download(self, url: str, dest: str, on_progress=None) -> None:
        """流式下载到 dest；on_progress(done_bytes, total_bytes)"""
        req = urllib.request.Request(url, headers={'User-Agent': 'AFS-updater'})
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
            total = int(r.headers.get('Content-Length') or 0)
            done = 0
            with open(dest, 'wb') as f:
                while True:
                    chunk = r.read(1 << 20)
                    if not chunk:
                        break
                    f.write(chunk)
                    done += len(chunk)
                    if on_progress:
                        on_progress(done, total)

    def downloadPackage(self, version: str, dest: str, on_progress=None) -> str:
        """下载增量包；404 时回退全量包。返回实际文件名（'update' 或 'full'）

        每类包遍历候选地址（配置镜像→直连→内置镜像）；全部 404 才换下一类。
        """
        for kind in ('update', 'full'):
            url = f'{self.base}/releases/download/v{version}/AFS_{kind}_{version}.zip'
            for u in self._candidate_urls(url):
                try:
                    self._download(u, dest, on_progress)
                    return kind
                except urllib.error.HTTPError:
                    continue  # 404 或其他 HTTP 错误（500/503/403）：试下一候选/换包类型
                except Exception:
                    continue  # 连接/超时等：试下一候选
        raise FileNotFoundError(f'no package for v{version}')

    # ------------------------------------------------------------------ 应用

    def apply(self, version: str, on_progress=None, on_log=None) -> str:
        """下载并校验更新包，解压到 update_pending/ 并生成应用脚本

        返回 'update'（增量包）或 'full'（全量包）；异常向上抛。
        完成提示用户关闭程序后由 apply_update.bat 落地并重启。
        """
        log = on_log or (lambda s: None)
        root = appRootGet()
        pending = os.path.join(root, _PENDING_DIR)
        shutil.rmtree(pending, ignore_errors=True)
        os.makedirs(pending, exist_ok=True)
        pending_real = os.path.realpath(pending)

        zip_path = os.path.join(tempfile.gettempdir(), f'AFS_update_{version}.zip')
        try:
            kind = self.downloadPackage(version, zip_path, on_progress)
            log(f'downloaded {kind} package for v{version}')
            with zipfile.ZipFile(zip_path) as zf:
                manifest = json.loads(zf.read('update_manifest.json').decode('utf-8-sig'))
                if manifest.get('version') != version:
                    raise ValueError(f'manifest version mismatch: {manifest.get("version")}')
                files = manifest['files']
                deleted = []   # 需在落地时删除的旧文件（增量包标记 DELETED）
                total = len(files)
                for i, (rel, expect_md5) in enumerate(files.items()):
                    if on_progress:
                        on_progress(i + 1, total)
                    rel = rel.replace('\\', '/')
                    if self._isPersonal(rel):
                        log(f'skip personal: {rel}')
                        continue
                    if expect_md5 == _DELETED_FLAG:
                        # DELETED 同样要过路径校验，防止 bat del 命令逃逸到程序根之外
                        del_path = os.path.normpath(os.path.join(pending, rel))
                        if del_path != pending_real and not del_path.startswith(pending_real + os.sep):
                            raise ValueError(f'unsafe path in manifest (deleted): {rel}')
                        deleted.append(rel)
                        continue
                    # 路径穿越防御：解压目标必须位于 pending 目录内
                    src = os.path.normpath(os.path.join(pending, rel))
                    if src != pending_real and not src.startswith(pending_real + os.sep):
                        raise ValueError(f'unsafe path in manifest: {rel}')
                    os.makedirs(os.path.dirname(src), exist_ok=True)
                    with zf.open(rel) as fsrc, open(src, 'wb') as fdst:
                        shutil.copyfileobj(fsrc, fdst)
                    log(f'verify {rel}')
                    if _md5(src).lower() != expect_md5.lower():
                        raise ValueError(f'md5 mismatch: {rel}')
        finally:
            try:
                os.remove(zip_path)
            except OSError:
                pass

        # 版本文件与落地脚本（bat 等待 AFS.exe 退出后再覆盖，避开运行中文件占用）
        with open(os.path.join(pending, 'version.json'), 'w', encoding='utf-8') as f:
            json.dump({'version': version}, f)
        del_lines = ''.join(f'del /q "{rel}" 2>nul\r\n' for rel in deleted)
        with open(os.path.join(root, _APPLY_BAT), 'w', encoding='utf-8', newline='\r\n') as f:
            f.write('@echo off\r\n'
                    'cd /d "%~dp0"\r\n'
                    ':wait\r\n'
                    'tasklist /fi "imagename eq AFS.exe" 2>nul | find /i "AFS.exe" >nul && (timeout /t 2 /nobreak >nul & goto :wait)\r\n'
                    f'robocopy "{_PENDING_DIR}" "." /E /MOV /XF setting.json screen.jpeg "screen copy.jpeg" assistServant*.png assistCloth*.png preServant*.png eyeServant*.png /XD logs >nul\r\n'
                    + del_lines +
                    'rd /s /q "' + _PENDING_DIR + '" 2>nul\r\n'
                    'start "" "AFS.exe"\r\n'
                    'del "%~f0"\r\n')
        return kind

    @staticmethod
    def _isPersonal(rel: str) -> bool:
        rel = rel.replace('\\', '/')
        for name in _PERSONAL_FILENAMES:
            if rel == name or rel.endswith('/' + name):
                return True
        for prefix in _PERSONAL_PREFIXES:
            if rel.startswith(prefix):
                return True
        return False
