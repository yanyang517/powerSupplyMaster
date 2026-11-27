# -*- coding: utf-8 -*-
"""悬浮窗界面构建代码（手工维护）。

界面不再由 Qt Designer 或 uic 生成；标签 objectName 是 FloatingWindow 的公共契约。
"""

from PySide6.QtCore import QCoreApplication, QMetaObject, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QFrame, QGroupBox, QHBoxLayout, QLabel


class Ui_Dialog:
    """构建悬浮窗的电压/电流读数区域。"""

    def setupUi(self, Dialog):
        if not Dialog.objectName():
            Dialog.setObjectName("Dialog")
        Dialog.setWindowModality(Qt.WindowModality.NonModal)
        Dialog.resize(407, 81)
        Dialog.setMouseTracking(True)
        Dialog.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        Dialog.setWindowOpacity(0.7)

        self.horizontalLayout = QHBoxLayout(Dialog)
        self.horizontalLayout.setSpacing(0)
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.horizontalLayout.setContentsMargins(0, 0, 0, 0)

        self.groupBox_4 = QGroupBox(Dialog)
        self.groupBox_4.setObjectName("groupBox_4")
        self.groupBox_4.setContextMenuPolicy(Qt.ContextMenuPolicy.DefaultContextMenu)
        self.groupBox_4.setFlat(True)
        self.horizontalLayout_2 = QHBoxLayout(self.groupBox_4)
        self.horizontalLayout_2.setObjectName("horizontalLayout_2")
        self.voltage_label = QLabel(self.groupBox_4)
        self.voltage_label.setObjectName("voltage_label")
        readout_font = QFont()
        readout_font.setPointSize(36)
        self.voltage_label.setFont(readout_font)
        self.voltage_label.setFrameShape(QFrame.Shape.NoFrame)
        self.voltage_label.setAlignment(
            Qt.AlignmentFlag.AlignRight
            | Qt.AlignmentFlag.AlignTrailing
            | Qt.AlignmentFlag.AlignVCenter
        )
        self.horizontalLayout_2.addWidget(self.voltage_label)
        self.horizontalLayout.addWidget(self.groupBox_4)

        self.groupBox_3 = QGroupBox(Dialog)
        self.groupBox_3.setObjectName("groupBox_3")
        self.groupBox_3.setMouseTracking(True)
        self.groupBox_3.setFlat(True)
        self.horizontalLayout_7 = QHBoxLayout(self.groupBox_3)
        self.horizontalLayout_7.setSpacing(0)
        self.horizontalLayout_7.setObjectName("horizontalLayout_7")
        self.horizontalLayout_7.setContentsMargins(0, 0, 20, 0)
        self.current_label = QLabel(self.groupBox_3)
        self.current_label.setObjectName("current_label")
        self.current_label.setFont(readout_font)
        self.current_label.setFrameShape(QFrame.Shape.NoFrame)
        self.current_label.setAlignment(
            Qt.AlignmentFlag.AlignRight
            | Qt.AlignmentFlag.AlignTrailing
            | Qt.AlignmentFlag.AlignVCenter
        )
        self.horizontalLayout_7.addWidget(self.current_label)
        self.horizontalLayout.addWidget(self.groupBox_3)

        self.retranslateUi(Dialog)
        QMetaObject.connectSlotsByName(Dialog)

    def retranslateUi(self, Dialog):
        translate = lambda text: QCoreApplication.translate("Dialog", text, None)
        Dialog.setWindowTitle(translate("Dialog"))
        self.groupBox_4.setTitle("")
        self.voltage_label.setToolTip(translate("当前电压"))
        self.voltage_label.setText(translate("12.00 V"))
        self.groupBox_3.setTitle("")
        self.current_label.setToolTip(translate("当前电流"))
        self.current_label.setText(translate("0.00 A"))
