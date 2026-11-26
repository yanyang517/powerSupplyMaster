import asyncio

from presenter.model import PowerSupplyModel


class FakeDevice:
    def __init__(self):
        self.calls = []

    async def get_on_off(self, *, timeout=1.0):
        self.calls.append(("get_on_off", timeout))
        return True

    async def get_voltage(self):
        self.calls.append(("get_voltage",))
        return 12.0

    async def get_current(self):
        self.calls.append(("get_current",))
        return 0.5


def test_output_query_forwards_calibration_timeout():
    model = PowerSupplyModel()
    model.device = FakeDevice()

    assert asyncio.run(model.get_on_off(timeout=0.25)) is True
    assert model.device.calls == [("get_on_off", 0.25)]


def test_voltage_current_queries_keep_existing_signature():
    model = PowerSupplyModel()
    model.device = FakeDevice()

    assert asyncio.run(model.get_voltage()) == 12.0
    assert asyncio.run(model.get_current()) == 0.5
    assert model.device.calls == [("get_voltage",), ("get_current",)]
