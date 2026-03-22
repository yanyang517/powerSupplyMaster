# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'mainWindowQIDXtX.ui'
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
from PySide6.QtWidgets import (QAbstractSpinBox, QApplication, QCheckBox, QComboBox,
    QDial, QDoubleSpinBox, QFormLayout, QFrame,
    QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QMainWindow, QPushButton, QSizePolicy, QSpacerItem,
    QSpinBox, QStatusBar, QTabWidget, QVBoxLayout,
    QWidget)

class Ui_MainWindow(object):
    def setupUi(self, MainWindow):
        if not MainWindow.objectName():
            MainWindow.setObjectName(u"MainWindow")
        MainWindow.resize(597, 592)
        font = QFont()
        font.setPointSize(11)
        MainWindow.setFont(font)
        self.centralwidget = QWidget(MainWindow)
        self.centralwidget.setObjectName(u"centralwidget")
        self.verticalLayout_6 = QVBoxLayout(self.centralwidget)
        self.verticalLayout_6.setObjectName(u"verticalLayout_6")
        self.tabWidget = QTabWidget(self.centralwidget)
        self.tabWidget.setObjectName(u"tabWidget")
        self.tabWidget.setTabPosition(QTabWidget.North)
        self.tabWidget.setTabShape(QTabWidget.Triangular)
        self.tab_control = QWidget()
        self.tab_control.setObjectName(u"tab_control")
        self.verticalLayout_5 = QVBoxLayout(self.tab_control)
        self.verticalLayout_5.setObjectName(u"verticalLayout_5")
        self.groupBox = QGroupBox(self.tab_control)
        self.groupBox.setObjectName(u"groupBox")
        self.horizontalLayout = QHBoxLayout(self.groupBox)
        self.horizontalLayout.setObjectName(u"horizontalLayout")
        self.formLayout_2 = QFormLayout()
        self.formLayout_2.setObjectName(u"formLayout_2")
        self.label = QLabel(self.groupBox)
        self.label.setObjectName(u"label")

        self.formLayout_2.setWidget(0, QFormLayout.LabelRole, self.label)

        self.com_num_comboBox = QComboBox(self.groupBox)
        self.com_num_comboBox.setObjectName(u"com_num_comboBox")

        self.formLayout_2.setWidget(0, QFormLayout.FieldRole, self.com_num_comboBox)


        self.horizontalLayout.addLayout(self.formLayout_2)

        self.formLayout = QFormLayout()
        self.formLayout.setObjectName(u"formLayout")
        self.label_2 = QLabel(self.groupBox)
        self.label_2.setObjectName(u"label_2")

        self.formLayout.setWidget(0, QFormLayout.LabelRole, self.label_2)

        self.baudrate_comboBox = QComboBox(self.groupBox)
        self.baudrate_comboBox.addItem("")
        self.baudrate_comboBox.addItem("")
        self.baudrate_comboBox.addItem("")
        self.baudrate_comboBox.addItem("")
        self.baudrate_comboBox.setObjectName(u"baudrate_comboBox")

        self.formLayout.setWidget(0, QFormLayout.FieldRole, self.baudrate_comboBox)


        self.horizontalLayout.addLayout(self.formLayout)

        self.connect_Btn = QPushButton(self.groupBox)
        self.connect_Btn.setObjectName(u"connect_Btn")
        self.connect_Btn.setCheckable(False)
        self.connect_Btn.setAutoExclusive(False)

        self.horizontalLayout.addWidget(self.connect_Btn)

        self.disconnect_Btn = QPushButton(self.groupBox)
        self.disconnect_Btn.setObjectName(u"disconnect_Btn")
        self.disconnect_Btn.setCheckable(False)
        self.disconnect_Btn.setAutoExclusive(False)

        self.horizontalLayout.addWidget(self.disconnect_Btn)

        self.auto_reconnect_CB = QCheckBox(self.groupBox)
        self.auto_reconnect_CB.setObjectName(u"auto_reconnect_CB")

        self.horizontalLayout.addWidget(self.auto_reconnect_CB)

        self.horizontalLayout.setStretch(0, 2)
        self.horizontalLayout.setStretch(1, 2)
        self.horizontalLayout.setStretch(2, 1)
        self.horizontalLayout.setStretch(3, 1)

        self.verticalLayout_5.addWidget(self.groupBox)

        self.groupBox_2 = QGroupBox(self.tab_control)
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
        self.horizontalLayout_8.setContentsMargins(-1, -1, 25, 9)
        self.volatage_label = QLabel(self.groupBox_4)
        self.volatage_label.setObjectName(u"volatage_label")
        font1 = QFont()
        font1.setPointSize(36)
        self.volatage_label.setFont(font1)
        self.volatage_label.setFrameShape(QFrame.NoFrame)
        self.volatage_label.setAlignment(Qt.AlignRight|Qt.AlignTrailing|Qt.AlignVCenter)

        self.horizontalLayout_8.addWidget(self.volatage_label)


        self.horizontalLayout_3.addWidget(self.groupBox_4)

        self.groupBox_3 = QGroupBox(self.groupBox_2)
        self.groupBox_3.setObjectName(u"groupBox_3")
        self.horizontalLayout_7 = QHBoxLayout(self.groupBox_3)
        self.horizontalLayout_7.setObjectName(u"horizontalLayout_7")
        self.horizontalLayout_7.setContentsMargins(-1, -1, 25, -1)
        self.current_label = QLabel(self.groupBox_3)
        self.current_label.setObjectName(u"current_label")
        self.current_label.setFont(font1)
        self.current_label.setFrameShape(QFrame.NoFrame)
        self.current_label.setAlignment(Qt.AlignRight|Qt.AlignTrailing|Qt.AlignVCenter)

        self.horizontalLayout_7.addWidget(self.current_label)


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

        self.voltage_spinBox = QDoubleSpinBox(self.groupBox1)
        self.voltage_spinBox.setObjectName(u"voltage_spinBox")
        self.voltage_spinBox.setSingleStep(0.100000000000000)
        self.voltage_spinBox.setStepType(QAbstractSpinBox.DefaultStepType)

        self.horizontalLayout_2.addWidget(self.voltage_spinBox)


        self.verticalLayout_2.addLayout(self.horizontalLayout_2)

        self.voltage_dial = QDial(self.groupBox1)
        self.voltage_dial.setObjectName(u"voltage_dial")
        self.voltage_dial.setNotchesVisible(False)

        self.verticalLayout_2.addWidget(self.voltage_dial)


        self.horizontalLayout_4.addWidget(self.groupBox1)

        self.groupBox2 = QGroupBox(self.groupBox_2)
        self.groupBox2.setObjectName(u"groupBox2")
        self.verticalLayout_3 = QVBoxLayout(self.groupBox2)
        self.verticalLayout_3.setObjectName(u"verticalLayout_3")
        self.ouput_ctrl_Btn = QPushButton(self.groupBox2)
        self.ouput_ctrl_Btn.setObjectName(u"ouput_ctrl_Btn")
        self.ouput_ctrl_Btn.setCheckable(True)

        self.verticalLayout_3.addWidget(self.ouput_ctrl_Btn)


        self.horizontalLayout_4.addWidget(self.groupBox2)


        self.verticalLayout_4.addLayout(self.horizontalLayout_4)

        self.horizontalLayout_5 = QHBoxLayout()
        self.horizontalLayout_5.setObjectName(u"horizontalLayout_5")
        self.formLayout_4 = QFormLayout()
        self.formLayout_4.setObjectName(u"formLayout_4")
        self.label_9 = QLabel(self.groupBox_2)
        self.label_9.setObjectName(u"label_9")

        self.formLayout_4.setWidget(0, QFormLayout.LabelRole, self.label_9)

        self.max_voltage_spinbox = QDoubleSpinBox(self.groupBox_2)
        self.max_voltage_spinbox.setObjectName(u"max_voltage_spinbox")
        self.max_voltage_spinbox.setSingleStep(0.100000000000000)

        self.formLayout_4.setWidget(0, QFormLayout.FieldRole, self.max_voltage_spinbox)


        self.horizontalLayout_5.addLayout(self.formLayout_4)

        self.formLayout_3 = QFormLayout()
        self.formLayout_3.setObjectName(u"formLayout_3")
        self.label_8 = QLabel(self.groupBox_2)
        self.label_8.setObjectName(u"label_8")

        self.formLayout_3.setWidget(0, QFormLayout.LabelRole, self.label_8)

        self.max_current_spinBox = QDoubleSpinBox(self.groupBox_2)
        self.max_current_spinBox.setObjectName(u"max_current_spinBox")
        self.max_current_spinBox.setSingleStep(0.100000000000000)

        self.formLayout_3.setWidget(0, QFormLayout.FieldRole, self.max_current_spinBox)


        self.horizontalLayout_5.addLayout(self.formLayout_3)


        self.verticalLayout_4.addLayout(self.horizontalLayout_5)

        self.horizontalLayout_6 = QHBoxLayout()
        self.horizontalLayout_6.setObjectName(u"horizontalLayout_6")
        self.formLayout_6 = QFormLayout()
        self.formLayout_6.setObjectName(u"formLayout_6")
        self.label_7 = QLabel(self.groupBox_2)
        self.label_7.setObjectName(u"label_7")

        self.formLayout_6.setWidget(0, QFormLayout.LabelRole, self.label_7)

        self.device_info_lineEdit = QLineEdit(self.groupBox_2)
        self.device_info_lineEdit.setObjectName(u"device_info_lineEdit")
        sizePolicy = QSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.device_info_lineEdit.sizePolicy().hasHeightForWidth())
        self.device_info_lineEdit.setSizePolicy(sizePolicy)
        self.device_info_lineEdit.setReadOnly(True)

        self.formLayout_6.setWidget(0, QFormLayout.FieldRole, self.device_info_lineEdit)


        self.horizontalLayout_6.addLayout(self.formLayout_6)

        self.ctrl_enable_CB = QCheckBox(self.groupBox_2)
        self.ctrl_enable_CB.setObjectName(u"ctrl_enable_CB")
        self.ctrl_enable_CB.setChecked(True)

        self.horizontalLayout_6.addWidget(self.ctrl_enable_CB)


        self.verticalLayout_4.addLayout(self.horizontalLayout_6)

        self.verticalLayout_4.setStretch(0, 1)
        self.verticalLayout_4.setStretch(1, 2)

        self.verticalLayout_5.addWidget(self.groupBox_2)

        self.verticalLayout_5.setStretch(1, 1)
        self.tabWidget.addTab(self.tab_control, "")
        self.tab_wave = QWidget()
        self.tab_wave.setObjectName(u"tab_wave")
        self.verticalLayout_7 = QVBoxLayout(self.tab_wave)
        self.verticalLayout_7.setObjectName(u"verticalLayout_7")
        self.groupBox_8 = QGroupBox(self.tab_wave)
        self.groupBox_8.setObjectName(u"groupBox_8")
        self.groupBox_8.setCheckable(True)
        self.groupBox_8.setChecked(False)

        self.verticalLayout_7.addWidget(self.groupBox_8)

        self.tabWidget.addTab(self.tab_wave, "")
        self.tab_client = QWidget()
        self.tab_client.setObjectName(u"tab_client")
        self.groupBox_9 = QGroupBox(self.tab_client)
        self.groupBox_9.setObjectName(u"groupBox_9")
        self.groupBox_9.setGeometry(QRect(80, 190, 371, 141))
        self.groupBox_10 = QGroupBox(self.tab_client)
        self.groupBox_10.setObjectName(u"groupBox_10")
        self.groupBox_10.setGeometry(QRect(110, 50, 311, 80))
        self.tabWidget.addTab(self.tab_client, "")
        self.tab_floating = QWidget()
        self.tab_floating.setObjectName(u"tab_floating")
        self.verticalLayout_8 = QVBoxLayout(self.tab_floating)
        self.verticalLayout_8.setObjectName(u"verticalLayout_8")
        self.groupBox_5 = QGroupBox(self.tab_floating)
        self.groupBox_5.setObjectName(u"groupBox_5")
        self.groupBox_5.setCheckable(True)
        self.groupBox_5.setChecked(False)
        self.verticalLayout_9 = QVBoxLayout(self.groupBox_5)
        self.verticalLayout_9.setObjectName(u"verticalLayout_9")
        self.horizontalLayout_9 = QHBoxLayout()
        self.horizontalLayout_9.setObjectName(u"horizontalLayout_9")
        self.groupBox_6 = QGroupBox(self.groupBox_5)
        self.groupBox_6.setObjectName(u"groupBox_6")
        self.formLayout_7 = QFormLayout(self.groupBox_6)
        self.formLayout_7.setObjectName(u"formLayout_7")
        self.label_6 = QLabel(self.groupBox_6)
        self.label_6.setObjectName(u"label_6")

        self.formLayout_7.setWidget(0, QFormLayout.LabelRole, self.label_6)

        self.label_10 = QLabel(self.groupBox_6)
        self.label_10.setObjectName(u"label_10")

        self.formLayout_7.setWidget(1, QFormLayout.LabelRole, self.label_10)

        self.pushButton_4 = QPushButton(self.groupBox_6)
        self.pushButton_4.setObjectName(u"pushButton_4")

        self.formLayout_7.setWidget(1, QFormLayout.FieldRole, self.pushButton_4)

        self.pushButton_8 = QPushButton(self.groupBox_6)
        self.pushButton_8.setObjectName(u"pushButton_8")

        self.formLayout_7.setWidget(0, QFormLayout.FieldRole, self.pushButton_8)


        self.horizontalLayout_9.addWidget(self.groupBox_6)

        self.groupBox_7 = QGroupBox(self.groupBox_5)
        self.groupBox_7.setObjectName(u"groupBox_7")
        self.formLayout_9 = QFormLayout(self.groupBox_7)
        self.formLayout_9.setObjectName(u"formLayout_9")
        self.label_15 = QLabel(self.groupBox_7)
        self.label_15.setObjectName(u"label_15")

        self.formLayout_9.setWidget(0, QFormLayout.LabelRole, self.label_15)

        self.label_16 = QLabel(self.groupBox_7)
        self.label_16.setObjectName(u"label_16")

        self.formLayout_9.setWidget(1, QFormLayout.LabelRole, self.label_16)

        self.pushButton_6 = QPushButton(self.groupBox_7)
        self.pushButton_6.setObjectName(u"pushButton_6")

        self.formLayout_9.setWidget(1, QFormLayout.FieldRole, self.pushButton_6)

        self.pushButton_5 = QPushButton(self.groupBox_7)
        self.pushButton_5.setObjectName(u"pushButton_5")

        self.formLayout_9.setWidget(0, QFormLayout.FieldRole, self.pushButton_5)


        self.horizontalLayout_9.addWidget(self.groupBox_7)


        self.verticalLayout_9.addLayout(self.horizontalLayout_9)

        self.horizontalLayout_10 = QHBoxLayout()
        self.horizontalLayout_10.setObjectName(u"horizontalLayout_10")
        self.horizontalLayout_10.setContentsMargins(10, -1, -1, -1)
        self.verticalLayout = QVBoxLayout()
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.formLayout_8 = QFormLayout()
        self.formLayout_8.setObjectName(u"formLayout_8")
        self.label_17 = QLabel(self.groupBox_5)
        self.label_17.setObjectName(u"label_17")

        self.formLayout_8.setWidget(0, QFormLayout.LabelRole, self.label_17)

        self.spinBox = QSpinBox(self.groupBox_5)
        self.spinBox.setObjectName(u"spinBox")
        self.spinBox.setAlignment(Qt.AlignRight|Qt.AlignTrailing|Qt.AlignVCenter)
        self.spinBox.setMaximum(100)
        self.spinBox.setStepType(QAbstractSpinBox.DefaultStepType)
        self.spinBox.setValue(10)

        self.formLayout_8.setWidget(0, QFormLayout.FieldRole, self.spinBox)


        self.verticalLayout.addLayout(self.formLayout_8)

        self.formLayout_5 = QFormLayout()
        self.formLayout_5.setObjectName(u"formLayout_5")
        self.label_18 = QLabel(self.groupBox_5)
        self.label_18.setObjectName(u"label_18")

        self.formLayout_5.setWidget(0, QFormLayout.LabelRole, self.label_18)

        self.pushButton_7 = QPushButton(self.groupBox_5)
        self.pushButton_7.setObjectName(u"pushButton_7")

        self.formLayout_5.setWidget(0, QFormLayout.FieldRole, self.pushButton_7)


        self.verticalLayout.addLayout(self.formLayout_5)


        self.horizontalLayout_10.addLayout(self.verticalLayout)

        self.horizontalSpacer_3 = QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum)

        self.horizontalLayout_10.addItem(self.horizontalSpacer_3)

        self.horizontalLayout_10.setStretch(0, 2)
        self.horizontalLayout_10.setStretch(1, 3)

        self.verticalLayout_9.addLayout(self.horizontalLayout_10)


        self.verticalLayout_8.addWidget(self.groupBox_5)

        self.verticalSpacer = QSpacerItem(20, 40, QSizePolicy.Minimum, QSizePolicy.Expanding)

        self.verticalLayout_8.addItem(self.verticalSpacer)

        self.tabWidget.addTab(self.tab_floating, "")
        self.tab_about = QWidget()
        self.tab_about.setObjectName(u"tab_about")
        self.tabWidget.addTab(self.tab_about, "")

        self.verticalLayout_6.addWidget(self.tabWidget)

        MainWindow.setCentralWidget(self.centralwidget)
        self.statusbar = QStatusBar(MainWindow)
        self.statusbar.setObjectName(u"statusbar")
        MainWindow.setStatusBar(self.statusbar)

        self.retranslateUi(MainWindow)

        self.tabWidget.setCurrentIndex(0)
        self.baudrate_comboBox.setCurrentIndex(3)


        QMetaObject.connectSlotsByName(MainWindow)
    # setupUi

    def retranslateUi(self, MainWindow):
        MainWindow.setWindowTitle(QCoreApplication.translate("MainWindow", u"MainWindow", None))
        self.groupBox.setTitle(QCoreApplication.translate("MainWindow", u"\u8bbe\u5907\u901a\u4fe1", None))
        self.label.setText(QCoreApplication.translate("MainWindow", u"\u4e32\u53e3:", None))
        self.label_2.setText(QCoreApplication.translate("MainWindow", u"\u6ce2\u7279\u7387:", None))
        self.baudrate_comboBox.setItemText(0, QCoreApplication.translate("MainWindow", u"9600", None))
        self.baudrate_comboBox.setItemText(1, QCoreApplication.translate("MainWindow", u"19200", None))
        self.baudrate_comboBox.setItemText(2, QCoreApplication.translate("MainWindow", u"38400", None))
        self.baudrate_comboBox.setItemText(3, QCoreApplication.translate("MainWindow", u"115200", None))

        self.connect_Btn.setText(QCoreApplication.translate("MainWindow", u"\u8fde\u63a5", None))
        self.disconnect_Btn.setText(QCoreApplication.translate("MainWindow", u"\u65ad\u5f00", None))
        self.auto_reconnect_CB.setText(QCoreApplication.translate("MainWindow", u"\u81ea\u52a8\u91cd\u8fde", None))
        self.groupBox_2.setTitle(QCoreApplication.translate("MainWindow", u"\u72b6\u6001\u63a7\u5236", None))
        self.groupBox_4.setTitle(QCoreApplication.translate("MainWindow", u"\u7535\u538b", None))
