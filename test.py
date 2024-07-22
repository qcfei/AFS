from pytool.basicFunction import *
from pytool.basicQObject import *
from pytool.pauseableThread import *


_DEVICE_ID='127.0.0.1:16384'
sysInput(f'adb connect {_DEVICE_ID}')
device=MNTDevice(_DEVICE_ID)
device.tap([(50,50)])
device.stop()
sysInput(f'adb kill-server')
