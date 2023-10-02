# 原生库
from PyQt5.QtWidgets import *
from PyQt5.QtGui import *
from PyQt5.QtCore import Qt,pyqtSignal,QRect
import win32gui
import time
from pyminitouch import MNTDevice

# 自制库
from pytool.basicQObject import *
from pytool.pauseableThread import *
from pytool.flow import *
from pytool.minicap import *

class TabWidgt_Total(QTabWidget):
    def __init__(self) -> None:
        print('TabWidgt_Total initializing')
        super(QTabWidget,self).__init__()
        self.setStyleSheet('font-size: 13pt;style=line-height:200%;color:white;')
        WindowGeometry=settingRead(['fixed','WindowGeometry'])
        wx,wy,ww,wh=WindowGeometry
        self.setGeometry(wx,wy,ww,wh)
        self.setWindowTitle('AFS ver1.0.2')
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
        gbStrategy2.btn21_add.clicked.connect(cbStrategy1.itemAdd)
        gbStrategy2.btn22_remove.clicked.connect(cbStrategy1.itemRemove)
        cbStrategy1.indexChanged.connect(cbStrategy2.setCurrentIndex)
        cbStrategy2.indexChanged.connect(cbStrategy1.setCurrentIndex)
        gbStrategy2.btn21_add.clicked.connect(self.lastVbDetailConnect)

        laSimulatorSelect=self.wi1_run.la11_simulator
        cbSimulatorSelect=self.wi2_setting.scrollArea_setting.gb5_simulator.cbb12_simulatorChoose
        cbSimulatorSelect.simulatorIndexChange.connect(laSimulatorSelect.simulaterIndexChange)

        leFightCount1=self.wi1_run.le25_fightCount
        leFightCount2=self.wi2_setting.scrollArea_setting.gb3_repeat.le22_numCount
        leFightCount1.numCountChanged.connect(leFightCount2.textUpdate)
        leFightCount2.numCountChanged.connect(leFightCount1.textUpdate)

        servantIconSignal=self.wi1_run.th_operate.servantIconChanged
        servantIconSignal.connect(self.wi2_setting.scrollArea_setting.gb4_checkServantIcon.servantIconUpdate)

        print('TabWidgt_Total initializied')

    def vbDetailConnect(self,vbDetailI:int):
        gbStrategy2=self.wi2_setting.scrollArea_setting.gb1_strategy
        cbStrategy1=self.wi1_run.cb23_strategyChoose
        cbStrategy2=gbStrategy2.cb11_strategyChoose
        vbDetail_lst=gbStrategy2.vb31_detail_lst
        vbDetail_lst[vbDetailI].objectChanged.connect(cbStrategy1.itemUpdate)
        vbDetail_lst[vbDetailI].objectChanged.connect(cbStrategy2.itemUpdate)

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
        wx=self.geometry().x()
        wy=self.geometry().y()
        ww=self.geometry().width()
        wh=self.geometry().height()
        WindowGeometry=[wx,wy,ww,wh]
        settingWrite(WindowGeometry,['fixed','WindowGeometry'])
        if self.wi1_run.th_operate.device is not None:
            self.wi1_run.th_operate.device.stop()
        super().closeEvent(a0)
        ip=ipGet()
        sysInput(f'adb disconnect {ip}')
        devicesInfo=subprocess.getoutput('adb devices')
        if re.findall(r'\d+',devicesInfo)==[]:
            sysInput('adb kill-server')

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
    
    class Thread_MinicapSocket(PauseableThread):
        def __init__(self):
            super(Widget_run.Thread_MinicapSocket,self).__init__()

        def initialAction(self):
            ip=ipGet()
            dpi=subprocess.getoutput(f'adb -s {ip} shell wm size')
            if not ('notfound' in dpi):
                dpiX,dpiY=[int(dpii) for dpii in re.findall(r'\d+',dpi)]
            sysInput(f'adb forward tcp:1717 localabstract:minicap')
            sysInput(f'adb -s {ip} shell LD_LIBRARY_PATH=/data/local/tmp /data/local/tmp/minicap -Q 40 -P {dpiX}x{dpiY}@{dpiX}x{dpiY}/0')

    class Thread_GraphicCapture(PauseableThread):
        
        def __init__(self):
            super(Widget_run.Thread_GraphicCapture,self).__init__() 
            self.th_minicapSocket=Widget_run.Thread_MinicapSocket()
            self.captureMethod:int=None
            self.la_log:Signal_log=None
            self.qImg=QImage('screen.jpeg')

        def methodUpdate(self):
            self.simulatorIndex=settingRead(['changable','simulatorIndex'])
            self.captureMethod:int=settingRead(['changable','simulator',self.simulatorIndex,'captureMethod'])
            self.captureRect:list[int]=settingRead(['changable','simulator',self.simulatorIndex,'captureRect'])

        def logBind(self,la_log:Signal_log):
            self.la_log=la_log

        def initialAction(self):
            print('starting graphic capture')
            self.methodUpdate()
            if self.captureMethod==0:
                self.la_log.log_add(f'minicap loading')
                ip=ipGet()
                sysInput(f'adb connect {ip}')       
                self.mc = Minicap('localhost', 1717, Banner())
                self.th_minicapSocket.start()
                time.sleep(1)
                self.mc.connect()
                self.la_log.log_add(f'minicap loaded')
            if self.captureMethod==1:
                self.windowsTitle:str=settingRead(['changable','simulator',self.simulatorIndex,'windowsTitle'])
                self.screen = QApplication.primaryScreen()
                self.hwnd=win32gui.FindWindow(None,self.windowsTitle)

        def action(self):
            if self.captureMethod==1:
                if self.hwnd:
                    qImg = self.screen.grabWindow(self.hwnd).toImage()
                    x,y,w,h=self.captureRect
                    qImg=qImg.copy(QRect(x,y,w,h))
                    self.qImg=qImg
                    qImg.save("screen.jpeg")
                time.sleep(0.05)
            elif self.captureMethod==0:
                f=self.mc.consume()
                if f:
                    self.qImg=QImage('screen.jpeg')

        def finalAction(self):
            if self.captureMethod==0:
                self.la_log.log_add('mincap stopped')
                self.mc.disconnect()
                ip=ipGet()
                sysInput(f'adb disconnect {ip}')
                self.th_minicapSocket.stop()

    class Thread_LaScreenImgUpdate(PauseableThread):
        def __init__(self):
            super(Widget_run.Thread_LaScreenImgUpdate,self).__init__()
            self.la_screen:QLabel=None
            self.th_graphicCapture:Widget_run.Thread_GraphicCapture=None
            self.qPixMap:QPixmap=QPixmap('screen.jpeg')
            
        def threadBind(self,th_graphicCapture:PauseableThread):
            self.th_graphicCapture=th_graphicCapture
        
        def laScreenBind(self,la_screen:QLabel):
            self.la_screen=la_screen

        def action(self):
            self.qPixMap=QPixmap.fromImage(self.th_graphicCapture.qImg)
            self.la_screen.setPixmap(self.qPixMap)
            time.sleep(0.15)

    class Thread_Operate(PauseableThread):
        quitSignal=pyqtSignal()
        stateChanged=pyqtSignal(int)
        nowFightCountChanged=pyqtSignal(int)
        servantIconChanged=pyqtSignal()

        def __init__(self):
            super(Widget_run.Thread_Operate,self).__init__()
            self.fightCount=settingRead(['changable','again','fightCount'])
            self.th_graphicCapture:Widget_run.Thread_GraphicCapture=None

            self.flowGeneral=Flow_General()
            self.flowAssist=self.flowGeneral.state3_assistChoose.flow_assist
            self.flowFight=self.flowGeneral.state5_fight.flow_fight
            self.flow_lst=[self.flowGeneral,self.flowAssist,self.flowFight]

            self.simulatorOperator=None
            self.device=None
            self.la_log:Signal_log=None
            self.currentImg:np.ndarray=imgResize2512(cv2.imread('screen.jpeg'))
            
        def threadBind(self,th_graphicCapture:PauseableThread):
            self.th_graphicCapture=th_graphicCapture

        def logBind(self,la_log:Signal_log):
            self.la_log=la_log

        def flowImgBind(self):
            self.flowGeneral.currentImgBind(self.currentImg)
            self.flowFight.currentImgBind(self.currentImg)
            self.flowAssist.currentImgBind(self.currentImg)

        def initialAction(self):
            print('starting script')
            self.la_log.log_add('flow/minitouch loading')
            try:
                self.flowGeneral=Flow_General()
                self.flowAssist=self.flowGeneral.state3_assistChoose.flow_assist
                self.flowFight=self.flowGeneral.state5_fight.flow_fight
                self.flow_lst:list[Flow]=[self.flowGeneral,self.flowAssist,self.flowFight]
                self.flowImgBind()
            except Exception as e:
                # self.la_log.log_add(f'flow/minitouch load failed: {e}')
                open('log.txt','+w').write(str(e))
            self.la_log.log_add('flow loaded')
            if self.device == None:
                self.simulatorOperator=SimulatorOperator()
                _DEVICE_ID=ipGet()
                self.device=MNTDevice(_DEVICE_ID)
                self.simulatorOperator.deviceBind(self.device)
            self.la_log.log_add('minitouch loaded')

            for flow in self.flow_lst:
                flow.simulatorOperatorBind(self.simulatorOperator)
                flow.logBind(self.la_log)
                
        def action(self):
            self.currentImg=imgResize2512(qImg2Mat(self.th_graphicCapture.qImg))
            self.flowImgBind()
            self.flowGeneral.run()
            self.stateChanged.emit(self.flowGeneral.state_idx)
            if self.flowGeneral.isQuit:
                self.stop()
            self.nowFightCountChanged.emit(self.flowGeneral.fightCurrentCount)
            if self.flowGeneral.state4_prepare.progress==5:
                self.servantIconChanged.emit()

        def finishAction(self):
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
            [thread.stop() for thread in self.thread_lst]

        def pause(self):
            [thread.pause() for thread in self.thread_lst]

        def resume(self):
            [thread.resume() for thread in self.thread_lst]

        def initialize(self):
            self.btn1.setText(self.startName)
            self.btn2.setText(self.stopName)
            self.btn1.setEnabled(True)
            self.btn2.setEnabled(False)

    class ButtonCouple_Operator(ButtonCouple):
        def __init__(self,thread:PauseableThread) -> None:
            super(Widget_run.ButtonCouple_Operator,self).__init__('脚本开始','脚本暂停','脚本恢复','脚本结束',[thread])

        # def pause(self):
        #     [thread.pause() for thread in self.thread_lst]

        # def resume(self):
        #     [thread.resume() for thread in self.thread_lst]

    def __init__(self) -> None:
        print('Widget_run initializing')
        super(Widget_run,self).__init__()
        self.th_graphicCapture=Widget_run.Thread_GraphicCapture()
        self.th_operate=Widget_run.Thread_Operate()
        self.th_laScreenImgUpdate=Widget_run.Thread_LaScreenImgUpdate()
        self.th_operate.threadBind(self.th_graphicCapture)
        self.th_laScreenImgUpdate.threadBind(self.th_graphicCapture)

        self.vb1_general = QVBoxLayout()
        self.setLayout(self.vb1_general)

        self.hb1_description  =named_HBLayout ('description'  ,1)
        self.hb2_quickSet     =named_HBLayout ('quickset'     ,2)
        # self.hb3_testBtn      =named_HBLayout ('testBtn'      ,3)
        self.hb4_switch       =named_HBLayout ('switch'       ,4)
        self.hb5_screen       =HBox_Screen    ('screen'       ,5)
        self.vb1_general      .addLayout(self.hb1_description )
        self.vb1_general      .addLayout(self.hb2_quickSet    )
        # self.vb1_general      .addLayout(self.hb3_testBtn     )
        self.vb1_general      .addLayout(self.hb4_switch      )
        self.vb1_general      .addLayout(self.hb5_screen      )
        self.th_laScreenImgUpdate.laScreenBind(self.hb5_screen.la1_screen)
        self.sgn_log=Signal_log()
        self.sgn_log.sgn.connect(self.hb5_screen.la22_log.log_add)
        self.th_operate.logBind(self.sgn_log)
        self.th_graphicCapture.logBind(self.sgn_log)

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
    
        self.la21_quickSet      =QLabel('快捷设置：')
        self.la22_strategyChoose=QLabel('策略选择')   
        self.cb23_strategyChoose=GroupBox_Strategy.ComboBox_StrategyChoose()
        self.la24_fightCountt   =QLabel('战斗次数')
        self.le25_fightCount    =GroupBox_Repeat.LineEdit_numCount()
        self.hb2_quickSet     .addStretch(1)
        self.hb2_quickSet     .addWidget(self.la21_quickSet          )
        self.hb2_quickSet     .addWidget(self.la22_strategyChoose    )
        self.hb2_quickSet     .addWidget(self.cb23_strategyChoose    )
        self.hb2_quickSet     .addWidget(self.la24_fightCountt       )
        self.hb2_quickSet     .addWidget(self.le25_fightCount        )
        self.hb2_quickSet     .addStretch(1)

        # self.btn32_test         =QPushButton('test')
        # self.hb3_testBtn      .addStretch(1)
        # self.hb3_testBtn      .addWidget(self.btn32_test)
        # self.hb3_testBtn      .addStretch(1)
        # self.btn32_test.clicked.connect(self.test)
        
        self.btnc41_connect=Widget_run.ButtonCouple('连接开始','连接暂停','连接恢复','连接结束',[self.th_graphicCapture,self.th_laScreenImgUpdate])
        self.btn42_stateReset=Widget_run.Button_ChangeEnable(text='状态重置')
        self.btnc43_script=Widget_run.ButtonCouple_Operator(self.th_operate)
        self.btn44_logReset=Widget_run.Button_ChangeEnable(text='清空日志')
        self.hb4_switch.addStretch(1)
        self.hb4_switch.addWidget(self.btnc41_connect.btn1)
        self.hb4_switch.addWidget(self.btnc41_connect.btn2)
        self.hb4_switch.addWidget(self.btn42_stateReset)
        self.hb4_switch.addWidget(self.btnc43_script.btn1)
        self.hb4_switch.addWidget(self.btnc43_script.btn2)
        self.hb4_switch.addWidget(self.btn44_logReset)
        self.hb4_switch.addStretch(1)
        self.th_operate.quitSignal.connect(self.btnc43_script.initialize)
        self.btn42_stateReset.clicked.connect(self.th_operate.stateReset)
        self.btn44_logReset.clicked.connect(self.hb5_screen.la22_log.log_reset)

        print('Widget_run initializied')
        
    # def test(self):
    #     self.hb5_screen.la22_log.log_add('aaa')

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
        
        self.laList_lst:list[list[Widget_set.setLabel]] =[]
        self.vbNm_lst:list[QVBoxLayout]=[]
        self.nmLaList_lst:list[str]=[['策略','助战','多次战斗','指令卡形象'],['模拟器','窗口捕获'],['搓丸子']]
        count=0
        for nmLa_lstI in range(len(self.nmLaList_lst)):
            nmLa_lst=self.nmLaList_lst[nmLa_lstI]
            la_lst:list[Widget_set.setLabel]=[]
            self.vbNm_lst.append(QVBoxLayout())
            self.vbNm_lst[nmLa_lstI].setSpacing(10)
            for nmLa in nmLa_lst:
                la_lst.append(Widget_set.setLabel(count,nmLa))
                self.vbNm_lst[nmLa_lstI].addWidget(la_lst[-1])
                count+=1
            self.laList_lst.append(la_lst)

        self.cp_lst     :list[CollapsibleBox] =[]
        self.nmCp_lst:list[str]=['战斗','模拟器','搓丸子']
        for nmCpI in range(len(self.nmCp_lst)):
            self.cp_lst.append(CollapsibleBox(self.nmCp_lst[nmCpI]))
            self.vb_titleLst.addWidget(self.cp_lst[nmCpI])
            self.cp_lst[nmCpI].setContentLayout(self.vbNm_lst[nmCpI])
            self.cp_lst[nmCpI].setFixedWidth(200)
            self.cp_lst[nmCpI].setFixedHeight(40)
            self.cp_lst[nmCpI].on_pressed()

        self.vb_titleLst.addStretch(1)
        self.laList_lst[0][0].setStyleSheet("background-color:#888888;")

        # 链接信号与槽
        for la_lst in self.laList_lst:
            for la in la_lst:
                la.labelClicked.connect(self.scrollArea_setting.setScrollBarValue)
                self.scrollArea_setting.scrolled.connect(la.select_change)
                
        print('Widget_set initializied')

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
        self.gb4_checkServantIcon=GroupBox_CheckServantIcon()
        self.gb5_simulator=GroupBox_Simulator()
        self.gb6_captureMethod=GroupBox_CaptureMethod()
        self.gb7_clothExperienceFeeding=GroupBox_ClothExperienceFeeding()
        self.gb_lst.append(self.gb1_strategy)
        self.gb_lst.append(self.gb2_assist)
        self.gb_lst.append(self.gb3_repeat)
        self.gb_lst.append(self.gb4_checkServantIcon)
        self.gb_lst.append(self.gb5_simulator)
        self.gb_lst.append(self.gb6_captureMethod)
        self.gb_lst.append(self.gb7_clothExperienceFeeding)
        for gbi in range(len(self.gb_lst)):
            self.vb.addWidget(self.gb_lst[gbi])

        h_lst=[gb.height() for gb in self.gb_lst]
        self.y_lst:list[int]=[]
        sum=0
        for h in h_lst:
            self.y_lst.append(sum)
            sum+=h

        self.verticalScrollBar().valueChanged.connect(self.scroll_emit)

        cbb1=self.gb5_simulator.cbb12_simulatorChoose
        cbb2=self.gb5_simulator.cbb52_simulatorName
        cbb3=self.gb6_captureMethod.hb1_copyFrom.cbb2_simulatorChoose
        cbb_lst=[cbb1,cbb2,cbb3]
        btn1=self.gb5_simulator.btn41_simulatorAdd
        btn2=self.gb5_simulator.btn51_simulatorRemove
        btn_lst=[btn1,btn2]
        for btn in btn_lst:
            for cbb in cbb_lst:
                btn.clicked.connect(cbb.itemUpdate)
        cbb1.currentIndexChanged.connect(self.gb6_captureMethod.selfUpdate)

    def y_lst_update(self):
        h_lst=[gb.height() for gb in self.gb_lst]
        self.y_lst:list[int]=[]
        sum=0
        for h in h_lst:
            self.y_lst.append(sum)
            sum+=h
        
    def setScrollBarValue(self,idx:int):
        self.y_lst_update()
        self.verticalScrollBar().setValue(self.y_lst[idx])

    def scroll_emit(self):
        self.y_lst_update()
        y=self.verticalScrollBar().value()
        self.scrolled.emit(self.y2idx(y),y)

    def y2idx(self,y:int):
        self.y_lst_update()
        bool_lst=[y>=y_i for y_i in self.y_lst]
        if False in bool_lst:
            min_false_idx=bool_lst.index(False)
            return min_false_idx-1
        else:
            return len(self.y_lst)-1
        
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
            if self.count()>0:
                if self.currentIndex()==self.count()-1:
                    self.setCurrentIndex(self.count()-2)
                self.removeItem(self.count()-1)
                self.indexWrite()

        def indexChangedEmit(self):
            self.indexWrite()
            self.indexChanged.emit(self.currentIndex())
    
        def itemUpdate(self):
            currentStrategyIndex:int=settingRead(['changable','currentStrategyIndex'])
            self.clear()
            strategy:list=settingRead(['changable','strategy'])
            self.addItems([(str(i+1)+' '+strategy[i]['name']) for i in range(len(strategy))])
            self.setCurrentIndex(currentStrategyIndex)
            self.indexWrite()

        def indexWrite(self):
            settingWrite(self.currentIndex(),['changable','currentStrategyIndex'])

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
        self.hb2_addRemove_btn.addWidget(self.btn21_add)
        self.hb2_addRemove_btn.addWidget(self.btn22_remove)
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
        self.btn21_add.clicked.connect(self.cb11_strategyChoose.itemAdd)
        self.btn22_remove.clicked.connect(self.cpbListRemove)
        self.btn22_remove.clicked.connect(self.cb11_strategyChoose.itemRemove)

    def cpbListAdd(self):
        strategy_lst:list=settingRead(self.strategyPath_lst)
        strategy_lst.append(strategy_lst[-1])
        settingWrite(strategy_lst,self.strategyPath_lst)
        self.cpb3_detail_lst.append(CollapsibleBox_Strategy(len(self.cpb3_detail_lst)))
        self.vb_strategy.addWidget(self.cpb3_detail_lst[-1])
        self.vb31_detail_lst.append(VBoxLayout_Strategy(len(self.cpb3_detail_lst)-1))
        self.cpb3_detail_lst[-1].setContentLayout(self.vb31_detail_lst[-1])
        self.vb31_detail_lst[-1].objectChanged.connect(self.cpb3_detail_lst[-1].nameUpdate)
        
    def cpbListRemove(self):
        if len(self.cpb3_detail_lst)>0:
            self.cpb3_detail_lst[-1].deleteLater()
            self.vb31_detail_lst[-1].deleteLater()
            del self.vb31_detail_lst[-1]
            del self.cpb3_detail_lst[-1]
            strategy_lst:list=settingRead(self.strategyPath_lst)
            strategy_lst.pop()
            settingWrite(strategy_lst,self.strategyPath_lst)

