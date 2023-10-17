
from PyQt5.QtWidgets import *
from PyQt5.QtGui import *
from PyQt5.QtCore import pyqtSignal

from thiredtool.CollapsibleBox import *

from pytool.basicFunction import *
from pytool.log import *

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

        # self.la21_time = QLabel('0')
        self.la22_log=Label_Log()
        # self.vb2_log.addWidget(self.la21_time)
        self.vb2_log.addWidget(self.la22_log)
        # self.la21_time.setAlignment(Qt.AlignCenter)

class VBoxLayout_Strategy(QVBoxLayout):
    objectChanged=pyqtSignal()
    def __init__(self,idx):
        super(VBoxLayout_Strategy,self).__init__()
        self.idx=idx
        self.la1_name=QLabel('名称')
        self.le2_name=QLineEdit()
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
        while True:
            currentImg=cv2.imread("screen.jpeg")
            if np.max(currentImg) is None:
                continue
            else:
                break
        currentImgSmall=cv2.resize(currentImg,(512,288))
        info_lst:list[dict]=[self.servantFeatureInfo,self.clothFeatureInfo]
        for info in info_lst:
            Rect:list[int]=info['Rect']
            y,x,h,w=Rect
            newFeatureImg=currentImgSmall[y:y+h,x:x+w]
            cv2.imwrite(info['featureImagePath'],newFeatureImg)

    def laUpdate(self):
        self.la4_servantImg.setPixmap(QPixmap(self.servantFeatureInfo['featureImagePath']))
        self.la6_clothImg.setPixmap(QPixmap(self.clothFeatureInfo['featureImagePath']))
