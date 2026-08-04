"""日志组件

Label_Log  : GUI 日志面板（QPlainTextEdit），支持按行数部分更新；日志追加写入 logs/innerLog.txt
Signal_log : 跨线程日志信号桥（PauseableThread 子类），供工作线程安全地向 GUI 发日志
"""
from PyQt5.QtWidgets import *
from PyQt5.QtGui import *
import time
import os
from PyQt5.QtCore import *
from pytool.pauseableThread import *
from pytool.basicFunction import logDirGet

class Label_Log(QPlainTextEdit):
    """GUI 日志显示面板，每次 log_add 追加写入 logs/innerLog.txt"""
    def __init__(self) -> None:
        super(Label_Log,self).__init__()
        self.setReadOnly(True)
        self.text=''  # 当前日志全文（用于增量更新）

    def log_add(self,text:str,sub_line_num:int=0):
        """向日志面板追加一条带时间戳的记录

        sub_line_num: 要替换掉的旧日志行数（0=仅追加；N=从末尾保留 N 行，其余被新内容顶掉）
        """
        # 新记录行：写入统一日志文件（追加模式）
        new_line=time.strftime('%H:%M:%S',time.localtime(time.time()))+'\t'+text+'\n'
        with open(os.path.join(logDirGet(),'innerLog.txt'),'a',encoding='utf-8') as f:
            f.write(new_line)

        idx=0
        if self.text.count('\n')>=sub_line_num:
            # 定位到保留区起点（倒数第 sub_line_num 行开头）
            for li in range(sub_line_num):
                idx=self.text[idx:].index('\n')+idx+1
            new_text=new_line+self.text[idx:]
        else:
            new_text=new_line
        # 保留用户当前的滚动位置
        oldValue=self.verticalScrollBar().value()
        self.text=new_text
        self.setPlainText(new_text)
        if self.verticalScrollBar().value()!=0:
            self.verticalScrollBar().setValue(oldValue)

    def log_reset(self):
        """清空日志面板"""
        self.setPlainText('')
        self.text=''

class Signal_log(PauseableThread):
    """跨线程日志信号：线程内调用 log_add 通过信号转发到 GUI 主线程"""
    sgn=pyqtSignal(str,int)
    def __init__(self) -> None:
        super(Signal_log,self).__init__()

    def log_add(self,text:str,sub_line_num:int=0):
        self.sgn.emit(text,sub_line_num)
