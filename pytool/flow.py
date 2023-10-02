from pytool.basicFunction import *
from pytool.basicFunction import np
from pytool.log import *

import cv2
import time


class State():
    def __init__(self):
        self.simulatorOperator:SimulatorOperator=None
        self.la_log:Signal_log=None

        self.isFinished=False
        
    def simulatorOperatorBind(self,simulatorOperator:SimulatorOperator):
        self.simulatorOperator=simulatorOperator

    def logBind(self,la_log:Signal_log):
        self.la_log=la_log

    def act(self):
        # waiting for rewriting
        pass

class State_General(State):
    def __init__(self,name:str):
        super(State_General,self).__init__()
        self.name=name
        self.parameter:dict=settingRead(['fixed','parameters','general',name])

        self.idx:int=self.parameter['idx']
        self.neighborState:list[int]=self.parameter['neighborState']
        self.checkMode:str=self.parameter['checkMode']
        self.featureInfo_lst:list[dict]=self.parameter['featureInfoList']
        self.action_lst:list[list[dict]]=self.parameter['actionList']
        self.actionMethod:str=self.parameter['actionMethod']

        for featureInfo in self.featureInfo_lst:
            featureImg=cv2.imread(featureInfo['featureImagePath'])
            maskImg=cv2.imread(featureInfo['maskImgPath'])
            mask=maskMake(maskImg)
            featureInfo['featureImg']=featureImg
            featureInfo['mask']=mask

    def pause(self):
        time.sleep(0.3)

class State_InFight(State):
    def __init__(self):
        super(State_InFight,self).__init__()

        self.name=''

        self.progress=0
        self.isFinished=False
        self.strategyText=''
        self.currentImg:np.ndarray=None
        
    def currentImgBind(self,img: np.ndarray):
        self.currentImg=img

class Flow():
    def __init__(self,state_lst:list[State]):
        self.state_lst=state_lst

        self.state_idx:int=0
        self.isRunning:bool=False

        self.simulatorOperator:SimulatorOperator=None
        self.la_log:Signal_log=None

        self.currentImg:np.ndarray=None

    def simulatorOperatorBind(self,simulatorOperator:SimulatorOperator):
        self.simulatorOperator=simulatorOperator
        for state in self.state_lst:
            state.simulatorOperatorBind(simulatorOperator)

    def logBind(self,la_log:Signal_log):
        self.la_log=la_log
        for state in self.state_lst:
            state.logBind(la_log)

    def currentImgBind(self,img:np.ndarray):
        self.currentImg=img

    def run(self):
        pass    

