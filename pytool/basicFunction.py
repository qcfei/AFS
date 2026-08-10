"""AFS 核心工具库

职责：
- 图像处理：模板匹配、图像缩放/裁剪、掩码制作、中文路径读写
- 配置读写：setting.json（运行时可变配置）与 settingFixed.json（固定参数模板）
- ADB / minitouch：模拟器连接、触控注入（SimulatorOperator）、minitouch 安装
- 场景识别：checkIsFeatureScene / findWhereMatched

全局约定：
- 所有截图统一降采样到 outputX×outputY = 512×288（与 mask/ 目录下掩码一致）
- 触控坐标均基于 512×288 坐标系，由 bs 缩放系数换算到真实设备分辨率
"""
import json
import subprocess
import re
import sys
import copy
from PyQt5.QtGui import QImage,QPixmap
import os
import numpy as np
from pyminitouch import MNTDevice
from cv2 import imshow,waitKey,destroyAllWindows,matchTemplate,TM_CCOEFF_NORMED,TM_CCORR,minMaxLoc,resize,imdecode,imencode
from pytool.pauseableThread import *

# ---------------------------------------------------------------------------
# Windows 无控制台进程的 subprocess 静默化
# ---------------------------------------------------------------------------
# AFS.exe 以 --noconsole 打包（无控制台宿主）。无控制台进程用 subprocess 启动
# adb.exe/cmd.exe 时，Windows 会为子进程分配一个新控制台窗口，命令执行完即
# 关闭，表现为"控制台闪现"。pyminitouch 内部多处直接调 subprocess（无 flags），
# 无法逐一修改第三方库，故在模块加载时补丁 Popen：未显式指定 creationflags 时
# 注入 CREATE_NO_WINDOW。run/getoutput/check_call 等高层函数底层均走 Popen，
# 一处补丁即可覆盖本项目与 pyminitouch 的全部调用。
if os.name == 'nt':
    _Popen_orig = subprocess.Popen
    def _Popen_no_window(*args, **kwargs):
        if 'creationflags' not in kwargs:
            kwargs['creationflags'] = subprocess.CREATE_NO_WINDOW
        return _Popen_orig(*args, **kwargs)
    subprocess.Popen = _Popen_no_window


# ---------------------------------------------------------------------------
# 全局常量
# ---------------------------------------------------------------------------
outputX,outputY=512,288  # 统一处理分辨率（所有掩码/坐标均按此设计）
PLATFORM_TOOLS_DIR=r'platform-tools_r33.0.3-windows\platform-tools'  # 本地 adb 目录（相对项目根）
MATCH_POS_TOLERANCE=8     # 特征匹配位置容差（像素）
MATCH_RADIO_ERR=0.1       # 多分辨率匹配搜索区域扩展比例


def _adbDirSearch() -> str:
    """在常见位置查找本地 platform-tools 目录

    查找顺序：当前工作目录 → exe/入口脚本所在目录 → 本模块目录 → 模块上级目录。
    找到包含 adb.exe 的目录则返回其绝对路径，否则返回空串。
    打包后 exe 与源码运行时均可定位，实现"免环境变量"使用 adb。
    """
    cwd=os.getcwd()
    exeDir=os.path.dirname(os.path.abspath(sys.argv[0]))
    srcDir=os.path.dirname(os.path.abspath(__file__))
    candidate_lst=[cwd,exeDir,srcDir,os.path.dirname(srcDir)]
    for candidate in candidate_lst:
        adbDir=os.path.join(candidate,PLATFORM_TOOLS_DIR)
        if os.path.exists(os.path.join(adbDir,'adb.exe')):
            return adbDir
    return ''

def appRootGet() -> str:
    """程序根目录：源码运行=项目根（script.py 所在），exe 运行=exe 所在目录

    以 sys.argv[0]（入口脚本/exe 路径）为锚点定位，不依赖当前工作目录，
    保证从快捷方式启动时资源与日志路径依然稳定。
    """
    return os.path.dirname(os.path.abspath(sys.argv[0]))