class GroupBox_Assist(QGroupBox):
    
    def __init__(self):
        super(GroupBox_Assist,self).__init__('助战')
        self.vb_assist=QVBoxLayout()
        self.setLayout(self.vb_assist)

        self.cb1_isCloth=QCheckBox('是否关心礼装')
        self.cb1_isCloth.setChecked(settingRead(['changable','isCloth']))
        self.cb1_isCloth.stateChanged.connect(self.isClothChangeEmit)
        self.hb2_assistChoose_lst=[]
        for i in range(3):
            self.hb2_assistChoose_lst.append(HBoxLayout_AssistChoose(i+1))
            self.vb_assist.addLayout(self.hb2_assistChoose_lst[i])
        self.vb_assist.addWidget(self.cb1_isCloth)

    def isClothChangeEmit(self):
        settingWrite(self.cb1_isCloth.isChecked(),['changable','isCloth'])

class GroupBox_Repeat(QGroupBox):

    class CheckBox_isRepeat(QCheckBox):
        isRepeatChanged=pyqtSignal()
        def __init__(self) -> None:
            super(GroupBox_Repeat.CheckBox_isRepeat, self).__init__()
            self.setText('是否多次战斗')
            self.stateChanged.connect(self.isRepeatChangeEmit)
            self.setChecked(settingRead(['changable','again','isAgain']))

        def isRepeatChangeEmit(self):
            settingWrite(self.isChecked(),['changable','again','isAgain'])
            self.isRepeatChanged.emit()

    class LineEdit_numCount(QLineEdit):
        numCountChanged=pyqtSignal()
        def __init__(self):
            super(GroupBox_Repeat.LineEdit_numCount,self).__init__()
            self.textUpdate()
            self.textChanged.connect(self.numCountChangeEmit)
        
        def numCountChangeEmit(self):
            if self.text().isdigit():
                settingWrite(int(self.text()),['changable','again','fightCount'])
                self.numCountChanged.emit()

        def textUpdate(self):
            text=str(settingRead(['changable','again','fightCount']))
            self.setText(text)

    class ComboBox_appleType(QComboBox):
        appleTypeChanged=pyqtSignal()
        def __init__(self) -> None:
            super(GroupBox_Repeat.ComboBox_appleType, self).__init__()
            self.appleName_lst=settingRead(['fixed','appleNameList'])
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

        self.cb1_isRepeat=GroupBox_Repeat.CheckBox_isRepeat()
        self.hb2_numCount=QHBoxLayout()
        self.hb3_appleType=QHBoxLayout()
        self.vb_repeat.addWidget(self.cb1_isRepeat)
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