class Flow_General(Flow):

    class State_Init(State_General):
        def __init__(self):
            super(Flow_General.State_Init,self).__init__('init')

        def act(self):
            pass

    class State_Before(State_General):
        def __init__(self):
            super(Flow_General.State_Before,self).__init__('before')

        def pause(self):
            time.sleep(0.5)

        def act(self):
            self.la_log.log_add('before')
            self.simulatorOperator.actionByDictList(self.action_lst[0],self.pause)
            time.sleep(2)

    class State_Drug(State_General):
        def __init__(self):
            super(Flow_General.State_Drug,self).__init__('drug')
            self.appleIdx:int=settingRead(['changable','again','appleIndex']) #0,1,2,3代表金银蓝铜苹果
            self.appleName_lst:list[str]=settingRead(['fixed','appleNameList'])

        def pause(self):
            time.sleep(1)

        def act(self):
            self.la_log.log_add('drug: '+self.appleName_lst[self.appleIdx])
            self.simulatorOperator.actionByDictList(self.action_lst[self.appleIdx],self.pause)
            time.sleep(3)

    class State_AssistChoose(State_General):
        def __init__(self):
            super(Flow_General.State_AssistChoose,self).__init__('assistChoose')
            self.flow_assist=Flow_Assist()

        def act(self):
            self.flow_assist.run()

    class State_Prepare(State_General):
        def __init__(self,):
            super().__init__('prepare')
            self.fightCurrentCount=0
            self.progress:int=0
            self.initF=False
            self.currentImg:np.ndarray=None
            self.isCheckServantIconFirstTime:bool=settingRead(['changable','isCheckServantIconFirstTime'])

        def act(self):
            if self.progress==0:
                self.la_log.log_add('prepare')
                self.fightCurrentCount=settingRead(['changable','fightCurrentCount'])
                if self.fightCurrentCount==0:
                    if self.isCheckServantIconFirstTime:
                        self.progress=1
                    else:
                        self.progress=5
                else :
                    self.progress=5
            elif self.progress<5:
                    if self.progress==settingRead(['changable','assistIndex']):
                        self.progress+=1
                    else:
                        if not self.initF:
                            self.simulatorOperator.actionByDictList(self.action_lst[1+self.progress])
                            self.initF=True
                            time.sleep(3)
                        else:
                            # cv2.imshow(',',self.currentImg)
                            # cv2.waitKey(0)
                            # cv2.destroyAllWindows()
                            checkF=self.preServantGet(self.progress-1)
                            if checkF:
                                self.simulatorOperator.actionByDictList(self.action_lst[6])
                                self.progress+=1
                                self.initF=False
                            else:
                                self.simulatorOperator.actionByDictList(self.action_lst[1])
                            time.sleep(0.8)
            elif self.progress==5:
                self.simulatorOperator.actionByDictList(self.action_lst[0])
                self.progress=0
                time.sleep(3)

        def currentImgBind(self,img:np.ndarray):
            self.currentImg=img

        def preServantGet(self,idx:int):
            w0=50
            h1,w1=110,90
            h0=h1*w0//w1
            maskImgR=cv2.imread('mask/orderRed.png')
            maskImgR=cv2.resize(maskImgR,(w0,h0))
            mask=maskMake(maskImgR)
            res=cv2.matchTemplate(self.currentImg,maskImgR,cv2.TM_CCOEFF_NORMED,mask=mask)
            _,maxVal,_,maxLoc=cv2.minMaxLoc(res)
            if maxVal>0.45:
                x0,y0=maxLoc
                imgCut=self.currentImg[y0:y0+h0,x0:x0+w0]
                maskImgR=cv2.imread('mask/orderRed.png')
                maskImgG=cv2.imread('mask/orderGreen.png')
                maskImgB=cv2.imread('mask/orderBlue.png')
                h,w=maskImgR.shape[:2]
                imgCut=cv2.resize(imgCut,(w,h))
                maskR=np.array([[255 if min(pt==[0,0,255])==False else 0 for pt in ptLine]for ptLine in maskImgR],np.float32)
                maskG=np.array([[255 if min(pt==[0,0,255])==False else 0 for pt in ptLine]for ptLine in maskImgG],np.float32)
                maskB=np.array([[255 if min(pt==[0,0,255])==False else 0 for pt in ptLine]for ptLine in maskImgB],np.float32)
                imgMasked=np.array([[[0,0,255] if (maskR[yi,xi]==255 or maskG[yi,xi]==255 or maskB[yi,xi]==255 or 
                                                (imgCut[yi,xi,0]<30 and imgCut[yi,xi,1]<30 and imgCut[yi,xi,2]>100) or 
                                                ((imgCut[yi,xi,0]<60 and imgCut[yi,xi,1]<60 and imgCut[yi,xi,2]<60) and
                                                    (imgCut[yi,xi,0]>37 and imgCut[yi,xi,1]>37 and imgCut[yi,xi,2]>37)))
                                                else imgCut[yi,xi] for xi in range(w)]for yi in range(h)],np.uint8)
                cv2.imwrite(f'fgoMaterial/preServant{str(idx+1)}.png',imgMasked)
                self.la_log.log_add(f'r{list2str([str(i+1) for i in range(idx+1)])} found',min(idx,1))
                print(idx,'found')
                return True
            else:
                return False

    class State_Fight(State_General):
        def __init__(self,):
            super(Flow_General.State_Fight,self).__init__('fight')
            self.flow_fight=Flow_Fight()
        
        def act(self):
            self.flow_fight.isRunning=True
            self.flow_fight.run()

    class State_Result(State_General):
        def __init__(self):
            super(Flow_General.State_Result,self).__init__('result')
        
        def act(self):
            self.la_log.log_add('result')
            for i in range(8):
                self.simulatorOperator.actionByDict(self.action_lst[0][0])
                time.sleep(0.3)
            time.sleep(2)

    class State_FightAgain(State_General):
        def __init__(self,):
            super(Flow_General.State_FightAgain,self).__init__('fightAgain')
            self.isAgain:bool=settingRead(['changable','again','isAgain'])

        def act(self):
            self.la_log.log_add('fightAgain')
            if self.isAgain:
                self.simulatorOperator.actionByDictList(self.action_lst[0])
            else:
                self.simulatorOperator.actionByDictList(self.action_lst[1])
            time.sleep(2)
    
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
        self.fightCount=settingRead(['changable','again','fightCount'])
        self.fightCurrentCount=0
        settingWrite(self.fightCurrentCount,['changable','fightCurrentCount'])
        self.isLock=False
        self.isQuit=False

        self.state_idx=0

    def run(self):
        # cv2.imshow(',',self.currentImg)
        # cv2.waitKey(0)
        # cv2.destroyAllWindows()
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
            
        if self.state_idx==7 and not self.isLock:
            self.fightCurrentCount+=1
            print('finished'+str(self.fightCurrentCount)+'/'+str(self.fightCount))
            settingWrite(self.fightCurrentCount,['changable','fightCurrentCount'])
            self.isLock=True
            if self.fightCurrentCount>=self.fightCount:
                self.isRunning=False
                self.isQuit=True
        elif self.state_idx!=7:
            self.isLock=False
        
        if not self.isQuit:
            print('checking current state')
            print(str(self.state_idx)+' -> ',end=' ')
            flag=checkIsFeatureScene(state.featureInfo_lst,self.currentImg,state.checkMode)
            if (flag or 
                (self.state_idx==4 and self.state4_prepare.progress!=0) or
                (self.state_idx==5 and np.max([self.state5_fight.flow_fight.state_lst[i].progress!=0 for i in [1,3,5,6]])==True)):
                state.act()

        if self.state_idx==6:   
            self.state5_fight.flow_fight.refresh()

        time.sleep(0.2)

    def currentImgBind(self, img: np.ndarray):
        super().currentImgBind(img)
        self.state4_prepare.currentImgBind(img)

