# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'mainWindowHrugOE.ui'
##
## Created by: Qt User Interface Compiler version 6.2.4
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
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDial,
    QDoubleSpinBox, QFontComboBox, QFormLayout, QFrame,
    QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QMainWindow, QPushButton, QSizePolicy, QSlider,
    QSpacerItem, QSpinBox, QStatusBar, QTabWidget,
    QVBoxLayout, QWidget)

class Ui_MainWindow(object):
    def setupUi(self, MainWindow):
        if not MainWindow.objectName():
            MainWindow.setObjectName(u"MainWindow")
        MainWindow.resize(584, 603)
        font = QFont()
        font.setPointSize(11)
        MainWindow.setFont(font)
        self.centralwidget = QWidget(MainWindow)
        self.centralwidget.setObjectName(u"centralwidget")
        self.horizontalLayout_11 = QHBoxLayout(self.centralwidget)
        self.horizontalLayout_11.setObjectName(u"horizontalLayout_11")
        self.tabWidget = QTabWidget(self.centralwidget)
        self.tabWidget.setObjectName(u"tabWidget")
        self.tabWidget.setTabPosition(QTabWidget.North)
        self.tabWidget.setTabShape(QTabWidget.Triangular)
        self.tab = QWidget()
        self.tab.setObjectName(u"tab")
        self.verticalLayout_5 = QVBoxLayout(self.tab)
        self.verticalLayout_5.setObjectName(u"verticalLayout_5")
        self.groupBox = QGroupBox(self.tab)
        self.groupBox.setObjectName(u"groupBox")
        self.horizontalLayout = QHBoxLayout(self.groupBox)
        self.horizontalLayout.setObjectName(u"horizontalLayout")
        self.formLayout_2 = QFormLayout()
        self.formLayout_2.setObjectName(u"formLayout_2")
        self.label = QLabel(self.groupBox)
        self.label.setObjectName(u"label")

        self.formLayout_2.setWidget(0, QFormLayout.LabelRole, self.label)

        self.comboBox = QComboBox(self.groupBox)
        self.comboBox.setObjectName(u"comboBox")

        self.formLayout_2.setWidget(0, QFormLayout.FieldRole, self.comboBox)


        self.horizontalLayout.addLayout(self.formLayout_2)

        self.formLayout = QFormLayout()
        self.formLayout.setObjectName(u"formLayout")
        self.label_2 = QLabel(self.groupBox)
        self.label_2.setObjectName(u"label_2")

        self.formLayout.setWidget(0, QFormLayout.LabelRole, self.label_2)

        self.comboBox_2 = QComboBox(self.groupBox)
        self.comboBox_2.addItem("")
        self.comboBox_2.addItem("")
        self.comboBox_2.addItem("")
        self.comboBox_2.addItem("")
        self.comboBox_2.setObjectName(u"comboBox_2")

        self.formLayout.setWidget(0, QFormLayout.FieldRole, self.comboBox_2)


        self.horizontalLayout.addLayout(self.formLayout)

        self.pushButton = QPushButton(self.groupBox)
        self.pushButton.setObjectName(u"pushButton")
        self.pushButton.setCheckable(True)
        self.pushButton.setAutoExclusive(True)

        self.horizontalLayout.addWidget(self.pushButton)

        self.pushButton_2 = QPushButton(self.groupBox)
        self.pushButton_2.setObjectName(u"pushButton_2")
        self.pushButton_2.setCheckable(True)
        self.pushButton_2.setAutoExclusive(True)

        self.horizontalLayout.addWidget(self.pushButton_2)

        self.autoReconnectCB = QCheckBox(self.groupBox)
        self.autoReconnectCB.setObjectName(u"autoReconnectCB")

        self.horizontalLayout.addWidget(self.autoReconnectCB)

        self.horizontalSpacer_2 = QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum)

        self.horizontalLayout.addItem(self.horizontalSpacer_2)


        self.verticalLayout_5.addWidget(self.groupBox)

        self.groupBox_2 = QGroupBox(self.tab)
        self.groupBox_2.setObjectName(u"groupBox_2")
        self.verticalLayout_4 = QVBoxLayout(self.groupBox_2)
        self.verticalLayout_4.setObjectName(u"verticalLayout_4")
        self.horizontalLayout_3 = QHBoxLayout()
        self.horizontalLayout_3.setSpacing(9)
        self.horizontalLayout_3.setObjectName(u"horizontalLayout_3")
        self.horizontalLayout_3.setContentsMargins(9, 9, 9, 9)
        self.groupBox_4 = QGroupBox(self.groupBox_2)
        self.groupBox_4.setObjectName(u"groupBox_4")
        self.horizontalLayout_8 = QHBoxLayout(self.groupBox_4)
        self.horizontalLayout_8.setObjectName(u"horizontalLayout_8")
        self.label_3 = QLabel(self.groupBox_4)
        self.label_3.setObjectName(u"label_3")
        font1 = QFont()
        font1.setPointSize(36)
        self.label_3.setFont(font1)
        self.label_3.setFrameShape(QFrame.NoFrame)
        self.label_3.setAlignment(Qt.AlignRight|Qt.AlignTrailing|Qt.AlignVCenter)

        self.horizontalLayout_8.addWidget(self.label_3)


        self.horizontalLayout_3.addWidget(self.groupBox_4)

        self.groupBox_3 = QGroupBox(self.groupBox_2)
        self.groupBox_3.setObjectName(u"groupBox_3")
        self.horizontalLayout_7 = QHBoxLayout(self.groupBox_3)
        self.horizontalLayout_7.setObjectName(u"horizontalLayout_7")
        self.label_4 = QLabel(self.groupBox_3)
        self.label_4.setObjectName(u"label_4")
        self.label_4.setFont(font1)
        self.label_4.setFrameShape(QFrame.NoFrame)
        self.label_4.setAlignment(Qt.AlignRight|Qt.AlignTrailing|Qt.AlignVCenter)

        self.horizontalLayout_7.addWidget(self.label_4)


        self.horizontalLayout_3.addWidget(self.groupBox_3)


        self.verticalLayout_4.addLayout(self.horizontalLayout_3)

        self.horizontalLayout_4 = QHBoxLayout()
        self.horizontalLayout_4.setObjectName(u"horizontalLayout_4")
        self.groupBox1 = QGroupBox(self.groupBox_2)
        self.groupBox1.setObjectName(u"groupBox1")
        self.verticalLayout_2 = QVBoxLayout(self.groupBox1)
        self.verticalLayout_2.setObjectName(u"verticalLayout_2")
        self.horizontalLayout_2 = QHBoxLayout()
        self.horizontalLayout_2.setObjectName(u"horizontalLayout_2")
        self.horizontalSpacer = QSpacerItem(40, 20, QSizePolicy.Preferred, QSizePolicy.Minimum)

        self.horizontalLayout_2.addItem(self.horizontalSpacer)

        self.doubleSpinBox = QDoubleSpinBox(self.groupBox1)
        self.doubleSpinBox.setObjectName(u"doubleSpinBox")

        self.horizontalLayout_2.addWidget(self.doubleSpinBox)


        self.verticalLayout_2.addLayout(self.horizontalLayout_2)

        self.dial = QDial(self.groupBox1)
        self.dial.setObjectName(u"dial")
        self.dial.setNotchesVisible(True)

        self.verticalLayout_2.addWidget(self.dial)


        self.horizontalLayout_4.addWidget(self.groupBox1)

        self.groupBox2 = QGroupBox(self.groupBox_2)
        self.groupBox2.setObjectName(u"groupBox2")
        self.verticalLayout_3 = QVBoxLayout(self.groupBox2)
        self.verticalLayout_3.setObjectName(u"verticalLayout_3")
        self.pushButton_3 = QPushButton(self.groupBox2)
        self.pushButton_3.setObjectName(u"pushButton_3")

        self.verticalLayout_3.addWidget(self.pushButton_3)


        self.horizontalLayout_4.addWidget(self.groupBox2)


        self.verticalLayout_4.addLayout(self.horizontalLayout_4)

        self.horizontalLayout_5 = QHBoxLayout()
        self.horizontalLayout_5.setObjectName(u"horizontalLayout_5")
        self.formLayout_4 = QFormLayout()
        self.formLayout_4.setObjectName(u"formLayout_4")
        self.label_9 = QLabel(self.groupBox_2)
        self.label_9.setObjectName(u"label_9")

        self.formLayout_4.setWidget(0, QFormLayout.LabelRole, self.label_9)

        self.doubleSpinBox_3 = QDoubleSpinBox(self.groupBox_2)
        self.doubleSpinBox_3.setObjectName(u"doubleSpinBox_3")

        self.formLayout_4.setWidget(0, QFormLayout.FieldRole, self.doubleSpinBox_3)


        self.horizontalLayout_5.addLayout(self.formLayout_4)

        self.formLayout_3 = QFormLayout()
        self.formLayout_3.setObjectName(u"formLayout_3")
        self.label_8 = QLabel(self.groupBox_2)
        self.label_8.setObjectName(u"label_8")

        self.formLayout_3.setWidget(0, QFormLayout.LabelRole, self.label_8)

        self.doubleSpinBox_2 = QDoubleSpinBox(self.groupBox_2)
        self.doubleSpinBox_2.setObjectName(u"doubleSpinBox_2")

        self.formLayout_3.setWidget(0, QFormLayout.FieldRole, self.doubleSpinBox_2)


        self.horizontalLayout_5.addLayout(self.formLayout_3)


        self.verticalLayout_4.addLayout(self.horizontalLayout_5)

        self.horizontalLayout_6 = QHBoxLayout()
        self.horizontalLayout_6.setObjectName(u"horizontalLayout_6")
        self.formLayout_6 = QFormLayout()
        self.formLayout_6.setObjectName(u"formLayout_6")
        self.label_7 = QLabel(self.groupBox_2)
        self.label_7.setObjectName(u"label_7")

        self.formLayout_6.setWidget(0, QFormLayout.LabelRole, self.label_7)

        self.lineEdit = QLineEdit(self.groupBox_2)
        self.lineEdit.setObjectName(u"lineEdit")
        sizePolicy = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.lineEdit.sizePolicy().hasHeightForWidth())
        self.lineEdit.setSizePolicy(sizePolicy)

        self.formLayout_6.setWidget(0, QFormLayout.FieldRole, self.lineEdit)


        self.horizontalLayout_6.addLayout(self.formLayout_6)

        self.checkBox = QCheckBox(self.groupBox_2)
        self.checkBox.setObjectName(u"checkBox")

        self.horizontalLayout_6.addWidget(self.checkBox)


        self.verticalLayout_4.addLayout(self.horizontalLayout_6)

        self.verticalLayout_4.setStretch(0, 1)
        self.verticalLayout_4.setStretch(1, 2)

        self.verticalLayout_5.addWidget(self.groupBox_2)

        self.verticalLayout_5.setStretch(1, 1)
        self.tabWidget.addTab(self.tab, "")
        self.tab_2 = QWidget()
        self.tab_2.setObjectName(u"tab_2")
        self.tabWidget.addTab(self.tab_2, "")
        self.tab_3 = QWidget()
        self.tab_3.setObjectName(u"tab_3")
        self.tabWidget.addTab(self.tab_3, "")
        self.tab_5 = QWidget()
        self.tab_5.setObjectName(u"tab_5")
        self.groupBox_5 = QGroupBox(self.tab_5)
        self.groupBox_5.setObjectName(u"groupBox_5")
        self.groupBox_5.setGeometry(QRect(20, 36, 491, 251))
        self.groupBox_5.setCheckable(True)
        self.groupBox_5.setChecked(False)
        self.groupBox_6 = QGroupBox(self.groupBox_5)
        self.groupBox_6.setObjectName(u"groupBox_6")
        self.groupBox_6.setGeometry(QRect(10, 29, 223, 128))
        self.formLayout_7 = QFormLayout(self.groupBox_6)
        self.formLayout_7.setObjectName(u"formLayout_7")
        self.label_5 = QLabel(self.groupBox_6)
        self.label_5.setObjectName(u"label_5")

        self.formLayout_7.setWidget(0, QFormLayout.LabelRole, self.label_5)

        self.spinBox = QSpinBox(self.groupBox_6)
        self.spinBox.setObjectName(u"spinBox")

        self.formLayout_7.setWidget(0, QFormLayout.FieldRole, self.spinBox)

        self.label_6 = QLabel(self.groupBox_6)
        self.label_6.setObjectName(u"label_6")

        self.formLayout_7.setWidget(1, QFormLayout.LabelRole, self.label_6)

        self.fontComboBox = QFontComboBox(self.groupBox_6)
        self.fontComboBox.setObjectName(u"fontComboBox")

        self.formLayout_7.setWidget(1, QFormLayout.FieldRole, self.fontComboBox)

        self.label_10 = QLabel(self.groupBox_6)
        self.label_10.setObjectName(u"label_10")

        self.formLayout_7.setWidget(2, QFormLayout.LabelRole, self.label_10)

        self.pushButton_4 = QPushButton(self.groupBox_6)
        self.pushButton_4.setObjectName(u"pushButton_4")

        self.formLayout_7.setWidget(2, QFormLayout.FieldRole, self.pushButton_4)

        self.groupBox_7 = QGroupBox(self.groupBox_5)
        self.groupBox_7.setObjectName(u"groupBox_7")
        self.groupBox_7.setGeometry(QRect(239, 29, 222, 128))
        self.formLayout_9 = QFormLayout(self.groupBox_7)
        self.formLayout_9.setObjectName(u"formLayout_9")
        self.label_14 = QLabel(self.groupBox_7)
        self.label_14.setObjectName(u"label_14")

        self.formLayout_9.setWidget(0, QFormLayout.LabelRole, self.label_14)

        self.spinBox_3 = QSpinBox(self.groupBox_7)
        self.spinBox_3.setObjectName(u"spinBox_3")

        self.formLayout_9.setWidget(0, QFormLayout.FieldRole, self.spinBox_3)

        self.label_15 = QLabel(self.groupBox_7)
        self.label_15.setObjectName(u"label_15")

        self.formLayout_9.setWidget(1, QFormLayout.LabelRole, self.label_15)

        self.fontComboBox_3 = QFontComboBox(self.groupBox_7)
        self.fontComboBox_3.setObjectName(u"fontComboBox_3")

        self.formLayout_9.setWidget(1, QFormLayout.FieldRole, self.fontComboBox_3)

        self.label_16 = QLabel(self.groupBox_7)
        self.label_16.setObjectName(u"label_16")

        self.formLayout_9.setWidget(2, QFormLayout.LabelRole, self.label_16)

        self.pushButton_6 = QPushButton(self.groupBox_7)
        self.pushButton_6.setObjectName(u"pushButton_6")

        self.formLayout_9.setWidget(2, QFormLayout.FieldRole, self.pushButton_6)

        self.label_17 = QLabel(self.groupBox_5)
        self.label_17.setObjectName(u"label_17")
        self.label_17.setGeometry(QRect(30, 180, 54, 16))
        self.horizontalSlider = QSlider(self.groupBox_5)
        self.horizontalSlider.setObjectName(u"horizontalSlider")
        self.horizontalSlider.setGeometry(QRect(100, 180, 160, 18))
        self.horizontalSlider.setOrientation(Qt.Horizontal)
        self.label_18 = QLabel(self.groupBox_5)
        self.label_18.setObjectName(u"label_18")
        self.label_18.setGeometry(QRect(30, 210, 54, 16))
        self.pushButton_7 = QPushButton(self.groupBox_5)
        self.pushButton_7.setObjectName(u"pushButton_7")
        self.pushButton_7.setGeometry(QRect(110, 200, 137, 28))
        self.tabWidget.addTab(self.tab_5, "")
        self.tab_4 = QWidget()
        self.tab_4.setObjectName(u"tab_4")
        self.tabWidget.addTab(self.tab_4, "")

        self.horizontalLayout_11.addWidget(self.tabWidget)

        MainWindow.setCentralWidget(self.centralwidget)
        self.statusbar = QStatusBar(MainWindow)
        self.statusbar.setObjectName(u"statusbar")
        MainWindow.setStatusBar(self.statusbar)

        self.retranslateUi(MainWindow)

        self.tabWidget.setCurrentIndex(0)
        self.comboBox_2.setCurrentIndex(3)


        QMetaObject.connectSlotsByName(MainWindow)
    # setupUi

    def retranslateUi(self, MainWindow):
        MainWindow.setWindowTitle(QCoreApplication.translate("MainWindow", u"MainWindow", None))
        self.groupBox.setTitle(QCoreApplication.translate("MainWindow", u"\u8bbe\u5907\u901a\u4fe1", None))
        self.label.setText(QCoreApplication.translate("MainWindow", u"\u4e32\u53e3:", None))
        self.label_2.setText(QCoreApplication.translate("MainWindow", u"\u6ce2\u7279\u7387:", None))
        self.comboBox_2.setItemText(0, QCoreApplication.translate("MainWindow", u"9600", None))
        self.comboBox_2.setItemText(1, QCoreApplication.translate("MainWindow", u"19200", None))
        self.comboBox_2.setItemText(2, QCoreApplication.translate("MainWindow", u"38400", None))
        self.comboBox_2.setItemText(3, QCoreApplication.translate("MainWindow", u"115200", None))

        self.pushButton.setText(QCoreApplication.translate("MainWindow", u"\u8fde\u63a5", None))
        self.pushButton_2.setText(QCoreApplication.translate("MainWindow", u"\u65ad\u5f00", None))
        self.autoReconnectCB.setText(QCoreApplication.translate("MainWindow", u"\u81ea\u52a8\u91cd\u8fde", None))
        self.groupBox_2.setTitle(QCoreApplication.translate("MainWindow", u"\u72b6\u6001\u63a7\u5236", None))
        self.groupBox_4.setTitle(QCoreApplication.translate("MainWindow", u"\u7535\u538b", None))
