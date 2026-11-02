"""Vortran Stradus laser on its serial port (vortran_laser): on at Laser.power_mw for a run, always off after."""

from __future__ import annotations

import logging
import time

from serial import SerialException
from vortran_laser.stradus import FaultCodeField, Query, StradusLaser

from dmdcontrol.utils import CONFIG

logger = logging.getLogger('Laser')

SETTLE_TIMEOUT_S = 15.0  # covers the 5 s CDRH emission delay
POWER_TOLERANCE = 0.05   # measured power within 5% (at least 1 mW) of the setpoint counts as on


class Laser:
    """Context manager for a run's laser.

    With Laser.control off, or nothing answering on Laser.port, it logs and does nothing else so
    the run carries on. A connected laser that reports a fault or an open interlock stops the run
    instead of letting it collect in the dark.
    """

    def __init__(self):
        self.device: StradusLaser | None = None

    def __enter__(self) -> Laser:
        config = CONFIG.Laser
        if not config.control:
            logger.info('Laser control off (Laser.control: False)')
            return self
        try:
            self.device = StradusLaser(config.port)
        except SerialException as exc:
            logger.warning('Laser not connected on %s, running without laser control (%s)', config.port, exc)
            return self
        try:
            self._turn_on(self.device, config.power_mw)
        except BaseException:
            self.__exit__(None, None, None)
            raise
        return self

    def __exit__(self, *_) -> None:
        if self.device is None:
            return
        try:
            self.device.disable()
            logger.info('Laser off')
        finally:
            self.device.ser.close()
            self.device = None

    def faults(self) -> list[str]:
        """Names of the active fault bits (vortran_laser's own `faults` stops after the first bit)."""
        if self.device is None:
            return []
        code = int(self.device.get(Query.FaultCode))
        return [field.name for field in FaultCodeField if field.value >= 4 and code & field.value]

    def _turn_on(self, device: StradusLaser, power_mw: float) -> None:
        if not device.interlock_is_closed:
            raise RuntimeError(f'{device.wavelength} nm laser interlock is open: turn the key')
        if faults := self.faults():
            raise RuntimeError(f'{device.wavelength} nm laser faults: {", ".join(faults)}')
        if float(device.power_setpoint) != power_mw:
            device.power_setpoint = power_mw
        device.enable()

        deadline = time.monotonic() + SETTLE_TIMEOUT_S
        while (power := float(device.power)) < power_mw - max(1.0, POWER_TOLERANCE * power_mw):
            if time.monotonic() > deadline:
                raise RuntimeError(f'laser reached {power} mW of {power_mw} mW in {SETTLE_TIMEOUT_S:.0f} s')
            time.sleep(0.25)
        logger.info('%s nm laser on: %.1f mW (setpoint %s mW), base plate %s C',
                    device.wavelength, power, device.power_setpoint, device.temperature)
