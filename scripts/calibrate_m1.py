import argparse
import math
import time

import odrive
from odrive.libodrive import DeviceLostException, TransportException


def check_errors(axis):
    errors = []
    for name, component in (
        ("axis", axis),
        ("motor", axis.motor),
        ("encoder", axis.encoder),
        ("controller", axis.controller),
        ("sensorless_estimator", axis.sensorless_estimator),
    ):
        if component.error:
            errors.append(f"{name}={component.error:#x}")
    if errors:
        raise RuntimeError("M1 errors: " + ", ".join(errors))


def calibrate(serial, current):
    device = odrive.find_any(serial_number=serial, timeout=15)
    if (device.fw_version_major, device.fw_version_minor, device.fw_version_revision) != (0, 5, 1):
        raise RuntimeError("This script requires firmware 0.5.1")
    if device.axis0.current_state != 1 or device.axis1.current_state != 1:
        raise RuntimeError("Both axes must be IDLE")
    if not 10 <= device.vbus_voltage <= 14:
        raise RuntimeError(f"Expected approximately 12V, got {device.vbus_voltage}V")
    axis = device.axis1
    check_errors(axis)
    settings = {
        "motor_type": 0,
        "pole_pairs": 7,
        "torque_constant": 8.27 / 150,
        "current_lim": 10,
        "calibration_current": current,
        "resistance_calib_max_voltage": 2,
    }
    for name, value in settings.items():
        setattr(axis.motor.config, name, value)
        if not math.isclose(getattr(axis.motor.config, name), value, rel_tol=1e-5):
            raise RuntimeError(f"Motor setting verification failed: {name}")
    flux = 5.51328895422 / (7 * 150)
    axis.sensorless_estimator.config.pm_flux_linkage = flux
    if not math.isclose(axis.sensorless_estimator.config.pm_flux_linkage, flux, rel_tol=1e-5):
        raise RuntimeError("Flux linkage verification failed")
    print(f"M1 calibration: {current}A, {device.vbus_voltage:.2f}V", flush=True)
    try:
        axis.requested_state = 4
        time.sleep(0.25)
        deadline = time.monotonic() + 20
        while axis.current_state != 1:
            check_errors(axis)
            if time.monotonic() > deadline:
                raise TimeoutError("Motor calibration timed out")
            time.sleep(0.25)
        check_errors(axis)
        resistance = axis.motor.config.phase_resistance
        inductance = axis.motor.config.phase_inductance
        if not axis.motor.is_calibrated or not (resistance > 0 and inductance > 0):
            raise RuntimeError("Motor calibration did not produce valid parameters")
        print(f"Calibration passed: R={resistance:.6f} ohm, L={inductance:.9f} H", flush=True)
    finally:
        axis.requested_state = 1
    axis.motor.config.pre_calibrated = True
    try:
        device.save_configuration()
    except (DeviceLostException, TransportException):
        pass
    time.sleep(3)
    device = odrive.find_any(serial_number=serial, timeout=15)
    axis = device.axis1
    check_errors(axis)
    if not device.user_config_loaded or not axis.motor.config.pre_calibrated or not axis.motor.is_calibrated:
        raise RuntimeError("Saved calibration verification failed")
    if device.axis0.current_state != 1 or axis.current_state != 1:
        raise RuntimeError("Expected both axes IDLE after saving")
    if not math.isclose(axis.motor.config.phase_resistance, resistance, rel_tol=1e-5) or not math.isclose(axis.motor.config.phase_inductance, inductance, rel_tol=1e-5):
        raise RuntimeError("Saved motor parameters do not match")
    print("Saved calibration verified; both axes IDLE. No continuous rotation requested.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Calibrate M1 D6374-150KV on the confirmed 12V setup")
    parser.add_argument("--serial", default="355B30693133")
    parser.add_argument("--current", type=float, default=5)
    args = parser.parse_args()
    if not 1 <= args.current <= 10:
        parser.error("--current must be between 1 and 10A")
    calibrate(args.serial, args.current)
