from pytool.basicFunction import *
from pytool.basicFunction import np
from pytool.log import *

from cv2 import imread,imwrite,resize
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
        self.parameter:dict=fixedSettingRead(['fixed','parameters','general',name])

        self.idx:int=self.parameter['idx']
        self.neighborState:list[int]=self.parameter['neighborState']
        self.checkMode:str=self.parameter['checkMode']
        self.featureInfo_lst:list[dict]=self.parameter['featureInfoList']
        self.action_lst:list[list[dict]]=self.parameter['actionList']
        self.actionMethod:str=self.parameter['actionMethod']

        for featureInfo in self.featureInfo_lst:
            featureImg=imread(featureInfo['featureImagePath'])
            maskImg=imread(featureInfo['maskImgPath'])
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
            time.sleep(4)

    class State_Drug(State_General):
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
        def __init__(self):
            super(Flow_General.State_AssistChoose,self).__init__('assistChoose')
            self.flow_assist=Flow_Assist()

        def act(self):
            self.flow_assist.run()

    class State_Prepare(State_General):
        def __init__(self,):
            super().__init__('prepare')

        def act(self):
            self.simulatorOperator.actionByDictList(self.action_lst[0])
            time.sleep(3)

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
        self.fightCount=settingRead(['changable','again','fightCount'])
        self.fightCurrentCount=0
        settingWrite(self.fightCurrentCount,['changable','fightCurrentCount'])
        self.isLock=False
        self.isQuit=False

        self.state_idx=0

    def run(self):
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

