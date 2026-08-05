"""AFS 主 GUI

TabWidgt_Total   : 主窗口（双页：运行 / 设置），负责跨页信号联动与关闭清理
Widget_run       : 运行页——模拟器/次数/状态显示、策略快捷选择、开始/暂停/恢复/停止、屏幕预览+日志
Widget_set       : 设置页——策略、助战、多次战斗、模拟器、关于、搓丸子(占位) 管理
ScrollArea_setting / GroupBox_* : 设置页各分组面板
"""
# 原生库
from PyQt5.QtWidgets import QTabWidget,QWidget,QScrollArea,QGroupBox,QComboBox,QCheckBox,QSpinBox
from PyQt5.QtGui import QIcon,QCloseEvent
from PyQt5.QtCore import Qt,pyqtSignal,QTimer
import time
import traceback
import sys
from pyminitouch import MNTDevice
import shutil
import threading

# 自制库
from pytool.basicQObject import *
from pytool.pauseableThread import *
from pytool.flow import *
from pytool.minicapScreen import MinicapScreen, mat2QImage
from pytool.adbScreencap import AdbScreencap
from pytool.mumuExtras import MuMuScreencap
from pytool.updater import Updater, compareVersion

class TabWidgt_Total(QTabWidget):
    """主窗口：运行页 + 设置页，联动两页的控件（策略选择/次数/模拟器）"""
    def __init__(self) -> None:
        print('TabWidgt_Total initializing')
        super(QTabWidget,self).__init__()
        self.setStyleSheet('font-size: 13pt;style=line-height:200%;color:white;')
        # 恢复上次窗口位置与尺寸：存 setting.json（个人数据，更新时不覆盖）；
        # 旧版存 settingFixed.json（更新会被覆盖导致位置丢失），读到则沿用一次，关闭时写入新位置
        try:
            WindowGeometry=settingRead(['changable','windowGeometry'])
        except Exception:
            try:
                WindowGeometry=fixedSettingRead(['fixed','WindowGeometry'])
            except Exception:
                WindowGeometry=[100,100,1200,720]
        wx,wy,ww,wh=WindowGeometry
        self.setGeometry(wx,wy,ww,wh)
        self.setWindowTitle('AFS ver'+Updater.localVersion())
        self.setWindowIcon(QIcon('litShk.ico'))

        self.wi1_run = Widget_run()
        self.wi2_setting = Widget_set()
        self.addTab(self.wi1_run, '运行')
        self.addTab(self.wi2_setting, '设置')
        
        gbStrategy2=self.wi2_setting.scrollArea_setting.gb1_strategy
        cbStrategy1=self.wi1_run.cb23_strategyChoose
        cbStrategy2=gbStrategy2.cb11_strategyChoose
        vbDetail_lst=gbStrategy2.vb31_detail_lst
        for vbDetailI in range(len(vbDetail_lst)):
            self.vbDetailConnect(vbDetailI)
        gbStrategy2.btn21_add.clicked.connect(cbStrategy1.itemUpdate)
        gbStrategy2.btn22_remove.clicked.connect(cbStrategy1.itemUpdate)
        cbStrategy1.indexChanged.connect(cbStrategy2.setCurrentIndex)
        cbStrategy2.indexChanged.connect(cbStrategy1.setCurrentIndex)
        gbStrategy2.btn21_add.clicked.connect(self.lastVbDetailConnect)
        self.wi2_setting.scrollArea_setting.gb2_assist.btn21_add.pressed.connect(self.wi2_setting.scrollArea_setting.gb1_strategy.assistAdd)
        self.wi2_setting.scrollArea_setting.gb2_assist.btn22_remove.pressed.connect(self.wi2_setting.scrollArea_setting.gb1_strategy.assistRemove)
        # self.wi2_setting.scrollArea_setting.gb1_strategy.deleteSignal.connect(cbStrategy1.itemUpdate)

        # 模拟器当前项由设置页「模拟器类型+端口」决定（simulatorIndex 自动同步），此处仅初始化显示
        self.wi1_run.la11_simulator.simulaterIndexChange(settingRead(['changable','simulatorIndex']))

        leFightCount1=self.wi1_run.le25_fightCount
        leFightCount2=self.wi2_setting.scrollArea_setting.gb3_repeat.le22_numCount
        leFightCount1.numCountChanged.connect(leFightCount2.textUpdate)
        leFightCount2.numCountChanged.connect(leFightCount1.textUpdate)

        self.th_lst:list[PauseableThread]=[self.wi1_run.th_operate]

        # 后台预热 adb server：窗口显示后静默启动，点"开始"时 adb connect 立即可用
        # （adb server 冷启动约 2s，预热后无需等待）
        self._adbWarmTimer=QTimer(self)
        self._adbWarmTimer.setSingleShot(True)
        self._adbWarmTimer.timeout.connect(self._adbWarmUp)
        self._adbWarmTimer.start(1000)

        print('TabWidgt_Total initializied')

        # 调试后门：--autostart 启动后自动触发"脚本开始"（等价自动点击开始按钮）
        if '--autostart' in sys.argv:
            QTimer.singleShot(2500,self.wi1_run.btnc43_script.btn1.click)

    def _adbWarmUp(self):
        """后台线程静默执行 adb start-server（不阻塞 UI）"""
        def _run():
            try:
                sysInput('adb start-server')
            except Exception as e:
                print(f'adb warmup error: {e}')
        threading.Thread(target=_run,daemon=True).start()

    def vbDetailConnect(self,vbDetailI:int):
        gbStrategy2=self.wi2_setting.scrollArea_setting.gb1_strategy
        cbStrategy1=self.wi1_run.cb23_strategyChoose
        cbStrategy2=gbStrategy2.cb11_strategyChoose
        vbDetail_lst=gbStrategy2.vb31_detail_lst
        vbDetail_lst[vbDetailI].le2_name.textChanged.connect(cbStrategy1.itemUpdate)
        vbDetail_lst[vbDetailI].le2_name.textChanged.connect(cbStrategy2.itemUpdate)

    def lastVbDetailConnect(self):
        gbStrategy2=self.wi2_setting.scrollArea_setting.gb1_strategy
        vbDetail_lst=gbStrategy2.vb31_detail_lst
        self.vbDetailConnect(len(vbDetail_lst)-1)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape:
            self.close()
        elif event.key() == Qt.Key_1:
            self.setCurrentWidget(self.wi1_run)
        elif event.key() == Qt.Key_2:
            self.setCurrentWidget(self.wi2_setting)
        elif event.key() == Qt.Key_Right:
            self.setCurrentIndex(self.currentIndex())
        elif event.key() == Qt.Key_Left:
            self.setCurrentIndex(self.currentIndex())

    def closeEvent(self, a0: QCloseEvent) -> None:
        """窗口关闭：保存窗口几何 → 停止设备连接与线程 → 断开 adb"""
        wx=self.geometry().x()
        wy=self.geometry().y()
        ww=self.geometry().width()
        wh=self.geometry().height()
        WindowGeometry=[wx,wy,ww,wh]
        try:
            settingWrite(WindowGeometry,['changable','windowGeometry'])
        except Exception as e:
            print(f'window geometry save failed: {e}')
        if self.wi1_run.th_operate.device is not None:
            try:
                self.wi1_run.th_operate.device.stop()
            except Exception as e:
                print(f'device stop error: {e}')
        self.th_lst.reverse()
        for th in self.th_lst:
            th.stop()
        super().closeEvent(a0)
        ip=ipGet()
        sysInput(f'adb disconnect {ip}')