class Flow_Assist(Flow):
    def __init__(self, ):
        state_lst=[]

        self.failNum=0
        self.refreshNum=0
        self.isConcernCloth=settingRead(['changable','isCloth'])
        super().__init__(state_lst)
        
        self.parameter:dict=settingRead(['fixed','parameters','assist'])
        self.assistServantFeatureInfo_lst:list[dict]=self.parameter['assistServantFeatureInfoList']
        self.assistClothFeatureInfo_lst:list[dict]=self.parameter['assistClothFeatureInfoList']
        for assistServantFeatureInfo in self.assistServantFeatureInfo_lst:
            assistServantFeatureInfo['featureImg']=cv2.imread(assistServantFeatureInfo['featureImagePath'])
        for assistClothFeatureInfo in self.assistClothFeatureInfo_lst:
            assistClothFeatureInfo['featureImg']=cv2.imread(assistClothFeatureInfo['featureImagePath'])
        
        self.failAction_lst:list[list[dict]]=self.parameter['failActionList']

    def findTargetServant(self)->list[int]:
        servantX_lst:list[int]=[]
        servantY_lst:list[int]=[]
        h,w=self.assistServantFeatureInfo_lst[0]['Rect'][2:4]
        print('assist servant')
        for assistServantFeatureInfo in self.assistServantFeatureInfo_lst:
            print('single step',end=' ')
            servant_lst=findWhereMatched(assistServantFeatureInfo,self.currentImg)
            print('')
            servantY_lst+=servant_lst[0]
            servantX_lst+=servant_lst[1]
        if self.isConcernCloth:
            clothX_lst:list[int]=[]
            clothY_lst:list[int]=[]
            print('assist cloth')
            for assistClothFeatureInfo in self.assistClothFeatureInfo_lst:
                print('single step',end=' ')
                cloth_lst=findWhereMatched(assistClothFeatureInfo,self.currentImg)
                print('')
                clothY_lst+=cloth_lst[0]
                clothX_lst+=cloth_lst[1]
            radio=6
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
        point=self.findTargetServant()
        if point!=None:
            action={"type": "tap","x": point[0],"y": point[1]}
            self.simulatorOperator.actionByDict(action)
            self.la_log.log_add(f'success in {str(self.refreshNum)}-{str(self.failNum)} times',min(1,self.failNum+self.refreshNum))
            self.isRunning=False
        else:
            if self.failNum<5:
                self.simulatorOperator.actionByDictList(self.failAction_lst[0])
                self.failNum+=1
                self.la_log.log_add(f'fail {str(self.refreshNum)}-{str(self.failNum)} times',min(1,self.failNum+self.refreshNum))
            else:
                self.simulatorOperator.actionByDictList(self.failAction_lst[1],self.pause)
                self.failNum=0
                self.refreshNum+=1
                self.la_log.log_add(f'fail {str(self.refreshNum)}-{str(self.failNum)} times',1)
        time.sleep(1)
           
