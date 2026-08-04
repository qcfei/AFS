"""可搜索下拉框：输入文字时通过 QCompleter 过滤候选项

当前项目未直接使用，保留作通用 UI 组件备用。
"""
from PyQt5.QtWidgets import QWidget, QComboBox, QLineEdit, QApplication
from PyQt5.QtGui import QMouseEvent
from PyQt5.Qt import Qt, QRect, QCompleter, QSortFilterProxyModel
import sys

class ExtendedComboBox(QComboBox):
    """支持输入过滤的 QComboBox"""
    def __init__(self, parent=None):
        super(ExtendedComboBox, self).__init__(parent)
        self.setEditable(True)
 
        # 添加筛选器模型来筛选匹配项
        self.pFilterModel = QSortFilterProxyModel(self)
        self.pFilterModel.setFilterCaseSensitivity(Qt.CaseInsensitive)  # 大小写不敏感
        self.pFilterModel.setSourceModel(self.model())
 
        # 添加一个使用筛选器模型的QCompleter
        self.completer = QCompleter(self.pFilterModel, self)
        # 始终显示所有(过滤后的)补全结果
        self.completer.setCompletionMode(QCompleter.UnfilteredPopupCompletion)
        self.completer.setCaseSensitivity(Qt.CaseInsensitive)  # 不区分大小写
        self.setCompleter(self.completer)
 
        # Qcombobox编辑栏文本变化时对应的槽函数
        self.lineEdit().textEdited.connect(self.pFilterModel.setFilterFixedString)
        self.completer.activated.connect(self.on_completer_activated)
 
    # 当在Qcompleter列表选中候，下拉框项目列表选择相应的子项目
    def on_completer_activated(self, text):
        if text:
            index = self.findText(text)
            self.setCurrentIndex(index)
 
    # 在模型更改时，更新过滤器和补全器的模型
    def setModel(self, model):
        super(ExtendedComboBox, self).setModel(model)
        self.pFilterModel.setSourceModel(model)
        self.completer.setModel(self.pFilterModel)
 
    # 在模型列更改时，更新过滤器和补全器的模型列
    def setModelColumn(self, column):
        self.completer.setCompletionColumn(column)
        self.pFilterModel.setFilterKeyColumn(column)
        super(ExtendedComboBox, self).setModelColumn(column)
 
    # 回应回车按钮事件
    def keyPressEvent(self, e):
        if (e.key() == Qt.Key_Enter or e.key() == Qt.Key_Return):
            text = self.currentText()
            index = self.findText(text, Qt.MatchExactly | Qt.MatchCaseSensitive)
            self.setCurrentIndex(index)
            self.hidePopup()
            super(ExtendedComboBox, self).keyPressEvent(e)
        else:
            super(ExtendedComboBox, self).keyPressEvent(e)