#1
class Widget_run(QWidget):

    class Label_SimulatorSelect(QLabel):
        def __init__(self):
            super(Widget_run.Label_SimulatorSelect,self).__init__()
            indexKey_lst=['changable','simulatorIndex']
            index:int=settingRead(indexKey_lst)
            self.simulaterIndexChange(index)

        def simulaterIndexChange(self,index:int):
            simulatorKey_lst=['changable','simulator']
            simulator_lst:list=settingRead(simulatorKey_lst)
            simulatorName_lst:list=[simulator['name'] for simulator in simulator_lst]
            text:str=simulatorName_lst[index]
            self.setText(text)
    
    class Thread_Operate(PauseableThread):
        quitSignal=pyqtSignal()
        stateChanged=pyqtSignal(int)
        nowFightCountChanged=pyqtSignal(int)
        errorDialog=pyqtSignal(str)  # 依赖安装/通道失败等严重错误（GUI 线程弹对话框）
        frameReady=pyqtSignal(object)  # 识别用帧已刷新（GUI 线程更新屏幕预览）

        def __init__(self):
            super(Widget_run.Thread_Operate,self).__init__()
            self.fightCount=settingRead(['changable','again','fightCount'])

            # 惰性构造：Flow_General 涉及大量图像加载(~1.8s)，延迟到 initialAction（点击开始后）
            # 避免 GUI 启动阻塞，也消除与 initialAction 的重复构造
            self.flowGeneral=None
            self.flowAssist=None
            self.flowFight=None
            self.flow_lst=[]

            self.simulatorOperator=None
            self.device=None
            self.minicapScreen=None
            self.adbScreencap=None
            self.la_log:Signal_log=None
            self.la_screen:QLabel=None
            # 屏幕占位图：程序根下 screen.jpeg 不存在时生成纯黑占位，避免 resize 空图像崩溃
            self.screenPath=os.path.join(appRootGet(),'screen.jpeg')
            if not os.path.exists(self.screenPath):
                imwrite(self.screenPath,np.zeros((288,512,3),np.uint8))
            self.qPixMap:QPixmap=QPixmap(self.screenPath)
            self.qImg=QImage(self.screenPath)
            self.ip=ipGet()
            self.currentImg:np.ndarray=imgResize2512(imread(self.screenPath))
            self.currentFrame:np.ndarray=None
            
        def logBind(self,la_log:Signal_log):
            self.la_log=la_log

        def flowImgBind(self):
            self.flowGeneral.currentImgBind(self.currentImg)
            self.flowFight.currentImgBind(self.currentImg)
            self.flowAssist.currentImgBind(self.currentImg)
            if self.currentFrame is not None:
                self.flowGeneral.originalFrameBind(self.currentFrame)
                self.flowFight.originalFrameBind(self.currentFrame)
                self.flowAssist.originalFrameBind(self.currentFrame)

        def laScreenBind(self,la_screen:QLabel):
            self.la_screen=la_screen

        def initialAction(self):
            print('starting script')
            ip=ipGet()
            sysInput(f'adb connect {ip}')       
            self.la_log.log_add('flow/minitouch loading')
            try:
                self.flowGeneral=Flow_General()
                self.flowAssist=self.flowGeneral.state3_assistChoose.flow_assist
                self.flowFight=self.flowGeneral.state5_fight.flow_fight
                self.flow_lst:list[Flow]=[self.flowGeneral,self.flowAssist,self.flowFight]
                self.flowImgBind()
            except Exception as e:
                with open(os.path.join(logDirGet(),'innerLog.txt'),'a',encoding='utf-8') as f:
                    f.write('[flow exception]\n'+traceback.format_exc())
            self.la_log.log_add('flow loaded')
            # 模块加载状态收集（末尾汇总一条「模块加载完成」）
            mntStatus='OK'
            if self.device == None:
                # 运行前依赖检查：minitouch 缺失或版本不符 → 本地推送（避免 pyminitouch 联网下载）
                abi=myGetoutput(f'adb -s {ip} shell getprop ro.product.cpu.abi').strip()
                localMntPath=os.path.join(appRootGet(),'minitouch',abi,'minitouch')
                mntInfo=myGetoutput(f'adb -s {ip} shell ls -l /data/local/tmp/minitouch')
                mntReady=os.path.exists(localMntPath) and len(mntInfo.split())>=5 and mntInfo.split()[4].isdigit() and int(mntInfo.split()[4])==os.path.getsize(localMntPath)
                if not mntReady:
                    ok,err=miniInstall(abi,ip)
                    if ok:
                        self.la_log.log_add('minitouch pushed')
                        mntStatus='pushed'
                    else:
                        # 依赖安装失败：日志 + 对话框报错（避免无提示静默失败后主流程卡死）
                        self.la_log.log_add(f'minitouch install failed: {err}')
                        mntStatus=f'FAIL({err})'
                        self.errorDialog.emit(f'minitouch 安装失败：{err}\n请检查模拟器 adb 连接与本地 minitouch 二进制（minitouch/{abi}/minitouch）。')
                # 清理设备端残留 minitouch 进程（异常退出遗留会占用 socket 导致连接失败）
                sysInput(f'adb -s {ip} shell "kill $(pidof minitouch) 2>/dev/null"')
                time.sleep(0.5)
                self.simulatorOperator=SimulatorOperator()
                self.device=MNTDevice(ip)
                self.simulatorOperator.deviceBind(self.device)

            # 截图通道初始化：按设置页「截图方式」构造（adb截图拉取/mumu专项/雷电专项/夜神专项/minicap）
            try:
                screencapMethod=settingRead(['changable','screencapMethod'])
            except Exception:
                screencapMethod='adb'
            # 兼容旧配置：useMinicap=true 且未设置新字段 → minicap 流式
            if screencapMethod not in ('mumu','ld','nox','minicap','adb','auto'):
                screencapMethod='minicap' if settingRead(['changable','useMinicap']) else 'adb'
            self.screencapMethod=screencapMethod

            # minicap 流式截图：失败自动回退 adb 截图；由「截图方式」=minicap 启用
            # （minicap 虚拟显示在部分模拟器上可能导致 adbd 挂起/掉线，禁用即回到 adb 截图）
            mcStatus='未启用'
            self.minicapScreen=None
            if screencapMethod=='minicap':
                mc=MinicapScreen(ip)
                # 断线自动恢复（拉流线程内完成，不阻塞主循环）；回调经 Signal_log 信号转发到 GUI 线程
                mc.on_lost=lambda err: self.la_log.log_add(f'minicap lost ({err}), auto-recovering...')
                mc.on_recovered=lambda: self.la_log.log_add('minicap recovered')
                if mc.connect():
                    self.minicapScreen=mc
                    mcStatus=f'minicap({mc.arch}/android-{mc.sdk})'
                else:
                    mcStatus='minicap失败，回退adb'
                    self.errorDialog.emit(f'minicap 连接失败：{mc._last_error}\n已回退 adb 截图，可切换「截图方式」为 adb截图拉取。')
                    self.minicapScreen=None

            # adb 截图通道（Maa ScreencapAgent 思路）：按截图方式注册通道，失败自动降级
            # mumu专项=只 mumu 专线+Pull；adb=Raw/Netcat/RawGzip/Encode/Pull 实测排序；auto=全部含专线
            adbStatus='不可用'
            self.adbScreencap=AdbScreencap(ip,self.screenPath,method=screencapMethod)
            if self.adbScreencap.init():
                adbStatus=self.adbScreencap.channelInfo()
            else:
                self.adbScreencap=None

            # 随用随调：状态机识别前经 grabFrame 取帧（不再每轮预截图），识别帧经 onFrame 回显 GUI
            self.flowGeneral.frameBind(self._grabOnce,self._showFrame)

            for flow in self.flow_lst:
                flow.simulatorOperatorBind(self.simulatorOperator)
                flow.logBind(self.la_log)
            # 模块加载汇总（minitouch/flow/截图通道状态一条线）
            methodLabel={'mumu':'mumu专项','ld':'雷电专项','nox':'夜神专项',
                         'minicap':'minicap','adb':'adb截图','auto':'自动'}.get(screencapMethod,screencapMethod)
            mcPart=f'，{mcStatus}' if screencapMethod=='minicap' else ''
            self.la_log.log_add(f'模块加载完成（minitouch {mntStatus}，flow loaded，截图方式：{methodLabel} → {adbStatus}{mcPart}）')
                
        def _grabOnce(self):
            """取一帧 BGR 原分辨率（随用随调）：minicap 流式优先 → adb 多通道 → screencap+pull 兜底"""
            frame=None
            if self.minicapScreen is not None:
                frame=self.minicapScreen.getFrame()
                # 断开/恢复中 → frame 为 None，本轮回退 adb 截图通道；恢复由拉流线程自动完成
            if frame is None and self.adbScreencap is not None:
                frame=self.adbScreencap.grab()
            if frame is None:
                sysInput(f'adb -s {self.ip} shell screencap -p /sdcard/screenshot.jpeg')
                sysInput(f'adb -s {self.ip} pull /sdcard/screenshot.jpeg {self.screenPath}')
                frame=imread(self.screenPath)
            return frame

        def _showFrame(self, frame):
            """识别用帧已刷新：经信号转发到 GUI 线程更新屏幕预览（随用随调，与识图同一帧，零额外截图）"""
            self.frameReady.emit(frame)

        def action(self):
            # 截图由状态机内部按需执行（flow.run 内 _refreshFrame → grabFrame），此处只推进状态机
            self.flowGeneral.run()
            self.stateChanged.emit(self.flowGeneral.state_idx)
            if self.flowGeneral.isQuit:
                self.stop()
            self.nowFightCountChanged.emit(self.flowGeneral.fightCurrentCount)

        def finishAction(self):
            if self.minicapScreen is not None:
                self.minicapScreen.stop()
                self.minicapScreen=None
            if self.adbScreencap is not None:
                self.adbScreencap.stop()  # 释放 mumu 专线连接句柄（nemu_disconnect）
                self.adbScreencap=None
            self.la_log.log_add(f'finished {self.flowGeneral.fightCurrentCount} fights')
            print('totally finished')
            self.quitSignal.emit()
            time.sleep(0.3)

        def stateReset(self):
            self.flowGeneral.state_idx=0

    class Button_ChangeEnable(QPushButton):
        def __init__(self,text:str):
            super(Widget_run.Button_ChangeEnable,self).__init__(text)
        
        def changeEnable(self):
            self.setEnabled(not self.isEnabled())

    class ButtonCouple():
        def __init__(self,startName:str,pauseName:str,resumeName:str,stopName:str,thread_lst:list[PauseableThread]) -> None:
            self.startName=startName
            self.pauseName=pauseName
            self.resumeName=resumeName
            self.stopName=stopName

            self.thread_lst=thread_lst

            self.btn1=Widget_run.Button_ChangeEnable(self.startName)
            self.btn2=Widget_run.Button_ChangeEnable(self.stopName)
            self.initialize()
            self.btn1.clicked.connect(self.btn1ClickedAction)
            self.btn2.clicked.connect(self.btn2ClickedAction)

        def btn1ClickedAction(self):
            self.btn2.setEnabled(True)
            if self.btn1.text()==self.startName:
                [thread.start() for thread in self.thread_lst]
                self.btn1.setText(self.pauseName)
            elif self.btn1.text()==self.pauseName:
                self.pause()
                self.btn1.setText(self.resumeName)
            elif self.btn1.text()==self.resumeName:
                self.resume()
                self.btn1.setText(self.pauseName)

        def btn2ClickedAction(self):
            self.btn2.setEnabled(False)
            self.btn1.setText(self.startName)
            for thread in self.thread_lst:
                if thread._isPause:
                    thread.resume()
                thread.stop()

        def pause(self):
            [thread.pause() for thread in self.thread_lst]

        def resume(self):
            [thread.resume() for thread in self.thread_lst]

        def initialize(self):
            self.btn1.setText(self.startName)
            self.btn2.setText(self.stopName)
            self.btn1.setEnabled(True)
            self.btn2.setEnabled(False)

    def __init__(self) -> None:
        print('Widget_run initializing')
        super(Widget_run,self).__init__()
        self.th_operate=Widget_run.Thread_Operate()

        self.vb1_general = QVBoxLayout()
        self.setLayout(self.vb1_general)

        self.hb1_description  =named_HBLayout ('description'  ,1)
        self.hb2_quickSet     =named_HBLayout ('quickset'     ,2)
        self.hb4_switch       =named_HBLayout ('switch'       ,3)
        self.hb5_screen       =HBox_Screen    ('screen'       ,4)
        self.vb1_general      .addLayout(self.hb1_description )
        self.vb1_general      .addLayout(self.hb2_quickSet    )
        self.vb1_general      .addLayout(self.hb4_switch      )
        self.vb1_general      .addLayout(self.hb5_screen      )#1 4
        self.th_operate.laScreenBind(self.hb5_screen.la1_screen)
        self.sgn_log=Signal_log()
        self.sgn_log.sgn.connect(self.hb5_screen.la22_log.log_add)
        self.th_operate.logBind(self.sgn_log)

