"""可暂停线程基类

所有自动化工作线程继承本类，获得统一的 启动/暂停/恢复/停止 生命周期控制。
暂停通过 QMutex + QWaitCondition 实现；停止通过 _isRun 标志在循环头部检查退出。
"""
from PyQt5.QtCore import QThread,QWaitCondition,QMutex
from PyQt5.QtCore import pyqtSignal

class PauseableThread(QThread):
    """可暂停/恢复/停止的线程基类

    run() 循环体内每次执行 action()，完成后发出 doneSignal。
    派生类只需覆写 initialAction / action / finishAction 三个钩子。
    """
    quitSignal=pyqtSignal()      # 线程正常退出信号（finishAction 后发出）
    doneSignal=pyqtSignal()      # 每轮 action 完成信号

    def __init__(self):
        super(PauseableThread,self).__init__()
        self._isPause = False      # 暂停标志
        self._isExtraPause = False # 额外暂停标志（与 _isPause 独立，resume 不解除）
        self._value = 0
        self.cond = QWaitCondition()
        self.mutex = QMutex()
        self._isRun= False         # 运行标志，False 时线程退出循环

    def run(self):
        self._isRun= True
        try:
            self.initialAction()
        except Exception:
            import traceback
            print('[initialAction exception]\n'+traceback.format_exc())
            self._isRun=False
        while self._isRun:
            try:
                self.mutex.lock()       # 上锁
                if self._isPause:
                    self.cond.wait(self.mutex)  # 暂停时阻塞等待 resume
                self.action()
                self.doneSignal.emit()
                self.mutex.unlock()     # 解锁
            except Exception:
                import traceback
                print('[action exception]\n'+traceback.format_exc())
                self._isRun=False      # 单轮异常：记录后优雅停止（避免线程死而不自知）
                try:
                    self.mutex.unlock()
                except Exception:
                    pass
                break
        try:
            self.finishAction()
        except Exception:
            import traceback
            print('[finishAction exception]\n'+traceback.format_exc())
        self.quitSignal.emit()

    def pause(self):
        """请求暂停（下一轮循环进入等待）"""
        self._isPause = True

    def extraPause(self):
        """请求额外暂停（resume 无法解除，需 extraResume）"""
        self._isExtraPause = True

    def resume(self):
        """解除暂停；若处于额外暂停则不唤醒"""
        self._isPause = False
        if not self._isExtraPause:
            self.cond.wakeAll()

    def extraResume(self):
        """解除额外暂停"""
        self._isExtraPause = False

    def stop(self) -> None:
        """请求停止（下一轮循环退出）"""
        self._isRun=False

    def action(self):
        """每轮循环要执行的任务（派生类覆写）"""
        pass

    def initialAction(self):
        """线程启动时执行一次的任务（派生类覆写）"""
        pass

    def finishAction(self):
        """线程结束前执行一次的任务（派生类覆写）"""
        pass
