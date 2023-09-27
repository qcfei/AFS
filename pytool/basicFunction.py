import json
import subprocess
import re
from PyQt5.QtWidgets import *
from PyQt5.QtGui import *
import os
import numpy as np
from pyminitouch import MNTDevice
import cv2

outputX,outputY=512,288

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

def maskMake(maskImg:np.ndarray):
    return np.array([[255 if min(pt==[0,0,255])==False else 0 for pt in ptLine]for ptLine in maskImg],np.float32)

def simulatorIndexGet()->int:
    return settingRead(['changable','simulatorIndex'])

def ipGet()->str:
    simulatorIndex=simulatorIndexGet()
    simulator:dict=settingRead(['changable','simulator',simulatorIndex])
    return simulator['ip']

def bsGet()->float:
    bs=3.75
    ip=ipGet()
    devicesInfo=subprocess.getoutput('adb devices')
    if ip not in devicesInfo:
        sysInput(f'adb connect {ip}')
    dpi=subprocess.getoutput(f'adb -s {ip} shell wm size')
    if not ('notfound' in dpi):
        dpiY,dpiX=[int(dpii) for dpii in re.findall(r'\d+',dpi)]
        bs=max(dpiX,dpiY)/outputX
    return bs

def stateNameGet()->list[str]:
    stateInfo_lst:dict[str,dict[str,int|list[int]|list[list[dict[str,str|int]]]|str]]=settingRead(['fixed','parameters','general'])
    return list(stateInfo_lst.keys())

def neighborStateNameGet()->dict[str,list[int]]:
    stateInfo_lst:dict[str,dict[str,int|list[int]|list[list[dict[str,str|int]]]|str]]=settingRead(['fixed','parameters','general'])
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
        simulatorIndex=simulatorIndexGet()
        self.captureMode=settingRead(['changable','simulator',simulatorIndex,'captureMethod'])

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

    def actionByDict(self,dictionary:dict):
        if self.captureMode==1:
            if dictionary['type']=='tap':
                self.simulatorTap(outputY-dictionary['y'],dictionary['x'],self.bs)
            elif dictionary['type']=='swipe':
                self.simulatorSwipe(outputY-dictionary['y0'],dictionary['x0'],outputY-dictionary['y1'],dictionary['x1'],dictionary['duration'],self.bs)
        elif self.captureMode==0:
            if dictionary['type']=='tap':
                self.simulatorTap(dictionary['x'],dictionary['y'],self.bs)
            elif dictionary['type']=='swipe':
                self.simulatorSwipe(dictionary['x0'],dictionary['y0'],dictionary['x1'],dictionary['y1'],dictionary['duration'],self.bs)

    def actionByDictList(self,dictionary_lst:list[dict],pause=pause):
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
    adbInfo=subprocess.getoutput('adb shell ls -all data/local/tmp')
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

def checkIsFeatureScene(featureInfo_lst:list[dict],sceneImg:np.ndarray,checkMode:str,isPrint:bool=False)->bool:
    radio=8
    if checkMode=='and':
        flag=True
        for featureInfo in featureInfo_lst:
            featureImg:np.ndarray=featureInfo['featureImg']
            featureRect:list[int]=featureInfo['Rect']
            confidenceThreshold:float=featureInfo['confidenceThreshold']
            mask:np.ndarray[np.float32]=featureInfo['mask']
            res=cv2.matchTemplate(sceneImg,featureImg,cv2.TM_CCOEFF_NORMED,mask=mask)
            _,maxVal,_,maxLoc=cv2.minMaxLoc(res)
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
            res=cv2.matchTemplate(sceneImg,featureImg,cv2.TM_CCOEFF_NORMED,mask=mask)
            _,maxVal,_,maxLoc=cv2.minMaxLoc(res)
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
    res=cv2.matchTemplate(sceneImg,featureImg,cv2.TM_CCOEFF_NORMED,mask=mask)
    print(np.max(res))
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
    return cv2.resize(img,(512,288))