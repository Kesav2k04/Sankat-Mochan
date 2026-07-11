"""
Sankat-Mochan field node — Arduino App entry point.

This App exists to put the LoRa **modem firmware** on the UNO Q's MCU: starting the App
builds and flashes ../sketch/sketch.ino (the Router-Bridge LoRa modem) onto the STM32 and
keeps the arduino-router link to it alive. The actual field-node mesh logic (BLE to the
victim's phones, envelope validation, LoRa forwarding) does NOT run here — it runs as a
separate host process with full Bluetooth access, launched with:

    ./field-node/run.sh

That process reaches this modem over the Router Bridge (transport: "bridge" in
field-node/config.json). See field-node/FIELD-NODE.md for the whole picture.

So this Python side is intentionally just a keepalive: it holds the App "running" so the
MCU stays flashed with the modem. Everything interesting is on the MCU and in run.sh.
"""
import time

from arduino.app_utils import App, Logger

logger = Logger(__name__)
logger.info("Sankat field-node modem host: MCU runs the LoRa modem; start the mesh with "
            "./field-node/run.sh")


def loop():
    # Nothing to do here — the MCU modem and the field-node process do the work.
    time.sleep(10)


App.run(user_loop=loop)