class GroupBox_CheckServantIcon(QGroupBox):

    def __init__(self):
        super(GroupBox_CheckServantIcon,self).__init__('指令卡形象')
        self.vb_heckServantIcon=QVBoxLayout()
        self.setLayout(self.vb_heckServantIcon)

        self.orderImgNum=4
        self.hb1_assistIndex=QHBoxLayout()
        self.hb2_servantIcon=QHBoxLayout()
        self.hb3_isCheckFirstTime=QHBoxLayout()
        self.vb_heckServantIcon.addLayout(self.hb1_assistIndex)
        self.vb_heckServantIcon.addLayout(self.hb2_servantIcon)
        self.vb_heckServantIcon.addLayout(self.hb3_isCheckFirstTime)
        
        self.la11_assistIndex=QLabel('助战角色位置')
        self.cbb12_assistIndex=QComboBox()
        self.cbb12_assistIndex.addItems([str(i) for i in range(1,1+self.orderImgNum)])
        self.cbb12_assistIndex.setCurrentIndex(int(settingRead(['changable','assistIndex']))-1)
        self.cbb12_assistIndex.currentIndexChanged.connect(self.assistIndexChanged)
        self.hb1_assistIndex.addWidget(self.la11_assistIndex)
        self.hb1_assistIndex.addWidget(self.cbb12_assistIndex)
        self.hb1_assistIndex.addStretch(1)
        
        self.la21_servantIcon=QLabel('指令卡形象: ')
        self.laList22_servantIcon:list[QLabel]=[]
        self.hb2_servantIcon.addWidget(self.la21_servantIcon)
        for laI in range(self.orderImgNum):
            self.laList22_servantIcon.append(QLabel())
            self.hb2_servantIcon.addWidget(self.laList22_servantIcon[laI])
        self.servantIconUpdate()

        self.cb31_isCheckFirstTime=QCheckBox('首次战斗是否确认所有角色指令卡形象')
        self.cb31_isCheckFirstTime.setChecked(settingRead(['changable','isCheckServantIconFirstTime']))
        self.hb3_isCheckFirstTime.addWidget(self.cb31_isCheckFirstTime)
        self.hb3_isCheckFirstTime.addStretch(1)
        self.cb31_isCheckFirstTime.stateChanged.connect(self.isCheckFirstTimeChanged)

    def servantIconUpdate(self):
        self.servantIconPath_lst:list[str]=settingRead(['fixed','parameters','fight','order','servantMaskImgPathList'])
        self.servantIconPath_lst.reverse()
        for laI in range(self.orderImgNum):
            self.laList22_servantIcon[laI].setPixmap(QPixmap(self.servantIconPath_lst[laI]))

    def assistIndexChanged(self):
        settingWrite(self.cbb12_assistIndex.currentIndex()+1,['changable','assistIndex'])

    def isCheckFirstTimeChanged(self):
        settingWrite(self.cb31_isCheckFirstTime.isChecked(),['changable','isCheckServantIconFirstTime'])