class Flow_Assist(Flow):
    def __init__(self, ):
        state_lst=[]

        self.strategyIdx=settingRead(['changable','currentStrategyIndex'])
        self.strategyAssistChooseLst=settingRead(['changable','strategyAssistChoose',self.strategyIdx])
        self.failNum=0
        self.refreshNum=0
        self.isConcernCloth=settingRead(['changable','isCloth'])
        super().__init__(state_lst)
        
        self.parameter:dict=fixedSettingRead(['fixed','parameters','assist'])
        self.assistServantFeatureInfo_lst:list[dict]=self.parameter['assistServantFeatureInfoList']
        self.assistClothFeatureInfo_lst:list[dict]=self.parameter['assistClothFeatureInfoList']
        for assistServantFeatureInfoI in range(len(self.assistServantFeatureInfo_lst)):
            assistServantFeatureInfo=self.assistServantFeatureInfo_lst[assistServantFeatureInfoI]
            assistClothFeatureInfo=self.assistClothFeatureInfo_lst[assistServantFeatureInfoI]
            assistServantFeatureInfo['featureImagePath']=assistServantFeatureInfo['featureImagePath'][:-5]+str(self.strategyAssistChooseLst[assistServantFeatureInfoI]+1)+assistServantFeatureInfo['featureImagePath'][-4:]
            assistClothFeatureInfo['featureImagePath']=assistClothFeatureInfo['featureImagePath'][:-5]+str(self.strategyAssistChooseLst[assistServantFeatureInfoI]+1)+assistClothFeatureInfo['featureImagePath'][-4:]
            assistServantFeatureInfo['featureImg']=imread(assistServantFeatureInfo['featureImagePath'])
            assistClothFeatureInfo['featureImg']=imread(assistClothFeatureInfo['featureImagePath'])
        print([assistServantFeatureInfo['featureImagePath'] for assistServantFeatureInfo in self.assistServantFeatureInfo_lst])
        
        self.failAction_lst:list[list[list[int]]]=self.parameter['failActionList']

    def findTargetServant(self)->list[int]:
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
        print(self.parameter['failActionList'][0],'!!!')
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

    class State_Check(State_InFight):

        def __init__(self,):
            super().__init__()
            self.roleNum=6
            
            step=150
            self.loc_lst=[np.array((50+step*i,175))for i in range(3)]
            pos_lst:dict[str,list[list[int]]]=fixedSettingRead(['fixed','skill_pas'])
            self.quitAction=[0,pos_lst['0'][0][0],pos_lst['0'][0][1]]

            self.checkAble=False

            self.greatMask=imread('mask/greatMask.png',0)
            self.maskwh=whOfImg(self.greatMask)
            
        def imgSave(self):
            img=cutImg(self.currentImg,np.array((100,53)),np.array((63,63*8//6)))
            imgmskd=np.array([[(0,0,255) if self.greatMask[yi,xi]==0 else img[yi,xi] for xi in range(self.maskwh[0])]for yi in range(self.maskwh[1])],np.uint8)
            imwrite(f'fgoMaterial/preServant{str(self.progress//2+1)}.png',imgmskd)

        def pause(self):
            time.sleep(0.2)

        def act(self):
            if self.progress<self.roleNum:
                if not self.checkAble:
                    self.simulatorOperator.actionByDict([0,self.loc_lst[self.progress//2][0],self.loc_lst[self.progress//2][1]])
                    time.sleep(0.2)
                    self.simulatorOperator.actionByDict([0,95,30])
                    self.checkAble=True
                else:
                    self.imgSave()
                    self.simulatorOperator.actionByDict(self.quitAction)
                    time.sleep(0.4)
                    self.checkAble=False
                self.progress+=1
            else :
                self.progress=0
                self.isFinished=True
            
    class State_Skill(State_InFight):
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
                self.progress=0
                    
    class State_Order(State_InFight):

        def __init__(self,idx:int,strategy:str):
            super(Flow_Fight.State_Order,self).__init__()

            self.name='order'+str(idx//2+1)
            self.idx=idx
            self.strategy=strategy
            
            self.wNum=5
            self.w_lst=[512*i//self.wNum for i in range(self.wNum)]+[512]
            self.yMin=140

            self.colorImgFn_lst:list[str]=fixedSettingRead(['fixed','parameters','fight','order','colorImgPathList'])
            self.colorImg_lst=[imread(fn) for fn in self.colorImgFn_lst]
            self.color_lst=['r','g','b']

            self.servantImgFn_lst:list[str]=fixedSettingRead(['fixed','parameters','fight','order','servantImgPathList'])
            self.servant_lst=['3','2','1']
            self.roleImgListLoad()

            self.pos_lst:dict[str,list[list[int]]]=fixedSettingRead(['fixed','order_pas'])
            self.action:list[dict]=[[0,self.pos_lst['i'][0],self.pos_lst['i'][1]]]
            self.orderAction:list[dict]=[]
            self.orderIndex_lst=['uc']*self.wNum

        def roleImgListLoad(self):
            self.servantImg_lst=[imread(fn) for fn in self.servantImgFn_lst]

        def orderCardRecognize(self):
            crdImg_lst=[]
            gtMask=imread('mask/greatMask.png',0).astype(np.float32)

            clrRes=[0]*5
            rleRes=[0]*5
            clrInfo_lst=[(clrTmp,maskMake(clrTmp)) for clrTmp in self.colorImg_lst]

            for cardI in range(self.wNum):
                cardAreaImg=cutImg(self.currentImg,np.array((self.w_lst[cardI],self.yMin)),np.array((self.w_lst[cardI+1]-self.w_lst[cardI],self.yMin+120)))
                clrMaxIdx,clrMaxVal=0,0
                for clrTmpI in range(len(self.colorImg_lst)):
                    clrTmpLm,clrMskLm=clrInfo_lst[clrTmpI]
                    clrVal,clrLoc=selfmatchTemplate(cardAreaImg,clrTmpLm,clrMskLm)
                    if clrVal>clrMaxVal:
                        clrMaxVal=clrVal
                        clrMaxIdx=clrTmpI
                        clrMaxLoc=clrLoc
                clrRes[cardI]=clrMaxIdx

                crdImg=cutImg(cardAreaImg,clrMaxLoc,np.array((clrTmpLm.shape[1],clrTmpLm.shape[0])))
                crdImgMskd=np.array([[(0,0,255) if gtMask[yi,xi]==0 or pixCheck(crdImg[yi,xi]) else crdImg[yi,xi] for xi in range(crdImg.shape[1])] for yi in range(crdImg.shape[0])],np.uint8)
                crdImg_lst.append(crdImgMskd)
                
                rleTmpLm,rleMskLm=crdImgMskd,maskMake(crdImgMskd)

                rleMaxIdx,rleMaxVal=0,0
                for rleImgI in range(len(self.servantImg_lst)):
                    rleImg=self.servantImg_lst[rleImgI]
                    rleVal,_=selfmatchTemplate(rleImg,rleTmpLm,rleMskLm)
                    if rleVal>rleMaxVal:
                        rleMaxVal=rleVal
                        rleMaxIdx=rleImgI
                rleRes[cardI]=rleMaxIdx

            self.orderIndex_lst=[self.color_lst[clrRes[i]]+self.servant_lst[rleRes[i]] for i in range(self.wNum)]
                            

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
                self.orderAction+=[[0,self.pos_lst[singleAction][0],self.pos_lst[singleAction][1]]]

        def pause(self):
            time.sleep(0.3)

        def act(self):
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
            
        self.state_lst:list[State_InFight]=[Flow_Fight.State_Check()]
        self.checkNum=1
        for idx in range(3):
            self.state_lst.append(Flow_Fight.State_Skill(2*idx,self.strategy_lst[f'skill{str(idx+1)}']))
            if '530' in self.strategy_lst[f'skill{str(idx+1)}']:
                self.state_lst.append(Flow_Fight.State_Check())
                self.checkNum+=1
            self.state_lst.append(Flow_Fight.State_Order(2*idx+1,self.strategy_lst[f'order{str(idx+1)}']))
        self.state_lst.append(Flow_Fight.State_Order(6+self.checkNum,'1/2/3'))
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
        if self.state_idx>6+self.checkNum:
            self.state_idx=6+self.checkNum
            self.state_lst[6+self.checkNum].isFinished=False

    def currentImgBind(self,img: np.ndarray):
        super(Flow_Fight,self).currentImgBind(img)
        for state in self.state_lst:
            state.currentImgBind(img)