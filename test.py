import pytool.basicFunction
import pyminitouch

模拟器操作器=pytool.basicFunction.SimulatorOperator()
device=pyminitouch.MNTDevice('127.0.0.1:16384')
模拟器操作器.deviceBind(device)
动作列表=[[1,213,251,213,107,100]]
模拟器操作器.actionByDictList(动作列表)