class GroupBox_Simulator(QGroupBox):
    
    class ComboBox_simulatorSelect(QComboBox):
        simulatorIndexChange=pyqtSignal(int)
        def __init__(self) -> None:
            super(GroupBox_Simulator.ComboBox_simulatorSelect, self).__init__()
            indexKey_lst=['changable','simulatorIndex']
            index:int=settingRead(indexKey_lst)
            simulatorKey_lst=['changable','simulator']
            simulator_lst:list=settingRead(simulatorKey_lst)
            simulatorName_lst:list=[simulator['name'] for simulator in simulator_lst]
            self.addItems(simulatorName_lst)
            self.setCurrentIndex(index)

        def itemUpdate(self):
            index=self.currentIndex()
            simulatorKey_lst=['changable','simulator']
            simulator_lst:list=settingRead(simulatorKey_lst)
            simulatorName_lst:list=[simulator['name'] for simulator in simulator_lst]
            self.clear()
            self.addItems(simulatorName_lst)
            self.setCurrentIndex(min(index,len(simulatorName_lst)-1))

        def simulatorIndexChangeEmit(self):
            settingWrite(self.currentIndex(),['changable','simulatorIndex'])
            self.simulatorIndexChange.emit(self.currentIndex())
    
    class VBoxLayout_SimulatorList(QVBoxLayout):
        def __init__(self):
            super(GroupBox_Simulator.VBoxLayout_SimulatorList,self).__init__()
            self.la_simulatorList=QPlainTextEdit()
            self.addWidget(self.la_simulatorList)
            self.la_simulatorList.setReadOnly(True)
            self.simulatorListUpdate()

        def simulatorListUpdate(self):
            scrollValue=self.la_simulatorList.verticalScrollBar().value()
            self.simulatorPath_lst=['changable','simulator']
            self.simulatorInfo_lst:list[dict[str]]=settingRead(self.simulatorPath_lst)
            self.simulatorName_lst=[simulatorInfo['name'] for simulatorInfo in self.simulatorInfo_lst]
            self.simulatorInfoText:str=''
            for simulatorInfo in self.simulatorInfo_lst:
                self.simulatorInfoText+=simulatorInfo['name']+' '+simulatorInfo['ip']+'\n'
            self.la_simulatorList.setPlainText(self.simulatorInfoText)
            self.la_simulatorList.verticalScrollBar().setValue(scrollValue)

    def __init__(self):
        super(GroupBox_Simulator,self).__init__('模拟器')
        self.vb_simulator=QVBoxLayout()
        self.setLayout(self.vb_simulator)

        self.hb1_simulatorChoose=QHBoxLayout()
        self.cpb2_simulatorList=CollapsibleBox('模拟器列表')
        self.hb3_connectTest=QHBoxLayout()
        self.hb4_simulatorAdd=QHBoxLayout()
        self.hb5_simulatorRemove=QHBoxLayout()
        self.hb6_miniInstall=QHBoxLayout()
        self.vb_simulator.addLayout(self.hb1_simulatorChoose)
        self.vb_simulator.addWidget(self.cpb2_simulatorList)
        self.vb_simulator.addLayout(self.hb3_connectTest)
        self.vb_simulator.addLayout(self.hb4_simulatorAdd)
        self.vb_simulator.addLayout(self.hb5_simulatorRemove)
        self.vb_simulator.addLayout(self.hb6_miniInstall)

        self.la11_simulatorChoose=QLabel('模拟器选择')
        self.cbb12_simulatorChoose=GroupBox_Simulator.ComboBox_simulatorSelect()
        self.hb1_simulatorChoose.addWidget(self.la11_simulatorChoose)
        self.hb1_simulatorChoose.addWidget(self.cbb12_simulatorChoose)
        self.hb1_simulatorChoose.addStretch(1)
        self.cbb12_simulatorChoose.currentIndexChanged.connect(self.cbb12_simulatorChoose.simulatorIndexChangeEmit)
        
        self.vb21_simulatorList=GroupBox_Simulator.VBoxLayout_SimulatorList()
        self.cpb2_simulatorList.setContentLayout(self.vb21_simulatorList)

        self.btn31_connectTest=QPushButton('模拟器链接测试')
        self.la32_connectResult=QLabel('')
        self.hb3_connectTest.addWidget(self.btn31_connectTest)
        self.hb3_connectTest.addStretch(1)
        self.hb3_connectTest.addWidget(self.la32_connectResult)
        self.btn31_connectTest.clicked.connect(self.la32_successConnect)

        self.btn41_simulatorAdd=QPushButton('模拟器添加')
        self.le42_simulatorInfo=QLineEdit('mumu1 127.0.0.1:88143288')
        self.la43_simulatorAddResult=QLabel('')
        self.hb4_simulatorAdd.addWidget(self.btn41_simulatorAdd)
        self.hb4_simulatorAdd.addWidget(self.le42_simulatorInfo)
        self.hb4_simulatorAdd.addWidget(self.la43_simulatorAddResult)
        self.btn41_simulatorAdd.clicked.connect(self.btn41_simulatorAddAction)
        self.btn41_simulatorAdd.clicked.connect(self.vb21_simulatorList.simulatorListUpdate)

        self.btn51_simulatorRemove=QPushButton('模拟器删除')
        self.cbb52_simulatorName=GroupBox_Simulator.ComboBox_simulatorSelect()
        self.la53_simulatorRemoveResult=QLabel('')
        self.hb5_simulatorRemove.addWidget(self.btn51_simulatorRemove)
        self.hb5_simulatorRemove.addWidget(self.cbb52_simulatorName)
        self.hb5_simulatorRemove.addStretch(1)
        self.hb5_simulatorRemove.addWidget(self.la53_simulatorRemoveResult)
        self.btn51_simulatorRemove.clicked.connect(self.btn51_simulatorRemoveAction)
        self.btn51_simulatorRemove.clicked.connect(self.vb21_simulatorList.simulatorListUpdate)

        self.vb61_miniInstall=QVBoxLayout()
        self.la63_miniInstallResult=QLabel('')
        self.hb6_miniInstall.addLayout(self.vb61_miniInstall)
        self.hb6_miniInstall.addWidget(self.la63_miniInstallResult)
        self.hb6_miniInstall.addStretch(1)
        self.la63_miniInstallResult.setWordWrap(True)
        
        self.btn611_miniInstall=QPushButton('安装mini')
        self.btn612_miniCheck=QPushButton('查看mini安装情况')
        self.vb61_miniInstall.addWidget(self.btn611_miniInstall)
        self.vb61_miniInstall.addWidget(self.btn612_miniCheck)
        self.vb61_miniInstall.addStretch(1)
        self.btn611_miniInstall.clicked.connect(self.btn611_miniInstallAction)
        self.btn612_miniCheck.clicked.connect(self.btn612_miniCheckAction)

    def la32_successConnect(self):
        self.la32_connectResult.setText('adb success connect to '+self.cbb12_simulatorChoose.currentText())

    def btn41_simulatorAddAction(self):
        simulatorInfo_lst=self.le42_simulatorInfo.text().split(' ')
        newSimulatorInfo=settingRead(['changable','simulator',-1])
        newSimulatorInfo['name']=simulatorInfo_lst[0]
        newSimulatorInfo['ip']=simulatorInfo_lst[1]
        simulator_lst:list=settingRead(['changable','simulator'])
        simulator_lst.append(newSimulatorInfo)
        settingWrite(simulator_lst,['changable','simulator'])
        self.la43_simulatorAddResult.setText('success add '+self.le42_simulatorInfo.text().split(' ')[0])

    def btn51_simulatorRemoveAction(self):
        simulator_lst:list=settingRead(['changable','simulator'])
        simulator_lst.remove(simulator_lst[self.cbb52_simulatorName.currentIndex()])
        settingWrite(simulator_lst,['changable','simulator'])
        self.la53_simulatorRemoveResult.setText('success delete '+self.cbb52_simulatorName.currentText())

    def btn611_miniInstallAction(self):
        simulatorIndex=self.cbb12_simulatorChoose.currentIndex()
        simulator_lst:list=settingRead(['changable','simulator'])
        ip=simulator_lst[simulatorIndex]['ip']
        sysInput('adb connect '+ip)
        struc=subprocess.getoutput(f'adb -s {ip} shell getprop ro.product.cpu.abi')
        sdk=subprocess.getoutput(f'adb -s {ip} shell getprop ro.build.version.sdk')
        f,errorText=miniInstall(struc,sdk,ip)
        adbInfo=subprocess.getoutput('adb shell ls -all data/local/tmp')
        text='success install minicap&minitouch\nstruc: '+struc+'   sdk:'+sdk+'\nfiles in data/local/tmp:\t'+ adbInfo
        text=f'<font color="white">{text}</font>'
        for keyText in ['minicap','minitouch']:
            text=text.replace(keyText,f'</font><font color="yellow">{keyText}</font><font color="white">')
        if not f:
            text=f'<font color="red">{errorText}\n</font>'+text
        text=text.replace('\n','<br/>')
        self.la63_miniInstallResult.setText(text)
        sysInput('adb disconnect '+ip)

    def btn612_miniCheckAction(self):
        ip=ipGet()
        sysInput('adb connect '+ip)
        struc=subprocess.getoutput(f'adb -s {ip} shell getprop ro.product.cpu.abi')
        sdk=subprocess.getoutput(f'adb -s {ip} shell getprop ro.build.version.sdk')
        adbInfo=subprocess.getoutput(f'adb -s {ip} shell ls -all data/local/tmp')
        text='struc: '+struc+'   sdk:'+sdk+'\nfiles in data/local/tmp:\t'+ adbInfo
        text=f'<font color="white">{text}</font>'
        for keyText in ['minicap','minitouch','sdk','struc']:
            text=text.replace(keyText,f'</font><font color="yellow">{keyText}</font><font color="white">')
        text=text.replace('\n','<br/>')
        self.la63_miniInstallResult.setText(text)
        sysInput('adb disconnect '+ip)

