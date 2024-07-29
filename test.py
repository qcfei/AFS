
import cv2
from pytool.basicFunction import *

img=cv2.imread('screen.jpeg')
mask0=cv2.imread('mask/greatMask.png')
mask1=cv2.imread('mask/orderBlue.png')
mask2=cv2.imread('mask/orderGreen.png')
mask3=cv2.imread('mask/orderRed.png')
print(mask0.shape)