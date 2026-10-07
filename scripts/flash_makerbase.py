import asyncio
from pathlib import Path

from odrive import legacy_dfu
from odrive.device_manager import find_async
from odrive.firmware import FirmwareFile
from odrive.hw_version import HwVersion
from odrive.runtime_device import RuntimeDevice


SERIAL = "355B30693133"
FIRMWARE = Path(__file__).resolve().parents[1] / "mks-source/ODrive-fw-v0.5.1/Firmware/build/ODriveFirmware.elf"


async def main():
    device = await asyncio.wait_for(find_async(serial_number=SERIAL, return_type=RuntimeDevice), 10)
    hardware = tuple([await device.try_read(name, None) for name in ("hw_version_major", "hw_version_minor", "hw_version_variant")])
    states = [await device.try_read(name, None) for name in ("axis0.current_state", "axis1.current_state")]
    if hardware != (3, 6, 56) or states != [1, 1]:
        raise RuntimeError("Require verified v3.6/56V board with both axes IDLE")
    sections = list(FirmwareFile.from_file(str(FIRMWARE)).get_flash_sections())
    if not sections or any(address < 0x08000000 or address + len(data) > 0x080C0000 for _, address, data in sections):
        raise RuntimeError("Firmware outside STM32 application flash")
    original_init = legacy_dfu.ODriveInDfuMode.init

    def verified_init(dfu_device, ask):
        original_init(dfu_device, ask)
        if dfu_device.board == HwVersion(3, 0, 0):
            if dfu_device._dev.serial_number != SERIAL:
                raise RuntimeError("Unexpected DFU serial")
            dfu_device.board = HwVersion(*hardware)
            print("Using runtime-verified MakerBase v3.6/56V identity; OTP unchanged.", flush=True)
        if dfu_device.board != HwVersion(*hardware):
            raise RuntimeError("DFU hardware mismatch")

    legacy_dfu.ODriveInDfuMode.init = verified_init
    await legacy_dfu.launch_dfu(SERIAL, str(FIRMWARE), None, None, True)


if __name__ == "__main__":
    asyncio.run(main())