#1 1
        self.la11_simulator     =Widget_run.Label_SimulatorSelect()
        self.la12_fightCount    =QLabel()
        self.la13_state         =QLabel()
        self.la14_neighborState =QLabel()
        self.hb1_description  .addWidget(self.la11_simulator)
        self.hb1_description  .addWidget(self.la12_fightCount)
        self.hb1_description  .addWidget(self.la13_state)
        self.hb1_description  .addWidget(self.la14_neighborState)
        self.stateName_lst=stateNameGet()
        self.neighborStateName_lst=neighborStateNameGet()
        self.la13a14_stateUpdate(0)
        self.la12_nowFightCountUpdate(0)
        self.th_operate.stateChanged.connect(self.la13a14_stateUpdate)
        self.th_operate.nowFightCountChanged.connect(self.la12_nowFightCountUpdate)
    
#1 2
        self.la21_quickSet      =QLabel('快捷设置')
        self.la22_strategyChoose=QLabel('策略选择')   
        self.cb23_strategyChoose=GroupBox_Strategy.ComboBox_StrategyChoose()
        self.la24_fightCountt   =QLabel('战斗次数')
        self.le25_fightCount    =GroupBox_Repeat.LineEdit_numCount()
        self.hb2_quickSet     .addStretch(2)
        self.hb2_quickSet     .addWidget(self.la21_quickSet          )
        self.hb2_quickSet     .addStretch(1)
        self.hb2_quickSet     .addWidget(self.la22_strategyChoose    )
        self.hb2_quickSet     .addWidget(self.cb23_strategyChoose    )
        self.hb2_quickSet     .addStretch(1)
        self.hb2_quickSet     .addWidget(self.la24_fightCountt       )
        self.hb2_quickSet     .addWidget(self.le25_fightCount        )
        self.hb2_quickSet     .addStretch(2)

#1 3
        self.btnc43_script=Widget_run.ButtonCouple('脚本开始','脚本暂停','脚本恢复','脚本结束',[self.th_operate])
        self.btn44_logReset=Widget_run.Button_ChangeEnable(text='清空日志')
        self.hb4_switch.addStretch(1)
        self.hb4_switch.addWidget(self.btnc43_script.btn1)
        self.hb4_switch.addWidget(self.btnc43_script.btn2)
        self.hb4_switch.addWidget(self.btn44_logReset)
        self.hb4_switch.addStretch(1)
        self.th_operate.quitSignal.connect(self.btnc43_script.initialize)
        self.th_operate.errorDialog.connect(self._dependencyErrorSlot)
        self.th_operate.frameReady.connect(self._frameReadySlot)
        self.btn44_logReset.clicked.connect(self.hb5_screen.la22_log.log_reset)

        print('Widget_run initializied')

    def _dependencyErrorSlot(self,text:str):
        """依赖安装/通道失败：弹对话框报错（GUI 线程）"""
        QMessageBox.critical(self,'依赖检查失败',text)

    def _frameReadySlot(self,frame):
        """识别帧到达（GUI 线程）：更新屏幕预览"""
        try:
            self.hb5_screen.la1_screen.setPixmap(QPixmap.fromImage(mat2QImage(frame)))
        except Exception:
            pass

    def la12_nowFightCountUpdate(self,idx:int):
        self.la12_fightCount.setText(f'战斗次数： {str(idx)}')

    def la13a14_stateUpdate(self,idx:int):
        self.la13_state.setText(f'状态： {self.stateName_lst[idx]}')
        neighborStateText=''
        if idx==0:
            neighborStateText='all'
        else:
            for neighborStateI in self.neighborStateName_lst[self.stateName_lst[idx]]:
                neighborStateText+=self.stateName_lst[neighborStateI]+'/'
        self.la14_neighborState.setText(f'近邻状态： {neighborStateText}')

#2
class Widget_set(QWidget):

    class setLabel(QLabel):
        labelClicked = pyqtSignal(int) # idx & scrallValue
        def __init__(self,idx:int,name:str, parent=None):
            super(Widget_set.setLabel, self).__init__(parent=parent,text=name)
            self.idx=idx
            
        def mouseReleaseEvent(self, QMouseEvent):
            self.labelClicked.emit(self.idx)

        def select_change(self,idx:int):
            if idx==self.idx:
                self.setStyleSheet("background-color:#888888;")
            else:
                self.setStyleSheet("background:transparent;")
    
    def __init__(self):
        print('Widget_set initializing')
        super(Widget_set, self).__init__()
        self.hbox = QHBoxLayout()
        self.setLayout(self.hbox)

        self.vb_titleLst=QVBoxLayout()
        self.scrollArea_setting=ScrollArea_setting()
        self.hbox.addLayout(self.vb_titleLst)
        self.hbox.addWidget(self.scrollArea_setting)

        # 左侧大模块导航：战斗/模拟器 带子模块；关于/搓丸子 无子模块（点标题直接跳到对应面板）
        self.nmCp_lst:list[str]=['战斗','模拟器','关于','搓丸子']
        self.nmLaList_lst:list[list[str]]=[['策略','助战','多次战斗'],['模拟器'],[],[]]
        self.nmGbIdx_lst:list[int]=[0,3,4,5]   # 各模块对应右侧分组框索引（与 gb_lst 顺序一致）
        self.laList_lst:list[list[Widget_set.setLabel]] =[]
        self.vbNm_lst:list[QVBoxLayout]=[]
        count=0
        for nmLaListI in range(len(self.nmLaList_lst)):
            nmLa_lst=self.nmLaList_lst[nmLaListI]
            la_lst:list[Widget_set.setLabel]=[]
            self.vbNm_lst.append(QVBoxLayout())
            self.vbNm_lst[nmLaListI].setSpacing(10)
            for nmLa in nmLa_lst:
                la_lst.append(Widget_set.setLabel(count,nmLa))
                self.vbNm_lst[nmLaListI].addWidget(la_lst[-1])
                count+=1
            self.laList_lst.append(la_lst)

        self.cp_lst     :list[CollapsibleBox] =[]
        for nmCpI in range(len(self.nmCp_lst)):
            cp=CollapsibleBox(self.nmCp_lst[nmCpI])
            self.vb_titleLst.addWidget(cp)
            if self.nmLaList_lst[nmCpI]:
                cp.setContentLayout(self.vbNm_lst[nmCpI])
            else:
                # 无子模块大模块：隐藏箭头，点标题跳到对应面板，滚动联动高亮
                cp.toggle_button.setArrowType(Qt.NoArrow)
                cp.toggle_button.clicked.connect(
                    lambda _, idx=self.nmGbIdx_lst[nmCpI]: self.scrollArea_setting.setScrollBarValue(idx))
                self.scrollArea_setting.scrolled.connect(
                    lambda idx,y, cp=cp, gbIdx=self.nmGbIdx_lst[nmCpI]: self._bigModuleSelect(cp, idx==gbIdx))
            self.cp_lst.append(cp)
            cp.setFixedWidth(240)
            if self.nmLaList_lst[nmCpI]:
                cp.on_pressed()

        self.vb_titleLst.addStretch(1)
        self.laList_lst[0][0].setStyleSheet("background-color:#888888;")

        # 链接信号与槽
        for la_lst in self.laList_lst:
            for la in la_lst:
                la.labelClicked.connect(self.scrollArea_setting.setScrollBarValue)
                self.scrollArea_setting.scrolled.connect(la.select_change)

        print('Widget_set initializied')

    def _bigModuleSelect(self, cp:CollapsibleBox, selected:bool):
        """无子模块大模块的选中高亮：滚动到对应面板时点亮标题"""
        cp.toggle_button.setChecked(selected)
        cp.toggle_button.setArrowType(Qt.NoArrow)  # 抑制 on_pressed 的箭头副作用（无子模块不显示箭头）
        if selected:
            cp.toggle_button.setStyleSheet("QToolButton { border:none; background-color:#888888; }")
        else:
            cp.toggle_button.setStyleSheet("QToolButton { border: none; }")

