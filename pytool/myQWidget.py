# 原生库
from PyQt5.QtWidgets import QTabWidget,QWidget,QScrollArea,QGroupBox,QComboBox,QCheckBox,QSpinBox
from PyQt5.QtGui import QIcon,QCloseEvent
from PyQt5.QtCore import Qt,pyqtSignal
import time
from pyminitouch import MNTDevice
import shutil

# 自制库
from pytool.basicQObject import *
from pytool.pauseableThread import *
from pytool.flow import *

class TabWidgt_Total(QTabWidget):
    def __init__(self) -> None:
        print('TabWidgt_Total initializing')
        super(QTabWidget,self).__init__()
        self.setStyleSheet('font-size: 13pt;style=line-height:200%;color:white;')
        WindowGeometry=fixedSettingRead(['fixed','WindowGeometry'])
        wx,wy,ww,wh=WindowGeometry
        self.setGeometry(wx,wy,ww,wh)
        self.setWindowTitle('AFS ver1.0.3')
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

        laSimulatorSelect=self.wi1_run.la11_simulator
        cbSimulatorSelect=self.wi2_setting.scrollArea_setting.gb5_simulator.cbb12_simulatorChoose
        cbSimulatorSelect.simulatorIndexChange.connect(laSimulatorSelect.simulaterIndexChange)

        leFightCount1=self.wi1_run.le25_fightCount
        leFightCount2=self.wi2_setting.scrollArea_setting.gb3_repeat.le22_numCount
        leFightCount1.numCountChanged.connect(leFightCount2.textUpdate)
        leFightCount2.numCountChanged.connect(leFightCount1.textUpdate)

        self.th_lst:list[PauseableThread]=[self.wi1_run.th_operate]

        print('TabWidgt_Total initializied')

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
        wx=self.geometry().x()
        wy=self.geometry().y()
        ww=self.geometry().width()
        wh=self.geometry().height()
        WindowGeometry=[wx,wy,ww,wh]
        fixedsettingWrite(WindowGeometry,['fixed','WindowGeometry'])
        if self.wi1_run.th_operate.device is not None:
            self.wi1_run.th_operate.device.stop()
        self.th_lst.reverse()
        for th in self.th_lst:
            th.stop()
        super().closeEvent(a0)
        ip=ipGet()
        sysInput(f'adb disconnect {ip}')
        devicesInfo=myGetoutput('adb devices')
        if re.findall(r'\d+',devicesInfo)==[]:
            sysInput('adb kill-server')
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

        def __init__(self):
            super(Widget_run.Thread_Operate,self).__init__()
            self.fightCount=settingRead(['changable','again','fightCount'])

            self.flowGeneral=Flow_General()
            self.flowAssist=self.flowGeneral.state3_assistChoose.flow_assist
            self.flowFight=self.flowGeneral.state5_fight.flow_fight
            self.flow_lst=[self.flowGeneral,self.flowAssist,self.flowFight]

            self.simulatorOperator=None
            self.device=None
            self.la_log:Signal_log=None
            self.la_screen:QLabel=None
            self.qPixMap:QPixmap=QPixmap('screen.jpeg')
            self.qImg=QImage('screen.jpeg')
            self.ip=ipGet()
            self.currentImg:np.ndarray=imgResize2512(imread('screen.jpeg'))
            
        def logBind(self,la_log:Signal_log):
            self.la_log=la_log

        def flowImgBind(self):
            self.flowGeneral.currentImgBind(self.currentImg)
            self.flowFight.currentImgBind(self.currentImg)
            self.flowAssist.currentImgBind(self.currentImg)

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
            sysInput(f'adb -s {self.ip} shell screencap -p /sdcard/screenshot.jpeg')
            sysInput(f'adb -s {self.ip} pull /sdcard/screenshot.jpeg screen.jpeg')
            self.qImg=QImage('screen.jpeg')
            self.qPixMap=QPixmap.fromImage(self.qImg)
            self.la_screen.setPixmap(self.qPixMap)

            self.currentImg=imgResize2512(qImg2Mat(self.qImg))
            self.flowImgBind()
            self.flowGeneral.run()
            self.stateChanged.emit(self.flowGeneral.state_idx)
            if self.flowGeneral.isQuit:
                self.stop()
            self.nowFightCountChanged.emit(self.flowGeneral.fightCurrentCount)

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
        self.btn44_logReset.clicked.connect(self.hb5_screen.la22_log.log_reset)

        print('Widget_run initializied')

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
        
        self.laList_lst:list[list[Widget_set.setLabel]] =[]
        self.vbNm_lst:list[QVBoxLayout]=[]
        self.nmLaList_lst:list[str]=[['策略','助战','多次战斗'],['模拟器'],['搓丸子']]
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
        self.gb5_simulator=GroupBox_Simulator()
        self.gb7_clothExperienceFeeding=GroupBox_ClothExperienceFeeding()
        self.gb_lst.append(self.gb1_strategy)
        self.gb_lst.append(self.gb2_assist)
        self.gb_lst.append(self.gb3_repeat)
        self.gb_lst.append(self.gb5_simulator)
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
        cbb_lst=[cbb1,cbb2]
        btn1=self.gb5_simulator.btn41_simulatorAdd
        btn2=self.gb5_simulator.btn51_simulatorRemove
        btn_lst=[btn1,btn2]
        for btn in btn_lst:
            for cbb in cbb_lst:
                btn.clicked.connect(cbb.itemUpdate)

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
            os.remove(f'fgoMaterial/assistServant_{delIdx+1}.png')
            os.remove(f'fgoMaterial/assistCloth_{delIdx+1}.png')
            for i in range(delIdx+1,self.count):
                os.rename(f'fgoMaterial/assistServant_{str(i+1)}.png',f'fgoMaterial/assistServant_{str(i)}.png')
                os.rename(f'fgoMaterial/assistCloth_{str(i+1)}.png',f'fgoMaterial/assistCloth_{str(i)}.png')
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
        self.la63_miniInstallResult.setWordWrap(True)
        
        self.btn611_miniInstall=QPushButton('安装mini')
        self.btn612_miniCheck=QPushButton('查看mini安装情况')
        self.btn611_miniInstall.setFixedWidth(300)
        self.btn612_miniCheck.setFixedWidth(300)
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
        self.la43_simulatorAddResult.setText(self.le42_simulatorInfo.text().split(' ')[0]+' added')

    def btn51_simulatorRemoveAction(self):
        simulator_lst:list=settingRead(['changable','simulator'])
        simulator_lst.remove(simulator_lst[self.cbb52_simulatorName.currentIndex()])
        settingWrite(simulator_lst,['changable','simulator'])
        self.la53_simulatorRemoveResult.setText(self.cbb52_simulatorName.currentText()+' deleted')

    def btn611_miniInstallAction(self):
        simulatorIndex=self.cbb12_simulatorChoose.currentIndex()
        simulator_lst:list=settingRead(['changable','simulator'])
        ip=simulator_lst[simulatorIndex]['ip']
        sysInput('adb connect '+ip)
        struc=myGetoutput(f'adb -s {ip} shell getprop ro.product.cpu.abi')
        f,errorText=miniInstall(struc,ip)
        adbInfo=myGetoutput('adb shell ls -all data/local/tmp')
        text='success install minitouch\nstruc: '+struc+'\nfiles in data/local/tmp:\t'+ adbInfo
        text=f'<font color="white">{text}</font>'
        for keyText in ['minitouch']:
            text=text.replace(keyText,f'</font><font color="yellow">{keyText}</font><font color="white">')
        if not f:
            text=f'<font color="red">{errorText}\n</font>'+text
        text=text.replace('\n','<br/>')
        self.la63_miniInstallResult.setText(text)

    def btn612_miniCheckAction(self):
        ip=ipGet()
        sysInput('adb connect '+ip)
        struc=myGetoutput(f'adb -s {ip} shell getprop ro.product.cpu.abi')
        adbInfo=myGetoutput(f'adb -s {ip} shell ls -all data/local/tmp')
        text='struc: '+struc+'\nfiles in data/local/tmp:\t'+ adbInfo
        text_lst=text.split('\n')
        for texti in range(len(text_lst)-1,1,-1):
            if not 'minitouch' in text_lst[texti]:
                text_lst.pop(texti)
        text='\n'.join(text_lst)
        text=f'<font color="white">{text}</font>'
        for keyText in ['minitouch','struc']:
            text=text.replace(keyText,f'</font><font color="yellow">{keyText}</font><font color="white">')
        text=text.replace('\n','<br/>')
        self.la63_miniInstallResult.setText(text)

#2 5
class GroupBox_ClothExperienceFeeding(QGroupBox):

    def __init__(self):
        super(GroupBox_ClothExperienceFeeding,self).__init__('搓丸子')
        self.vb_clothExperienceFeeding=QVBoxLayout()
        self.setLayout(self.vb_clothExperienceFeeding)

        self.hb1_set=QLabel('waiting for updating')
        self.vb_clothExperienceFeeding.addWidget(self.hb1_set)
