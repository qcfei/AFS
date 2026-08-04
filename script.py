"""AFS 入口

启动流程：
1. 重定向 stdout/stderr 到 innerLog.txt（行缓冲，保证崩溃时日志不丢）
2. 安装全局异常兜底：主线程/子线程/Qt 消息 的未捕获异常统一落盘
3. 应用 qt-material dark_teal 主题，创建主窗口进入事件循环
"""
from pytool.myQWidget import TabWidgt_Total
from pytool.basicFunction import settingMigrate, logDirGet, appRootGet
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QFontDatabase
from PyQt5.QtCore import qInstallMessageHandler, QtMsgType
import sys
import os
import traceback
import threading
from qt_material import apply_stylesheet

# 切换到程序根目录：统一所有相对路径（configure/mask/fgoMaterial）的解析基准，
# 从快捷方式等其他 CWD 启动时资源与数据依然稳定。必须在任何相对路径访问前执行。
os.chdir(appRootGet())

# stdout/stderr 重定向到 logs/innerLog.txt：先 'w' 清空，再以 'a' 追加打开——
# 与 Label_Log.log_add 的追加写共用同一模式，避免两个句柄（w 从头写 / a 从尾写）交叉覆盖
logPath = os.path.join(logDirGet(),'innerLog.txt')
open(logPath, 'w', encoding='utf-8').close()
logFile = open(logPath, 'a', encoding='utf-8', buffering=1)
sys.stdout = logFile
sys.stderr = logFile

def _excepthook(excType, excValue, excTB):
    """主线程未捕获异常兜底：完整堆栈写入 innerLog.txt"""
    logFile.write('[unhandled exception]\n' + ''.join(traceback.format_exception(excType, excValue, excTB)))
    logFile.flush()

def _thread_excepthook(args):
    """子线程未捕获异常兜底"""
    logFile.write('[thread exception]\n' + ''.join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)))
    logFile.flush()

def _qt_message_handler(mode: QtMsgType, context, message: str):
    """Qt 层消息（警告/错误）写入日志"""
    logFile.write(f'[qt {mode}] {message}\n')
    logFile.flush()

sys.excepthook = _excepthook
threading.excepthook = _thread_excepthook
qInstallMessageHandler(_qt_message_handler)

# 配置迁移：补齐旧配置缺失的新增字段（保留个人数据），须在 GUI 构造前执行
settingMigrate()

app = QApplication(sys.argv)
extra = {
'density_scale': '1',}
apply_stylesheet(app, theme='dark_teal.xml', extra=extra)

total_tab = TabWidgt_Total()
total_tab.show()
sys.exit(app.exec_())