class ScrollArea_setting(QScrollArea):
    scrolled=pyqtSignal(int,int)
    def __init__(self,):
        super(ScrollArea_setting, self).__init__()
        self.setWidgetResizable(True)

        self.wid=QWidget()
        self.setWidget(self.wid)
        self.vb=QVBoxLayout()
        self.wid.setLayout(self.vb)
        self.gb_lst:list[QGroupBox]=[]
        self.gb1_strategy=GroupBox_Strategy()
        self.gb2_assist=GroupBox_Assist()
        self.gb3_repeat=GroupBox_Repeat()
        self.gb5_simulator=GroupBox_Simulator()
        self.gb8_about=GroupBox_About()
        self.gb7_clothExperienceFeeding=GroupBox_ClothExperienceFeeding()
        self.gb_lst.append(self.gb1_strategy)
        self.gb_lst.append(self.gb2_assist)
        self.gb_lst.append(self.gb3_repeat)
        self.gb_lst.append(self.gb5_simulator)
        self.gb_lst.append(self.gb8_about)  # 关于 在 搓丸子 前（与左侧导航顺序一致）
        self.gb_lst.append(self.gb7_clothExperienceFeeding)
        for gbi in range(len(self.gb_lst)):
            self.vb.addWidget(self.gb_lst[gbi])

        h_lst=[gb.height() for gb in self.gb_lst]
        self.y_lst:list[int]=[]
        sum=0
        for h in h_lst:
            self.y_lst.append(sum)
            sum+=h

        self._jumpIdx=None  # 导航点击强制高亮目标模块（滚动被视口钳制到不了目标顶时也按目标高亮）
        self._jumpY=None
        self.verticalScrollBar().valueChanged.connect(self.scroll_emit)

    def y_lst_update(self):
        h_lst=[gb.height() for gb in self.gb_lst]
        self.y_lst:list[int]=[]
        sum=0
        for h in h_lst:
            self.y_lst.append(sum)
            sum+=h
        
    def setScrollBarValue(self,idx:int):
        self.y_lst_update()
        sb=self.verticalScrollBar()
        target=min(self.y_lst[idx], sb.maximum())
        self._jumpIdx=idx
        self._jumpY=target
        sb.setValue(target)
        if self._jumpY is not None:
            # setValue 未改变值（已在底部/值相同）→ 不触发 valueChanged，手动补发高亮
            self._jumpIdx=None
            self._jumpY=None
            self.scrolled.emit(idx,target)

    def scroll_emit(self):
        self.y_lst_update()
        y=self.verticalScrollBar().value()
        if self._jumpY is not None and y==self._jumpY:
            idx=self._jumpIdx
            self._jumpIdx=None
            self._jumpY=None
        else:
            idx=self.y2idx(y)
        self.scrolled.emit(idx,y)

    def y2idx(self,y:int):
        self.y_lst_update()
        bool_lst=[y>=y_i for y_i in self.y_lst]
        if False in bool_lst:
            min_false_idx=bool_lst.index(False)
            return min_false_idx-1
        else:
            return len(self.y_lst)-1
#2 1        
class GroupBox_Strategy(QGroupBox):

    class ComboBox_StrategyChoose(QComboBox):
        indexChanged=pyqtSignal(int)
        def __init__(self):
            super(GroupBox_Strategy.ComboBox_StrategyChoose, self).__init__()
            self.itemUpdate()
            self.currentIndexChanged.connect(self.indexChangedEmit)
            
        def itemAdd(self):
            strategy:list=settingRead(['changable','strategy'])
            self.addItem(str(len(strategy))+' '+strategy[-1]['name'])

        def itemRemove(self):
            idx=settingRead(['changable', 'deleteStrategyIdx'])
            print(self.currentIndex(),idx,'!!!')
            if self.count()>0:
                if self.currentIndex()>=idx:
                    self.setCurrentIndex(self.currentIndex()-1)
                self.removeItem(idx)
                self.indexWrite()
            st_lst=settingRead(['changable','strategy'])
            title_lst=[st['name'] for st in st_lst]
            for i in range(idx,self.count()):
                self.setItemText(i, str(i+1)+' '+title_lst[i])

        def indexChangedEmit(self):
            self.indexWrite()
            self.indexChanged.emit(self.currentIndex())
    
        def itemUpdate(self):
            currentStrategyIndex:int=settingRead(['changable','currentStrategyIndex'])
            strategy:list=settingRead(['changable','strategy'])
            if self.count()<len(strategy):
                for i in range(self.count(),len(strategy)):
                    self.addItem(' ')
            elif self.count()>len(strategy):
                if currentStrategyIndex==self.count()-1:
                    currentStrategyIndex-=1
                self.removeItem(self.count()-1)
            self.setCurrentIndex(currentStrategyIndex)
            self.indexWrite()
            for i in range(self.count()):
                self.setItemText(i,(str(i+1)+' '+strategy[i]['name']))

        def indexWrite(self):
            settingWrite(self.currentIndex(),['changable','currentStrategyIndex'])

    deleteSignal=pyqtSignal()
    def __init__(self):
        super(GroupBox_Strategy, self).__init__('策略')
        self.vb_strategy=QVBoxLayout()
        self.setLayout(self.vb_strategy)

        self.hb1_strategyChoose=QHBoxLayout()
        self.hb2_addRemove_btn=QHBoxLayout()
        self.vb_strategy.addLayout(self.hb1_strategyChoose)
        self.vb_strategy.addLayout(self.hb2_addRemove_btn)

        self.la_strategyChoose=QLabel('选择策略')
        self.cb11_strategyChoose=GroupBox_Strategy.ComboBox_StrategyChoose()
        self.hb1_strategyChoose.addWidget(self.la_strategyChoose)
        self.hb1_strategyChoose.addWidget(self.cb11_strategyChoose)
        self.hb1_strategyChoose.addStretch(1)

        self.btn21_add=QPushButton('增添策略')
        self.btn22_remove=QPushButton('删除策略')
        qspIdx=settingRead(['changable','deleteStrategyIdx'])
        self.qspb23_idx=QSpinBox()
        self.qspb23_idx.setMinimum(1)
        self.qspb23_idx.setValue(qspIdx)
        self.qspb23_idx.valueChanged.connect(self.qspIdx_change)
        self.hb2_addRemove_btn.addWidget(self.btn21_add)
        self.hb2_addRemove_btn.addWidget(self.btn22_remove)
        self.hb2_addRemove_btn.addWidget(self.qspb23_idx)
        self.hb2_addRemove_btn.addStretch(1)

        self.cpb3_detail_lst:list[CollapsibleBox_Strategy]=[]
        self.vb31_detail_lst:list[VBoxLayout_Strategy]=[]
        self.strategyPath_lst=['changable','strategy']
        strategy_lst=settingRead(self.strategyPath_lst)
        strategy_num=len(strategy_lst)
        for i in range(strategy_num):
            self.cpb3_detail_lst.append(CollapsibleBox_Strategy(i))
            self.vb_strategy.addWidget(self.cpb3_detail_lst[i])
            self.vb31_detail_lst.append(VBoxLayout_Strategy(i))
            self.cpb3_detail_lst[i].setContentLayout(self.vb31_detail_lst[i])
            self.vb31_detail_lst[i].objectChanged.connect(self.cpb3_detail_lst[i].nameUpdate)
        self.btn21_add.clicked.connect(self.cpbListAdd)
        self.btn22_remove.clicked.connect(self.cpbListRemove)

    def qspIdx_change(self):
        settingWrite(self.qspb23_idx.value(),['changable','deleteStrategyIdx'])

    def assistAdd(self):
        for stI in range(len(self.cpb3_detail_lst)):
            self.vb31_detail_lst[stI].assistAdd()
            
    def assistRemove(self):
        for stI in range(len(self.cpb3_detail_lst)):
            self.vb31_detail_lst[stI].assistRemove()

    def cpbListAdd(self):
        strategy_lst:list=settingRead(self.strategyPath_lst)
        strategy_lst.append(strategy_lst[-1])
        settingWrite(strategy_lst,self.strategyPath_lst)
        assist_lst:list=settingRead(['changable','strategyAssistChoose'])
        assist_lst.append(assist_lst[-1])
        settingWrite(assist_lst,['changable','strategyAssistChoose'])
        self.cpb3_detail_lst.append(CollapsibleBox_Strategy(len(self.cpb3_detail_lst)))
        self.vb_strategy.addWidget(self.cpb3_detail_lst[-1])
        self.vb31_detail_lst.append(VBoxLayout_Strategy(len(self.cpb3_detail_lst)-1))
        self.cpb3_detail_lst[-1].setContentLayout(self.vb31_detail_lst[-1])
        self.vb31_detail_lst[-1].le2_name.textChanged.connect(self.cpb3_detail_lst[-1].nameUpdate)
        self.cb11_strategyChoose.itemUpdate()

    def cpbListRemove(self):
        delIdx=self.qspb23_idx.value()-1
        if delIdx<len(self.cpb3_detail_lst):
            self.cpb3_detail_lst[delIdx].deleteLater()
            self.vb31_detail_lst[delIdx].deleteLater()
            del self.vb31_detail_lst[delIdx]
            del self.cpb3_detail_lst[delIdx]
            strategy_lst:list=settingRead(self.strategyPath_lst)
            strategy_lst.pop(delIdx)
            settingWrite(strategy_lst,self.strategyPath_lst)
            assist_lst:list=settingRead(['changable','strategyAssistChoose'])
            assist_lst.pop(delIdx)
            settingWrite(assist_lst,['changable','strategyAssistChoose'])
            for i in range(delIdx,len(self.cpb3_detail_lst)):
                title=settingRead(['changable','strategy',i,'name'])
                self.vb31_detail_lst[i].idx=i
                for j in range(3):
                    self.vb31_detail_lst[i].hb_3strategyAssist.vbStrategy_lst[j].idx=i
                self.cpb3_detail_lst[i].idx=i
                self.cpb3_detail_lst[i].toggle_button.setText(str(i+1)+' '+title)
            self.cb11_strategyChoose.itemUpdate()
            self.deleteSignal.emit()

