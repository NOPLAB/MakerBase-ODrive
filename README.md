# MakerBase v3.6/56V: sensorless firmware and motor tools

Modified ODrive 0.5.1 firmware and tools for a MakerBase v3.6/56V board.
Maintainer: nop <noplab90@gmail.com>.

The verified setup uses serial `355B30693133`, M1/axis1, an ODrive
D6374-150KV motor with 7 pole pairs, and an approximately 12V supply.
Secure the motor and keep its shaft unloaded and free to rotate.
Disconnect power if abnormal behavior occurs.

## Layout

- `scripts/`: calibration, motor tests, flashing and Windows USB repair.
- `tests/`: checks that do not connect to the motor.
- `mks-source/ODrive-fw-v0.5.1/`: modified firmware source and upstream notices.
- `firmware/`: original vendor recovery `.bin` and `.dfu` images.
- `build-tools/`: local build tools, excluded from Git.
- `archives/`: downloaded ZIP archives, excluded from Git.
- `backups/`: device configuration and registry backups, excluded from Git.
- `logs/`: build and USB repair logs, excluded from Git.

## Python environment

Install uv and run all commands from this repository's root:

```powershell
uv sync --locked
uv run python tests/test_sensorless_units.py
uv run python tests/test_spin_stages.py
uv run python tests/test_motor_selection.py
uv run odrivetool --help
```

The project uses Python 3.11 or newer and pins the ODrive tool version to
`0.6.11.post1`, with legacy DFU support and `libusb-package`.

## Calibration and rotation

```powershell
uv run python scripts/calibrate.py --motor m1
uv run python scripts/spin.py --motor m1 --duration 30
```

Both scripts accept `--motor m0` (axis0) or `--motor m1` (axis1), defaulting
to `m1` when omitted. For M0:

```powershell
uv run python scripts/calibrate.py --motor m0
uv run python scripts/spin.py --motor m0 --duration 30
```

The same D6374-150KV, 7-pole-pair and approximately 12V setup is required
on the selected output. The recorded physical trials below were on M1.
Both axes must be IDLE before starting. Calibration verifies the selected
axis again after reconnecting; rotation cleanup stops that same axis.
Firmware flashing and USB repair operate on the entire board, not one motor.

Calibration uses 5A. The default rotation test uses 600RPM, a 2A startup
current, a 10A current limit with a 2A margin and a 2-second watchdog. The hold timer starts
after estimated speed stabilizes; the axis returns to IDLE on exit.
Only calibration results are saved. Rotation-test settings are not saved,
and automatic rotation at power-up is not configured.
CLI speed and current have no fixed upper bounds; values must be finite and
positive, with startup current no greater than `--current-limit` (default 10A).
Controller velocity limiting and runtime telemetry checks remain enabled.
Current monitoring follows the requested limit plus the 2A margin. During a
hold, speed deviations beyond 3% have a 1-second recovery window; completion
requires three consecutive samples within 3%.
RPM is a sensorless estimate, not an external tachometer measurement.

For a staged 600-1200RPM test in 100RPM steps:

```powershell
uv run python scripts/spin.py --motor m1 --current-limit 2 --current 1.5 --accel 50 --duration 3 --max-rpm 1200
```

Startup current is 1.5A, startup acceleration is 50 electrical rad/s^2,
and subsequent speed ramps use 60RPM/s. The 2A setting limits commanded
current; it does not guarantee instantaneous peaks. The overcurrent
shutdown threshold is reduced to 4A.

On 2026-10-06, all stages through 1200RPM passed. The final estimated
speed was 1201RPM, sampled peak current was 2.17A, and the axis finished
IDLE without errors. This does not establish a maximum speed at 2A.

`--max-rpm` permits higher stages in 100RPM steps without a fixed upper bound. Each hold starts only after the
command ramp finishes and estimated speed converges within 3%.
In the 2026-10-06 trial, stages through 1200RPM held for 3 seconds each,
but overcurrent protection tripped during the 1300RPM hold:
axis error `0x40`, motor error `0x1000`. The motor did not reach 2000RPM.
Both axes were confirmed IDLE; the protection errors were left uncleared.

## Modified firmware

The MakerBase `ODrive-fw-v0.5.1.zip` distribution was extracted into
`mks-source/`. Local changes in `Firmware/MotorControl/axis.cpp`:

- Pass electrical angular velocity in rad/s to the motor update instead
  of mechanical revolutions per second.
- Initialize the current PI integrator on the first sensorless handoff
  using the preceding stationary-frame voltage and current, preserving
  voltage continuity.
- Keep overcurrent protection and the current-limit margin unchanged.

Build fixes explicitly include `<optional>` and generate firmware version
0.5.1 when building from an archive. The tracked `Firmware/tup.config`
selects `v3.6-56V`, native USB and ASCII UART.

### Build and flash

The existing Windows build setup requires the local `build-tools/` folder,
the ARM embedded compiler and the firmware's build dependencies.
`uv sync` configures the host scripts, not the firmware toolchain.

```powershell
uv run python tests/test_sensorless_units.py
Push-Location mks-source/ODrive-fw-v0.5.1/Firmware
try {
    $env:PATH = "$((Resolve-Path ../../../build-tools/python/Scripts).Path);$env:PATH"
    & ../../../build-tools/tup.exe --quiet --no-environ-check -j4
    if ($LASTEXITCODE -ne 0) { throw "Firmware build failed" }
} finally {
    Pop-Location
}
uv run python scripts/flash_makerbase.py
```

Flashing erases the entire application flash: recalibrate afterward.
Do not disconnect power or USB during flashing.
The script checks the target serial, runtime v3.6/56V identity, both axes'
IDLE state and the ELF flash address range.
For a compatible board with uninitialized OTP, it uses the verified runtime
identity without writing OTP, then performs standard DFU write/readback checks.

The original recovery images in `firmware/` do not contain the local fixes.
The modified build output is
`mks-source/ODrive-fw-v0.5.1/Firmware/build/ODriveFirmware.elf`.
Build outputs are excluded from Git.

The local `backups/before-fw-update.json` contains settings from failed
tests; do not restore it wholesale.
Vendor source:
https://github.com/makerbase-motor/MKS-ODrive/tree/master/Firmware/ODrive_V3.6

## Windows USB repair

Run `.\scripts\repair-usb.ps1` in an administrator PowerShell session.
It repairs the recorded ODrive native interface, stores its transcript
in `logs/repair-usb.log`, and exports the original registry parameters
to `backups/usb-parameters-before.reg` when a repair is needed.

## License

Project-specific code, documentation and local firmware modifications are
MIT licensed: see [LICENSE](LICENSE).
The ODrive MIT notices and bundled-component licenses are preserved in
the firmware source. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)
for attribution and binary distribution requirements.
In particular, bundled FreeRTOS 9 uses GPLv2 with the FreeRTOS exception,
ARM/ST code retains its own terms, and the historical upstream DFUse module
has an explicitly unclear license.
