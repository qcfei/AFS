"""可折叠面板：点击标题按钮展开/收起内容区域（带高度动画）

CollapsibleBox         : 通用折叠面板
CollapsibleBox_Strategy: 策略条目折叠面板（标题自动跟随策略名更新）
"""
from PyQt5 import QtCore, QtWidgets
from pytool.basicFunction import *


class CollapsibleBox(QtWidgets.QWidget):
    """通用可折叠面板"""
    def __init__(self, title="", parent=None):
        super(CollapsibleBox, self).__init__(parent)

        # 标题按钮（可勾选，驱动展开/收起）
        self.toggle_button = QtWidgets.QToolButton(
            text=title, checkable=True, checked=False
        )
        self.toggle_button.setStyleSheet("QToolButton { border: none; }")
        self.toggle_button.setToolButtonStyle(
            QtCore.Qt.ToolButtonTextBesideIcon
        )
        self.toggle_button.setArrowType(QtCore.Qt.RightArrow)
        self.toggle_button.pressed.connect(self.on_pressed)

        self.toggle_animation = QtCore.QParallelAnimationGroup(self)

        # 内容区域（初始高度 0，展开时由动画拉高）
        self.content_area = QtWidgets.QScrollArea(
            maximumHeight=0, minimumHeight=0
        )
        self.content_area.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed
        )
        self.content_area.setFrameShape(QtWidgets.QFrame.NoFrame)

        lay = QtWidgets.QVBoxLayout(self)
        lay.setSpacing(0)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.toggle_button)
        lay.addWidget(self.content_area)

        # 动画同时作用于：面板高度 + 内容区高度
        self.toggle_animation.addAnimation(
            QtCore.QPropertyAnimation(self, b"minimumHeight")
        )
        self.toggle_animation.addAnimation(
            QtCore.QPropertyAnimation(self, b"maximumHeight")
        )
        self.toggle_animation.addAnimation(
            QtCore.QPropertyAnimation(self.content_area, b"maximumHeight")
        )

    @QtCore.pyqtSlot()
    def on_pressed(self):
        """标题被点击：切换展开/收起方向并播放动画"""
        checked = self.toggle_button.isChecked()
        self.toggle_button.setArrowType(
            QtCore.Qt.DownArrow if not checked else QtCore.Qt.RightArrow
        )
        self.toggle_animation.setDirection(
            QtCore.QAbstractAnimation.Forward
            if not checked
            else QtCore.QAbstractAnimation.Backward
        )
        self.toggle_animation.start()

    def setContentLayout(self, layout):
        """设置内容区域的布局，并计算展开动画的起始/结束高度"""
        self.content_area.setLayout(layout)
        collapsed_height=40  # 收起时面板高度
        content_height = layout.sizeHint().height()+30
        for i in range(self.toggle_animation.animationCount()):
            animation = self.toggle_animation.animationAt(i)
            animation.setDuration(200)
            animation.setStartValue(collapsed_height)
            animation.setEndValue(collapsed_height + content_height)

        content_animation = self.toggle_animation.animationAt(
            self.toggle_animation.animationCount() - 1
        )
        content_animation.setDuration(200)
        content_animation.setStartValue(0)
        content_animation.setEndValue(content_height)

class CollapsibleBox_Strategy(CollapsibleBox):
    """策略条目折叠面板：标题显示"序号 策略名"，随策略改名自动更新"""
    def __init__(self, idx:int):
        super().__init__('')
        self.idx=idx
        self.nameUpdate()

    def nameUpdate(self):
        """从配置读取策略名并更新标题"""
        title=settingRead(['changable','strategy',self.idx,'name'])
        self.toggle_button.setText(f'{str(self.idx+1)} {title}')

if __name__ == "__main__":
    # 独立演示/调试入口：运行本文件直接查看折叠面板效果
    import sys

    app = QtWidgets.QApplication(sys.argv)

    w = QtWidgets.QMainWindow()
    w.setCentralWidget(QtWidgets.QWidget())
    dock = QtWidgets.QDockWidget("Collapsible Demo")
    w.addDockWidget(QtCore.Qt.LeftDockWidgetArea, dock)
    scroll = QtWidgets.QScrollArea()
    dock.setWidget(scroll)
    content = QtWidgets.QWidget()
    scroll.setWidget(content)
    scroll.setWidgetResizable(True)
    vlay = QtWidgets.QVBoxLayout(content)
    for nmCpI in range(11):
        box = CollapsibleBox("strategy-{}".format(nmCpI+1))
        vlay.addWidget(box)
        lay = QtWidgets.QVBoxLayout()
        for j in range(13):
            label = QtWidgets.QLabel("{}".format(j))
            lay.addWidget(label)

        box.setContentLayout(lay)
    vlay.addStretch()
    w.resize(640, 480)
    w.show()
    sys.exit(app.exec_())
