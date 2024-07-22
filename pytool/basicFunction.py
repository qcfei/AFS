import json
import subprocess
import re
from PyQt5.QtGui import QImage,QPixmap
import os
import numpy as np
from pyminitouch import MNTDevice
from cv2 import imshow,waitKey,destroyAllWindows,matchTemplate,TM_CCOEFF_NORMED,minMaxLoc,resize,imdecode,imencode
from pytool.pauseableThread import *

outputX,outputY=512,288

def imgLstShow(img_lst:list[np.ndarray]):
    for i in range(len(img_lst)):
        imshow(str(i),img_lst[i])
    waitKey(0)
    destroyAllWindows()

def selfmatchTemplate(img:np.ndarray,template:np.ndarray,mask:np.ndarray=None):
    res=matchTemplate(img,template,TM_CCOEFF_NORMED,mask=mask)
    _,max_val,_,max_loc=minMaxLoc(res)
    return max_val,max_loc

def resizedReduceMatch(scene:np.ndarray,temp:np.ndarray,mask:np.ndarray=None,w_min:int=40,w_max:int=90,step:int=5):
    w_lst=range(w_min,min(w_max,whOfImg(scene)[0]),step)
    maxInfo={'val':0,'loc':None,'wh':None}
    val_lst=[]
    for w in w_lst:
        h=temp.shape[0]*w//temp.shape[1]
        tempwh=np.array((w,h))
        resizedtemp=resize(temp,tempwh)
        if mask is not None:
            resizedMask=resize(mask,tempwh)
        else:
            resizedMask=None
        # val,loc=reduceToMatchTemplate(scene,resizedtemp,resizedMask)
        val,loc=selfmatchTemplate(scene,resizedtemp,resizedMask)
        val_lst.append(val)
        if val>maxInfo['val'] and val<1:
            maxInfo={'val':val,'loc':loc,'wh':tempwh}
    val,loc,wh=maxInfo.values()
    return val,loc,wh

class cplCount():
    def __init__(self) -> None:
        self.count=0

    def countAdd(self):
        self.count+=1

def pixCheck(pix:np.ndarray):
    return  (not (min(pix==[0,0,255])==False) or
             
            (not (min(pix<[30,30,255])==False) and
            not (min(pix>[0,0,100]))==False) or

            (not (min(pix<[60,255,60])==False) and
            not (min(pix>[0,100,0]))==False) or
            
            (not (min(pix<[255,70,70])==False) and
            not (min(pix>[80,0,0]))==False)
            )

def cutImg(img:np.ndarray,loc:np.ndarray,wh:np.ndarray):
    x0,y0=loc
    x1,y1=loc+wh
    return img[y0:y1,x0:x1]

def locwh2xy(loc:np.ndarray,wh:np.ndarray):
    x0,y0=loc
    x1,y1=loc+wh
    return x0,y0,x1,y1

def getCNPathImg(path:str):
    fn=path[(path.index(re.findall(r'/[^/]*.png',path)[0]))+1:]
    dir=path[:(path.index(re.findall(r'/[^/]*.png',path)[0]))]
    img:np.ndarray = imdecode(np.fromfile(os.path.join(f'{dir}', fn), dtype=np.uint8), -1)
    return img

def dumImg2CNPath(img:np.ndarray,path:str):
    imencode('.png', img )[1].tofile(path)

def findServantInFolder(temp:np.ndarray,mask:np.ndarray,fdir:str):
    maxVal=0
    wh=0
    '''get dir'''
    dir_lst:list[str]=[]
    for root, dirs, _ in os.walk(fdir):
        for dir in dirs:
            dir_lst.append(dir)
    max_info={'val':0,'loc':np.ndarray((0,0)),'wh':np.ndarray((0,0)),'path':''}
    for dir in dir_lst:
        fn_lst=os.listdir(f'{fdir}/{dir}')
        for fn in fn_lst:
            img=getCNPathImg(f'{fdir}/{dir}/{fn}')
            val,loc=reduceToMatchTemplate(img,temp,mask)
            if val>max_info['val']:
                max_info={'val':val,'loc':loc,'wh':wh,'path':f'{fdir}/{dir}/{fn}'}
                maxVal=val
            # print(f'{dir_lst.index(dir)}-{len(dir_lst)}/{fn_lst.index(fn)}-{len(fn_lst)} val: {str(maxVal)} fn: {max_info["path"]} cfn:{fdir}/{dir}/{fn}',end='\r')
    val,loc,wh,path=max_info.values()
    return val,loc,wh,path

def whOfImg(img:np.ndarray)->np.ndarray[int]:
    return np.array(list(img.shape[:2])[::-1]).astype(int)