#if QT_CONFIG(tooltip)
        self.label_3.setToolTip(QCoreApplication.translate("MainWindow", u"\u5f53\u524d\u7535\u538b", None))
#endif // QT_CONFIG(tooltip)
        self.label_3.setText(QCoreApplication.translate("MainWindow", u"12.00 V", None))
        self.groupBox_3.setTitle(QCoreApplication.translate("MainWindow", u"\u7535\u6d41", None))
#if QT_CONFIG(tooltip)
        self.label_4.setToolTip(QCoreApplication.translate("MainWindow", u"\u5f53\u524d\u7535\u6d41", None))
#endif // QT_CONFIG(tooltip)
        self.label_4.setText(QCoreApplication.translate("MainWindow", u"0.00 A", None))
        self.groupBox1.setTitle(QCoreApplication.translate("MainWindow", u"\u8f93\u51fa\u7535\u538b", None))
        self.doubleSpinBox.setSuffix(QCoreApplication.translate("MainWindow", u"V", None))
        self.groupBox2.setTitle(QCoreApplication.translate("MainWindow", u"\u8f93\u51fa\u5f00\u5173", None))
        self.pushButton_3.setText(QCoreApplication.translate("MainWindow", u"PushButton", None))
        self.label_9.setText(QCoreApplication.translate("MainWindow", u"\u6700\u5927\u8f93\u51fa\u7535\u6d41:", None))
        self.doubleSpinBox_3.setSuffix(QCoreApplication.translate("MainWindow", u"A", None))
        self.label_8.setText(QCoreApplication.translate("MainWindow", u"\u6700\u5927\u8f93\u51fa\u7535\u538b:", None))
        self.doubleSpinBox_2.setSuffix(QCoreApplication.translate("MainWindow", u"V", None))
        self.label_7.setText(QCoreApplication.translate("MainWindow", u"\u8bbe\u5907\u4fe1\u606f:", None))
        self.checkBox.setText(QCoreApplication.translate("MainWindow", u"\u63a7\u5236\u4f7f\u80fd", None))
        self.tabWidget.setTabText(self.tabWidget.indexOf(self.tab), QCoreApplication.translate("MainWindow", u"\u63a7\u5236\u9762\u677f", None))
        self.tabWidget.setTabText(self.tabWidget.indexOf(self.tab_2), QCoreApplication.translate("MainWindow", u"\u5ba2\u6237\u7aef", None))
        self.tabWidget.setTabText(self.tabWidget.indexOf(self.tab_3), QCoreApplication.translate("MainWindow", u"\u6ce2\u5f62", None))
        self.groupBox_5.setTitle(QCoreApplication.translate("MainWindow", u"\u4f20\u7edf\u60ac\u6d6e\u7a97", None))
        self.groupBox_6.setTitle(QCoreApplication.translate("MainWindow", u"\u7535\u538b", None))
        self.label_5.setText(QCoreApplication.translate("MainWindow", u"\u5b57\u4f53\u5927\u5c0f", None))
        self.label_6.setText(QCoreApplication.translate("MainWindow", u"\u5b57\u4f53", None))
        self.label_10.setText(QCoreApplication.translate("MainWindow", u"\u5b57\u4f53\u989c\u8272", None))
        self.pushButton_4.setText(QCoreApplication.translate("MainWindow", u"\u989c\u8272", None))
        self.groupBox_7.setTitle(QCoreApplication.translate("MainWindow", u"\u7535\u6d41", None))
        self.label_14.setText(QCoreApplication.translate("MainWindow", u"\u5b57\u4f53\u5927\u5c0f", None))
        self.label_15.setText(QCoreApplication.translate("MainWindow", u"\u5b57\u4f53", None))
        self.label_16.setText(QCoreApplication.translate("MainWindow", u"\u5b57\u4f53\u989c\u8272", None))
        self.pushButton_6.setText(QCoreApplication.translate("MainWindow", u"\u989c\u8272", None))
        self.label_17.setText(QCoreApplication.translate("MainWindow", u"\u900f\u660e\u5ea6", None))
        self.label_18.setText(QCoreApplication.translate("MainWindow", u"\u80cc\u666f\u989c\u8272", None))
        self.pushButton_7.setText(QCoreApplication.translate("MainWindow", u"\u989c\u8272", None))
        self.tabWidget.setTabText(self.tabWidget.indexOf(self.tab_5), QCoreApplication.translate("MainWindow", u"\u60ac\u6d6e\u7a97", None))
        self.tabWidget.setTabText(self.tabWidget.indexOf(self.tab_4), QCoreApplication.translate("MainWindow", u"\u5173\u4e8e", None))
    # retranslateUi

