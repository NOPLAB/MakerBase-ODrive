import runpy
import sys
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

scripts = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(scripts))

from calibrate import calibrate
from spin import spin


class FakeAxis:
    def __init__(self) -> None:
        self.error = 0
        self.current_state = 1
        self.requested_states = []
        self.motor = SimpleNamespace(
            error=0,
            is_calibrated=True,
            config=SimpleNamespace(
                pole_pairs=7, phase_resistance=0.1,
                phase_inductance=0.0002, pre_calibrated=False,
            ),
            current_control=SimpleNamespace(
                p_gain=0.1, Id_measured=0, Iq_measured=1,
            ),
        )
        self.encoder = SimpleNamespace(error=0)
        self.controller = SimpleNamespace(error=0, config=SimpleNamespace())
        self.sensorless_estimator = SimpleNamespace(
            error=0, vel_estimate=10, config=SimpleNamespace(),
        )
        self.fet_thermistor = SimpleNamespace(temperature=25)
        self.config = SimpleNamespace(sensorless_ramp=SimpleNamespace())
        self.lockin_state = 0
        self.watchdog_feed = Mock()

    @property
    def requested_state(self) -> int:
        return self.current_state

    @requested_state.setter
    def requested_state(self, state: int) -> None:
        self.requested_states.append(state)
        # The fake completes calibration immediately and enters rotation on request.
        self.current_state = 5 if state == 5 else 1


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def monotonic(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def make_device() -> SimpleNamespace:
    return SimpleNamespace(
        fw_version_major=0, fw_version_minor=5, fw_version_revision=1,
        vbus_voltage=12, axis0=FakeAxis(), axis1=FakeAxis(),
        user_config_loaded=True, save_configuration=Mock(),
    )


for motor in ("m0", "m1", None):
    # Given two idle axes and deterministic time, with only one output selected.
    device = make_device()
    selected = device.axis0 if motor == "m0" else device.axis1
    other = device.axis1 if motor == "m0" else device.axis0
    other_config = deepcopy(other.motor.config)
    clock = FakeClock()
    selected.sensorless_estimator.vel_estimate = 20
    selected.motor.current_control.Iq_measured = 11
    argv = ["spin.py", "--speed", "20", "--current", "7", "--current-limit", "10", "--duration", "1", "--bandwidth", "500"]
    if motor is not None:
        argv += ["--motor", motor]

    # When the actual CLI performs its timed rotation and cleanup.
    with patch("odrive.find_any", return_value=device), \
            patch("time.monotonic", clock.monotonic), \
            patch("time.sleep", clock.advance), \
            patch.object(sys, "argv", argv):
        runpy.run_path(str(scripts / "spin.py"), run_name="__main__")

    # Then only the selected output was run, configured, and returned to IDLE.
    assert selected.motor.config.current_lim == 10
    assert selected.motor.config.current_lim_margin == 2
    assert selected.controller.config.vel_limit == 24
    assert selected.config.sensorless_ramp.current == 7
    assert selected.requested_states == [5, 1]
    assert selected.current_state == 1
    assert selected.controller.input_vel == 0
    assert selected.config.enable_watchdog is False
    assert other.requested_states == []
    assert other.motor.config == other_config

    # Given a distinct device instance after saving calibration.
    device = make_device()
    reconnected = make_device()
    selected = device.axis0 if motor == "m0" else device.axis1
    other = device.axis1 if motor == "m0" else device.axis0
    saved_axis = reconnected.axis0 if motor == "m0" else reconnected.axis1
    clock = FakeClock()

    def save_configuration() -> None:
        reconnected.axis0.motor.config = deepcopy(device.axis0.motor.config)
        reconnected.axis1.motor.config = deepcopy(device.axis1.motor.config)

    device.save_configuration.side_effect = save_configuration
    argv = ["calibrate.py"]
    if motor is not None:
        argv += ["--motor", motor]

    # When the CLI calibrates, saves and reconnects to verify the selected axis.
    with patch("odrive.find_any", side_effect=[device, reconnected]) as find, \
            patch("time.monotonic", clock.monotonic), \
            patch("time.sleep", clock.advance), \
            patch.object(sys, "argv", argv):
        runpy.run_path(str(scripts / "calibrate.py"), run_name="__main__")

    # Then calibration and saved-parameter checks use that same output.
    assert selected.requested_states == [4, 1]
    assert selected.motor.config.pre_calibrated is True
    assert saved_axis.motor.config.pre_calibrated is True
    assert other.requested_states == []
    assert other.motor.config.pre_calibrated is False
    assert find.call_count == 2
    device.save_configuration.assert_called_once()

for operation in (calibrate, spin):
    # Given an invalid motor selector, connection must not be attempted.
    with patch("odrive.find_any") as find:
        try:
            if operation is calibrate:
                operation("test-serial", 5, motor="m2")
            else:
                operation(10, 2, 1, 100, 500, motor="m2")
        except ValueError:
            pass
        else:
            raise AssertionError("Invalid motor selector accepted")
        find.assert_not_called()

    # Given M0 selected but M1 busy, the two-axis IDLE interlock still applies.
    device = make_device()
    device.axis1.current_state = 5
    with patch("odrive.find_any", return_value=device):
        try:
            if operation is calibrate:
                operation("test-serial", 5, motor="m0")
            else:
                operation(10, 2, 1, 100, 500, motor="m0")
        except RuntimeError:
            pass
        else:
            raise AssertionError("Busy unselected axis accepted")
    assert device.axis0.requested_states == []

print("M0/M1 CLI selection, default, cleanup, reconnect and IDLE interlock checks passed")

# A short load dip recovers, sustained loss and current above 12A still stop.
for failure in (None, "tracking", "current"):
    device = make_device()
    axis = device.axis1
    clock = FakeClock()

    def advance(seconds):
        clock.advance(seconds)
        axis.sensorless_estimator.vel_estimate = 9 if 1 <= clock.now < (1.5 if failure is None else 4) else 10
        axis.motor.current_control.Iq_measured = 13 if failure == "current" and clock.now >= 1 else 11

    with patch("odrive.find_any", return_value=device), \
            patch("time.monotonic", clock.monotonic), \
            patch("time.sleep", advance):
        try:
            spin(10, 2, 3, 100, 500)
        except RuntimeError as error:
            assert failure is not None
            assert ("tracking lost for 1s" if failure == "tracking" else "Unsafe current") in str(error)
        else:
            assert failure is None
    assert axis.current_state == 1
    assert axis.controller.input_vel == 0
print("10A + 2A margin and transient load recovery checks passed")