class Flow_Fight(Flow):
                
    class State_Skill(State_InFight):
        def __init__(self,idx:int,strategy:str):
            super(Flow_Fight.State_Skill,self).__init__()

            self.name='skill'+str(idx//2+1)
            self.idx=idx

            self.strategySpilted=strategy.split(' ')
            pos_lst:dict[str,list[list[int]]]=settingRead(['fixed','skill_pas'])
            self.action_lst:list[list[dict]]=[]
            self.strategyNum_lst:list[int]=[]
            for singleAction in self.strategySpilted:
                action=[]
                str1=f'{singleAction[0]}_{singleAction[1]}'
                action+=[{"type": "tap","x": pos[0],"y": pos[1]} for pos in pos_lst[str1]]
                action+=[{"type": "tap","x": pos[0],"y": pos[1]} for pos in pos_lst[singleAction[2]]]
                action+=[{"type": "tap","x": pos_lst['0'][0][0],"y": pos_lst['0'][0][1]}]
                self.action_lst.append(action)
                self.strategyNum_lst.append(len(self.action_lst)-1)

        def pause(self):
            time.sleep(0.4)

        def act(self):
            if self.progress<len(self.strategySpilted):
                self.strategyText=self.strategyText+self.strategySpilted[self.progress]+' '
            self.la_log.log_add('skill: '+self.strategyText,min(1,self.progress))
            self.simulatorOperator.actionByDictList(self.action_lst[self.progress],self.pause)
            self.progress+=1
            time.sleep(0.2)
            if self.progress==len(self.action_lst):
                self.isFinished=True
                    
    class State_Order(State_InFight):
        def __init__(self,idx:int,strategy:str):
            super(Flow_Fight.State_Order,self).__init__()

            self.name='order'+str(idx//2+1)
            self.idx=idx
            self.strategy=strategy
            
            self.wNum=5
            self.w_lst=[512*i//self.wNum for i in range(self.wNum)]

            self.colorMaskImgFn_lst:list[str]=settingRead(['fixed','parameters','fight','order','colorMaskImgPathList'])
            self.colorMaskImg_lst=[cv2.imread(fn) for fn in self.colorMaskImgFn_lst]
            self.colorMask_lst=[maskMake(maskImg) for maskImg in self.colorMaskImg_lst]
            self.color_lst=['r','g','b']
            self.colorOrderIndex_lst:list[str]=['n']*5
            self.colorInfo:dict={'MaskImgList':self.colorMaskImg_lst,
                            'MaskList':self.colorMask_lst,}

            self.servantMaskImgFn_lst:list[str]=settingRead(['fixed','parameters','fight','order','servantMaskImgPathList'])
            self.servantMaskImg_lst=[cv2.imread(fn) for fn in self.servantMaskImgFn_lst]
            self.servantMask_lst=[maskMake(maskImg) for maskImg in self.servantMaskImg_lst]
            self.servant_lst=[4,3,2,1]
            self.servantOrderIndex_lst:list[int]=[0]*5
            self.servantInfo:dict={'MaskImgList':self.servantMaskImg_lst,
                            'MaskList':self.servantMask_lst,}

            self.orderIndex_lst:list[str]=['n0']*5

            self.pos_lst:dict[str,list[list[int]]]=settingRead(['fixed','order_pas'])
            self.action:list[dict]=[{"type": "tap","x": self.pos_lst['i'][0],"y": self.pos_lst['i'][1]}]
            self.orderAction:list[dict]=[]

        def cosRecognize(self,info:dict,list:list,orderIndex:list):
            MaskImg_lst=info['MaskImgList']
            Mask_lst=info['MaskList']
            for i in range(len(Mask_lst)):
                pt_lst=findWhereMatched(
                {
                    'featureImg':MaskImg_lst[i],
                    'confidenceThreshold':0.47,
                    },
                self.currentImg,mask=Mask_lst[i])
                for xi in range(len(pt_lst[0])):
                    if pt_lst[0][xi]>140:
                        in_bool=[pt_lst[1][xi]>self.w_lst[i] for i in range(self.wNum)]+[False]
                        latestTrue=in_bool.index(False)-1
                        orderIndex[latestTrue]=list[i]
            return orderIndex

        def orderCardRecognize(self):
            self.colorOrderIndex_lst=self.cosRecognize(self.colorInfo,self.color_lst,self.colorOrderIndex_lst)
            self.servantOrderIndex_lst=self.cosRecognize(self.servantInfo,self.servant_lst,self.servantOrderIndex_lst)
            self.servantOrderIndex_lst=[settingRead(['changable','assistIndex'])+1 if i==0 else i for i in self.servantOrderIndex_lst]
                
            self.orderIndex_lst=[f'{self.colorOrderIndex_lst[i]}{self.servantOrderIndex_lst[i]}' for i in range(self.wNum)]

        def strategyGenerate(self):
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
                        for idx in range(len(self.orderIndex_lst)):
                            if self.orderIndex_lst[idx]!='uc':
                                self.originalStrategy+=[str(idx+1)]
                                self.orderIndex_lst[idx]='uc'
                                break
            for singleAction in self.originalStrategy:
                self.orderAction+=[{"type": "tap","x": self.pos_lst[singleAction][0],"y": self.pos_lst[singleAction][1]}]

        def pause(self):
            time.sleep(0.3)

        def act(self):
            if self.progress==0:
                self.simulatorOperator.actionByDict(self.action[0])
                self.progress=1
                time.sleep(1)
            elif self.progress==1:
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
        self.state_lst:list[State_InFight]=[]
        for idx in range(3):
            self.state_lst.append(Flow_Fight.State_Skill(2*idx,self.strategy_lst[f'skill{str(idx+1)}']))
            self.state_lst.append(Flow_Fight.State_Order(2*idx+1,self.strategy_lst[f'order{str(idx+1)}']))
        self.state_lst.append(Flow_Fight.State_Order(6,'1/2/3'))
        super(Flow_Fight,self).__init__(self.state_lst)

    def refresh(self):
        self.state_idx=0
        for state in self.state_lst:
            state.progress=0
            state.isFinished=False
            state.strategyText=''

    def run(self):
        self.state_lst[self.state_idx].act()
        if self.state_lst[self.state_idx].isFinished:
            self.state_idx+=1
        if self.state_idx>6:
            self.state_idx=6
            self.state_lst[6].isFinished=False

    def currentImgBind(self,img: np.ndarray):
        super(Flow_Fight,self).currentImgBind(img)
        for state in self.state_lst:
            state.currentImgBind(img)