def cutForLeastMask(temp:np.ndarray,mask:np.ndarray):
    wh=whOfImg(temp)
    print(wh)
    bool_lst=[list(mask[yi,:]).count(0)>wh[0]//2 for yi in range(wh[1])]
    if False in bool_lst:
        Ystart_idx=bool_lst.index(False)
        bool_lst.reverse()
        Yend_idx=bool_lst.index(False)
    else:
        Ystart_idx=1
        Yend_idx=1
    temp=temp[Ystart_idx:-1-Yend_idx,:]
    mask=mask[Ystart_idx:-1-Yend_idx,:]
    wh=whOfImg(temp)
    bool_lst=[list(mask[:,xi]).count(0)>wh[1]//2 for xi in range(wh[0])]+[True]
    if False in bool_lst:
        Xstart_idx=bool_lst.index(False)
        Xstart_idx=Xstart_idx+6+bool_lst[Xstart_idx+6:].index(False)
        bool_lst.reverse()
        Xend_idx=bool_lst.index(False)
    else:
        Xstart_idx=1
        Xend_idx=1
    temp=temp[:,Xstart_idx:-1-Xend_idx,:]
    mask=mask[:,Xstart_idx:-1-Xend_idx]
    return temp,mask,np.array((Xstart_idx,Ystart_idx)),np.array((wh[0]-Xend_idx-Xstart_idx,wh[1]-Yend_idx-Ystart_idx))

def settingWrite(obj,key_lst:list):
    obj_lst=[]
    obj_lst.append(json.load(open('./setting.json','r',encoding='utf-8')))
    for key in key_lst:
        obj_lst.append(obj_lst[-1][key])
    obj_lst[-1]=obj
    obj_lst.reverse()
    key_lst.reverse()
    for obji in range(len(obj_lst)-1):
        obj_lst[obji+1][key_lst[obji]]=obj_lst[obji]
    key_lst.reverse()
    json.dump(obj_lst[-1],open('./setting.json','w',encoding='utf-8'),ensure_ascii=True,indent=2)

def settingRead(key_lst:list):
    obj=json.load(open('./setting.json','r',encoding='utf-8'))
    for key in key_lst:
        obj=obj[key]
    return obj

def fixedSettingRead(key_lst:list):
    obj=json.load(open('settingFixed.json','r',encoding='utf-8'))
    for key in key_lst:
        obj=obj[key]
    return obj

def fixedsettingWrite(obj,key_lst:list):
    obj_lst=[]
    obj_lst.append(json.load(open('settingFixed.json','r',encoding='utf-8')))
    for key in key_lst:
        obj_lst.append(obj_lst[-1][key])
    obj_lst[-1]=obj
    obj_lst.reverse()
    key_lst.reverse()
    for obji in range(len(obj_lst)-1):
        obj_lst[obji+1][key_lst[obji]]=obj_lst[obji]
    key_lst.reverse()
    json.dump(obj_lst[-1],open('settingFixed.json','w',encoding='utf-8'),ensure_ascii=True,indent=2)

def maskMake(maskImg:np.ndarray):
    return np.array([[255 if min(pt==[0,0,255])==False else 0 for pt in ptLine]for ptLine in maskImg],np.float32)

def simulatorIndexGet()->int:
    simulatorIndex=settingRead(['changable','simulatorIndex'])
    print('simulatorIndexGet->simulatorIndex: '+str(simulatorIndex))
    return simulatorIndex

def ipGet()->str:
    simulatorIndex=simulatorIndexGet()
    simulator:dict=settingRead(['changable','simulator',simulatorIndex])
    print('ipGet->simulatorInfo: '+simulator['name']+' '+simulator['ip'])
    return simulator['ip']

def bsGet()->float:
    bs=3.75
    ip=ipGet()
    devicesInfo=subprocess.getoutput('platform-tools_r33.0.3-windows\platform-tools\\adb.exe devices')
    if ip not in devicesInfo:
        sysInput(f'adb connect {ip}')
    dpi=subprocess.getoutput(f'platform-tools_r33.0.3-windows\platform-tools\\adb.exe -s {ip} shell wm size')
    if not ('notfound' in dpi):
        dpiY,dpiX=[int(dpii) for dpii in re.findall(r'\d+',dpi)]
        bs=max(dpiX,dpiY)/outputX
    return bs

def stateNameGet()->list[str]:
    stateInfo_lst:dict[str,dict[str,int|list[int]|list[list[dict[str,str|int]]]|str]]=fixedSettingRead(['fixed','parameters','general'])
    return list(stateInfo_lst.keys())

def neighborStateNameGet()->dict[str,list[int]]:
    stateInfo_lst:dict[str,dict[str,int|list[int]|list[list[dict[str,str|int]]]|str]]=fixedSettingRead(['fixed','parameters','general'])
    return {stateName:stateInfo_lst[stateName]['neighborState'] for stateName in stateInfo_lst.keys()}

def sysInput(text:str):
    if 'adb' in text:
        text=text.replace('adb',r'platform-tools_r33.0.3-windows\platform-tools\adb.exe')
    subprocess.run(text,shell=True)

def pause():
    pass

class SimulatorOperator():
    
    def __init__(self):
        self.bs=bsGet()
        self.device:MNTDevice=None

    def deviceBind(self,device:MNTDevice):
        self.device=device
    
    def simulatorTap(self,x:int,y:int,bs:float=1):
        self.device.tap([(int(x*bs),int(y*bs))])

    def simulatorSwipe(self,x0:int,y0:int,x1:int,y1:int,duration:int,bs:float=1):
        num=10
        x0=int(x0*bs)
        y0=int(y0*bs)
        x1=int(x1*bs)
        y1=int(y1*bs)
        if not x0-x1:
            x_lst=[x0]*num
        else:
            x_lst=range(x0,x1,int((x1-x0)/num))
        if not y0-y1:
            y_lst=[y0]*num
        else:
            y_lst=range(y0,y1,int((y1-y0)/num))
        pos_lst=[]
        for i in range(num):
            pos_lst.append((x_lst[i],y_lst[i]))
        self.device.swipe(pos_lst,duration=duration)

    def actionByDict(self,dictionary:list[int]):
        if dictionary[0]==0:
            self.simulatorTap(outputY-dictionary[2],dictionary[1],self.bs)
        elif dictionary[0]==1:
            self.simulatorSwipe(outputY-dictionary[2],dictionary[1],outputY-dictionary[4],dictionary[3],dictionary[5],self.bs)
        # if dictionary['type']=='tap':
        #     self.simulatorTap(dictionary['x'],dictionary['y'],self.bs)
        # elif dictionary['type']=='swipe':
        #     self.simulatorSwipe(dictionary['x0'],dictionary['y0'],dictionary['x1'],dictionary['y1'],dictionary['duration'],self.bs)

    def actionByDictList(self,dictionary_lst:list[list[int]],pause=pause):
        print(dictionary_lst,sep='\n')
        for dictionary in dictionary_lst:
            self.actionByDict(dictionary)
            pause()
         
def miniInstall(struc:str,sdk:str,ip:str):
    minicapso_pn=r'minicap\minicap-shared\aosp\libs\android-{}\{}\minicap.so'.format(sdk,struc)
    minicap_pn=r'minicap\{}\minicap'.format(struc)
    minitouch_pn=r'minitouch\{}\minitouch'.format(struc)
    pn_lst=[minitouch_pn,minicap_pn,minicapso_pn]
    minicapso_fn,minicap_fn,minitouch_fn='minicap.so','minicap','minitouch'
    fn_lst=[minitouch_fn,minicap_fn,minicapso_fn]
    adbInfo=subprocess.getoutput('platform-tools_r33.0.3-windows\platform-tools\\adb.exe shell ls -all data/local/tmp')
    errorText=''
    f=True
    for fni in range(len(fn_lst)):
        if os.path.exists(pn_lst[fni]):
            if  re.findall(fn_lst[fni],adbInfo):
                sysInput(f'adb -s {ip} shell rm -r /data/local/tmp/{fn_lst[fni]}')
            sysInput(f'adb -s {ip} push {pn_lst[fni]} /data/local/tmp')
            sysInput(f'adb -s {ip} shell chmod 777 /data/local/tmp/{fn_lst[fni]}')
        else:
            f=False
            errorText=pn_lst[fni]+'不存在,请检查文件夹'
            break
    return f,errorText

def qImg2Mat(qImg:QImage)->np.ndarray:
    width = qImg.width()
    height = qImg.height()
    ptr=qImg.bits()
    ptr.setsize(qImg.byteCount())
    arr = np.array(ptr).reshape(height, width, 4) 
    return arr[:,:,:3]

def img2pixmap(image:np.ndarray):
        Y, X = image.shape[:2]
        _bgra = np.zeros((Y, X, 4), dtype=np.uint8, order='C')
        _bgra[..., 0] = image[..., 2]
        _bgra[..., 1] = image[..., 1]
        _bgra[..., 2] = image[..., 0]
        qimage = QImage(_bgra.data, X, Y, QImage.Format_RGB32)
        pixmap = QPixmap.fromImage(qimage)
        return pixmap

def reduce50percent(img:np.ndarray):
    return resize(img,(img.shape[1]//2,img.shape[0]//2))

def reduceToMatchTemplate(img:np.ndarray,template:np.ndarray,mask:np.ndarray=None):
    rdc_num=2
    rdc_temp:list[np.ndarray]=[template]
    rdc_img:list[np.ndarray]=[img]
    rdc_mask:list[np.ndarray]=[mask]
    if mask is None:
        rdc_mask+=[None]*5
        rdc_lst=[rdc_temp,rdc_img]
    else:
        rdc_lst=[rdc_temp,rdc_img,rdc_mask]
    for i in range(rdc_num):
        for rdc in rdc_lst:
            rdc.append(reduce50percent(rdc[-1]))
    for rdc in rdc_lst:
        rdc.reverse()
    acc_max,app_loc_lu=0,np.array((0,0))
    radio_err=0.1
    for i in range(len(rdc_temp)):
        temp=rdc_temp[i]
        img=rdc_img[i]
        mask=rdc_mask[i]
        imgwh,tempwh=np.array(list(img.shape)[::-1][-2:]),np.array(list(temp.shape)[::-1][-2:])
        acc_loc_lu=np.maximum(np.array((0,0)),app_loc_lu-np.floor(radio_err*imgwh).astype(int))
        acc_loc_rd=np.minimum(imgwh,app_loc_lu+tempwh+np.floor(radio_err*imgwh).astype(int))
        res=matchTemplate(img if i==0 else img[acc_loc_lu[1]:acc_loc_rd[1],acc_loc_lu[0]:acc_loc_rd[0]],temp,TM_CCOEFF_NORMED,mask=mask)
        _,acc_max,_,temp_app_loc_lu=minMaxLoc(res)
        app_loc_lu=acc_loc_lu+temp_app_loc_lu
        app_loc_lu=app_loc_lu*2
    return acc_max,app_loc_lu//2

def checkIsFeatureScene(featureInfo_lst:list[dict],sceneImg:np.ndarray,checkMode:str,isPrint:bool=False)->bool:
    radio=8
    if checkMode=='and':
        flag=True
        for featureInfo in featureInfo_lst:
            featureImg:np.ndarray=featureInfo['featureImg']
            featureRect:list[int]=featureInfo['Rect']
            confidenceThreshold:float=featureInfo['confidenceThreshold']
            mask:np.ndarray[np.float32]=featureInfo['mask']
            maxVal,maxLoc=reduceToMatchTemplate(sceneImg,featureImg,mask=mask)
            if isPrint:
                print(maxVal,confidenceThreshold,maxLoc,checkMode,sceneImg.shape,featureImg.shape)
            pos_bool=[abs(maxLoc[i]-featureRect[1-i])<radio for i in range(2)]
            if maxVal<confidenceThreshold or not pos_bool[0] or not pos_bool[1]:
                flag=False
                break
    elif checkMode=='or':
        flag=False
        for featureInfo in featureInfo_lst:
            featureImg:np.ndarray=featureInfo['featureImg']
            featureRect:list[int]=featureInfo['Rect']
            confidenceThreshold:float=featureInfo['confidenceThreshold']
            mask:np.ndarray[np.float32]=featureInfo['mask']
            maxVal,maxLoc=reduceToMatchTemplate(sceneImg,featureImg,mask=mask)
            if isPrint:
                print(maxVal,confidenceThreshold,maxLoc,checkMode,sceneImg.shape,featureImg.shape)
            pos_bool=[abs(maxLoc[i]-featureRect[1-i])<radio for i in range(2)]
            if maxVal>confidenceThreshold and pos_bool[0] and pos_bool[1]:
                flag=True
                break
    return flag

def findWhereMatched(featureInfo:dict,sceneImg:np.ndarray,mask:np.ndarray[np.float32]=None)->list[list[int]]:
    featureImg:np.ndarray=featureInfo['featureImg']
    confidenceThreshold:float=featureInfo['confidenceThreshold']
    res=matchTemplate(sceneImg,featureImg,TM_CCOEFF_NORMED,mask=mask)
    res_bool:np.ndarray=np.array([[(resPix>confidenceThreshold) for resPix in resLine] for resLine in res])
    h,w=res_bool.shape[:2]
    radio=8
    for yi in range(h):
        for xi in range(w):    
            if res_bool[yi,xi]:
                x0,y0,x1,y1=max(0,xi-radio),max(0,yi-radio),min(w,xi+radio),min(h,yi+radio)
                res_bool[y0:y1,x0:x1]=False
                res_bool[yi,xi]=True

    pos=np.where(res_bool==True)
    print(list(pos[0]),list(pos[1]),end=' ')
    return [list(pos[0]),list(pos[1])]

def list2str(lst:list):
    text=''
    for obj in lst:
        text+=str(obj)+' '
    return text

def is_valid_jpg(jpg_file):
    """判断JPG文件下载是否完整     """ 
    if jpg_file.split('.')[-1].lower() == 'jpg':          
        with open(jpg_file, 'rb') as f:              
            f.seek(-2, 2)              
            return f.read() == b'\xff\xd9'      
    else:          
        return True

def imgResize2512(img:np.ndarray)->np.ndarray:
    return resize(img,(512,288))