def logDirGet() -> str:
    """日志目录（程序根/logs），不存在则自动创建"""
    d=os.path.join(appRootGet(),'logs')
    if not os.path.exists(d):
        os.makedirs(d,exist_ok=True)
    return d

# 模块加载时自动把本地 adb 目录插入 PATH，供 pyminitouch（硬编码调用 adb）使用
_adbDir=_adbDirSearch()
if _adbDir and _adbDir not in os.environ.get('PATH',''):
    os.environ['PATH']=_adbDir+os.pathsep+os.environ['PATH']


# ---------------------------------------------------------------------------
# 图像处理
# ---------------------------------------------------------------------------
def imgLstShow(img_lst:list[np.ndarray]):
    """调试用：依次弹窗显示图像列表，按任意键关闭"""
    for i in range(len(img_lst)):
        imshow(str(i),img_lst[i])
    waitKey(0)
    destroyAllWindows()

def selfmatchTemplate(img:np.ndarray,template:np.ndarray,mask:np.ndarray=None):
    """单尺度模板匹配，返回 (最大相似度, 最大位置)"""
    res=matchTemplate(img,template,TM_CCOEFF_NORMED,mask=mask)
    _,max_val,_,max_loc=minMaxLoc(res)
    return max_val,max_loc

# 指令卡背景板 9 色号（BGR：红绿蓝 × 3 档亮暗，用户截图确认），反向蒙版用（见 build9Mask）
CARD9_COLORS:list[tuple[int,int,int]]=[
    (20,20,134),(23,23,159),(12,12,88),    # 红
    (159,65,22),(132,52,17),(79,31,9),     # 蓝
    (16,116,33),(14,101,30),(9,65,18),     # 绿
]

def build9Mask(img:np.ndarray,tol:int=15)->np.ndarray:
    """9 色号反向蒙版：背景板色命中像素置 0（透明），其余 255。TOL=15 实测最优。"""
    m=np.ones(img.shape[:2],np.uint8)*255
    for (b,g,r) in CARD9_COLORS:
        hit=(np.abs(img[:,:,0].astype(np.int16)-b)<tol)& \
            (np.abs(img[:,:,1].astype(np.int16)-g)<tol)& \
            (np.abs(img[:,:,2].astype(np.int16)-r)<tol)
        m[hit]=0
    return m

def maskedCCOEFF(roi:np.ndarray,tpl:np.ndarray,mask:np.ndarray)->float:
    """带蒙版去均值相关（CCOEFF 语义，区分度大，默认方法）

    OpenCV 5 不支持 CCOEFF+mask，手动向量化：
    num = Σts - mean_s·Σt；den = sqrt(t_var · (Σs² - Σs²/N3))
    Σts/Σs/Σs² 用 cv2.matchTemplate(TM_CCORR) 批量滑动窗口和。
    返回最大相关分数。
    """
    th,tw=tpl.shape[:2]
    m2=(mask>0).astype(np.float32)
    t_masked=tpl.astype(np.float32)*m2[:,:,None]
    t_vec=tpl[m2>0].astype(np.float32)
    N3=t_vec.size
    sum_t=t_vec.sum()
    t_var=((t_vec-t_vec.mean())**2).sum()
    roi_f=roi.astype(np.float32)
    roi2=(roi_f**2).sum(axis=2)
    num_ts=np.zeros((roi.shape[0]-th+1,roi.shape[1]-tw+1),np.float32)
    sum_s=np.zeros_like(num_ts)
    for c in range(3):
        num_ts+=matchTemplate(roi_f[:,:,c],t_masked[:,:,c],TM_CCORR)
        sum_s+=matchTemplate(roi_f[:,:,c],m2,TM_CCORR)
    sum_s2=matchTemplate(roi2,m2,TM_CCORR)
    mean_s=sum_s/N3
    num=num_ts-mean_s*sum_t
    var_s=np.maximum(sum_s2-sum_s*sum_s/N3,0)
    den=np.sqrt(t_var*var_s+1e-9)
    corr=num/den
    return float(corr.max())