# #2 2
# class GroupBox_Assist(QGroupBox):
    
#     def __init__(self):
#         super(GroupBox_Assist,self).__init__('助战')
#         self.vb_assist=QVBoxLayout()
#         self.setLayout(self.vb_assist)

#         self.cb1_isCloth=QCheckBox('是否关心礼装')
#         self.cb1_isCloth.setChecked(settingRead(['changable','isCloth']))
#         self.cb1_isCloth.stateChanged.connect(self.isClothChangeEmit)
#         self.hb2_assistChoose_lst=[]
#         for i in range(3):
#             self.hb2_assistChoose_lst.append(HBoxLayout_AssistChoose(i+1))
#             self.vb_assist.addLayout(self.hb2_assistChoose_lst[i])
#         self.vb_assist.addWidget(self.cb1_isCloth)

#     def isClothChangeEmit(self):
#         settingWrite(self.cb1_isCloth.isChecked(),['changable','isCloth'])

        
#2 2
class GroupBox_Assist(QGroupBox):
    
    def __init__(self):
        super(GroupBox_Assist,self).__init__('助战')
        self.vb_assist=QVBoxLayout()
        self.setLayout(self.vb_assist)

        self.hb2_addRemove_btn=QHBoxLayout()
        
        self.cb1_isCloth=QCheckBox('是否关心礼装')
        self.cb1_isCloth.setChecked(settingRead(['changable','isCloth']))
        self.cb1_isCloth.stateChanged.connect(self.isClothChangeEmit)
        self.vb_assist.addWidget(self.cb1_isCloth)

        self.btn21_add=QPushButton('增添助战')
        self.btn22_remove=QPushButton('删除助战')
        qspIdx=settingRead(['changable','deleteAssistIdx'])
        self.qspb23_idx=QSpinBox()
        self.qspb23_idx.setMinimum(1)
        self.qspb23_idx.setValue(qspIdx)
        self.qspb23_idx.valueChanged.connect(self.qspIdx_change)
        self.hb2_addRemove_btn.addWidget(self.btn21_add)
        self.hb2_addRemove_btn.addWidget(self.btn22_remove)
        self.hb2_addRemove_btn.addWidget(self.qspb23_idx)
        self.hb2_addRemove_btn.addStretch(1)
        self.btn21_add.clicked.connect(self.cpbListAdd)
        self.btn22_remove.clicked.connect(self.cpbListRemove)
        self.vb_assist.addLayout(self.hb2_addRemove_btn)

        self.hb2_assistChoose_lst:list[HBoxLayout_AssistChoose]=[]
        self.count=settingRead(['changable','assistIndex'])
        for i in range(self.count):
            self.hb2_assistChoose_lst.append(HBoxLayout_AssistChoose(i+1))
            self.vb_assist.addLayout(self.hb2_assistChoose_lst[i])

    def qspIdx_change(self):
        settingWrite(self.qspb23_idx.value(),['changable','deleteAssistIdx'])

    def isClothChangeEmit(self):
        settingWrite(self.cb1_isCloth.isChecked(),['changable','isCloth'])
        
    def cpbListAdd(self):
        self.count+=1
        shutil.copy(f'fgoMaterial/assistServant_{self.count-1}.png', f'fgoMaterial/assistServant_{self.count}.png')
        shutil.copy(f'fgoMaterial/assistCloth_{self.count-1}.png', f'fgoMaterial/assistCloth_{self.count}.png')
        self.hb2_assistChoose_lst.append(HBoxLayout_AssistChoose(self.count))
        self.vb_assist.addLayout(self.hb2_assistChoose_lst[-1])
        settingWrite(len(self.hb2_assistChoose_lst),['changable','assistIndex'])
        
    def cpbListRemove(self):
        delIdx=self.qspb23_idx.value()-1
        if delIdx<len(self.hb2_assistChoose_lst):
            self.hb2_assistChoose_lst[delIdx].clear()
            self.vb_assist.removeItem(self.hb2_assistChoose_lst[delIdx])
            del self.hb2_assistChoose_lst[delIdx]
            settingWrite(len(self.hb2_assistChoose_lst),['changable','assistIndex'])
            # 删除素材图（文件可能被手动删过，需容错），并顺次改名补位
            for target in [f'fgoMaterial/assistServant_{delIdx+1}.png',f'fgoMaterial/assistCloth_{delIdx+1}.png']:
                if os.path.exists(target):
                    os.remove(target)
            for i in range(delIdx+1,self.count):
                srcServant=f'fgoMaterial/assistServant_{str(i+1)}.png'
                dstServant=f'fgoMaterial/assistServant_{str(i)}.png'
                srcCloth=f'fgoMaterial/assistCloth_{str(i+1)}.png'
                dstCloth=f'fgoMaterial/assistCloth_{str(i)}.png'
                if os.path.exists(srcServant):
                    os.rename(srcServant,dstServant)
                if os.path.exists(srcCloth):
                    os.rename(srcCloth,dstCloth)
                self.hb2_assistChoose_lst[i-1].la1_name.setText('助战选择'+str(i))
            self.count-=1

#2 3
class GroupBox_Repeat(QGroupBox):

    class LineEdit_numCount(QSpinBox):
        numCountChanged=pyqtSignal()
        def __init__(self):
            super(GroupBox_Repeat.LineEdit_numCount,self).__init__()
            self.textUpdate()
            self.textChanged.connect(self.numCountChangeEmit)
            self.setMinimum(1)
        
        def numCountChangeEmit(self):
            if self.text().isdigit():
                settingWrite(int(self.text()),['changable','again','fightCount'])
                self.numCountChanged.emit()

        def textUpdate(self):
            text=str(settingRead(['changable','again','fightCount']))
            self.setValue(int(text))

    class ComboBox_appleType(QComboBox):
        appleTypeChanged=pyqtSignal()
        def __init__(self) -> None:
            super(GroupBox_Repeat.ComboBox_appleType, self).__init__()
            self.appleName_lst=fixedSettingRead(['fixed','appleNameList'])
            self.addItems(self.appleName_lst)
            self.currentIndexChanged.connect(self.appleTypeChangeEmit)
            index=int(settingRead(['changable','again','appleIndex']))
            self.setCurrentIndex(index)

        def appleTypeChangeEmit(self):
            settingWrite(self.currentIndex(),['changable','again','appleIndex'])
            self.appleTypeChanged.emit()

    def __init__(self):
        super(GroupBox_Repeat,self).__init__('多次战斗')
        self.vb_repeat=QVBoxLayout()
        self.setLayout(self.vb_repeat)

        self.hb2_numCount=QHBoxLayout()
        self.hb3_appleType=QHBoxLayout()
        self.vb_repeat.addLayout(self.hb2_numCount)
        self.vb_repeat.addLayout(self.hb3_appleType)

        self.la21_numCount=QLabel('战斗次数')
        self.le22_numCount=GroupBox_Repeat.LineEdit_numCount()
        self.hb2_numCount.addWidget(self.la21_numCount)
        self.hb2_numCount.addWidget(self.le22_numCount)
        self.hb2_numCount.addStretch(1)
        
        self.la31_appleType=QLabel('苹果类型')
        self.cbb32_appleType=GroupBox_Repeat.ComboBox_appleType()
        self.hb3_appleType.addWidget(self.la31_appleType)
        self.hb3_appleType.addWidget(self.cbb32_appleType)
        self.hb3_appleType.addStretch(1)

