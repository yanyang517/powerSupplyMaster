# -*- coding: utf-8 -*-
"""主窗口界面构建代码（手工维护）。

控件 objectName 同时是 MainWindow、Presenter 和测试的公共契约；增删或改名时，
必须同步检查这些引用。界面不再由 Qt Designer 或 uic 生成。
"""

from PySide6.QtCore import QCoreApplication, QMetaObject, QRect, QSize, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QCheckBox,
    QComboBox,
    QDial,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QSpinBox,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)


class Ui_MainWindow:
    """构建主窗口的基础控件与布局，业务控件由 MainWindow 继续挂载。"""

    def setupUi(self, MainWindow):
        if not MainWindow.objectName():
            MainWindow.setObjectName("MainWindow")
        MainWindow.resize(591, 622)
        font = QFont()
        font.setPointSize(11)
        MainWindow.setFont(font)

        self.centralwidget = QWidget(MainWindow)
        self.centralwidget.setObjectName("centralwidget")
        self.verticalLayout_6 = QVBoxLayout(self.centralwidget)
        self.verticalLayout_6.setObjectName("verticalLayout_6")

        self.tabWidget = QTabWidget(self.centralwidget)
        self.tabWidget.setObjectName("tabWidget")
        self.tabWidget.setTabPosition(QTabWidget.TabPosition.North)
        self.tabWidget.setTabShape(QTabWidget.TabShape.Triangular)

        self._build_control_tab()
        self._build_wave_tab()
        self._build_client_tab()
        self._build_floating_tab()
        self._build_about_tab()

        self.verticalLayout_6.addWidget(self.tabWidget)
        MainWindow.setCentralWidget(self.centralwidget)

        self.statusbar = QStatusBar(MainWindow)
        self.statusbar.setObjectName("statusbar")
        MainWindow.setStatusBar(self.statusbar)

        self.retranslateUi(MainWindow)
        self.tabWidget.setCurrentIndex(0)
        self.baudrate_comboBox.setCurrentIndex(3)
        QMetaObject.connectSlotsByName(MainWindow)

    def _build_control_tab(self):
        self.tab_control = QWidget()
        self.tab_control.setObjectName("tab_control")
        self.verticalLayout_5 = QVBoxLayout(self.tab_control)
        self.verticalLayout_5.setObjectName("verticalLayout_5")

        self.groupBox = QGroupBox(self.tab_control)
        self.groupBox.setObjectName("groupBox")
        self.horizontalLayout = QHBoxLayout(self.groupBox)
        self.horizontalLayout.setObjectName("horizontalLayout")

        self.formLayout_2 = QFormLayout()
        self.formLayout_2.setObjectName("formLayout_2")
        self.label = QLabel(self.groupBox)
        self.label.setObjectName("label")
        self.formLayout_2.setWidget(0, QFormLayout.ItemRole.LabelRole, self.label)
        self.com_num_comboBox = QComboBox(self.groupBox)
        self.com_num_comboBox.setObjectName("com_num_comboBox")
        self.formLayout_2.setWidget(0, QFormLayout.ItemRole.FieldRole, self.com_num_comboBox)
        self.horizontalLayout.addLayout(self.formLayout_2)

        self.formLayout = QFormLayout()
        self.formLayout.setObjectName("formLayout")
        self.label_2 = QLabel(self.groupBox)
        self.label_2.setObjectName("label_2")
        self.formLayout.setWidget(0, QFormLayout.ItemRole.LabelRole, self.label_2)
        self.baudrate_comboBox = QComboBox(self.groupBox)
        self.baudrate_comboBox.addItems(["9600", "19200", "38400", "115200"])
        self.baudrate_comboBox.setObjectName("baudrate_comboBox")
        self.formLayout.setWidget(0, QFormLayout.ItemRole.FieldRole, self.baudrate_comboBox)
        self.horizontalLayout.addLayout(self.formLayout)

        self.connect_Btn = QPushButton(self.groupBox)
        self.connect_Btn.setObjectName("connect_Btn")
        self.connect_Btn.setCheckable(False)
        self.connect_Btn.setAutoExclusive(False)
        self.horizontalLayout.addWidget(self.connect_Btn)

        self.disconnect_Btn = QPushButton(self.groupBox)
        self.disconnect_Btn.setObjectName("disconnect_Btn")
        self.disconnect_Btn.setCheckable(False)
        self.disconnect_Btn.setAutoExclusive(False)
        self.horizontalLayout.addWidget(self.disconnect_Btn)

        self.auto_reconnect_CB = QCheckBox(self.groupBox)
        self.auto_reconnect_CB.setObjectName("auto_reconnect_CB")
        self.horizontalLayout.addWidget(self.auto_reconnect_CB)

        self.horizontalLayout.setStretch(0, 2)
        self.horizontalLayout.setStretch(1, 2)
        self.horizontalLayout.setStretch(2, 1)
        self.horizontalLayout.setStretch(3, 1)
        self.verticalLayout_5.addWidget(self.groupBox)

        self.groupBox_2 = QGroupBox(self.tab_control)
        self.groupBox_2.setObjectName("groupBox_2")
        self.verticalLayout_4 = QVBoxLayout(self.groupBox_2)
        self.verticalLayout_4.setObjectName("verticalLayout_4")

        self.horizontalLayout_3 = QHBoxLayout()
        self.horizontalLayout_3.setSpacing(9)
        self.horizontalLayout_3.setObjectName("horizontalLayout_3")
        self.horizontalLayout_3.setContentsMargins(9, 9, 9, 9)

        self.groupBox_4 = QGroupBox(self.groupBox_2)
        self.groupBox_4.setObjectName("groupBox_4")
        self.horizontalLayout_8 = QHBoxLayout(self.groupBox_4)
        self.horizontalLayout_8.setObjectName("horizontalLayout_8")
        self.horizontalLayout_8.setContentsMargins(-1, -1, 25, 9)
        self.volatage_label = QLabel(self.groupBox_4)
        self.volatage_label.setObjectName("volatage_label")
        readout_font = QFont()
        readout_font.setPointSize(36)
        self.volatage_label.setFont(readout_font)
        self.volatage_label.setFrameShape(QFrame.Shape.NoFrame)
        self.volatage_label.setAlignment(
            Qt.AlignmentFlag.AlignRight
            | Qt.AlignmentFlag.AlignTrailing
            | Qt.AlignmentFlag.AlignVCenter
        )
        self.horizontalLayout_8.addWidget(self.volatage_label)
        self.horizontalLayout_3.addWidget(self.groupBox_4)

        self.groupBox_3 = QGroupBox(self.groupBox_2)
        self.groupBox_3.setObjectName("groupBox_3")
        self.horizontalLayout_7 = QHBoxLayout(self.groupBox_3)
        self.horizontalLayout_7.setObjectName("horizontalLayout_7")
        self.horizontalLayout_7.setContentsMargins(-1, -1, 25, -1)
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
        self.horizontalLayout_3.addWidget(self.groupBox_3)
        self.verticalLayout_4.addLayout(self.horizontalLayout_3)

        self.horizontalLayout_4 = QHBoxLayout()
        self.horizontalLayout_4.setObjectName("horizontalLayout_4")

        self.groupBox1 = QGroupBox(self.groupBox_2)
        self.groupBox1.setObjectName("groupBox1")
        self.verticalLayout_2 = QVBoxLayout(self.groupBox1)
        self.verticalLayout_2.setObjectName("verticalLayout_2")
        self.horizontalLayout_2 = QHBoxLayout()
        self.horizontalLayout_2.setObjectName("horizontalLayout_2")
        self.horizontalSpacer = QSpacerItem(
            40, 20, QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum
        )
        self.horizontalLayout_2.addItem(self.horizontalSpacer)
        self.voltage_spinBox = QDoubleSpinBox(self.groupBox1)
        self.voltage_spinBox.setObjectName("voltage_spinBox")
        self.voltage_spinBox.setSingleStep(0.1)
        self.voltage_spinBox.setStepType(QAbstractSpinBox.StepType.DefaultStepType)
        self.voltage_spinBox.setValue(12.0)
        self.horizontalLayout_2.addWidget(self.voltage_spinBox)
        self.horizontalSpacer_5 = QSpacerItem(
            40, 20, QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum
        )
        self.horizontalLayout_2.addItem(self.horizontalSpacer_5)
        self.verticalLayout_2.addLayout(self.horizontalLayout_2)

        self.voltage_dial = QDial(self.groupBox1)
        self.voltage_dial.setObjectName("voltage_dial")
        self.voltage_dial.setMaximum(2000)
        self.voltage_dial.setValue(1200)
        self.voltage_dial.setNotchesVisible(False)
        self.verticalLayout_2.addWidget(self.voltage_dial)
        self.horizontalLayout_4.addWidget(self.groupBox1)

        self.groupBox2 = QGroupBox(self.groupBox_2)
        self.groupBox2.setObjectName("groupBox2")
        self.horizontalLayout_11 = QHBoxLayout(self.groupBox2)
        self.horizontalLayout_11.setObjectName("horizontalLayout_11")
        self.horizontalSpacer_2 = QSpacerItem(
            40, 20, QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum
        )
        self.horizontalLayout_11.addItem(self.horizontalSpacer_2)
        self.ouput_ctrl_Btn = QPushButton(self.groupBox2)
        self.ouput_ctrl_Btn.setObjectName("ouput_ctrl_Btn")
        size_policy = QSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
        size_policy.setHorizontalStretch(0)
        size_policy.setVerticalStretch(0)
        size_policy.setHeightForWidth(self.ouput_ctrl_Btn.sizePolicy().hasHeightForWidth())
        self.ouput_ctrl_Btn.setSizePolicy(size_policy)
        self.ouput_ctrl_Btn.setMinimumSize(QSize(100, 100))
        self.ouput_ctrl_Btn.setCheckable(True)
        self.horizontalLayout_11.addWidget(self.ouput_ctrl_Btn)
        self.horizontalSpacer_4 = QSpacerItem(
            40, 20, QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum
        )
        self.horizontalLayout_11.addItem(self.horizontalSpacer_4)
        self.horizontalLayout_4.addWidget(self.groupBox2)
        self.verticalLayout_4.addLayout(self.horizontalLayout_4)

        self.horizontalLayout_5 = QHBoxLayout()
        self.horizontalLayout_5.setObjectName("horizontalLayout_5")
        self.formLayout_4 = QFormLayout()
        self.formLayout_4.setObjectName("formLayout_4")
        self.label_9 = QLabel(self.groupBox_2)
        self.label_9.setObjectName("label_9")
        self.formLayout_4.setWidget(0, QFormLayout.ItemRole.LabelRole, self.label_9)
        self.max_voltage_spinbox = QDoubleSpinBox(self.groupBox_2)
        self.max_voltage_spinbox.setObjectName("max_voltage_spinbox")
        self.max_voltage_spinbox.setSingleStep(0.1)
        self.max_voltage_spinbox.setValue(20.0)
        self.formLayout_4.setWidget(0, QFormLayout.ItemRole.FieldRole, self.max_voltage_spinbox)
        self.horizontalLayout_5.addLayout(self.formLayout_4)

        self.formLayout_3 = QFormLayout()
        self.formLayout_3.setObjectName("formLayout_3")
        self.label_8 = QLabel(self.groupBox_2)
        self.label_8.setObjectName("label_8")
        self.formLayout_3.setWidget(0, QFormLayout.ItemRole.LabelRole, self.label_8)
        self.max_current_spinBox = QDoubleSpinBox(self.groupBox_2)
        self.max_current_spinBox.setObjectName("max_current_spinBox")
        self.max_current_spinBox.setSingleStep(0.1)
        self.max_current_spinBox.setValue(10.0)
        self.formLayout_3.setWidget(0, QFormLayout.ItemRole.FieldRole, self.max_current_spinBox)
        self.horizontalLayout_5.addLayout(self.formLayout_3)
        self.verticalLayout_4.addLayout(self.horizontalLayout_5)

        self.horizontalLayout_6 = QHBoxLayout()
        self.horizontalLayout_6.setObjectName("horizontalLayout_6")
        self.formLayout_6 = QFormLayout()
        self.formLayout_6.setObjectName("formLayout_6")
        self.label_7 = QLabel(self.groupBox_2)
        self.label_7.setObjectName("label_7")
        self.formLayout_6.setWidget(0, QFormLayout.ItemRole.LabelRole, self.label_7)
        self.device_info_lineEdit = QLineEdit(self.groupBox_2)
        self.device_info_lineEdit.setObjectName("device_info_lineEdit")
        size_policy = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        size_policy.setHorizontalStretch(0)
        size_policy.setVerticalStretch(0)
        size_policy.setHeightForWidth(
            self.device_info_lineEdit.sizePolicy().hasHeightForWidth()
        )
        self.device_info_lineEdit.setSizePolicy(size_policy)
        self.device_info_lineEdit.setReadOnly(True)
        self.formLayout_6.setWidget(0, QFormLayout.ItemRole.FieldRole, self.device_info_lineEdit)
        self.horizontalLayout_6.addLayout(self.formLayout_6)
        self.verticalLayout_4.addLayout(self.horizontalLayout_6)

        self.verticalLayout_4.setStretch(0, 1)
        self.verticalLayout_4.setStretch(1, 2)
        self.verticalLayout_5.addWidget(self.groupBox_2)
        self.verticalLayout_5.setStretch(1, 1)
        self.tabWidget.addTab(self.tab_control, "")

    def _build_wave_tab(self):
        self.tab_wave = QWidget()
        self.tab_wave.setObjectName("tab_wave")
        self.verticalLayout_7 = QVBoxLayout(self.tab_wave)
        self.verticalLayout_7.setObjectName("verticalLayout_7")
        self.groupBox_8 = QGroupBox(self.tab_wave)
        self.groupBox_8.setObjectName("groupBox_8")
        self.groupBox_8.setCheckable(True)
        self.groupBox_8.setChecked(False)
        self.verticalLayout_7.addWidget(self.groupBox_8)
        self.tabWidget.addTab(self.tab_wave, "")

    def _build_client_tab(self):
        self.tab_client = QWidget()
        self.tab_client.setObjectName("tab_client")
        self.groupBox_9 = QGroupBox(self.tab_client)
        self.groupBox_9.setObjectName("groupBox_9")
        self.groupBox_9.setGeometry(QRect(80, 190, 371, 141))
        self.groupBox_10 = QGroupBox(self.tab_client)
        self.groupBox_10.setObjectName("groupBox_10")
        self.groupBox_10.setGeometry(QRect(110, 50, 311, 80))
        self.tabWidget.addTab(self.tab_client, "")

    def _build_floating_tab(self):
        self.tab_floating = QWidget()
        self.tab_floating.setObjectName("tab_floating")
        self.verticalLayout_8 = QVBoxLayout(self.tab_floating)
        self.verticalLayout_8.setObjectName("verticalLayout_8")
        self.groupBox_5 = QGroupBox(self.tab_floating)
        self.groupBox_5.setObjectName("groupBox_5")
        self.groupBox_5.setCheckable(True)
        self.groupBox_5.setChecked(False)
        self.verticalLayout_9 = QVBoxLayout(self.groupBox_5)
        self.verticalLayout_9.setObjectName("verticalLayout_9")

        self.horizontalLayout_9 = QHBoxLayout()
        self.horizontalLayout_9.setObjectName("horizontalLayout_9")
        self.groupBox_6 = QGroupBox(self.groupBox_5)
        self.groupBox_6.setObjectName("groupBox_6")
        self.formLayout_7 = QFormLayout(self.groupBox_6)
        self.formLayout_7.setObjectName("formLayout_7")
        self.label_6 = QLabel(self.groupBox_6)
        self.label_6.setObjectName("label_6")
        self.formLayout_7.setWidget(0, QFormLayout.ItemRole.LabelRole, self.label_6)
        self.label_10 = QLabel(self.groupBox_6)
        self.label_10.setObjectName("label_10")
        self.formLayout_7.setWidget(1, QFormLayout.ItemRole.LabelRole, self.label_10)
        self.pushButton_4 = QPushButton(self.groupBox_6)
        self.pushButton_4.setObjectName("pushButton_4")
        self.formLayout_7.setWidget(1, QFormLayout.ItemRole.FieldRole, self.pushButton_4)
        self.pushButton_8 = QPushButton(self.groupBox_6)
        self.pushButton_8.setObjectName("pushButton_8")
        self.formLayout_7.setWidget(0, QFormLayout.ItemRole.FieldRole, self.pushButton_8)
        self.horizontalLayout_9.addWidget(self.groupBox_6)

        self.groupBox_7 = QGroupBox(self.groupBox_5)
        self.groupBox_7.setObjectName("groupBox_7")
        self.formLayout_9 = QFormLayout(self.groupBox_7)
        self.formLayout_9.setObjectName("formLayout_9")
        self.label_15 = QLabel(self.groupBox_7)
        self.label_15.setObjectName("label_15")
        self.formLayout_9.setWidget(0, QFormLayout.ItemRole.LabelRole, self.label_15)
        self.label_16 = QLabel(self.groupBox_7)
        self.label_16.setObjectName("label_16")
        self.formLayout_9.setWidget(1, QFormLayout.ItemRole.LabelRole, self.label_16)
        self.pushButton_6 = QPushButton(self.groupBox_7)
        self.pushButton_6.setObjectName("pushButton_6")
        self.formLayout_9.setWidget(1, QFormLayout.ItemRole.FieldRole, self.pushButton_6)
        self.pushButton_5 = QPushButton(self.groupBox_7)
        self.pushButton_5.setObjectName("pushButton_5")
        self.formLayout_9.setWidget(0, QFormLayout.ItemRole.FieldRole, self.pushButton_5)
        self.horizontalLayout_9.addWidget(self.groupBox_7)
        self.verticalLayout_9.addLayout(self.horizontalLayout_9)

        self.horizontalLayout_10 = QHBoxLayout()
        self.horizontalLayout_10.setObjectName("horizontalLayout_10")
        self.horizontalLayout_10.setContentsMargins(10, -1, -1, -1)
        self.verticalLayout = QVBoxLayout()
        self.verticalLayout.setObjectName("verticalLayout")
        self.formLayout_8 = QFormLayout()
        self.formLayout_8.setObjectName("formLayout_8")
        self.label_17 = QLabel(self.groupBox_5)
        self.label_17.setObjectName("label_17")
        self.formLayout_8.setWidget(0, QFormLayout.ItemRole.LabelRole, self.label_17)
        self.spinBox = QSpinBox(self.groupBox_5)
        self.spinBox.setObjectName("spinBox")
        self.spinBox.setAlignment(
            Qt.AlignmentFlag.AlignRight
            | Qt.AlignmentFlag.AlignTrailing
            | Qt.AlignmentFlag.AlignVCenter
        )
        self.spinBox.setMaximum(100)
        self.spinBox.setStepType(QAbstractSpinBox.StepType.DefaultStepType)
        self.spinBox.setValue(10)
        self.formLayout_8.setWidget(0, QFormLayout.ItemRole.FieldRole, self.spinBox)
        self.verticalLayout.addLayout(self.formLayout_8)

        self.formLayout_5 = QFormLayout()
        self.formLayout_5.setObjectName("formLayout_5")
        self.label_18 = QLabel(self.groupBox_5)
        self.label_18.setObjectName("label_18")
        self.formLayout_5.setWidget(0, QFormLayout.ItemRole.LabelRole, self.label_18)
        self.pushButton_7 = QPushButton(self.groupBox_5)
        self.pushButton_7.setObjectName("pushButton_7")
        self.formLayout_5.setWidget(0, QFormLayout.ItemRole.FieldRole, self.pushButton_7)
        self.verticalLayout.addLayout(self.formLayout_5)
        self.horizontalLayout_10.addLayout(self.verticalLayout)
        self.horizontalSpacer_3 = QSpacerItem(
            40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum
        )
        self.horizontalLayout_10.addItem(self.horizontalSpacer_3)
        self.horizontalLayout_10.setStretch(0, 2)
        self.horizontalLayout_10.setStretch(1, 3)
        self.verticalLayout_9.addLayout(self.horizontalLayout_10)
        self.verticalLayout_8.addWidget(self.groupBox_5)
        self.verticalSpacer = QSpacerItem(
            20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding
        )
        self.verticalLayout_8.addItem(self.verticalSpacer)
        self.tabWidget.addTab(self.tab_floating, "")

    def _build_about_tab(self):
        self.tab_about = QWidget()
        self.tab_about.setObjectName("tab_about")
        self.tabWidget.addTab(self.tab_about, "")

    def retranslateUi(self, MainWindow):
        translate = lambda text: QCoreApplication.translate("MainWindow", text, None)
        MainWindow.setWindowTitle(translate("MainWindow"))
        self.groupBox.setTitle(translate("设备通信"))
        self.label.setText(translate("串口:"))
        self.label_2.setText(translate("波特率:"))
        for index, text in enumerate(("9600", "19200", "38400", "115200")):
            self.baudrate_comboBox.setItemText(index, translate(text))
        self.connect_Btn.setText(translate("连接"))
        self.disconnect_Btn.setText(translate("断开"))
        self.auto_reconnect_CB.setText(translate("自动重连"))
        self.groupBox_2.setTitle(translate("状态控制"))
        self.groupBox_4.setTitle(translate("电压"))
        self.volatage_label.setToolTip(translate("当前电压"))
        self.volatage_label.setText(translate("12.00 V"))
        self.groupBox_3.setTitle(translate("电流"))
        self.current_label.setToolTip(translate("当前电流"))
        self.current_label.setText(translate("0.00 A"))
        self.groupBox1.setTitle(translate("输出电压"))
        self.voltage_spinBox.setSuffix(translate("V"))
        self.groupBox2.setTitle(translate("输出开关"))
        self.ouput_ctrl_Btn.setToolTip(translate("输出开关"))
        self.ouput_ctrl_Btn.setText(translate("开关"))
        self.label_9.setText(translate("最大输出电压:"))
        self.max_voltage_spinbox.setSuffix(translate("V"))
        self.label_8.setText(translate("最大输出电流:"))
        self.max_current_spinBox.setSuffix(translate("A"))
        self.label_7.setText(translate("设备信息:"))
        self.tabWidget.setTabText(
            self.tabWidget.indexOf(self.tab_control), translate("控制面板")
        )
        self.groupBox_8.setTitle(translate("显示波形"))
        self.tabWidget.setTabText(self.tabWidget.indexOf(self.tab_wave), translate("波形"))
        self.groupBox_9.setTitle(translate("在线的客户端"))
        self.groupBox_10.setTitle(translate("客户端管理"))
        self.tabWidget.setTabText(self.tabWidget.indexOf(self.tab_client), translate("客户端"))
        self.groupBox_5.setTitle(translate("传统悬浮窗"))
        self.groupBox_6.setTitle(translate("电压"))
        self.label_6.setText(translate("字体设置"))
        self.label_10.setText(translate("颜色设置"))
        self.pushButton_4.setText(translate("颜色"))
        self.pushButton_8.setText(translate("字体"))
        self.groupBox_7.setTitle(translate("电流"))
        self.label_15.setText(translate("字体设置"))
        self.label_16.setText(translate("颜色设置"))
        self.pushButton_6.setText(translate("颜色"))
        self.pushButton_5.setText(translate("字体"))
        self.label_17.setText(translate("透明度   "))
        self.spinBox.setSuffix(translate("%"))
        self.label_18.setText(translate("背景颜色"))
        self.pushButton_7.setText(translate("颜色"))
        self.tabWidget.setTabText(
            self.tabWidget.indexOf(self.tab_floating), translate("悬浮窗")
        )
        self.tabWidget.setTabText(self.tabWidget.indexOf(self.tab_about), translate("关于"))