class GroupBox_CaptureMethod(QGroupBox):

    class HBoxLayout_CopyFrom(QHBoxLayout):
        def __init__(self):
            super(GroupBox_CaptureMethod.HBoxLayout_CopyFrom,self).__init__()
            self.btn1_copy=QPushButton('复制')
            self.cbb2_simulatorChoose=GroupBox_Simulator.ComboBox_simulatorSelect()
            self.la3_text=QLabel('的捕获设置')
            self.addWidget(self.btn1_copy)  
            self.addWidget(self.cbb2_simulatorChoose)
            self.addWidget(self.la3_text)
            self.addStretch(1)
            self.btn1_copy.clicked.connect(self.btn1_copyAction)

        def btn1_copyAction(self):
            simulatorIndex=simulatorIndexGet()
            copySimulatorIndex:int=self.cbb2_simulatorChoose.currentIndex()
            simulator:list=settingRead(['changable','simulator',simulatorIndex])
            copySimulator:list=settingRead(['changable','simulator',copySimulatorIndex])
            copySimulator['name']=simulator['name']
            copySimulator['ip']=simulator['ip']
            settingWrite(copySimulator,['changable','simulator',simulatorIndex])

    class HBoxLayout_MethodSelect(QHBoxLayout):
        def __init__(self):
            super(GroupBox_CaptureMethod.HBoxLayout_MethodSelect,self).__init__()
            self.rb11_minicap=QRadioButton('minicap')
            self.rb12_win32gui=QRadioButton('win32gui')
            self.addWidget(self.rb11_minicap)
            self.addWidget(self.rb12_win32gui)
            self.addStretch(1)
            self.selfUpdate()
            self.rb11_minicap.clicked.connect(self.selectChange)
            self.rb12_win32gui.clicked.connect(self.selectChange)

        def selectChange(self):
            if self.rb11_minicap.isChecked():
                captureMethod=0
            elif self.rb12_win32gui.isChecked():
                captureMethod=1
            simulatorIndex=simulatorIndexGet()
            settingWrite(captureMethod,['changable','simulator',simulatorIndex,'captureMethod'])

        def selfUpdate(self):
            simulatorIndex=simulatorIndexGet()
            captureMethod:int=settingRead(['changable','simulator',simulatorIndex,'captureMethod'])
            if captureMethod==0:
                self.rb11_minicap.setChecked(True)
            elif captureMethod==1:
                self.rb12_win32gui.setChecked(True)

    class HBoxLayout_WindowsTitle(QHBoxLayout):
        def __init__(self):
            super(GroupBox_CaptureMethod.HBoxLayout_WindowsTitle,self).__init__()
            self.la21_windowsTitle=QLabel('窗口标题')
            self.le22_windowsTitle=QLineEdit()
            self.addWidget(self.la21_windowsTitle)
            self.addWidget(self.le22_windowsTitle)
            self.addStretch(1)
            self.selfUpdate()

        def titleChange(self):
            simulatorIndex=simulatorIndexGet()
            settingWrite(self.le22_windowsTitle.text(),['changable','simulator',simulatorIndex,'windowsTitle'])

        def selfUpdate(self):
            simulatorIndex=simulatorIndexGet()
            windowsTitle=settingRead(['changable','simulator',simulatorIndex,'windowsTitle'])
            self.le22_windowsTitle.setText(windowsTitle)
            self.le22_windowsTitle.textChanged.connect(self.titleChange)

    class HBoxLayout_WindowsRectXY(QHBoxLayout):
        def __init__(self):
            super(GroupBox_CaptureMethod.HBoxLayout_WindowsRectXY,self).__init__()
            self.la1_rectX=QLabel('X:')
            self.le1_rectX=QLineEdit()
            self.la2_rectY=QLabel('Y:')
            self.le2_rectY=QLineEdit()
            self.addWidget(self.la1_rectX)
            self.addWidget(self.le1_rectX)
            self.addStretch(1)
            self.addWidget(self.la2_rectY)
            self.addWidget(self.le2_rectY)
            self.addStretch(2)
            self.selfUpdate()

        def rectXChange(self):
            simulatorIndex=settingRead(['changable','simulatorIndex'])
            settingWrite(int(self.le1_rectX.text()),['changable','simulator',simulatorIndex,'captureRect',0])

        def rectYChange(self):
            simulatorIndex=settingRead(['changable','simulatorIndex'])
            settingWrite(int(self.le2_rectY.text()),['changable','simulator',simulatorIndex,'captureRect',1])
            
        def selfUpdate(self):
            simulatorIndex=settingRead(['changable','simulatorIndex'])
            rectX:int=settingRead(['changable','simulator',simulatorIndex,'captureRect',0])
            rectY:int=settingRead(['changable','simulator',simulatorIndex,'captureRect',1])
            self.le1_rectX.setText(str(rectX))
            self.le2_rectY.setText(str(rectY))
            self.le1_rectX.textChanged.connect(self.rectXChange)
            self.le2_rectY.textChanged.connect(self.rectYChange)

    class HBoxLayout_WindowsRectWH(QHBoxLayout):
        def __init__(self):
            super(GroupBox_CaptureMethod.HBoxLayout_WindowsRectWH,self).__init__()
            self.la1_rectW=QLabel('W:')
            self.le1_rectW=QLineEdit()
            self.la2_rectH=QLabel('H:')
            self.le2_rectH=QLineEdit()
            self.addWidget(self.la1_rectW)
            self.addWidget(self.le1_rectW)
            self.addStretch(1)
            self.addWidget(self.la2_rectH)
            self.addWidget(self.le2_rectH)
            self.addStretch(2)
            self.selfUpdate()

        def rectWChange(self):
            simulatorIndex=settingRead(['changable','simulatorIndex'])
            settingWrite(int(self.le1_rectW.text()),['changable','simulator',simulatorIndex,'captureRect',2])

        def rectHChange(self):
            simulatorIndex=settingRead(['changable','simulatorIndex'])
            settingWrite(int(self.le2_rectH.text()),['changable','simulator',simulatorIndex,'captureRect',3])

        def selfUpdate(self):
            simulatorIndex=settingRead(['changable','simulatorIndex'])
            rectW:int=settingRead(['changable','simulator',simulatorIndex,'captureRect',2])
            rectH:int=settingRead(['changable','simulator',simulatorIndex,'captureRect',3])
            self.le1_rectW.setText(str(rectW))
            self.le2_rectH.setText(str(rectH))
            self.le1_rectW.textChanged.connect(self.rectWChange)
            self.le2_rectH.textChanged.connect(self.rectHChange)

    class HBoxLayout_CaptureTest(QHBoxLayout):
        def __init__(self):
            super(GroupBox_CaptureMethod.HBoxLayout_CaptureTest,self).__init__()
            self.btn1_captureTest=QPushButton('捕获测试')
            self.la2_windowsImage=QLabel()
            self.addWidget(self.btn1_captureTest)
            self.addWidget(self.la2_windowsImage)
            self.addStretch(1)
            self.btn1_captureTest.clicked.connect(self.captureTest)

            simulatorIndex=settingRead(['changable','simulatorIndex'])
            captureSetting:dict=settingRead(['changable','simulator',simulatorIndex])
            windowsTitle:int=captureSetting['windowsTitle']
            self.screen = QApplication.primaryScreen()
            self.hwnd=win32gui.FindWindow(None,windowsTitle)
            self.captureTest()

        def captureTest(self):
            simulatorIndex=settingRead(['changable','simulatorIndex'])
            captureSetting:dict=settingRead(['changable','simulator',simulatorIndex])
            captureMethod:int=captureSetting['captureMethod']
            captureRect:int=captureSetting['captureRect']
            qImg=None
            if captureMethod==1:
                if self.hwnd:
                    qImg = self.screen.grabWindow(self.hwnd).toImage()
                    x,y,w,h=captureRect
                    qImg=qImg.copy(QRect(x,y,w,h))
                    qImg.save("screen.jpeg")
            if qImg is not None:
                qImg=qImg.scaled(400,225,Qt.KeepAspectRatio)
            self.la2_windowsImage.setPixmap(QPixmap(qImg))

    def __init__(self):
        super(GroupBox_CaptureMethod,self).__init__('窗口捕获')
        self.vb_captureMethod=QVBoxLayout()
        self.setLayout(self.vb_captureMethod)

        self.hb1_copyFrom=GroupBox_CaptureMethod.HBoxLayout_CopyFrom()
        self.hb2_methodSelect=GroupBox_CaptureMethod.HBoxLayout_MethodSelect()
        self.hb3_windowsTitle=GroupBox_CaptureMethod.HBoxLayout_WindowsTitle()
        self.hb4_windowsRectXY=GroupBox_CaptureMethod.HBoxLayout_WindowsRectXY()
        self.hb5_windowsRectWH=GroupBox_CaptureMethod.HBoxLayout_WindowsRectWH()
        self.hb6_captureTest=GroupBox_CaptureMethod.HBoxLayout_CaptureTest()
        self.vb_captureMethod.addLayout(self.hb1_copyFrom)
        self.vb_captureMethod.addLayout(self.hb2_methodSelect)
        self.vb_captureMethod.addLayout(self.hb3_windowsTitle)
        self.vb_captureMethod.addLayout(self.hb4_windowsRectXY)
        self.vb_captureMethod.addLayout(self.hb5_windowsRectWH)
        self.vb_captureMethod.addLayout(self.hb6_captureTest)

        self.hb1_copyFrom.btn1_copy.clicked.connect(self.selfUpdate)

    def selfUpdate(self):
        self.hb2_methodSelect.selfUpdate()
        self.hb3_windowsTitle.selfUpdate()
        self.hb4_windowsRectXY.selfUpdate()
        self.hb5_windowsRectWH.selfUpdate()

class GroupBox_ClothExperienceFeeding(QGroupBox):

    def __init__(self):
        super(GroupBox_ClothExperienceFeeding,self).__init__('搓丸子')
        self.vb_clothExperienceFeeding=QVBoxLayout()
        self.setLayout(self.vb_clothExperienceFeeding)

        self.hb1_set=QLabel('waiting for updating')
        self.vb_clothExperienceFeeding.addWidget(self.hb1_set)
