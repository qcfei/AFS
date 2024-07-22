
from PyQt5.QtWidgets import *
from PyQt5.QtGui import *
import time
import os
from PyQt5.QtCore import *
from pytool.pauseableThread import *

class Label_Log(QPlainTextEdit):
    def __init__(self) -> None:
        super(Label_Log,self).__init__()
        self.setReadOnly(True)
        self.text=''

    def log_add(self,text:str,sub_line_num:int=0):
        idx=0
        if self.text.count('\n')>=sub_line_num:
            for li in range(sub_line_num):
                idx=self.text[idx:].index('\n')+idx+1
            new_text=time.strftime('%H:%M:%S',time.localtime(time.time()))+'\t'+text+'\n'+self.text[idx:]
        else:
            new_text=time.strftime('%H:%M:%S',time.localtime(time.time()))+'\t'+text+'\n'
        oldValue=self.verticalScrollBar().value()
        self.text=new_text
        self.setPlainText(new_text)
        if self.verticalScrollBar().value==0:
            pass
        else:
            self.verticalScrollBar().setValue(oldValue)
        with open('./runningRecord.txt','w') as f:
            f.write(new_text)

    def log_reset(self):
        self.setPlainText('')
        self.text=''

class Signal_log(PauseableThread):
    sgn=pyqtSignal(str,int)
    def __init__(self) -> None:
        super(Signal_log,self).__init__()

    def log_add(self,text:str,sub_line_num:int=0):
        self.sgn.emit(text,sub_line_num)
        