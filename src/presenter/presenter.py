
import logging
import asyncio

import asyncio

from PySide6.QtCore import Qt, QObject
from qasync import QEventLoop, asyncSlot, asyncClose

from .model import PowerSupplyModel

class Presenter(QObject):
    def __init__(self, view_cls, model_cls=None):
        self.view = view_cls(presenter = self)
        self.model = PowerSupplyModel() if model_cls is None else model_cls()
        # self.view.connect_signal_slots(self)
        # self.view.setupUi()
        self.view.show()

    @asyncSlot()
    def close_device(self):
        self.model.close_device()

    # @asyncSlot()
    def open_device(self):
        self.model.open_device()

    @asyncSlot(float)
    def set_voltage(self, voltage):

        pass
