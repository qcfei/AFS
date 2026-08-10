"""AFS 自动化状态机

Flow_General : 主流程 8 状态循环（init→before→drug→assistChoose→prepare→fight→result→fightAgain）
Flow_Assist  : 助战从者/礼装选择子流程（模板匹配 + 滚动刷新重试）
Flow_Fight   : 战斗执行子流程（技能序列执行 + 指令卡识别排序）

状态定义：每个 State 从 settingFixed.json 的 'fixed.parameters.general.<state>' 读取
特征图像、匹配阈值、动作列表；场景跳转通过邻状态图像识别驱动。
"""
from pytool.basicFunction import *
from pytool.basicFunction import np
from pytool.log import *

from cv2 import imread,imwrite,resize
import time

class State():
    """状态基类：绑定模拟器操作器与日志通道"""
    def __init__(self):
        self.simulatorOperator:SimulatorOperator=None
        self.la_log:Signal_log=None
        self.originalFrame:np.ndarray=None  # 最新一帧原始截图（minicap 原分辨率 1080×1920）

        self.isFinished=False
        
    def simulatorOperatorBind(self,simulatorOperator:SimulatorOperator):
        """绑定模拟器触控操作器"""
        self.simulatorOperator=simulatorOperator

    def logBind(self,la_log:Signal_log):
        """绑定日志通道"""
        self.la_log=la_log

    def originalFrameBind(self,frame:np.ndarray):
        """绑定最新原始帧（未降采样）"""
        self.originalFrame=frame

    def act(self):
        """状态动作入口（子类覆写）"""
        # 占位：基类不执行任何动作
        pass

class State_General(State):
    """通用配置驱动状态：从 fixed 配置加载特征/动作，并预载特征图像与掩码"""
    def __init__(self,name:str):
        super(State_General,self).__init__()
        self.name=name
        self.parameter:dict=fixedSettingRead(['fixed','parameters','general',name])

        self.idx:int=self.parameter['idx']                        # 状态索引
        self.neighborState:list[int]=self.parameter['neighborState']  # 邻状态索引列表
        self.checkMode:str=self.parameter['checkMode']            # and/or 特征判定模式
        self.featureInfo_lst:list[dict]=self.parameter['featureInfoList']  # 特征信息（含图像/掩码）
        self.action_lst:list[list[dict]]=self.parameter['actionList']     # 动作列表（点击/滑动字典）
        self.actionMethod:str=self.parameter['actionMethod']

        for featureInfo in self.featureInfo_lst:
            featureImg=imread(featureInfo['featureImagePath'])
            maskImg=imread(featureInfo['maskImgPath'])
            mask=maskMake(maskImg)
            featureInfo['featureImg']=featureImg
            featureInfo['mask']=mask

    def pause(self):
        """步间延时：动作列表每步之间的间隔"""
        time.sleep(0.6)

class State_InFight(State):
    """战斗内状态基类：维护进度、当前截图、完成标志"""
    def __init__(self):
        super(State_InFight,self).__init__()

        self.name=''

        self.progress=0            # 当前进度（状态内部使用）
        self.isFinished=False      # 本状态是否完成（驱动子流程推进）
        self.strategyText=''       # 当前执行的策略文本
        self.currentImg:np.ndarray=None  # 最新一帧截图（512×288）
        
    def currentImgBind(self,img: np.ndarray):
        """绑定最新截图帧"""
        self.currentImg=img

class Flow():
    """状态机容器：管理状态列表、共享操作器/日志/截图绑定"""
    def __init__(self,state_lst:list[State]):
        self.state_lst=state_lst

        self.state_idx:int=0     # 当前状态索引
        self.isRunning:bool=False

        self.simulatorOperator:SimulatorOperator=None
        self.la_log:Signal_log=None

        self.currentImg:np.ndarray=None

        self.grabFrame=None  # 截图回调（调用方绑定）：返回最新一帧 BGR 原分辨率；None=未绑定
        self.onFrame=None    # 帧刷新回调（调用方绑定）：识别用帧刷新后通知 GUI 预览

    def simulatorOperatorBind(self,simulatorOperator:SimulatorOperator):
        """绑定模拟器操作器并广播给所有状态"""
        self.simulatorOperator=simulatorOperator
        for state in self.state_lst:
            state.simulatorOperatorBind(simulatorOperator)

    def logBind(self,la_log:Signal_log):
        """绑定日志通道并广播给所有状态"""
        self.la_log=la_log
        for state in self.state_lst:
            state.logBind(la_log)

    def frameBind(self,grabFrame,onFrame=None):
        """绑定截图回调（grabFrame：取一帧；onFrame：识别用帧已刷新，通知 GUI 预览）"""
        self.grabFrame=grabFrame
        self.onFrame=onFrame

    def _refreshFrame(self):
        """识别前取最新一帧（随用随调）：刷新降采样 currentImg + 原始帧，并通知 GUI

        截图在需要识图时进行，不再由调用方每轮预截图。
        """
        if not self.grabFrame:
            return
        try:
            frame=self.grabFrame()
        except Exception:
            return
        if frame is None:
            return
        self.currentImgBind(imgResize2512(frame))
        self.originalFrameBind(frame)
        if self.onFrame:
            try:
                self.onFrame(frame)
            except Exception:
                pass

    def currentImgBind(self,img:np.ndarray):
        """绑定最新截图帧"""
        self.currentImg=img

    def originalFrameBind(self,frame:np.ndarray):
        """绑定最新原始帧并广播给所有状态"""
        self.originalFrame=frame
        for state in self.state_lst:
            state.originalFrameBind(frame)

    def run(self):
        """推进一帧（子类覆写）"""
        pass    

