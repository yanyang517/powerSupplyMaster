# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'floating_classic.ui'
##
## Created by: Qt User Interface Compiler version 6.10.2
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from PySide6.QtCore import (QCoreApplication, QDate, QDateTime, QLocale,
    QMetaObject, QObject, QPoint, QRect,
    QSize, QTime, QUrl, Qt)
from PySide6.QtGui import (QBrush, QColor, QConicalGradient, QCursor,
    QFont, QFontDatabase, QGradient, QIcon,
    QImage, QKeySequence, QLinearGradient, QPainter,
    QPalette, QPixmap, QRadialGradient, QTransform)
from PySide6.QtWidgets import (QApplication, QDialog, QFrame, QGroupBox,
    QHBoxLayout, QLabel, QSizePolicy, QWidget)

class Ui_Dialog(object):
    def setupUi(self, Dialog):
        if not Dialog.objectName():
            Dialog.setObjectName(u"Dialog")
        Dialog.setWindowModality(Qt.WindowModality.NonModal)
        Dialog.resize(407, 81)
        Dialog.setMouseTracking(True)
        Dialog.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        Dialog.setWindowOpacity(0.700000000000000)
        self.horizontalLayout = QHBoxLayout(Dialog)
        self.horizontalLayout.setSpacing(0)
        self.horizontalLayout.setObjectName(u"horizontalLayout")
        self.horizontalLayout.setContentsMargins(0, 0, 0, 0)
        self.groupBox_4 = QGroupBox(Dialog)
        self.groupBox_4.setObjectName(u"groupBox_4")
        self.groupBox_4.setContextMenuPolicy(Qt.ContextMenuPolicy.DefaultContextMenu)
        self.groupBox_4.setFlat(True)
        self.horizontalLayout_2 = QHBoxLayout(self.groupBox_4)
        self.horizontalLayout_2.setObjectName(u"horizontalLayout_2")
        self.voltage_label = QLabel(self.groupBox_4)
        self.voltage_label.setObjectName(u"voltage_label")
        font = QFont()
        font.setPointSize(36)
        self.voltage_label.setFont(font)
        self.voltage_label.setFrameShape(QFrame.Shape.NoFrame)
        self.voltage_label.setAlignment(Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignTrailing|Qt.AlignmentFlag.AlignVCenter)

        self.horizontalLayout_2.addWidget(self.voltage_label)


        self.horizontalLayout.addWidget(self.groupBox_4)

        self.groupBox_3 = QGroupBox(Dialog)
        self.groupBox_3.setObjectName(u"groupBox_3")
        self.groupBox_3.setMouseTracking(True)
        self.groupBox_3.setFlat(True)
        self.horizontalLayout_7 = QHBoxLayout(self.groupBox_3)
        self.horizontalLayout_7.setSpacing(0)
        self.horizontalLayout_7.setObjectName(u"horizontalLayout_7")
        self.horizontalLayout_7.setContentsMargins(0, 0, 20, 0)
        self.current_label = QLabel(self.groupBox_3)
        self.current_label.setObjectName(u"current_label")
        self.current_label.setFont(font)
        self.current_label.setFrameShape(QFrame.Shape.NoFrame)
        self.current_label.setAlignment(Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignTrailing|Qt.AlignmentFlag.AlignVCenter)

        self.horizontalLayout_7.addWidget(self.current_label)


        self.horizontalLayout.addWidget(self.groupBox_3)


        self.retranslateUi(Dialog)

        QMetaObject.connectSlotsByName(Dialog)
    # setupUi

    def retranslateUi(self, Dialog):
        Dialog.setWindowTitle(QCoreApplication.translate("Dialog", u"Dialog", None))
        self.groupBox_4.setTitle("")
#if QT_CONFIG(tooltip)
        self.voltage_label.setToolTip(QCoreApplication.translate("Dialog", u"\u5f53\u524d\u7535\u538b", None))
#endif // QT_CONFIG(tooltip)
        self.voltage_label.setText(QCoreApplication.translate("Dialog", u"12.00 V", None))
        self.groupBox_3.setTitle("")
#if QT_CONFIG(tooltip)
        self.current_label.setToolTip(QCoreApplication.translate("Dialog", u"\u5f53\u524d\u7535\u6d41", None))
#endif // QT_CONFIG(tooltip)
        self.current_label.setText(QCoreApplication.translate("Dialog", u"0.00 A", None))
    # retranslateUi

