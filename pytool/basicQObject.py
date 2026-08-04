"""UI 布局组件库

named_HBLayout          : 带名称/索引标记的水平布局（用于界面元素标识）
HBox_Screen             : 屏幕预览 + 日志面板组合布局
VBoxLayout_Strategy     : 单个策略的编辑面板（名称/助战/3回合技能+指令卡）
HBoxLayout_AssistChoose : 单个助战从者的选择/更新面板（含从者/礼装截图更新）
Vbox_StrategyAssistChoose: 策略内单个助战槽（下拉选择 + 图片预览 + 自动写配置）
Hbox_3StrategyAssist    : 3 个助战槽的横向组合
"""
import re

from PyQt5.QtWidgets import QHBoxLayout,QVBoxLayout,QLabel,QLineEdit,QPushButton
from PyQt5.QtCore import pyqtSignal

from pytool.CollapsibleBox import *
from pytool.basicFunction import *
from pytool.log import *
from cv2 import imread,resize,imwrite

class named_HBLayout(QHBoxLayout):
    """带 name 与 idx 标记的水平布局"""
    def __init__(self,name:str,idx:int)->None:
        super(named_HBLayout,self).__init__()
        self.name=name
        self.idx=idx

class HBox_Screen(named_HBLayout):
    """屏幕预览（左）+ 日志面板（右）"""
    def __init__(self,name:str,idx:int) -> None:
        super(HBox_Screen, self).__init__(name,idx)

        self.vb1_screen=QVBoxLayout()
        self.vb2_log=QVBoxLayout()
        self.addLayout(self.vb1_screen)
        self.addLayout(self.vb2_log)
        self.pm11_screen=QPixmap(os.path.join(appRootGet(),'screen.jpeg'))
        
        # 屏幕预览：按 512×288 比例缩放到 715px 宽
        self.la1_screen=QLabel()
        self.la1_screen.setPixmap(self.pm11_screen)
        self.la1_screen.setScaledContents(True)
        self.la1_screen.setFixedSize(715,715*outputY//outputX)
        self.vb1_screen.addStretch(1)
        self.vb1_screen.addWidget(self.la1_screen)

        self.la22_log=Label_Log()
        self.vb2_log.addWidget(self.la22_log)

class VBoxLayout_Strategy(QVBoxLayout):
    """策略编辑面板：名称 + 助战选择 + 3 回合（技能/指令卡），文本变化实时写配置"""
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
        """从配置读取策略初始值填充编辑框"""
        strategy:dict[str,str]=settingRead(['changable','strategy',self.idx])
        for nameI in range(len(strategy.keys())):
            self.le_lst[nameI].setText(strategy[list(strategy.keys())[nameI]])

    def updateStrategy(self):
        """所有编辑框非空时，把当前内容写回配置"""
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

    def assistAdd(self):
        """助战列表增加后：为 3 个助战槽下拉框追加新编号"""
        time.sleep(0.1)
        count=self.hb_3strategyAssist.vbStrategy_lst[0].cbb_assistChoose.count()
        [self.hb_3strategyAssist.vbStrategy_lst[i].cbb_assistChoose.addItem(str(count+1)) for i in range(3)]

    def assistRemove(self):
        """助战列表删除后：3 个助战槽下拉框移除末尾编号并修正选中项"""
        time.sleep(0.1)
        count=self.hb_3strategyAssist.vbStrategy_lst[0].cbb_assistChoose.count()
        if self.hb_3strategyAssist.vbStrategy_lst[0].cbb_assistChoose.count()>0:
            [self.hb_3strategyAssist.vbStrategy_lst[i].cbb_assistChoose.setCurrentIndex(min(count-2,self.hb_3strategyAssist.vbStrategy_lst[i].cbb_assistChoose.currentIndex())) for i in range(3)]
            [self.hb_3strategyAssist.vbStrategy_lst[i].cbb_assistChoose.removeItem(count-1) for i in range(3)]


class HBoxLayout_AssistChoose(QHBoxLayout):
    """单个助战从者面板：名称 + 更新按钮 + 从者/礼装图片预览

    '更新'按钮：从模拟器当前截图按 Rect 裁剪出从者/礼装素材图保存到 fgoMaterial/。
    """
    def __init__(self,idx:int):
        super(HBoxLayout_AssistChoose,self).__init__()
        self.idx=idx
        self.servantFeatureInfo:dict=fixedSettingRead(['fixed','parameters','assist','assistServantFeatureInfoList',1])
        self.clothFeatureInfo:dict=fixedSettingRead(['fixed','parameters','assist','assistClothFeatureInfoList',1])
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
        """从模拟器截图按 Rect 裁剪从者/礼装素材并保存"""
        ip=ipGet()
        sysInput(f'adb connect {ip}')       
        sysInput(f'adb -s {ip} shell screencap -p /sdcard/screenshot.jpeg')
        screenPath=os.path.join(appRootGet(),'screen.jpeg')
        sysInput(f'adb -s {ip} pull /sdcard/screenshot.jpeg {screenPath}')
        currentImg=imread(screenPath)
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
        """刷新从者/礼装预览图"""
        self.la4_servantImg.setPixmap(QPixmap(f'fgoMaterial/assistServant_{self.idx}.png'))
        self.la6_clothImg.setPixmap(QPixmap(f'fgoMaterial/assistCloth_{self.idx}.png'))

    def clear(self):
        """删除面板内全部子控件（删除助战时调用）"""
        for i in range(self.count()):
            self.itemAt(i).widget().deleteLater()


class Vbox_StrategyAssistChoose(QVBoxLayout):
    """策略内的单个助战槽：下拉选择助战编号 + 从者/礼装预览 + 选中变化写配置"""
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

        # 下拉项 = fgoMaterial 下已有的助战素材编号（按编号数字排序，避免 10+ 时字典序错位）
        assistServantImgFn_lst=sorted([i for i in os.listdir('fgoMaterial') if 'assistServant_' in i],key=lambda fn:int(re.findall(r'\d+',fn)[0]))
        countOfCbb=self.cbb_assistChoose.count()
        self.cbb_assistChoose.addItems(list([str(i) for i in range(countOfCbb+1,len(assistServantImgFn_lst)+1)]))
        self.initAssistIdx=settingRead(self.settingPathLst)
        # 配置的编号可能超出素材数量（如新装用户），钳制到有效范围
        self.cbb_assistChoose.setCurrentIndex(min(self.initAssistIdx,max(0,len(assistServantImgFn_lst)-1)))
        self.cbb_assistChoose.currentIndexChanged.connect(self.update)
        self.update()
        
    def update(self):
        """切换助战编号：刷新预览图并把选中值写回配置"""
        imgFn_lst=os.listdir('fgoMaterial')
        assistServantImgFn_lst=sorted([i for i in imgFn_lst if 'assistServant_' in i],key=lambda fn:int(re.findall(r'\d+',fn)[0]))
        assistClothImgFn_lst=sorted([i for i in imgFn_lst if 'assistCloth_' in i],key=lambda fn:int(re.findall(r'\d+',fn)[0]))
        # 素材未配置（分发初始状态）时跳过预览与写配置，避免越界
        if not assistServantImgFn_lst or not assistClothImgFn_lst:
            return
        idx=min(self.cbb_assistChoose.currentIndex(),len(assistServantImgFn_lst)-1,len(assistClothImgFn_lst)-1)
        assistServantImg=assistServantImgFn_lst[idx]
        assistClothImg=assistClothImgFn_lst[idx]
        countOfCbb=self.cbb_assistChoose.count()
        self.cbb_assistChoose.addItems(list([str(i) for i in range(countOfCbb+1,len(assistServantImgFn_lst)+1)]))
        self.lb_assistServantImg.setPixmap(QPixmap('fgoMaterial/'+assistServantImg))
        self.lb_assistClothImg.setPixmap(QPixmap('fgoMaterial/'+assistClothImg))

        settingWrite(self.cbb_assistChoose.currentIndex(), self.settingPathLst)


class Hbox_3StrategyAssist(QHBoxLayout):
    """3 个助战槽的横向组合"""
    def __init__(self,sidx:int) -> None:
        super().__init__()
        self.vbStrategy_lst:list[Vbox_StrategyAssistChoose]=[]
        self.addStretch(1)
        for i in range(3):
            self.vbStrategy_lst.append(Vbox_StrategyAssistChoose(sidx,i))
            self.addLayout(self.vbStrategy_lst[i])
            self.addStretch(1)
        self.addStretch(1)