class Flow_General(Flow):
    """主流程状态机：8 状态循环，每帧执行邻状态检测与当前状态动作"""

    class State_Init(State_General):
        """状态0：初始/空闲。动作列表为空，等待外部跳转"""
        def __init__(self):
            super(Flow_General.State_Init,self).__init__('init')

        def act(self):
            pass

    class State_Before(State_General):
        """状态1：战前准备——点击开始战斗按钮"""
        def __init__(self):
            super(Flow_General.State_Before,self).__init__('before')

        def pause(self):
            time.sleep(0.5)

        def act(self):
            self.la_log.log_add('before')
            self.simulatorOperator.actionByDictList(self.action_lst[0],self.pause)
            time.sleep(4)

    class State_Drug(State_General):
        """状态2：体力回复——按设置吃指定类型的苹果"""
        def __init__(self):
            super(Flow_General.State_Drug,self).__init__('drug')
            self.appleIdx:int=settingRead(['changable','again','appleIndex']) #0,1,2,3代表金银蓝铜苹果
            self.appleName_lst:list[str]=fixedSettingRead(['fixed','appleNameList'])

        def pause(self):
            time.sleep(1)

        def act(self):
            self.la_log.log_add('drug: '+self.appleName_lst[self.appleIdx])
            self.simulatorOperator.actionByDictList(self.action_lst[self.appleIdx],self.pause)
            time.sleep(4)

    class State_AssistChoose(State_General):
        """状态3：助战选择——委托给 Flow_Assist 子流程"""
        def __init__(self):
            super(Flow_General.State_AssistChoose,self).__init__('assistChoose')
            self.flow_assist=Flow_Assist()

        def act(self):
            self.flow_assist.run()

    class State_Prepare(State_General):
        """状态4：出阵确认"""
        def __init__(self,):
            super().__init__('prepare')

        def act(self):
            self.simulatorOperator.actionByDictList(self.action_lst[0])
            time.sleep(3)

    class State_Fight(State_General):
        """状态5：战斗——委托给 Flow_Fight 子流程"""
        def __init__(self,):
            super(Flow_General.State_Fight,self).__init__('fight')
            self.flow_fight=Flow_Fight()
        
        def act(self):
            self.flow_fight.isRunning=True
            self.flow_fight.run()

    class State_Result(State_General):
        """状态6：结算界面——连续点击跳过结算"""
        def __init__(self):
            super(Flow_General.State_Result,self).__init__('result')
        
        def act(self):
            self.la_log.log_add('result')
            for i in range(8):
                self.simulatorOperator.actionByDict(self.action_lst[0][0])
                time.sleep(0.3)
            time.sleep(2)

    class State_FightAgain(State_General):
        """状态7：再来一次——按设置继续战斗或退出"""
        def __init__(self,):
            super(Flow_General.State_FightAgain,self).__init__('fightAgain')
            self.isAgain:bool=settingRead(['changable','again','isAgain'])

        def act(self):
            self.la_log.log_add('fightAgain')
            if self.isAgain:
                self.simulatorOperator.actionByDictList(self.action_lst[0])
            else:
                self.simulatorOperator.actionByDictList(self.action_lst[1])
            time.sleep(4)
    
    def __init__(self):
        self.state0_init=Flow_General.State_Init()
        self.state1_before=Flow_General.State_Before()
        self.state2_drug=Flow_General.State_Drug()
        self.state3_assistChoose=Flow_General.State_AssistChoose()
        self.state4_prepare=Flow_General.State_Prepare()
        self.state5_fight=Flow_General.State_Fight()
        self.state6_result=Flow_General.State_Result()
        self.state7_fightAgain=Flow_General.State_FightAgain()
        self.state_lst:list[State_General]=[self.state0_init,self.state1_before,self.state2_drug,self.state3_assistChoose,self.state4_prepare,
            self.state5_fight,self.state6_result,self.state7_fightAgain]
        
        self.name_lst=[self.state_lst[i].name for i in range(len(self.state_lst))]
        self.neighborState_lst=[self.state_lst[i].neighborState for i in range(len(self.state_lst))]
        
        super(Flow_General,self).__init__(self.state_lst)
        self.fightCount=settingRead(['changable','again','fightCount'])      # 总战斗次数
        self.fightCurrentCount=0                                             # 已完成战斗次数
        settingWrite(self.fightCurrentCount,['changable','fightCurrentCount'])
        self.isLock=False   # 结算计数锁（防止同一结算重复计数）
        self.isQuit=False   # 全部完成标志

        self.state_idx=0

    def run(self):
        """推进一帧：
        1) 取最新帧（随用随调）
        2) 检测邻状态是否出现，出现则跳转
        3) 检测当前状态特征，命中则执行该状态动作
        4) 结算状态时累计战斗次数，达上限则停止
        """
        self._refreshFrame()
        state=self.state_lst[self.state_idx]
        print('checking neighbor states')
        for neighborStateI in state.neighborState:
            neighborState=self.state_lst[neighborStateI]
            print(str(neighborStateI)+' -> ',end=' ')
            flag=checkIsFeatureScene(neighborState.featureInfo_lst,self.currentImg,neighborState.checkMode,isPrint=True)
            if flag:
                self.state_idx=neighborStateI
                state=self.state_lst[self.state_idx]
                break
            
        if not self.isQuit:
            print('checking current state')
            print(str(self.state_idx)+' -> ',end=' ')
            flag=checkIsFeatureScene(state.featureInfo_lst,self.currentImg,state.checkMode)
            if (flag or 
                (self.state_idx==5 and np.max([state.progress!=0 for state in self.state5_fight.flow_fight.state_lst])==True)):
                state.act()

        if self.state_idx==6:   
            self.state5_fight.flow_fight.refresh()

        if self.state_idx==6 and not self.isLock:
            self.fightCurrentCount+=1
            print('finished'+str(self.fightCurrentCount)+'/'+str(self.fightCount))
            settingWrite(self.fightCurrentCount,['changable','fightCurrentCount'])
            self.isLock=True
            if self.fightCurrentCount>=self.fightCount:
                self.isRunning=False
                self.isQuit=True
                
        elif self.state_idx!=7:
            self.isLock=False

        time.sleep(0.2)

    def currentImgBind(self, img: np.ndarray):
        super().currentImgBind(img)

    def frameBind(self, grabFrame, onFrame=None):
        """绑定截图回调并广播给子流程（助战/战斗）"""
        super().frameBind(grabFrame, onFrame)
        self.state3_assistChoose.flow_assist.frameBind(grabFrame, onFrame)
        self.state5_fight.flow_fight.frameBind(grabFrame, onFrame)

