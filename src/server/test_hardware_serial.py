"""Opt-in real-serial checks; the default gate never touches laboratory hardware.

    PSM_TEST_SERIAL_PORT=COM8 python -m pytest src -m hardware

These tests are read-only: they never change voltage, current or output state.
Without PSM_TEST_SERIAL_PORT they skip cleanly, including on CI runners.
"""
import asyncio
import os

import pytest
import pytest_asyncio

from device.scpi_power_supply import SCPI_PowerSupply

pytestmark = [pytest.mark.integration, pytest.mark.hardware, pytest.mark.asyncio]

PORT_ENV = "PSM_TEST_SERIAL_PORT"


@pytest_asyncio.fixture
async def real_device(monkeypatch):
    psu = SCPI_PowerSupply()
    port = os.environ.get(PORT_ENV, "").strip()
    if not port:
        pytest.skip(f"set {PORT_ENV} (for example COM8) to run real-serial tests")

    # Avoid reusing a lock bound to an earlier test's event loop.
    monkeypatch.setattr(psu, "_locker", asyncio.Lock())
    if not await psu.connect(serial_number=port):
        pytest.fail(f"{PORT_ENV}={port} could not be opened: {psu.last_error}")
    try:
        yield psu
    finally:
        await psu.disconnect()


class TestRealSerialReadback:
    async def test_identifier_comes_back_from_the_device(self, real_device):
        assert real_device.identifier
        assert await real_device.get_identifier()

    async def test_measurements_are_numeric(self, real_device):
        voltage = await real_device.get_voltage()
        current = await real_device.get_current()

        assert voltage >= 0.0
        assert current >= 0.0

    async def test_output_state_is_readable(self, real_device):
        assert isinstance(await real_device.get_on_off(), bool)
