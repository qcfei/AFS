from PyQt5.QtCore import QThread,QWaitCondition,QMutex
from PyQt5.QtCore import pyqtSignal

class PauseableThread(QThread):
    quitSignal=pyqtSignal()
    def __init__(self):
        super(PauseableThread,self).__init__()
        self._isPause = False
        self._isExtraPause = False
        self._value = 0
        self.cond = QWaitCondition()
        self.mutex = QMutex()
        self._isRun= False

    def run(self):
        self._isRun= True
        self.initialAction()
        while self._isRun:
            self.mutex.lock()       # 上锁
            if self._isPause:
                self.cond.wait(self.mutex)
            self.action()
            self.mutex.unlock()  # 解锁
        self.finishAction()
        self.quitSignal.emit()

    def pause(self):    
        self._isPause = True

    def extraPause(self):
        self._isExtraPause = True
 
    def resume(self):
        self._isPause = False
        if not self._isExtraPause:
            self.cond.wakeAll()

    def extraResume(self):
        self._isExtraPause = False

    def stop(self) -> None:
        self._isRun=False

    def action(self):
        pass

    def initialAction(self):
        pass

    def finishAction(self):
        pass