class Flow_Assist(Flow):
    """助战选择子流程

    在助战列表中模板匹配目标从者（可附带礼装条件），命中则点击选中；
    失败累计 5 次后执行"刷新助战列表"动作重试。
    """
    def __init__(self, ):
        state_lst=[]

        self.strategyIdx=settingRead(['changable','currentStrategyIndex'])       # 当前策略索引
        self.strategyAssistChooseLst=settingRead(['changable','strategyAssistChoose',self.strategyIdx])  # 该策略选定的助战编号列表
        self.failNum=0       # 当前连续失败次数
        self.refreshNum=0    # 刷新次数
        self.isConcernCloth=settingRead(['changable','isCloth'])   # 是否关心礼装
        super().__init__(state_lst)
        
        self.parameter:dict=fixedSettingRead(['fixed','parameters','assist'])
        self.assistServantFeatureInfo_lst:list[dict]=self.parameter['assistServantFeatureInfoList']
        self.assistClothFeatureInfo_lst:list[dict]=self.parameter['assistClothFeatureInfoList']
        # 按策略选定的助战编号拼接特征图像路径（assistServant_1.png ~ _N.png）
        for assistServantFeatureInfoI in range(len(self.assistServantFeatureInfo_lst)):
            assistServantFeatureInfo=self.assistServantFeatureInfo_lst[assistServantFeatureInfoI]
            assistClothFeatureInfo=self.assistClothFeatureInfo_lst[assistServantFeatureInfoI]
            assistServantFeatureInfo['featureImagePath']=assistServantFeatureInfo['featureImagePath'][:-5]+str(self.strategyAssistChooseLst[assistServantFeatureInfoI]+1)+assistServantFeatureInfo['featureImagePath'][-4:]
            assistClothFeatureInfo['featureImagePath']=assistClothFeatureInfo['featureImagePath'][:-5]+str(self.strategyAssistChooseLst[assistServantFeatureInfoI]+1)+assistClothFeatureInfo['featureImagePath'][-4:]
            assistServantFeatureInfo['featureImg']=imread(assistServantFeatureInfo['featureImagePath'])
            assistClothFeatureInfo['featureImg']=imread(assistClothFeatureInfo['featureImagePath'])
        print([assistServantFeatureInfo['featureImagePath'] for assistServantFeatureInfo in self.assistServantFeatureInfo_lst])
        
        self.failAction_lst:list[list[list[int]]]=self.parameter['failActionList']  # 失败动作序列 [滚动, 刷新]

    def findTargetServant(self)->list[int]:
        """在当前截图里查找目标助战从者位置

        匹配所有目标从者/礼装特征；若关心礼装则要求从者与礼装位置符合相对偏移，
        返回命中的从者中心坐标；未命中返回 None。
        """
        servantX_lst:list[int]=[]
        servantY_lst:list[int]=[]
        h,w=self.assistServantFeatureInfo_lst[0]['Rect'][2:4]
        print('assist servant')
        for assistServantFeatureInfo in self.assistServantFeatureInfo_lst:
            servant_lst=findWhereMatched(assistServantFeatureInfo,self.currentImg)
            servantY_lst+=servant_lst[0]
            servantX_lst+=servant_lst[1]
        if self.isConcernCloth:
            clothX_lst:list[int]=[]
            clothY_lst:list[int]=[]
            print('assist cloth')
            for assistClothFeatureInfo in self.assistClothFeatureInfo_lst:
                cloth_lst=findWhereMatched(assistClothFeatureInfo,self.currentImg)
                clothY_lst+=cloth_lst[0]
                clothX_lst+=cloth_lst[1]
            radio=6
            # 礼装相对从者的位置偏移（由特征 Rect 计算）
            dyx=[assistClothFeatureInfo['Rect'][dxyi]-assistServantFeatureInfo['Rect'][dxyi] for dxyi in range(2)]
            flag=False
            for servantI in range(len(servantX_lst)):
                for clothI in range(len(clothX_lst)):
                    if abs(clothY_lst[clothI]-servantY_lst[servantI]-dyx[0])<radio and abs(clothX_lst[clothI]-servantX_lst[servantI]-dyx[1])<radio:
                        flag=True
                        return [servantX_lst[servantI]+w//2,servantY_lst[servantI]+h//2]
            if not flag:
                return None
        else:
            if len(servantX_lst)==0:
                return None
            else:
                return [servantX_lst[0]+w//2,servantY_lst[0]+h//2]
        
    def pause(self):
        time.sleep(0.6)

    def run(self):
        """推进一帧：取最新帧 → 查找目标→点击；失败则滚动/刷新重试"""
        self._refreshFrame()
        point=self.findTargetServant()
        if point!=None:
            action=[0,point[0],point[1]]
            self.simulatorOperator.actionByDict(action)
            self.la_log.log_add(f'success in {str(self.refreshNum)}-{str(self.failNum)} times',min(1,self.failNum+self.refreshNum))
            self.isRunning=False
        else:
            if self.failNum<5:
                self.simulatorOperator.actionByDictList(self.failAction_lst[0])
                self.failNum+=1
                self.la_log.log_add(f'fail {str(self.refreshNum)}-{str(self.failNum)} times',min(1,self.failNum+self.refreshNum))
                time.sleep(2)
            else:
                self.simulatorOperator.actionByDictList(self.failAction_lst[1],self.pause)
                self.failNum=0
                self.refreshNum+=1
                self.la_log.log_add(f'fail {str(self.refreshNum)}-{str(self.failNum)} times',1)
                time.sleep(2)
           
class Flow_Fight(Flow):
    """战斗执行子流程

    状态序列：State_Check(读取出战从者头像) → State_Skill(技能) → State_Order(指令卡) 循环 3 回合，
    若策略含换人技能(530)则回合间插入额外的 State_Check。
    """

    class State_Check(State_InFight):
        """检查状态：逐个点击出战从者查看详情并截取头像，供指令卡识别使用"""

        def __init__(self,):
            super().__init__()
            self.roleNum=6  # 需检查的从者数量（前3个出战，含备用）
            
            step=150
            self.loc_lst=[np.array((50+step*i,175))for i in range(3)]  # 从者头像点击位置
            pos_lst:dict[str,list[list[int]]]=fixedSettingRead(['fixed','skill_pas'])
            self.quitAction=[0,pos_lst['0'][0][0],pos_lst['0'][0][1]]  # 详情页返回动作

            self.checkAble=False

            self.greatMask=imread('mask/greatMask.png',0)   # 头像剪影掩码
            self.maskwh=whOfImg(self.greatMask)
            
        def imgSave(self):
            """截取当前从者头像区域并保存到 fgoMaterial/preServantN.png"""
            img=cutImg(self.currentImg,np.array((100,53)),np.array((63,63*8//6)))
            imgmskd=np.array([[(0,0,255) if self.greatMask[yi,xi]==0 else img[yi,xi] for xi in range(self.maskwh[0])]for yi in range(self.maskwh[1])],np.uint8)
            imwrite(f'fgoMaterial/preServant{str(self.progress//2+1)}.png',imgmskd)
            # 眼睛区模板：详情面板固定位置 (512 坐标 114,86 起 29x12)，供指令卡从者识别
            # 跨"详情面板/指令卡"同源且无遮挡；保持 512 分辨率（高分辨率会暴露立绘细节差异）
            # 2026-08-09：多 y 带保存（80/86/92）——不同从者立绘眼睛位置不同（实测 59~103），
            # 固定单带只对部分从者有效；多带匹配取 max 提升判别力（详见 wiki/vision.md）
            for eyeY0 in (80,86,92):
                eyeImg=cutImg(self.currentImg,np.array((114,eyeY0)),np.array((29,12)))
                imwrite(f'fgoMaterial/eyeServant{str(self.progress//2+1)}.png' if eyeY0==86
                        else f'fgoMaterial/eyeServant{str(self.progress//2+1)}_{eyeY0}.png',eyeImg)
            # 宝具卡图：详情面板固定位置 (512 坐标 100,71 起 61x75，1080 (377,265) 230x281 缩放)，
            # 供指令卡从者识别（蒙版匹配方案，见 State_Order.orderCardRecognize）
            baojuImg=cutImg(self.currentImg,np.array((100,71)),np.array((61,75)))
            imwrite(f'fgoMaterial/baojuServant{str(self.progress//2+1)}.png',baojuImg)

        def pause(self):
            time.sleep(0.4)

        def act(self):
            """每帧推进：先点击从者查看详情，下一帧截图保存并返回"""
            if self.progress<self.roleNum:
                if not self.checkAble:
                    # 点击当前从者头像 → 打开详情页
                    self.simulatorOperator.actionByDict([0,self.loc_lst[self.progress//2][0],self.loc_lst[self.progress//2][1]])
                    time.sleep(0.8)
                    self.simulatorOperator.actionByDict([0,95,30])
                    self.checkAble=True
                else:
                    self.imgSave()
                    self.simulatorOperator.actionByDict(self.quitAction)
                    time.sleep(0.8)
                    self.checkAble=False
                self.progress+=1
            else :
                self.progress=0
                self.isFinished=True
            
    class State_Skill(State_InFight):
        """技能状态：按策略文本执行技能序列

        策略文本形如 "110 120 231"：三位一组，前两位为 从者_技能，第三位为 目标从者。
        """

        def __init__(self,idx:int,strategy:str):
            super(Flow_Fight.State_Skill,self).__init__()

            self.name='skill'+str(idx//2+1)
            self.idx=idx

            self.strategySpilted=strategy.split(' ')
            pos_lst:dict[str,list[list[int]]]=fixedSettingRead(['fixed','skill_pas'])
            self.action_lst:list[list[dict]]=[]
            self.strategyNum_lst:list[int]=[]
            for singleAction in self.strategySpilted:
                action=[]
                str1=f'{singleAction[0]}_{singleAction[1]}'
                action+=[[0,pos[0],pos[1]] for pos in pos_lst[str1]]
                action+=[[0,pos[0],pos[1]] for pos in pos_lst[singleAction[2]]]
                action+=[[0,pos_lst['0'][0][0],pos_lst['0'][0][1]]]
                self.action_lst.append(action)
                self.strategyNum_lst.append(len(self.action_lst)-1)

        def pause(self):
            time.sleep(0.8)

        def act(self):
            """每帧执行一个技能组，全部执行完置 isFinished"""
            if self.progress<len(self.strategySpilted):
                self.strategyText=self.strategyText+self.strategySpilted[self.progress]+' '
            self.la_log.log_add('skill: '+self.strategyText,min(1,self.progress))
            self.simulatorOperator.actionByDictList(self.action_lst[self.progress],self.pause)
            self.progress+=1
            time.sleep(0.4)
            if self.progress==len(self.action_lst):
                self.isFinished=True
                self.progress=0
                    
    class State_Order(State_InFight):
        """指令卡状态：识别 5 张指令卡的颜色与从者，按策略文本生成点击序列

        策略文本形如 "z/b1 r1 g1"：'/' 分隔步骤，空格分隔同一步骤内可交换的卡；
        z/x/c/1~5 为固定位置指令，b/r/g+数字 为按 颜色+从者 匹配的指令卡。
        """

        def __init__(self,idx:int,strategy:str):
            super(Flow_Fight.State_Order,self).__init__()

            self.name='order'+str(idx//2+1)
            self.idx=idx
            self.strategy=strategy
            
            self.wNum=5  # 指令卡数量
            self.w_lst=[512*i//self.wNum for i in range(self.wNum)]+[512]  # 5 等分横向分界
            self.yMin=140  # 指令卡区域起始 y

            self.colorImgFn_lst:list[str]=fixedSettingRead(['fixed','parameters','fight','order','colorImgPathList'])
            self.colorImg_lst=[imread(fn) for fn in self.colorImgFn_lst]
            self.color_lst=['r','g','b']

            self.servantImgFn_lst:list[str]=fixedSettingRead(['fixed','parameters','fight','order','servantImgPathList'])
            self.servant_lst=['1','2','3']  # eyeServant/preServant 编号 ↔ 从者编号（State_Check 按 1→3 顺序截取）
            self.roleImgListLoad()

            self.pos_lst:dict[str,list[list[int]]]=fixedSettingRead(['fixed','order_pas'])
            self.action:list[dict]=[[0,self.pos_lst['i'][0],self.pos_lst['i'][1]]]  # 攻击按钮动作
            self.orderAction:list[dict]=[]
            self.orderIndex_lst=['uc']*self.wNum  # 每张卡的识别结果（'uc'=未识别）

        def roleImgListLoad(self):
            """加载出战从者头像（用于指令卡从者匹配）"""
            self.servantImg_lst=[imread(fn) for fn in self.servantImgFn_lst]
            # 眼睛区模板：详情面板固定位置截取（State_Check.imgSave 保存），跨详情面板/指令卡同源
            # 多 y 带（80/86/92）：不同从者立绘眼睛位置不同，匹配时多带取 max
            self.eyeImg_lst=[]
            for i in range(1,4):
                bands=[imread(f'fgoMaterial/eyeServant{i}.png')]
                bands+=[imread(f'fgoMaterial/eyeServant{i}_{y0}.png') for y0 in (80,92)]
                self.eyeImg_lst.append([b for b in bands if b is not None])
            # 宝具卡模板：详情面板固定位置截取（State_Check.imgSave 保存），与指令卡立绘同源
            # 蒙版匹配方案用（9 色号反向蒙版 + 去均值相关），缺失时从者识别退化为 uc
            self.baojuImg_lst=[imread(f'fgoMaterial/baojuServant{i}.png') for i in range(1,4)]
            # 2026-08-10：同一从者重复出场时宝具卡模板像素完全相同（如 lineup05 从者2/3）——
            # 匹配分数必然相同（gap=0 误判 uc）。加载时按像素完全相同去重，判定后映射回原从者编号
            self.baojuUniq:list[np.ndarray]=[]
            self.baojuUniqMap:list[int]=[]
            for i,img in enumerate(self.baojuImg_lst):
                if img is None:
                    continue
                # 近似去重：差异像素比例 <0.5%（同从者两次截图间立绘动画/特效有微差，实测 22px/13725）
                idx=next((j for j,u in enumerate(self.baojuUniq)
                          if u.shape==img.shape and
                          (np.abs(u.astype(np.int32)-img.astype(np.int32)).sum(axis=2)>20).mean()<0.005),None)
                if idx is None:
                    self.baojuUniq.append(img)
                    self.baojuUniqMap.append(i)

        def locateCards(self)->list[tuple[int,int]]:
            """金边搜索定位 5 张指令卡（512 坐标系，蒙版匹配方案用）

            5 等分初筛 + 列窄强线（金色 RGB(243,238,133) 容差 30，宽≤2 且 n≥8 的最左带）定 left，
            行方向 y140-200 范围第一条 n≥8 强带定 top；left 缺失时用偏移先验补（实测 ~21px）。
            返回 [(left,top),...]（卡片固定尺寸 61x75）。
            """
            gold=((np.abs(self.currentImg[:,:,0].astype(np.int16)-133)<30)&
                  (np.abs(self.currentImg[:,:,1].astype(np.int16)-238)<30)&
                  (np.abs(self.currentImg[:,:,2].astype(np.int16)-243)<30))
            toplefts:list[tuple[int|None,int|None]]=[]
            for ci in range(self.wNum):
                x0,x1=self.w_lst[ci],self.w_lst[ci+1]
                seg=gold[self.yMin:self.yMin+100,x0:x1]
                rowcnt=seg.sum(axis=1)
                top=None
                for yy in range(len(rowcnt)):
                    if rowcnt[yy]>=8 and yy+self.yMin>=140 and yy+self.yMin<=200:
                        top=yy+self.yMin
                        break
                colcnt=seg.sum(axis=0)
                left=None
                # 偏移先验窗口（5 等分起点 + 21±10）：左金框线只在此范围找，
                # 排除卡内立绘金色线干扰（实测 c1 左框线被立绘盖住时卡内 x48/64 有金线）
                for xx in range(len(colcnt)):
                    if colcnt[xx]>=8:
                        j=xx
                        while j+1<len(colcnt) and colcnt[j+1]>=8:
                            j+=1
                        if j-xx+1<=2 and abs(xx-21)<=10:
                            left=xx
                            break
                # 窗口内无窄强线 → left 保持 None，由偏移先验兜底
                toplefts.append((None if left is None else x0+left,top))
            # 偏移先验补缺失 left（5 等分起点 + 偏移均值 ~21）
            offs=[v[0]-self.w_lst[i] for i,v in enumerate(toplefts) if v[0] is not None]
            off=round(sum(offs)/len(offs)) if offs else 21
            tops=[v[1] for v in toplefts if v[1] is not None]
            top0=round(sum(tops)/len(tops)) if tops else 164
            return [(self.w_lst[i]+off if lx is None else lx,
                     top0 if ty is None else ty) for i,(lx,ty) in enumerate(toplefts)]

        def orderCardRecognize(self):
            """识别 5 张指令卡：先匹配颜色（红/绿/蓝），再匹配从者（蒙版匹配方案）"""
            crdImg_lst=[]
            gtMask=imread('mask/greatMask.png',0).astype(np.float32)

            clrRes=[0]*5
            rleRes=['uc']*5  # 初始 'uc' 兜底：任何漏赋值的卡按未识别处理
            clrInfo_lst=[(clrTmp,maskMake(clrTmp)) for clrTmp in self.colorImg_lst]
            cards=self.locateCards()

            for cardI in range(self.wNum):
                # 裁剪单张指令卡区域
                cardAreaImg=cutImg(self.currentImg,np.array((self.w_lst[cardI],self.yMin)),np.array((self.w_lst[cardI+1]-self.w_lst[cardI],self.yMin+120)))
                # 颜色识别：三色模板中取相似度最高者
                clrMaxIdx,clrMaxVal=0,0
                for clrTmpI in range(len(self.colorImg_lst)):
                    clrTmpLm,clrMskLm=clrInfo_lst[clrTmpI]
                    clrVal,clrLoc=selfmatchTemplate(cardAreaImg,clrTmpLm,clrMskLm)
                    if clrVal>clrMaxVal:
                        clrMaxVal=clrVal
                        clrMaxIdx=clrTmpI
                        clrMaxLoc=clrLoc
                clrRes[cardI]=clrMaxIdx

                # 按颜色模板位置裁剪卡面，掩掉非颜色区/剪影区
                crdImg=cutImg(cardAreaImg,clrMaxLoc,np.array((clrTmpLm.shape[1],clrTmpLm.shape[0])))
                crdImgMskd=np.array([[(0,0,255) if gtMask[yi,xi]==0 or pixCheck(crdImg[yi,xi]) else crdImg[yi,xi] for xi in range(crdImg.shape[1])] for yi in range(crdImg.shape[0])],np.uint8)
                crdImg_lst.append(crdImgMskd)
                
                # 从者识别（蒙版匹配方案 2026-08-10 落地，替换多 y 带眼睛模板）：
                # 模板 = 卡片内 (3,12) 起 49x16 头部条带（上缩 1/5 右缩 1/8，避开助战文章干扰）
                #       + 9 色号反向蒙版（TOL=15，排除背景板色）；
                # 与 3 个宝具卡模板（State_Check.imgSave 截取）去均值相关匹配（maskedCCOEFF，
                # 区分度 gap 0.2-0.7，默认方法）。实测 lineup05 512 分辨率 5/5。
                rleScores:list[float]=[]
                lx,ly=cards[cardI]
                tpl=cutImg(self.currentImg,np.array((lx+3,ly+12)),np.array((49,16)))
                tplMsk=build9Mask(tpl)
                # 用去重后的宝具卡模板匹配（同一从者重复出场合并为一个候选）
                for baoju in self.baojuUniq:
                    rleScores.append(maskedCCOEFF(baoju,tpl,tplMsk))
                # 宝具卡模板缺失（baojuUniq 空）时从者识别退化为 uc
                if not rleScores:
                    rleRes[cardI]='uc'
                    continue
                # 不确定标记：分数低于阈值 或 最高与次高差距过小 → 'uc'（由策略退化逻辑兜底）
                best1=sorted(rleScores,reverse=True)
                if best1[0]<0.30 or (len(best1)>1 and best1[0]-best1[1]<0.05):
                    rleRes[cardI]='uc'
                else:
                    rleRes[cardI]=self.baojuUniqMap[rleScores.index(best1[0])]

            # 汇总为 "颜色+从者" 标签（如 b1 / r2 / g3）；识别不确定的卡标 'uc'
            self.orderIndex_lst=[]
            for i in range(self.wNum):
                if rleRes[i]=='uc':
                    self.orderIndex_lst.append('uc')
                else:
                    self.orderIndex_lst.append(self.color_lst[clrRes[i]]+self.servant_lst[rleRes[i]])
                            

        def strategyGenerate(self):
            """把策略文本翻译为具体指令卡点击序列

            - 直接指令（z/x/c/1~5）：直接落位
            - 条件指令（如 b1）：在识别结果中找该卡，找不到则按列表顺序取一张未用卡
            """
            directStep:list[str]=['z','x','c','1','2','3','4','5']
            strategySplited=self.strategy.split('/')

            self.originalStrategy:list[str]=[]
            self.orderAction=[]

            for singleStep in strategySplited:
                step_list=singleStep.split()
                f=False
                if len(step_list)==1 and step_list[0] in directStep: 
                    self.originalStrategy+=[step_list[0]]
                else:
                    for step in step_list:
                        if step in self.orderIndex_lst:
                            idx=self.orderIndex_lst.index(step)
                            self.originalStrategy+=[str(idx+1)]
                            self.orderIndex_lst[idx]='uc'
                            f=True
                            break
                    if not f:
                        # 找不到匹配卡时退化为：取第一张未被占用的卡
                        for idx in range(len(self.orderIndex_lst)):
                            if self.orderIndex_lst[idx]!='uc':
                                self.originalStrategy+=[str(idx+1)]
                                self.orderIndex_lst[idx]='uc'
                                break
            for singleAction in self.originalStrategy:
                self.orderAction+=[[0,self.pos_lst[singleAction][0],self.pos_lst[singleAction][1]]]

        def pause(self):
            time.sleep(0.6)

        def act(self):
            """三帧推进：点击攻击按钮 → 加载头像 → 识别并执行指令卡序列"""
            if self.progress==0:
                self.simulatorOperator.actionByDict(self.action[0])
                self.roleImgListLoad()
                self.progress=1
                time.sleep(1)
            elif self.progress==1:
                self.progress=2
            elif self.progress==2:
                self.orderCardRecognize()
                print(self.orderIndex_lst)
                self.la_log.log_add(f'orderCard: {list2str(self.orderIndex_lst)}')
                time.sleep(0.3)
                self.strategyGenerate()
                print(self.originalStrategy)
                self.la_log.log_add(f'orderResult: {list2str(self.originalStrategy)}')
                time.sleep(0.3)
                self.simulatorOperator.actionByDictList(self.orderAction,self.pause)
                self.progress=0
                self.isFinished=True
                time.sleep(10)

    def __init__(self):
        self.idx=5
        self.state_idx=0    
        strategyIdx=settingRead(['changable','currentStrategyIndex'])
        self.strategy_lst=settingRead(['changable','strategy',strategyIdx])
            
        # 状态序列：Check + (Skill, [Check], Order) × 3 回合 + 末尾补 Order
        self.state_lst:list[State_InFight]=[Flow_Fight.State_Check()]
        self.checkNum=1
        for idx in range(3):
            self.state_lst.append(Flow_Fight.State_Skill(2*idx,self.strategy_lst[f'skill{str(idx+1)}']))
            if '530' in self.strategy_lst[f'skill{str(idx+1)}']:  # 策略含换人技(530)时回合中需重新读头像
                self.state_lst.append(Flow_Fight.State_Check())
                self.checkNum+=1
            self.state_lst.append(Flow_Fight.State_Order(2*idx+1,self.strategy_lst[f'order{str(idx+1)}']))
        self.state_lst.append(Flow_Fight.State_Order(6+self.checkNum,'1/2/3'))
        super(Flow_Fight,self).__init__(self.state_lst)

    def refresh(self):
        """重置战斗子流程全部状态（新一场战斗开始时调用）"""
        self.state_idx=0
        for state in self.state_lst:
            state.progress=0
            state.isFinished=False
            state.strategyText=''

    def run(self):
        """推进一帧：取最新帧 → 执行当前状态动作，完成后切换到下一状态"""
        self._refreshFrame()
        self.state_lst[self.state_idx].act()
        if self.state_lst[self.state_idx].isFinished:
            self.state_idx+=1
        if self.state_idx>6+self.checkNum:
            self.state_idx=6+self.checkNum
            self.state_lst[6+self.checkNum].isFinished=False

    def currentImgBind(self,img: np.ndarray):
        super(Flow_Fight,self).currentImgBind(img)
        for state in self.state_lst:
            state.currentImgBind(img)