def resizedReduceMatch(scene:np.ndarray,temp:np.ndarray,mask:np.ndarray=None,w_min:int=40,w_max:int=90,step:int=5):
    """多宽度模板匹配：将模板缩放到多个宽度尝试匹配，取相似度最高的结果

    用于目标尺寸不确定的场景（如从者头像）。
    """
    w_lst=range(w_min,min(w_max,whOfImg(scene)[0]),step)
    maxInfo={'val':0,'loc':None,'wh':None}
    for w in w_lst:
        h=temp.shape[0]*w//temp.shape[1]
        tempwh=np.array((w,h))
        resizedtemp=resize(temp,tempwh)
        if mask is not None:
            resizedMask=resize(mask,tempwh)
        else:
            resizedMask=None
        val,loc=selfmatchTemplate(scene,resizedtemp,resizedMask)
        if val>maxInfo['val'] and val<1:
            maxInfo={'val':val,'loc':loc,'wh':tempwh}
    val,loc,wh=maxInfo.values()
    return val,loc,wh

def pixCheck(pix:np.ndarray):
    """判断像素是否为 红/绿/蓝 三原色（用于识别指令卡颜色标记）"""
    return  (not (min(pix==[0,0,255])==False) or  # 纯蓝
             
            (not (min(pix<[30,30,255])==False) and  # 偏蓝
            not (min(pix>[0,0,100]))==False) or

            (not (min(pix<[60,255,60])==False) and  # 偏绿
            not (min(pix>[0,100,0]))==False) or
            
            (not (min(pix<[255,70,70])==False) and  # 偏红
            not (min(pix>[80,0,0]))==False)
            )

def cutImg(img:np.ndarray,loc:np.ndarray,wh:np.ndarray):
    """按左上角坐标 loc 和尺寸 wh 裁剪图像"""
    x0,y0=loc
    x1,y1=loc+wh
    return img[y0:y1,x0:x1]

def locwh2xy(loc:np.ndarray,wh:np.ndarray):
    """将 (左上角, 宽高) 展开为 (x0,y0,x1,y1)"""
    x0,y0=loc
    x1,y1=loc+wh
    return x0,y0,x1,y1

def getCNPathImg(path:str):
    """中文路径安全读图：imread 不支持中文路径，改用 imdecode + fromfile"""
    fn=path[(path.index(re.findall(r'/[^/]*.png',path)[0]))+1:]
    dir=path[:(path.index(re.findall(r'/[^/]*.png',path)[0]))]
    img:np.ndarray = imdecode(np.fromfile(os.path.join(f'{dir}', fn), dtype=np.uint8), -1)
    return img

def dumImg2CNPath(img:np.ndarray,path:str):
    """中文路径安全写图：imwrite 不支持中文路径，改用 imencode + tofile"""
    imencode('.png', img )[1].tofile(path)

def whOfImg(img:np.ndarray)->np.ndarray[int]:
    """返回图像的 (宽, 高)"""
    return np.array(list(img.shape[:2])[::-1]).astype(int)

def maskMake(maskImg:np.ndarray):
    """由掩码图生成模板匹配用掩码

    掩码图中 红色(0,0,255) 像素对应区域被排除（置0），其余区域参与匹配（置255）。
    """
    return np.array([[255 if min(pt==[0,0,255])==False else 0 for pt in ptLine]for ptLine in maskImg],np.float32)

