# Third-party notices

The root `LICENSE` covers the project-specific scripts, documentation and
local firmware modifications by nop <noplab90@gmail.com>.
It does not replace the copyright or license notices of bundled software.

## ODrive and MakerBase firmware

The modified source is retained in `mks-source/ODrive-fw-v0.5.1/`.
It originated from the MakerBase ODrive v3.6 firmware distribution:
https://github.com/makerbase-motor/MKS-ODrive/tree/master/Firmware/ODrive_V3.6

The upstream MIT notices are preserved at:

- `mks-source/ODrive-fw-v0.5.1/LICENSE.md`: ODrive Robotics, 2016-2018.
- `mks-source/ODrive-fw-v0.5.1/Firmware/LICENSE`: Oskar Weigl, 2016-2018.
- `mks-source/ODrive-fw-v0.5.1/Arduino/ODriveArduino/LICENSE`: Oskar Weigl, 2017.

`firmware/LICENSE` accompanies the original MakerBase `.bin` and `.dfu`
recovery images with the ODrive MIT notices. These are original vendor
images, not builds of the local sensorless fixes.

## Bundled firmware dependencies

The firmware also includes third-party components such as ARM CMSIS,
STMicroelectronics drivers and FreeRTOS. Their original license and copyright
notices remain in the supplied source files and accompanying documents.
Those component terms continue to apply, including to binary distributions;
the root MIT license does not relicense those components.

ARM CMSIS and STMicroelectronics driver headers carry BSD-style redistribution
conditions. FreeRTOS V9.0.0 is copyright (C) 2016 Real Time Engineers Ltd. and
uses GPL version 2 with the FreeRTOS exception, not MIT. Its full license is at
`mks-source/ODrive-fw-v0.5.1/Firmware/Board/v3/Middlewares/Third_Party/FreeRTOS/LICENSE`,
copied from the official V9.0.0 distribution:
https://raw.githubusercontent.com/FreeRTOS/FreeRTOS/V9.0.0/FreeRTOS/License/license.txt

The historical Python DFUse module is retained unchanged in
`mks-source/ODrive-fw-v0.5.1/tools/odrive/dfuse/`. Its upstream `COPYING`
explicitly states that its license is unclear; this repository does not grant
MIT rights to that module. The host scripts instead use the separately
installed ODrive package declared in `pyproject.toml`.

When distributing a firmware image, include this notice, the ODrive MIT
licenses and the applicable bundled-component license notices from its source
tree. The exact contents of the vendor recovery binaries have not been
independently audited.