#2 4
class GroupBox_Simulator(QGroupBox):

    screenTestResult=pyqtSignal(str)  # 截图测试结果（耗时/通道信息）
    portFound=pyqtSignal(str)         # 自动搜索找到的端口（GUI 线程填输入框）
    searchResult=pyqtSignal(str)      # 自动搜索/添加结果（GUI 线程显示）

    def __init__(self):
        super(GroupBox_Simulator,self).__init__('模拟器')
        self.vb_simulator=QVBoxLayout()
        self.setLayout(self.vb_simulator)

        self.hb3_connectTest=QHBoxLayout()
        self.hb71_simulatorType=QHBoxLayout()
        self.hb6_miniInstall=QHBoxLayout()
        self.vb_simulator.addLayout(self.hb3_connectTest)
        self.vb_simulator.addLayout(self.hb71_simulatorType)
        self.vb_simulator.addLayout(self.hb6_miniInstall)

        # 模拟器链接测试
        self.btn31_connectTest=QPushButton('模拟器链接测试')
        self.la32_connectResult=QLabel('')
        self.hb3_connectTest.addWidget(self.btn31_connectTest)
        self.hb3_connectTest.addStretch(1)
        self.hb3_connectTest.addWidget(self.la32_connectResult)
        self.btn31_connectTest.clicked.connect(self.la32_successConnect)

        # 模拟器类型 + 端口（一行）：类型选择即当前模拟器，端口行在类型行右侧
        self.la71_simulatorType=QLabel('模拟器类型')
        self.cbb72_simulatorType=QComboBox()
        self.cbb72_simulatorType.addItems(['--不选--','mumu','雷电','夜神','逍遥','其他'])
        self.la73_port=QLabel('端口')
        self.le74_port=QLineEdit()
        self.le74_port.setPlaceholderText('127.0.0.1:端口')
        self.hb71_simulatorType.addWidget(self.la71_simulatorType)
        self.hb71_simulatorType.addWidget(self.cbb72_simulatorType)
        self.hb71_simulatorType.addWidget(self.la73_port)
        self.hb71_simulatorType.addWidget(self.le74_port)
        self.hb71_simulatorType.addStretch(1)

        # 二级（初始隐藏）：自动搜索/添加到列表 + 专线配置行（mumu/雷电安装目录+索引）
        self.wid72_typeDetail=QWidget()
        self.vb72_typeDetail=QVBoxLayout(self.wid72_typeDetail)
        self.hb72_typeDetail=QHBoxLayout()
        self.hb73_typeAdd=QHBoxLayout()
        self.wid62_mumu=QWidget()
        self.hb62_mumu=QHBoxLayout(self.wid62_mumu)
        self.wid63_ld=QWidget()
        self.hb63_ld=QHBoxLayout(self.wid63_ld)
        self.vb72_typeDetail.addLayout(self.hb72_typeDetail)
        self.vb72_typeDetail.addLayout(self.hb73_typeAdd)
        self.vb72_typeDetail.addWidget(self.wid62_mumu)
        self.vb72_typeDetail.addWidget(self.wid63_ld)
        # 自动搜索 + 添加到列表
        self.btn75_autoSearch=QPushButton('自动搜索端口')
        self.btn76_addSimulator=QPushButton('添加到列表')
        self.la77_addResult=QLabel('')
        self.hb72_typeDetail.addWidget(self.btn75_autoSearch)
        self.hb72_typeDetail.addWidget(self.btn76_addSimulator)
        self.hb72_typeDetail.addStretch(1)
        self.hb73_typeAdd.addWidget(self.la77_addResult)
        # mumu 专线配置行（mumu 类型时显示）
        self.la62_mumuPath=QLabel('mumu安装目录')
        self.le62_mumuPath=QLineEdit()
        self.btn62_browse=QPushButton('浏览...')
        self.la62_mumuIndex=QLabel('实例索引')
        self.sp62_mumuIndex=QSpinBox()
        self.sp62_mumuIndex.setRange(0,99)
        self.hb62_mumu.addWidget(self.la62_mumuPath)
        self.hb62_mumu.addWidget(self.le62_mumuPath)
        self.hb62_mumu.addWidget(self.btn62_browse)
        self.hb62_mumu.addWidget(self.la62_mumuIndex)
        self.hb62_mumu.addWidget(self.sp62_mumuIndex)
        # 雷电专线配置行（雷电类型时显示；未实测）
        self.la63_ldPath=QLabel('雷电安装目录')
        self.le63_ldPath=QLineEdit()
        self.btn63_browse=QPushButton('浏览...')
        self.la63_ldIndex=QLabel('实例索引')
        self.sp63_ldIndex=QSpinBox()
        self.sp63_ldIndex.setRange(0,99)
        self.hb63_ld.addWidget(self.la63_ldPath)
        self.hb63_ld.addWidget(self.le63_ldPath)
        self.hb63_ld.addWidget(self.btn63_browse)
        self.hb63_ld.addWidget(self.la63_ldIndex)
        self.hb63_ld.addWidget(self.sp63_ldIndex)
        self.vb_simulator.addWidget(self.wid72_typeDetail)
        self.wid72_typeDetail.setVisible(False)
        self._screencapMethods=['adb','minicap']  # 提前赋初值（_simulatorTypeChange 可能先于 rebuild 触发）
        self.cbb72_simulatorType.currentIndexChanged.connect(self._simulatorTypeChange)
        self.le74_port.editingFinished.connect(self._simulatorSync)
        self.btn75_autoSearch.clicked.connect(self.btn75_autoSearchAction)
        self.btn76_addSimulator.clicked.connect(self.btn76_addSimulatorAction)
        self.btn62_browse.clicked.connect(lambda: self._browseDir(self.le62_mumuPath))
        self.btn63_browse.clicked.connect(lambda: self._browseDir(self.le63_ldPath))
        self.portFound.connect(self.le74_port.setText)
        self.searchResult.connect(self.la77_addResult.setText)

        self.vb61_miniInstall=QVBoxLayout()
        self.la63_miniInstallResult=QLabel('')
        self.hb6_miniInstall.addLayout(self.vb61_miniInstall)
        self.hb6_miniInstall.addWidget(self.la63_miniInstallResult)
        self.la63_miniInstallResult.setWordWrap(True)

        # 截图方式选择（持久化到 changable.screencapMethod；items 由模拟器类型过滤，见 _screencapItemsRebuild）
        self.hb61_screencap=QHBoxLayout()
        self.la61_screencapMethod=QLabel('截图方式')
        self.cbb61_screencapMethod=QComboBox()
        self.hb61_screencap.addWidget(self.la61_screencapMethod)
        self.hb61_screencap.addWidget(self.cbb61_screencapMethod)
        self.hb61_screencap.addStretch(1)

        self.btn613_screenTest=QPushButton('截图测试')
        self.btn615_simulatorDiscover=QPushButton('自动发现模拟器')
        self.btn613_screenTest.setFixedWidth(300)
        self.btn615_simulatorDiscover.setFixedWidth(300)
        self.vb61_miniInstall.addLayout(self.hb61_screencap)
        self.vb61_miniInstall.addWidget(self.btn613_screenTest)
        self.vb61_miniInstall.addWidget(self.btn615_simulatorDiscover)
        self.vb61_miniInstall.addStretch(1)
        self.btn613_screenTest.clicked.connect(self.btn613_screenTestAction)
        self.btn615_simulatorDiscover.clicked.connect(self.btn615_simulatorDiscoverAction)
        self.screenTestResult.connect(self.la63_miniInstallResult.setText)

        # 初始化截图方式控件：items 按模拟器类型过滤（专项只显示所选类型）；不写回，用户操作才持久化
        try:
            method=settingRead(['changable','screencapMethod'])
        except Exception:
            method=''
        if method not in ('mumu','ld','nox','minicap','adb'):
            method='adb'
        # 模拟器类型：优先已保存的类型；否则从截图方式推断（专项→对应类型，无专项→不选）
        try:
            savedType=settingRead(['changable','simulatorType'])
        except Exception:
            savedType=''
        typeIdx=0
        if savedType in ('mumu','ld','nox','xiaoyao','other'):
            typeIdx={'mumu':1,'ld':2,'nox':3,'xiaoyao':4,'other':5}[savedType]
        elif method in ('mumu','ld','nox'):
            typeIdx={'mumu':1,'ld':2,'nox':3}[method]
        self.cbb72_simulatorType.setCurrentIndex(typeIdx)
        # 截图方式 items 按类型过滤 + 选中当前（专项与类型不符时回退 adb）
        self._screencapItemsRebuild(typeIdx,method)
        self.cbb61_screencapMethod.currentIndexChanged.connect(self.cbb61_screencapMethodChange)
        try:
            self.le62_mumuPath.setText(settingRead(['changable','mumuPath']) or '')
        except Exception:
            pass
        try:
            self.sp62_mumuIndex.setValue(settingRead(['changable','mumuIndex']) or 0)
        except Exception:
            pass
        try:
            self.le63_ldPath.setText(settingRead(['changable','ldPath']) or '')
        except Exception:
            pass
        try:
            self.sp63_ldIndex.setValue(settingRead(['changable','ldIndex']) or 0)
        except Exception:
            pass
        self.le62_mumuPath.editingFinished.connect(self.le62_mumuPathSave)
        self.sp62_mumuIndex.valueChanged.connect(self.sp62_mumuIndexSave)
        self.le63_ldPath.editingFinished.connect(self.le63_ldPathSave)
        self.sp63_ldIndex.valueChanged.connect(self.sp63_ldIndexSave)
        # 二级区初始显示状态（--不选-- 隐藏）
        self.wid72_typeDetail.setVisible(typeIdx!=0)
        # 初始化端口：优先当前模拟器配置（类型切换已填默认端口）
        try:
            simulator_lst=settingRead(['changable','simulator'])
            index=settingRead(['changable','simulatorIndex'])
            if 0<=index<len(simulator_lst) and simulator_lst[index].get('ip'):
                self.le74_port.setText(simulator_lst[index]['ip'])
        except Exception:
            pass

    def la32_successConnect(self):
        self.la32_connectResult.setText('adb success connect to '+ipGet())

    def _typeName(self) -> str:
        """当前模拟器类型名（'mumu'/'ld'/'nox'/'xiaoyao'/'other'/''=不选）"""
        return {1:'mumu',2:'ld',3:'nox',4:'xiaoyao',5:'other'}.get(self.cbb72_simulatorType.currentIndex(),'')

    def _simulatorTypeChange(self,idx:int):
        """类型切换：显示/隐藏二级配置 + 端口（优先恢复已保存的该类型端口）+ 持久化 + 截图方式按类型过滤"""
        typeName=self._typeName()
        self.wid72_typeDetail.setVisible(idx!=0)
        # 优先恢复已保存的该类型端口（避免切换/重启覆盖用户自定义端口）；无则用默认
        savedPort=''
        try:
            simulator_lst=settingRead(['changable','simulator'])
            curIdx=settingRead(['changable','simulatorIndex'])
            if 0<=curIdx<len(simulator_lst) and simulator_lst[curIdx].get('name')==typeName:
                savedPort=simulator_lst[curIdx].get('ip') or ''
        except Exception:
            pass
        defaultPort=savedPort or {'mumu':'127.0.0.1:16384','ld':'127.0.0.1:5555',
                                  'nox':'127.0.0.1:62001','xiaoyao':'127.0.0.1:21503','other':''}.get(typeName,'')
        if defaultPort:
            self.le74_port.setText(defaultPort)
        else:
            self.le74_port.setPlaceholderText('127.0.0.1:端口')
            self.le74_port.setText('')
        settingWrite(typeName,['changable','simulatorType'])
        # 截图方式过滤重建：当前专项与类型不符时回退 adb（持久化，类型已切换）
        method=self._screencapMethods[self.cbb61_screencapMethod.currentIndex()]
        if method in ('mumu','ld','nox') and method!=typeName:
            method='adb'
            settingWrite(method,['changable','screencapMethod'])
        self._screencapItemsRebuild(idx,method)
        self._simulatorSync()

    def _typeRowsUpdate(self,typeName:str):
        """专线配置行可见性：mumu 行仅 mumu 类型、雷电行仅雷电类型（二级区内）"""
        self.wid62_mumu.setVisible(typeName=='mumu')
        self.wid63_ld.setVisible(typeName=='ld')

    def _simulatorSync(self):
        """类型+端口 → 当前模拟器：写入 changable.simulator（ip 匹配更新名称/无则追加）并选中"""
        typeName=self._typeName()
        if not typeName:
            return
        ip=self.le74_port.text().strip()
        if not ip:
            return
        if ip.isdigit():
            ip=f'127.0.0.1:{ip}'
            self.le74_port.setText(ip)  # 回写 UI，保持输入框与配置一致
        try:
            simulator_lst:list=settingRead(['changable','simulator'])
        except Exception:
            simulator_lst=[]
        idx=None
        for i,s in enumerate(simulator_lst):
            if s.get('ip')==ip:
                idx=i
                if s.get('name')!=typeName:
                    s['name']=typeName
                break
        if idx is None:
            simulator_lst.append({'name':typeName,'ip':ip})
            idx=len(simulator_lst)-1
        settingWrite(simulator_lst,['changable','simulator'])
        settingWrite(idx,['changable','simulatorIndex'])

    def _browseDir(self,lineEdit:QLineEdit):
        """目录选择对话框：填入选中的安装目录（mumu/雷电专线）"""
        from PyQt5.QtWidgets import QFileDialog
        path=QFileDialog.getExistingDirectory(self,'选择模拟器安装目录',lineEdit.text() or '')
        if path:
            lineEdit.setText(path)
            lineEdit.editingFinished.emit()  # 触发保存

    def btn75_autoSearchAction(self):
        """自动搜索端口：按当前模拟器类型匹配已发现的模拟器（adb 设备/常见端口探测/进程）"""
        self.la77_addResult.setText('searching...')
        threading.Thread(target=self._autoSearchThread,daemon=True).start()

    def _autoSearchThread(self):
        try:
            typeName=self._typeName()
            found,procs=discoverSimulators()
            portSet={'mumu':{'16384','7555'},'ld':{'5555'},'nox':{'62001'},
                     'xiaoyao':{'21503'}}.get(typeName)
            match=None
            for sim in found:
                port=sim['ip'].split(':')[-1]
                if portSet is None or port in portSet:
                    match=sim
                    break
            if match:
                self.portFound.emit(match['ip'])
                self.searchResult.emit(f'已找到 {match["name"]} {match["ip"]}')
                self.screenTestResult.emit(f'<font color="yellow">已找到 {typeName or "模拟器"}：{match["name"]} {match["ip"]}</font>')
            else:
                proc_hit=[p for p in procs if (not typeName) or (typeName in p)]
                text='、'.join(proc_hit) if proc_hit else '未找到，请确认模拟器已开启'
                self.searchResult.emit(text)
        except Exception as e:
            self.searchResult.emit(f'搜索异常：{type(e).__name__}: {e}')

    def btn76_addSimulatorAction(self):
        """添加到列表：类型+端口 → 同步当前模拟器（ip 匹配更新/无则追加并选中）"""
        if not self.le74_port.text().strip():
            self.searchResult.emit('请先填写端口或自动搜索')
            return
        self._simulatorSync()
        self.searchResult.emit(f'已添加/更新：{self.le74_port.text().strip()}')

    def _screencapItemsRebuild(self,typeIdx:int,method:str):
        """按模拟器类型重建截图方式下拉（专项只显示所选类型）；不写配置"""
        typeName={1:'mumu',2:'ld',3:'nox'}.get(typeIdx,'')
        if typeName=='mumu':
            items=['adb截图拉取','mumu专项','minicap']; methods=['adb','mumu','minicap']
        elif typeName=='ld':
            items=['adb截图拉取','雷电专项（未测试）','minicap']; methods=['adb','ld','minicap']
        elif typeName=='nox':
            items=['adb截图拉取','夜神专项（未测试）','minicap']; methods=['adb','nox','minicap']
        else:
            items=['adb截图拉取','minicap']; methods=['adb','minicap']
        self._screencapMethods=methods
        self.cbb61_screencapMethod.blockSignals(True)
        self.cbb61_screencapMethod.clear()
        self.cbb61_screencapMethod.addItems(items)
        if method in methods:
            self.cbb61_screencapMethod.setCurrentIndex(methods.index(method))
        else:
            self.cbb61_screencapMethod.setCurrentIndex(0)
        self.cbb61_screencapMethod.blockSignals(False)
        self._typeRowsUpdate(typeName)

    def cbb61_screencapMethodChange(self,idx:int):
        """截图方式切换：持久化 changable.screencapMethod"""
        method=self._screencapMethods[idx]
        settingWrite(method,['changable','screencapMethod'])

    def le62_mumuPathSave(self):
        settingWrite(self.le62_mumuPath.text().strip(),['changable','mumuPath'])

    def sp62_mumuIndexSave(self,val:int):
        settingWrite(val,['changable','mumuIndex'])

    def le63_ldPathSave(self):
        settingWrite(self.le63_ldPath.text().strip(),['changable','ldPath'])

    def sp63_ldIndexSave(self,val:int):
        settingWrite(val,['changable','ldIndex'])

    def btn615_simulatorDiscoverAction(self):
        """自动发现模拟器：adb 已连接设备 + 常见端口探测 + 进程识别，结果并入模拟器列表"""
        self.la63_miniInstallResult.setText('discovering simulators...')
        threading.Thread(target=self._discoverThread,daemon=True).start()

    def _discoverThread(self):
        try:
            found,procs=discoverSimulators()
        except Exception as e:
            self.screenTestResult.emit(f'<font color="red">自动发现异常：{type(e).__name__}: {e}</font>')
            return
        # 与现有列表去重后追加（新发现的 ip 已在配置中则跳过）
        simulator_lst:list=settingRead(['changable','simulator'])
        exist_ips={s.get('ip') for s in simulator_lst}
        added=[]
        for sim in found:
            if sim['ip'] not in exist_ips:
                simulator_lst.append(sim)
                exist_ips.add(sim['ip'])
                added.append(f"{sim['name']} ({sim['ip']})")
        if added:
            settingWrite(simulator_lst,['changable','simulator'])
        procs_text='、'.join(procs) if procs else '（未检测到模拟器进程）'
        added_text='、'.join(added) if added else '（无新增）'
        self.screenTestResult.emit(
            f'<font color="white">自动发现完成</font><br/>'
            f'<font color="yellow">新增：{added_text}</font><br/>'
            f'<font color="white">检测到进程：{procs_text}</font>')

    def btn613_screenTestAction(self):
        """截图测试：按当前「截图方式」截一帧并显示耗时（后台线程）"""
        self.la63_miniInstallResult.setText('screenshot test running...')
        threading.Thread(target=self._screenTestThread,daemon=True).start()

    def _screenTestThread(self):
        """按当前截图方式实测一帧耗时：mumu专项=专线直读；minicap=流式首帧；adb=多通道测速排序"""
        ip=ipGet()
        sysInput('adb connect '+ip)
        try:
            method=settingRead(['changable','screencapMethod'])
        except Exception:
            method='adb'
        t0=time.perf_counter()
        try:
            if method=='mumu':
                try:
                    path=settingRead(['changable','mumuPath']) or ''
                except Exception:
                    path=''
                try:
                    index=settingRead(['changable','mumuIndex']) or 0
                except Exception:
                    index=0
                mumu=MuMuScreencap(path,index)
                if not mumu.init():
                    self.screenTestResult.emit(f'<font color="red">mumu 专项初始化失败：{mumu.lastErr()}</font>')
                    return
                img=mumu.grab()
                mumu.stop()
                if img is None:
                    self.screenTestResult.emit(f'<font color="red">mumu 专项截图失败：{mumu.lastErr()}</font>')
                    return
                cost=(time.perf_counter()-t0)*1000
                self.screenTestResult.emit(f'<font color="white">mumu专项 OK（{img.shape[1]}×{img.shape[0]}）</font><br/>'
                                           f'<font color="yellow">单帧耗时 {cost:.1f} ms</font>')
            elif method=='minicap':
                mc=MinicapScreen(ip)
                if not mc.connect():
                    self.screenTestResult.emit(f'<font color="red">minicap 连接失败：{mc._last_error}</font>')
                    return
                frame=None
                deadline=time.time()+5
                while time.time()<deadline and frame is None:
                    frame=mc.getFrame()
                    time.sleep(0.005)
                cost=(time.perf_counter()-t0)*1000
                mc.stop()
                if frame is None:
                    self.screenTestResult.emit(f'<font color="red">minicap 5s 内未收到帧</font>')
                    return
                self.screenTestResult.emit(f'<font color="white">minicap OK（{mc.arch}/android-{mc.sdk}）</font><br/>'
                                           f'<font color="yellow">首帧耗时 {cost:.1f} ms（流式后续帧更快）</font>')
            elif method in ('ld','nox'):
                # 专线方式：经 AdbScreencap(method=对应值) 实测（含通道排序信息）
                cap=AdbScreencap(ip,os.path.join(appRootGet(),'screen.jpeg'),method=method)
                if not cap.init():
                    self.screenTestResult.emit(f'<font color="red">{method} 专线不可用（详见日志）</font>')
                    return
                img=cap.grab()
                cost=(time.perf_counter()-t0)*1000
                cap.stop()
                if img is None:
                    self.screenTestResult.emit(f'<font color="red">{method} 专线截图失败（详见日志）</font>')
                    return
                tag={'ld':'雷电专项（未测试）','nox':'夜神专项（未测试）'}[method]
                self.screenTestResult.emit(f'<font color="white">{tag} OK（{img.shape[1]}×{img.shape[0]}）</font><br/>'
                                           f'<font color="yellow">通道排序：{cap.channelInfo()}</font><br/>'
                                           f'<font color="yellow">单帧耗时 {cost:.1f} ms</font>')
            else:
                cap=AdbScreencap(ip,os.path.join(appRootGet(),'screen.jpeg'),method='adb')
                if not cap.init():
                    self.screenTestResult.emit(f'<font color="red">adb 截图通道不可用</font>')
                    return
                img=cap.grab()
                cost=(time.perf_counter()-t0)*1000
                cap.stop()
                if img is None:
                    self.screenTestResult.emit(f'<font color="red">adb 截图失败</font>')
                    return
                self.screenTestResult.emit(f'<font color="white">adb截图 OK（{img.shape[1]}×{img.shape[0]}）</font><br/>'
                                           f'<font color="yellow">通道排序：{cap.channelInfo()}</font><br/>'
                                           f'<font color="yellow">单帧耗时 {cost:.1f} ms（已含测速）</font>')
        except Exception as e:
            self.screenTestResult.emit(f'<font color="red">截图测试异常：{type(e).__name__}: {e}</font>')