def reduce50percent(img:np.ndarray):
    """图像缩小为原来一半"""
    return resize(img,(img.shape[1]//2,img.shape[0]//2))

def reduceToMatchTemplate(img:np.ndarray,template:np.ndarray,mask:np.ndarray=None):
    """多分辨率金字塔模板匹配（由粗到精）

    先逐级缩小图像/模板（共 rdc_num 级），在最粗尺度全局匹配定位，
    再逐级在上一级位置附近放大匹配，最终返回 (相似度, 原始尺度位置)。
    相比全尺度匹配大幅降低耗时。
    """
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
    radio_err=MATCH_RADIO_ERR
    for i in range(len(rdc_temp)):
        temp=rdc_temp[i]
        img=rdc_img[i]
        mask=rdc_mask[i]
        imgwh,tempwh=np.array(list(img.shape)[::-1][-2:]),np.array(list(temp.shape)[::-1][-2:])
        # 在上一级位置附近（±radio_err 比例）扩大搜索区域
        acc_loc_lu=np.maximum(np.array((0,0)),app_loc_lu-np.floor(radio_err*imgwh).astype(int))
        acc_loc_rd=np.minimum(imgwh,app_loc_lu+tempwh+np.floor(radio_err*imgwh).astype(int))
        res=matchTemplate(img if i==0 else img[acc_loc_lu[1]:acc_loc_rd[1],acc_loc_lu[0]:acc_loc_rd[0]],temp,TM_CCOEFF_NORMED,mask=mask)
        _,acc_max,_,temp_app_loc_lu=minMaxLoc(res)
        app_loc_lu=acc_loc_lu+temp_app_loc_lu
        app_loc_lu=app_loc_lu*2
    return acc_max,app_loc_lu//2

def imgResize2512(img:np.ndarray)->np.ndarray:
    """统一缩放为 512×288"""
    return resize(img,(512,288))


# ---------------------------------------------------------------------------
# 场景识别
# ---------------------------------------------------------------------------
def checkIsFeatureScene(featureInfo_lst:list[dict],sceneImg:np.ndarray,checkMode:str,isPrint:bool=False)->bool:
    """判断当前场景是否满足特征条件

    checkMode='and'：所有特征全部命中才算（用于唯一场景判定）
    checkMode='or' ：任一特征命中即算（用于模糊场景判定）
    每个特征需同时满足：相似度 ≥ confidenceThreshold 且 匹配位置与 Rect 偏差 < MATCH_POS_TOLERANCE。
    """
    radio=MATCH_POS_TOLERANCE
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
    """找出场景中所有与特征匹配的位置

    对超过阈值的响应点做局部非极大抑制（8px 邻域内只保留一个），
    返回 [Y 坐标列表, X 坐标列表]。
    """
    featureImg:np.ndarray=featureInfo['featureImg']
    confidenceThreshold:float=featureInfo['confidenceThreshold']
    res=matchTemplate(sceneImg,featureImg,TM_CCOEFF_NORMED,mask=mask)
    res_bool:np.ndarray=np.array([[(resPix>confidenceThreshold) for resPix in resLine] for resLine in res])
    h,w=res_bool.shape[:2]
    radio=MATCH_POS_TOLERANCE
    for yi in range(h):
        for xi in range(w):    
            if res_bool[yi,xi]:
                # 将邻域内其他响应点置 False，仅保留当前点
                x0,y0,x1,y1=max(0,xi-radio),max(0,yi-radio),min(w,xi+radio),min(h,yi+radio)
                res_bool[y0:y1,x0:x1]=False
                res_bool[yi,xi]=True

    pos=np.where(res_bool==True)
    print(list(pos[0]),list(pos[1]),end=' ')
    return [list(pos[0]),list(pos[1])]


# ---------------------------------------------------------------------------
# 配置读写
# ---------------------------------------------------------------------------
def _mergeDict(default:dict,user:dict):
    """把 default 中 user 缺失的键递归补进 user（已有值保留，不覆盖）

    用于配置结构升级：新版本新增字段 → 用默认值补齐，用户个人数据原样保留。
    """
    for k,v in default.items():
        if k not in user:
            user[k]=copy.deepcopy(v)
        elif isinstance(v,dict) and isinstance(user[k],dict):
            _mergeDict(v,user[k])
    return user

def _settingPath(fn:str) -> str:
    """定位配置文件绝对路径

    优先程序根/configure（exe 快捷方式启动也稳定），回退当前工作目录（旧约定兼容）。
    """
    p=os.path.join(appRootGet(),'configure',fn)
    if os.path.exists(p):
        return p
    return os.path.join('configure',fn)

def settingMigrate():
    """配置结构迁移：启动时用 settingDefault.json 补齐旧配置缺失的新增字段

    场景：update.bat 只更新代码，配置文件留在原地。若新代码需要新字段，
    直接读旧配置会 KeyError 崩溃。本函数在启动早期调用，保证：
    - setting.json（个人数据）→ 缺失字段补默认值，策略/模拟器等已有值不动
    - settingFixed.json（固定参数）→ 缺失字段补默认值
    """
    try:
        with open(_settingPath('settingDefault.json'),'r',encoding='utf-8') as f:
            default=json.load(f)
        # setting.json：顶层含 changable + fixed；损坏时自动从 .bak / 默认模板恢复
        damaged=False
        try:
            with open(_settingPath('setting.json'),'r',encoding='utf-8') as f:
                user=json.load(f)
            if 'changable' not in user:
                damaged=True
                user=None
        except Exception:
            damaged=True
            user=None
        if user is None:
            user=_settingLoad(_settingPath('setting.json'),fallback=default)
            if user is None or 'changable' not in user:
                user=json.loads(json.dumps(default))
            print('setting.json damaged, restored from .bak/default')
        before=json.dumps(user,ensure_ascii=True)
        merged=_mergeDict(default,user)
        if damaged or json.dumps(merged,ensure_ascii=True)!=before:
            _settingDump(merged,_settingPath('setting.json'))
            print('setting.json migrated')
        # settingFixed.json：顶层只有 fixed；损坏时回退默认
        damagedFixed=False
        try:
            with open(_settingPath('settingFixed.json'),'r',encoding='utf-8') as f:
                userFixed=json.load(f)
            if 'fixed' not in userFixed:
                damagedFixed=True
                userFixed=None
        except Exception:
            damagedFixed=True
            userFixed=None
        if userFixed is None:
            userFixed=_settingLoad(_settingPath('settingFixed.json'),fallback={'fixed':default.get('fixed',{})})
            if userFixed is None or 'fixed' not in userFixed:
                userFixed={'fixed':json.loads(json.dumps(default.get('fixed',{})))}
            print('settingFixed.json damaged, restored from .bak/default')
        beforeFixed=json.dumps(userFixed.get('fixed',{}),ensure_ascii=True)
        mergedFixed=_mergeDict(default.get('fixed',{}),userFixed.get('fixed',{}))
        if damagedFixed or json.dumps(mergedFixed,ensure_ascii=True)!=beforeFixed:
            _settingDump({'fixed':mergedFixed},_settingPath('settingFixed.json'))
            print('settingFixed.json migrated')
    except Exception as e:
        print(f'settingMigrate error: {e}')

def _settingDump(obj,path:str):
    """原子写 JSON：先写临时文件再 os.replace，防止写入中途崩溃/并发写导致截断损坏

    写前把旧文件备份为 .bak（最近一次完好版本，损坏时可由 _settingLoad 恢复）。
    """
    try:
        import shutil
        shutil.copy2(path,path+'.bak')
    except Exception:
        pass
    tmp=path+'.tmp'
    with open(tmp,'w',encoding='utf-8') as f:
        json.dump(obj,f,ensure_ascii=True,indent=2)
    os.replace(tmp,path)

def _settingLoad(path:str,fallback=None):
    """读 JSON，损坏时依次回退 .bak / fallback（防止启动崩溃）"""
    for p in (path,path+'.bak'):
        if os.path.exists(p):
            try:
                with open(p,'r',encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                continue
    return fallback

def settingWrite(obj,key_lst:list):
    """写运行时配置 setting.json（按 key_lst 路径逐层写入，原子写）"""
    obj_lst=[]
    obj_lst.append(_settingLoad(_settingPath('setting.json')))
    for key in key_lst:
        obj_lst.append(obj_lst[-1][key])
    obj_lst[-1]=obj
    obj_lst.reverse()
    key_lst.reverse()
    for obji in range(len(obj_lst)-1):
        obj_lst[obji+1][key_lst[obji]]=obj_lst[obji]
    key_lst.reverse()
    _settingDump(obj_lst[-1],_settingPath('setting.json'))

def settingRead(key_lst:list):
    """读运行时配置 setting.json（按 key_lst 路径逐层取值）"""
    obj=json.load(open(_settingPath('setting.json'),'r',encoding='utf-8'))
    for key in key_lst:
        obj=obj[key]
    return obj

def fixedSettingRead(key_lst:list):
    """读固定配置 settingFixed.json（按 key_lst 路径逐层取值）"""
    obj=json.load(open(_settingPath('settingFixed.json'),'r',encoding='utf-8'))
    for key in key_lst:
        obj=obj[key]
    return obj

def fixedsettingWrite(obj,key_lst:list):
    """写固定配置 settingFixed.json（按 key_lst 路径逐层写入，原子写）"""
    obj_lst=[]
    obj_lst.append(_settingLoad(_settingPath('settingFixed.json')))
    for key in key_lst:
        obj_lst.append(obj_lst[-1][key])
    obj_lst[-1]=obj
    obj_lst.reverse()
    key_lst.reverse()
    for obji in range(len(obj_lst)-1):
        obj_lst[obji+1][key_lst[obji]]=obj_lst[obji]
    key_lst.reverse()
    _settingDump(obj_lst[-1],_settingPath('settingFixed.json'))


# ---------------------------------------------------------------------------
# 模拟器 / ADB
# ---------------------------------------------------------------------------
def simulatorIndexGet()->int:
    """获取当前选中的模拟器索引"""
    simulatorIndex=settingRead(['changable','simulatorIndex'])
    print('simulatorIndexGet->simulatorIndex: '+str(simulatorIndex))
    return simulatorIndex

def ipGet()->str:
    """获取当前选中模拟器的 IP 地址"""
    simulatorIndex=simulatorIndexGet()
    simulator:dict=settingRead(['changable','simulator',simulatorIndex])
    print('ipGet->simulatorInfo: '+simulator['name']+' '+simulator['ip'])
    return simulator['ip']

# 模拟器自动发现（常见 adb 端口表 + 进程名表）
_COMMON_SIMULATOR_PORTS=[
    ('mumu12','127.0.0.1:16384'),
    ('mumu6','127.0.0.1:7555'),
    ('nox','127.0.0.1:62001'),
    ('ldplayer','127.0.0.1:5555'),
    ('xiaoyao','127.0.0.1:21503'),
]
_SIMULATOR_PROCESS_KEYS=[
    ('MuMuVMMHeadless','mumu12'),('MuMuNxMain','mumu12'),('MuMuPlayer','mumu12'),
    ('NemuHeadless','mumu6'),('NemuPlayer','mumu6'),
    ('HD-Player','ldplayer'),('LdVBox','ldplayer'),
    ('NoxVMHandle','nox'),('NoxPlayer','nox'),
    ('dnplayer','xiaoyao'),
]

def discoverSimulators()->tuple[list[dict],list[str]]:
    """自动发现模拟器：adb 已连接设备 + 常见端口 adb connect 探测 + 进程名识别

    返回 (found, process_names)：found=[{'name','ip'}] 新发现的模拟器（含已连接设备），
    process_names=检测到的模拟器进程名列表（提示用，不含 ip 时需用户手动补）。
    """
    import subprocess
    adb=os.path.join(PLATFORM_TOOLS_DIR,'adb.exe')
    found:list[dict]=[]; ip_set=set()
    # 1) adb 已连接设备
    out=myGetoutput('adb devices')
    for line in out.splitlines()[1:]:
        parts=line.split()
        if len(parts)>=2 and parts[1]=='device':
            ip=parts[0]
            if ip not in ip_set:
                ip_set.add(ip)
                found.append({'name':'auto-'+ip.replace(':','_'),'ip':ip})
    # 2) 常见端口探测（3s 超时逐个 adb connect，防挂起）
    for name,ip in _COMMON_SIMULATOR_PORTS:
        if ip in ip_set:
            continue
        try:
            r=subprocess.run([adb,'connect',ip],capture_output=True,timeout=3,
                             creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            out=(r.stdout or b'').decode(errors='ignore')
        except Exception:
            out=''
        if 'connected' in out or 'already connected' in out:
            ip_set.add(ip)
            found.append({'name':name,'ip':ip})
    # 3) 进程名识别（psutil 遍历；依赖在打包清单内）
    procs:list[str]=[]
    try:
        import psutil
        for proc in psutil.process_iter(['name']):
            pname=(proc.info.get('name') or '')
            for key,simName in _SIMULATOR_PROCESS_KEYS:
                if key.lower() in pname.lower() and simName not in procs:
                    procs.append(simName)
    except Exception:
        pass
    return found,procs

def bsGet()->float:
    """计算坐标缩放系数：真实屏幕宽度 / 512（将 512×288 坐标系映射到设备分辨率）

    若模拟器未连接则先尝试 adb connect。
    """
    bs=3.75  # 默认缩放系数（常见 1920/512）
    ip=ipGet()
    devicesInfo=myGetoutput('adb devices')
    if ip not in devicesInfo:
        sysInput(f'adb connect {ip}')
    dpi=myGetoutput(f'adb -s {ip} shell wm size')
    print(dpi)
    if not ('notfound' in dpi):
        dpiY,dpiX=[int(dpii) for dpii in re.findall(r'\d+',dpi)]
        bs=max(dpiX,dpiY)/outputX
    return bs

def stateNameGet()->list[str]:
    """获取全部主流程状态名（来自 fixed 配置）"""
    stateInfo_lst:dict[str,dict[str,int|list[int]|list[list[dict[str,str|int]]]|str]]=fixedSettingRead(['fixed','parameters','general'])
    return list(stateInfo_lst.keys())

def neighborStateNameGet()->dict[str,list[int]]:
    """获取各状态的可达邻状态索引映射（来自 fixed 配置）"""
    stateInfo_lst:dict[str,dict[str,int|list[int]|list[list[dict[str,str|int]]]|str]]=fixedSettingRead(['fixed','parameters','general'])
    return {stateName:stateInfo_lst[stateName]['neighborState'] for stateName in stateInfo_lst.keys()}

def _runCmd(text:str,capture:bool=False)->str:
    """统一执行 shell 命令（自动把 adb 替换为本地 adb.exe），带 15s 超时

    Windows 下 shell=True 超时只杀 cmd.exe、残留 adb.exe 持有管道导致 wait 卡死，
    故超时后 taskkill /T 杀整个进程树再收尾。
    """
    if 'adb' in text:
        text=text.replace('adb',PLATFORM_TOOLS_DIR+r'\adb.exe')
    proc=subprocess.Popen(text,shell=True,
                          stdout=subprocess.PIPE if capture else None,
                          stderr=subprocess.STDOUT if capture else None,
                          text=True,creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        out,_=proc.communicate(timeout=15)
        return out or ''
    except subprocess.TimeoutExpired:
        try:
            subprocess.run(['taskkill','/F','/T','/PID',str(proc.pid)],
                           capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW)
        except Exception:
            pass
        try:
            out,_=proc.communicate(timeout=5)
            return out or ''
        except Exception:
            return ''

def sysInput(text:str):
    """执行 shell 命令（自动把 adb 替换为本地平台工具中的 adb.exe）

    带 15s 超时：模拟器 adb 掉线时 adb 命令可能挂起，超时杀进程树避免阻塞主流程。
    """
    _runCmd(text)

def myGetoutput(text:str):
    """执行 shell 命令并返回输出（自动把 adb 替换为本地平台工具中的 adb.exe）

    带 15s 超时：adb 挂起时返回空串，避免阻塞主流程。
    """
    data=_runCmd(text,capture=True)
    if data.endswith('\n'):
        data=data[:-1]
    return data

def pause():
    """空函数：作为 actionByDictList 的默认步间延时钩子"""
    pass

class SimulatorOperator():
    """模拟器触控操作器：封装 minitouch 的点击/滑动

    内部坐标基于 512×288 坐标系；对竖屏模拟器自动做坐标旋转映射。
    """
    
    def __init__(self):
        self.bs=bsGet()                 # 坐标缩放系数
        self.device:MNTDevice=None      # pyminitouch 设备连接
        self.device_size=[0,0]          # 设备触摸面板尺寸 [宽,高]

    def deviceBind(self,device:MNTDevice):
        """绑定 minitouch 设备连接"""
        self.device=device
        self.device_size=[device.connection.max_x,device.connection.max_y]
    
    def simulatorTap(self,x:int,y:int,bs:float=1):
        """点击 (x,y)，坐标乘 bs 换算到设备分辨率"""
        self.device.tap([(int(x*bs),int(y*bs))])

    def simulatorSwipe(self,x0:int,y0:int,x1:int,y1:int,duration:int,bs:float=1):
        """从 (x0,y0) 滑动到 (x1,y1)，分 num 段插入中间点模拟平滑滑动"""
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
        """按动作字典执行一次操作

        dictionary=[0,x,y]      点击；dictionary=[1,x0,y0,x1,y1,duration] 滑动。
        竖屏设备（高>宽）时坐标按 90° 旋转映射。
        """
        if self.device_size[0]<self.device_size[1]:
            if dictionary[0]==0:
                self.simulatorTap(outputY-dictionary[2],dictionary[1],self.bs)
            elif dictionary[0]==1:
                self.simulatorSwipe(outputY-dictionary[2],dictionary[1],outputY-dictionary[4],dictionary[3],dictionary[5],self.bs)
        else:
            if dictionary[0]==0:
                self.simulatorTap(dictionary[1],dictionary[2],self.bs)
            elif dictionary[0]==1:
                self.simulatorSwipe(dictionary[1],dictionary[2],dictionary[3],dictionary[4],dictionary[5],self.bs)

    def actionByDictList(self,dictionary_lst:list[list[int]],pause=pause):
        """按动作字典列表依次执行，每步之间调用 pause()（默认不延时）"""
        print(dictionary_lst,sep='\n')
        for dictionary in dictionary_lst:
            self.actionByDict(dictionary)
            pause()
         
def miniInstall(struc:str,ip:str):
    """安装 minitouch 到模拟器：按 CPU 架构选择二进制，push + chmod

    返回 (是否成功, 错误信息)。已存在的旧 minitouch 会先删除再推送。
    """
    minitouch_pn=r'minitouch\{}\minitouch'.format(struc)
    pn_lst=[minitouch_pn]
    minitouch_fn='minitouch'
    fn_lst=[minitouch_fn]
    adbInfo=myGetoutput('adb shell ls -all data/local/tmp')
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


# ---------------------------------------------------------------------------
# Qt 图像互转
# ---------------------------------------------------------------------------
def qImg2Mat(qImg:QImage)->np.ndarray:
    """QImage → BGR ndarray（去掉 Alpha 通道）"""
    width = qImg.width()
    height = qImg.height()
    ptr=qImg.bits()
    ptr.setsize(qImg.byteCount())
    arr = np.array(ptr).reshape(height, width, 4) 
    return arr[:,:,:3]

def img2pixmap(image:np.ndarray):
    """BGR ndarray → QPixmap（转换通道顺序为 RGB）"""
    Y, X = image.shape[:2]
    _bgra = np.zeros((Y, X, 4), dtype=np.uint8, order='C')
    _bgra[..., 0] = image[..., 2]
    _bgra[..., 1] = image[..., 1]
    _bgra[..., 2] = image[..., 0]
    qimage = QImage(_bgra.data, X, Y, QImage.Format_RGB32)
    pixmap = QPixmap.fromImage(qimage)
    return pixmap


# ---------------------------------------------------------------------------
# 文本工具
# ---------------------------------------------------------------------------
def list2str(lst:list):
    """列表 → 空格分隔字符串"""
    text=''
    for obj in lst:
        text+=str(obj)+' '
    return text
