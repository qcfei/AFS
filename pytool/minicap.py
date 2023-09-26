
import socket
import struct
from collections import OrderedDict
import sys
import time
from PyQt5.QtWidgets import *
from PyQt5.QtGui import QImage,QPixmap

from pytool.basicFunction import *

#minicap相关类
class Banner:
    def __init__(self):
        self.__banner = OrderedDict(
            [('version', 0),
             ('length', 0),
             ('pid', 0),
             ('realWidth', 0),
             ('realHeight', 0),
             ('virtualWidth', 0),
             ('virtualHeight', 0),
             ('orientation', 0),
             ('quirks', 0)
             ])
 
    def __setitem__(self, key, value):
        self.__banner[key] = value
 
    def __getitem__(self, key):
        return self.__banner[key]
 
    def keys(self):
        return self.__banner.keys()
 
    def __str__(self):
        return str(self.__banner)
 
 
class Minicap:
    def __init__(self, host, port, banner):
        self.buffer_size = 1920*2
        self.host = host
        self.port = port
        self.banner = banner
        self.isConnected=False
        
        self.ip:str=ipGet()
        
        self.readBannerBytes = 0
        self.bannerLength = 24
        self.readFrameBytes = 0
        self.frameBodyLength = 0  
        self.data = []

    def connect(self):
        self.isConnected=True
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        except (socket.error) as e:
            # print(e)
            sys.exit(1)
        self.socket.connect((self.host, self.port))
    
    def disconnect(self):
        self.isConnected=False
        self.socket.close()

    def on_image_transfered(self):
        file_name = 'screen.jpeg'  # 图片名
        with open(file_name, 'wb') as f:
            for b in self.data:
                f.write((b).to_bytes(1,'big'))
 
    def consume(self)->bool:
        flag=False
        chunk = self.socket.recv(self.buffer_size)
        cursor = 0
        buf_len = len(chunk)    
        while cursor < buf_len:
            if self.readBannerBytes < self.bannerLength:
                map(lambda i, val: self.banner.__setitem__(self.banner.keys()[i], val),
                    [i for i in range(len(self.banner.keys()))], struct.unpack("<2b5ibB", chunk))
                cursor = buf_len
                self.readBannerBytes = self.bannerLength
            elif self.readFrameBytes < 4:
                self.frameBodyLength += (chunk[cursor] << (self.readFrameBytes * 8)) >> 0
                cursor += 1
                self.readFrameBytes += 1
            else:
                if buf_len - cursor >= self.frameBodyLength:
                    self.data.extend(chunk[cursor:cursor + self.frameBodyLength])
                    self.on_image_transfered()
                    cursor += self.frameBodyLength
                    self.frameBodyLength = self.readFrameBytes = 0
                    self.data = []
                    flag=True
                else:
                    self.data.extend(chunk[cursor:buf_len])
                    self.frameBodyLength -= buf_len - cursor
                    self.readFrameBytes += buf_len - cursor
                    cursor = buf_len
        return flag
 