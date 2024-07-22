from PyQt5.QtWidgets import QHBoxLayout,QVBoxLayout,QLabel,QLineEdit,QPushButton
from PyQt5.QtCore import pyqtSignal

from pytool.CollapsibleBox import *
from pytool.basicFunction import *
from pytool.log import *
from cv2 import imread,resize,imwrite

class named_HBLayout(QHBoxLayout):
    def __init__(self,name:str,idx:int)->None:
        super(named_HBLayout,self).__init__()
        self.name=name
        self.idx=idx

class HBox_Screen(named_HBLayout):
    def __init__(self,name:str,idx:int) -> None:
        super(HBox_Screen, self).__init__(name,idx)

        self.vb1_screen=QVBoxLayout()
        self.vb2_log=QVBoxLayout()
        self.addLayout(self.vb1_screen)
        self.addLayout(self.vb2_log)
        self.pm11_screen=QPixmap('screen.jpeg')
        
        self.la1_screen=QLabel()
        self.la1_screen.setPixmap(self.pm11_screen)
        self.la1_screen.setScaledContents(True)
        self.la1_screen.setFixedSize(715,715*outputY//outputX)
        self.vb1_screen.addStretch(1)
        self.vb1_screen.addWidget(self.la1_screen)

        self.la22_log=Label_Log()
        self.vb2_log.addWidget(self.la22_log)

class VBoxLayout_Strategy(QVBoxLayout):
    objectChanged=pyqtSignal()
    def __init__(self,idx):
        super(VBoxLayout_Strategy,self).__init__()
        self.idx=idx
        self.la1_name=QLabel('名称')
        self.le2_name=QLineEdit()
        self.hb_3strategyAssist=Hbox_3StrategyAssist(idx)
        self.la3_turn1=QLabel('回合1')
        self.le4_skill1=QLineEdit()
        self.le5_order1=QLineEdit()
        self.la6_turn2=QLabel('回合2')
        self.le7_skill2=QLineEdit()
        self.le8_order2=QLineEdit()
        self.la9_turn3=QLabel('回合3')
        self.leA_skill3=QLineEdit()
        self.leB_order3=QLineEdit()
        self.hbC_update=QHBoxLayout()
        self.le_lst:list[QLineEdit]=[self.le2_name,self.le4_skill1,self.le5_order1,self.le7_skill2,self.le8_order2,self.leA_skill3,self.leB_order3]
        self.addWidget(self.la1_name)
        self.addWidget(self.le2_name)
        self.addLayout(self.hb_3strategyAssist)
        self.addWidget(self.la3_turn1)
        self.addWidget(self.le4_skill1)
        self.addWidget(self.le5_order1)
        self.addWidget(self.la6_turn2)
        self.addWidget(self.le7_skill2)
        self.addWidget(self.le8_order2)
        self.addWidget(self.la9_turn3)
        self.addWidget(self.leA_skill3)
        self.addWidget(self.leB_order3)
        self.addLayout(self.hbC_update)
        self.initialStrategy()
        for le in self.le_lst:
            le.textChanged.connect(self.objectChanged.emit)
        self.objectChanged.connect(self.updateStrategy)

    def initialStrategy(self):
        strategy:dict[str,str]=settingRead(['changable','strategy',self.idx])
        for nameI in range(len(strategy.keys())):
            self.le_lst[nameI].setText(strategy[list(strategy.keys())[nameI]])

    def updateStrategy(self):
        if not max([le.text()=='' for le in self.le_lst]):
            strategy_dict={
                    "name"  : self.le2_name.text(),
                    "skill1": self.le4_skill1.text(),
                    "order1": self.le5_order1.text(),
                    "skill2": self.le7_skill2.text(),
                    "order2": self.le8_order2.text(),
                    "skill3": self.leA_skill3.text(),
                    "order3": self.leB_order3.text()
                    }
            settingWrite(strategy_dict,['changable','strategy',self.idx])

class HBoxLayout_AssistChoose(QHBoxLayout):
    def __init__(self,idx:int):
        super(HBoxLayout_AssistChoose,self).__init__()
        self.idx=idx
        self.servantFeatureInfo:dict=fixedSettingRead(['fixed','parameters','assist','assistServantFeatureInfoList',self.idx-1])
        self.clothFeatureInfo:dict=fixedSettingRead(['fixed','parameters','assist','assistClothFeatureInfoList',self.idx-1])
        self.servantFeatureInfo['featureImagePath']=r'fgoMaterial\assistServantFeature'+str(idx)+'.png'
        self.clothFeatureInfo['featureImagePath']=r'fgoMaterial\assistClothFeature'+str(idx)+'.png'

        self.la1_name=QLabel('助战选择'+str(idx))
        self.btn2_update=QPushButton('更新')
        self.la3_servantImgText=QLabel('助战从者')
        self.la4_servantImg=QLabel()
        self.la5_clothImgText=QLabel('助战礼装')
        self.la6_clothImg=QLabel()
        self.addWidget(self.la1_name)
        self.addWidget(self.btn2_update)
        self.addWidget(self.la3_servantImgText)
        self.addWidget(self.la4_servantImg)
        self.addWidget(self.la5_clothImgText)
        self.addWidget(self.la6_clothImg)
        self.laUpdate()
        self.btn2_update.clicked.connect(self.btnAction)
        self.btn2_update.clicked.connect(self.laUpdate)

    def btnAction(self):

        ip=ipGet()
        sysInput(f'adb connect {ip}')       
        sysInput(f'adb -s {ip} shell screencap -p /sdcard/screenshot.jpeg')
        sysInput(f'adb -s {ip} pull /sdcard/screenshot.jpeg screen.jpeg')
        currentImg=imread("screen.jpeg")
        currentImgSmall=resize(currentImg,(512,288))
        info_lst:list[dict]=[self.servantFeatureInfo,self.clothFeatureInfo]
        pathLst=[f'fgoMaterial/assistServant_{self.idx}.png',f'fgoMaterial/assistCloth_{self.idx}.png']
        for infoI in range(len(info_lst)):
            info=info_lst[infoI]
            Rect:list[int]=info['Rect']
            y,x,h,w=Rect
            newFeatureImg=currentImgSmall[y:y+h,x:x+w]
            imwrite(pathLst[infoI],newFeatureImg)

    def laUpdate(self):
        self.la4_servantImg.setPixmap(QPixmap(f'fgoMaterial/assistServant_{self.idx}.png'))
        self.la6_clothImg.setPixmap(QPixmap(f'fgoMaterial/assistCloth_{self.idx}.png'))


class Vbox_StrategyAssistChoose(QVBoxLayout):
    def __init__(self,sidx:int,idx:int) -> None:
        super().__init__()

        self.sidx=sidx
        self.idx=idx
        self.settingPathLst=['changable', 'strategyAssistChoose', self.sidx,self.idx]
        self.cbb_assistChoose=QComboBox()
        self.lb_assistServantImg=QLabel()
        self.lb_assistServantImg.setFixedSize(150,int(150*55/75))
        self.lb_assistServantImg.setScaledContents(True)
        self.lb_assistClothImg=QLabel()
        self.lb_assistClothImg.setFixedSize(150,int(150*30/75))
        self.lb_assistClothImg.setScaledContents(True)
        self.addWidget(self.cbb_assistChoose)
        self.addWidget(self.lb_assistServantImg)
        self.addWidget(self.lb_assistClothImg)

        imgFn_lst=os.listdir('fgoMaterial')
        assistServantImgFn_lst=[i for i in imgFn_lst if 'assistServant' in i]
        countOfCbb=self.cbb_assistChoose.count()
        self.cbb_assistChoose.addItems(list([str(i) for i in range(countOfCbb+1,len(assistServantImgFn_lst)+1)]))
        self.initAssistIdx=settingRead(self.settingPathLst)
        self.cbb_assistChoose.setCurrentIndex(self.initAssistIdx)
        self.cbb_assistChoose.currentIndexChanged.connect(self.update)
        self.update()
        
    def update(self):
        #setting write

        imgFn_lst=os.listdir('fgoMaterial')
        assistServantImgFn_lst=[i for i in imgFn_lst if 'assistServant' in i]
        assistClothImgFn_lst=[i for i in imgFn_lst if 'assistCloth' in i]
        assistServantImg=assistServantImgFn_lst[self.cbb_assistChoose.currentIndex()]
        assistClothImg=assistClothImgFn_lst[self.cbb_assistChoose.currentIndex()]
        countOfCbb=self.cbb_assistChoose.count()
        self.cbb_assistChoose.addItems(list([str(i) for i in range(countOfCbb+1,len(assistServantImgFn_lst)+1)]))
        self.lb_assistServantImg.setPixmap(QPixmap('fgoMaterial/'+assistServantImg))
        self.lb_assistClothImg.setPixmap(QPixmap('fgoMaterial/'+assistClothImg))

        settingWrite(self.cbb_assistChoose.currentIndex(), self.settingPathLst)


class Hbox_3StrategyAssist(QHBoxLayout):
    def __init__(self,sidx:int) -> None:
        super().__init__()
        self.vb1_strategy=Vbox_StrategyAssistChoose(sidx,0)
        self.vb2_strategy=Vbox_StrategyAssistChoose(sidx,1)
        self.vb3_strategy=Vbox_StrategyAssistChoose(sidx,2)
        self.addStretch(1)
        self.addLayout(self.vb1_strategy)
        self.addStretch(1)
        self.addLayout(self.vb2_strategy)
        self.addStretch(1)
        self.addLayout(self.vb3_strategy)
        self.addStretch(1)