#if QT_CONFIG(tooltip)
        self.volatage_label.setToolTip(QCoreApplication.translate("MainWindow", u"\u5f53\u524d\u7535\u538b", None))
#endif // QT_CONFIG(tooltip)
        self.volatage_label.setText(QCoreApplication.translate("MainWindow", u"12.00 V", None))
        self.groupBox_3.setTitle(QCoreApplication.translate("MainWindow", u"\u7535\u6d41", None))
#if QT_CONFIG(tooltip)
        self.current_label.setToolTip(QCoreApplication.translate("MainWindow", u"\u5f53\u524d\u7535\u6d41", None))
#endif // QT_CONFIG(tooltip)
        self.current_label.setText(QCoreApplication.translate("MainWindow", u"0.00 A", None))
        self.groupBox1.setTitle(QCoreApplication.translate("MainWindow", u"\u8f93\u51fa\u7535\u538b", None))
        self.voltage_spinBox.setSuffix(QCoreApplication.translate("MainWindow", u"V", None))
        self.groupBox2.setTitle(QCoreApplication.translate("MainWindow", u"\u8f93\u51fa\u5f00\u5173", None))
        self.ouput_ctrl_Btn.setText(QCoreApplication.translate("MainWindow", u"PushButton", None))
        self.label_9.setText(QCoreApplication.translate("MainWindow", u"\u6700\u5927\u8f93\u51fa\u7535\u538b:", None))
        self.max_voltage_spinbox.setSuffix(QCoreApplication.translate("MainWindow", u"V", None))
        self.label_8.setText(QCoreApplication.translate("MainWindow", u"\u6700\u5927\u8f93\u51fa\u7535\u6d41:", None))
        self.max_current_spinBox.setSuffix(QCoreApplication.translate("MainWindow", u"A", None))
        self.label_7.setText(QCoreApplication.translate("MainWindow", u"\u8bbe\u5907\u4fe1\u606f:", None))
        self.ctrl_enable_CB.setText(QCoreApplication.translate("MainWindow", u"\u63a7\u5236\u4f7f\u80fd", None))
        self.tabWidget.setTabText(self.tabWidget.indexOf(self.tab_control), QCoreApplication.translate("MainWindow", u"\u63a7\u5236\u9762\u677f", None))
        self.groupBox_8.setTitle(QCoreApplication.translate("MainWindow", u"\u663e\u793a\u6ce2\u5f62", None))
        self.tabWidget.setTabText(self.tabWidget.indexOf(self.tab_wave), QCoreApplication.translate("MainWindow", u"\u6ce2\u5f62", None))
        self.groupBox_9.setTitle(QCoreApplication.translate("MainWindow", u"\u5728\u7ebf\u7684\u5ba2\u6237\u7aef", None))
        self.groupBox_10.setTitle(QCoreApplication.translate("MainWindow", u"\u5ba2\u6237\u7aef\u7ba1\u7406", None))
        self.tabWidget.setTabText(self.tabWidget.indexOf(self.tab_client), QCoreApplication.translate("MainWindow", u"\u5ba2\u6237\u7aef", None))
        self.groupBox_5.setTitle(QCoreApplication.translate("MainWindow", u"\u4f20\u7edf\u60ac\u6d6e\u7a97", None))
        self.groupBox_6.setTitle(QCoreApplication.translate("MainWindow", u"\u7535\u538b", None))
        self.label_6.setText(QCoreApplication.translate("MainWindow", u"\u5b57\u4f53\u8bbe\u7f6e", None))
        self.label_10.setText(QCoreApplication.translate("MainWindow", u"\u989c\u8272\u8bbe\u7f6e", None))
        self.pushButton_4.setText(QCoreApplication.translate("MainWindow", u"\u989c\u8272", None))
        self.pushButton_8.setText(QCoreApplication.translate("MainWindow", u"\u5b57\u4f53", None))
        self.groupBox_7.setTitle(QCoreApplication.translate("MainWindow", u"\u7535\u6d41", None))
        self.label_15.setText(QCoreApplication.translate("MainWindow", u"\u5b57\u4f53\u8bbe\u7f6e", None))
        self.label_16.setText(QCoreApplication.translate("MainWindow", u"\u989c\u8272\u8bbe\u7f6e", None))
        self.pushButton_6.setText(QCoreApplication.translate("MainWindow", u"\u989c\u8272", None))
        self.pushButton_5.setText(QCoreApplication.translate("MainWindow", u"\u5b57\u4f53", None))
        self.label_17.setText(QCoreApplication.translate("MainWindow", u"\u900f\u660e\u5ea6   ", None))
        self.spinBox.setSuffix(QCoreApplication.translate("MainWindow", u"%", None))
        self.label_18.setText(QCoreApplication.translate("MainWindow", u"\u80cc\u666f\u989c\u8272", None))
        self.pushButton_7.setText(QCoreApplication.translate("MainWindow", u"\u989c\u8272", None))
        self.tabWidget.setTabText(self.tabWidget.indexOf(self.tab_floating), QCoreApplication.translate("MainWindow", u"\u60ac\u6d6e\u7a97", None))
        self.tabWidget.setTabText(self.tabWidget.indexOf(self.tab_about), QCoreApplication.translate("MainWindow", u"\u5173\u4e8e", None))
    # retranslateUi