#2 5
class GroupBox_About(QGroupBox):
    """关于模块：检查更新（GitHub 增量）+ 反馈问题（issue 预填）+ 版本信息

    与模拟器无关，独立于模拟器模块之外。
    """
    updateCheckResult=pyqtSignal(str,str)   # (最新版本, 当前版本)
    updateLog=pyqtSignal(str)
    updateApplied=pyqtSignal(str)           # (新版本) 下载已就绪，提示关闭程序

    def __init__(self):
        super(GroupBox_About,self).__init__('关于')
        self.vb_about=QVBoxLayout()
        self.setLayout(self.vb_about)

        self.la_aboutVersion=QLabel('AFS ver'+Updater.localVersion())
        self.btn614_updateCheck=QPushButton('检查更新(GitHub)')
        self.la64_updateResult=QLabel('')
        self.la64_updateResult.setWordWrap(True)
        self.btn616_feedback=QPushButton('反馈问题')
        self.btn614_updateCheck.setFixedSize(480,48)  # 加大：文字在真实字体下需要更宽（原 300 会截断）
        self.btn616_feedback.setFixedSize(480,48)
        self.vb_about.addWidget(self.la_aboutVersion)
        self.vb_about.addWidget(self.btn614_updateCheck)
        self.vb_about.addWidget(self.la64_updateResult)
        self.vb_about.addWidget(self.btn616_feedback)
        self.vb_about.addStretch(1)
        self.btn614_updateCheck.clicked.connect(self.btn614_updateCheckAction)
        self.btn616_feedback.clicked.connect(self.btn616_feedbackAction)
        self.updateCheckResult.connect(self.updateCheckSlot)
        self.updateLog.connect(self.la64_updateResult.setText)
        self.updateApplied.connect(self.updateAppliedSlot)

    # ------------------------------------------------------------------ 检查更新（GitHub，MaaUpdater 思路）

    def _updateRepoGet(self) -> str:
        """读取更新仓库配置 fixed.update.repo（owner/name，空=禁用）"""
        try:
            return str(fixedSettingRead(['fixed','update','repo']) or '').strip().strip('/')
        except Exception:
            return ''

    def btn614_updateCheckAction(self):
        repo=self._updateRepoGet()
        if not repo:
            self.la64_updateResult.setText('未配置更新仓库：请编辑 configure/settingFixed.json 的 fixed.update.repo（格式 owner/仓库名）')
            return
        self.la64_updateResult.setText('checking update...')
        threading.Thread(target=self._updateCheckThread,args=(repo,),daemon=True).start()

    def _updateCheckThread(self,repo:str):
        try:
            latest=Updater(repo).check()['version']
        except Exception as e:
            self.updateLog.emit(f'<font color="red">check failed: {type(e).__name__}: {e}</font>')
            return
        self.updateCheckResult.emit(latest,Updater.localVersion())

    def updateCheckSlot(self,latest:str,current:str):
        """检查结果（GUI 线程）：有新版本则询问下载"""
        cmp=compareVersion(latest,current)
        if cmp<=0:
            self.la64_updateResult.setText(f'已是最新版本 v{current}（仓库 v{latest}）')
            return
        ret=QMessageBox.question(self,f'发现新版本 v{latest}（当前 v{current}）',
                                 '是否下载增量更新包？下载完成后将自动关闭本程序，完成更新并自动重启。',
                                 QMessageBox.Yes|QMessageBox.No,QMessageBox.Yes)
        if ret!=QMessageBox.Yes:
            return
        repo=self._updateRepoGet()
        self.la64_updateResult.setText(f'downloading v{latest}...')
        threading.Thread(target=self._updateDownloadThread,args=(repo,latest),daemon=True).start()

    def _updateDownloadThread(self,repo:str,version:str):
        """后台下载+校验+解压到 update_pending，成功后发信号由 GUI 线程启动落地脚本"""
        def onLog(text:str):
            self.updateLog.emit(f'<font color="white">{text}</font>')
        try:
            updater=Updater(repo)
            kind=updater.apply(version,on_log=onLog)
            self.updateLog.emit(f'<font color="green">v{version} 已就绪（{kind}包），关闭程序后自动完成更新并重启</font>')
            self.updateApplied.emit(version)
        except Exception as e:
            self.updateLog.emit(f'<font color="red">update failed: {type(e).__name__}: {e}</font>')

    def updateAppliedSlot(self,version:str):
        """更新包已就绪（GUI 线程）：启动落地脚本，3 秒后自动关闭本程序
        （apply_update.bat 等待 AFS.exe 退出后覆盖文件并自动重启）"""
        os.startfile(os.path.join(appRootGet(),'apply_update.bat'))
        QMessageBox.information(self,'更新已就绪',
                                f'v{version} 更新包已下载并校验完成。\n本程序将在 3 秒后自动关闭，更新完成后自动重新启动。')
        QTimer.singleShot(3000,self._autoCloseForUpdate)

    def _autoCloseForUpdate(self):
        """自动关闭窗口：closeEvent 会保存窗口几何/停线程/断 adb，随后 bat 接管更新与重启"""
        win=self.window()
        if win is not None:
            win.close()

    # ------------------------------------------------------------------ 反馈问题

    def btn616_feedbackAction(self):
        """反馈问题：收集版本/截图方式/模拟器/日志尾部 → 打开 GitHub issue 新建页（预填内容）"""
        from urllib.parse import quote
        try:
            version=Updater.localVersion()
            method=settingRead(['changable','screencapMethod'])
        except Exception:
            version='?'; method='?'
        try:
            ip=ipGet()
        except Exception:
            ip='?'
        log_tail='（无日志）'
        try:
            log_path=os.path.join(logDirGet(),'innerLog.txt')
            if os.path.exists(log_path):
                with open(log_path,'r',encoding='utf-8',errors='ignore') as f:
                    log_tail='\n'.join(f.readlines()[-40:])
        except Exception:
            pass
        body=(f'**版本**：{version}\n'
              f'**截图方式**：{method}\n'
              f'**模拟器**：{ip}\n\n'
              f'**问题描述**：\n（请补充复现步骤）\n\n'
              f'**日志尾部**（logs/innerLog.txt）：\n```\n{log_tail}\n```')
        url=('https://github.com/qcfei/AFS/issues/new'
             f'?title={quote(f"AFS 报错反馈（{version}）")}&body={quote(body)}')
        os.startfile(url)

class GroupBox_ClothExperienceFeeding(QGroupBox):

    def __init__(self):
        super(GroupBox_ClothExperienceFeeding,self).__init__('搓丸子')
        self.vb_clothExperienceFeeding=QVBoxLayout()
        self.setLayout(self.vb_clothExperienceFeeding)

        self.hb1_set=QLabel('waiting for updating')
        self.vb_clothExperienceFeeding.addWidget(self.hb1_set)
