from pytool.myQWidget import TabWidgt_Total
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
import sys
from qt_material import apply_stylesheet    

app = QApplication(sys.argv)
extra = {
'density_scale': '1',}
apply_stylesheet(app, theme='dark_teal.xml', extra=extra)

total_tab = TabWidgt_Total()
total_tab.show()
sys.exit(app.exec_())
