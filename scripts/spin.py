import argparse
import math
import time

import odrive

from calibrate import check_errors


def speed_stages(speed, maximum_rpm):
    if maximum_rpm is None:
        return [speed]
    if not math.isclose(speed, 10) or maximum_rpm < 600 or maximum_rpm % 100:
        raise ValueError("Staged test requires 600rpm start and maximum of at least 600rpm in 100rpm steps")
    return [rpm / 60 for rpm in range(600, maximum_rpm + 1, 100)]


def spin(speed, current, duration, accel, bandwidth, current_limit=10, maximum_rpm=None, *, motor="m1"):
    if motor not in ("m0", "m1"):
        raise ValueError("Motor must be m0 or m1")
    stages = speed_stages(speed, maximum_rpm)
    if not all(math.isfinite(value) for value in (speed, current, duration, accel, bandwidth, current_limit)) or speed <= 0 or not 0 < current <= current_limit or not 1 <= duration <= 30 or not 50 <= accel <= 200 or not 500 <= bandwidth <= 3000:
        raise ValueError("Invalid motor-test parameters")
    device = odrive.find_any(serial_number="355B30693133", timeout=15)
    axis = device.axis0 if motor == "m0" else device.axis1
    if (device.fw_version_major, device.fw_version_minor, device.fw_version_revision) != (0, 5, 1):
        raise RuntimeError("This script requires firmware 0.5.1")
    if device.axis0.current_state != 1 or device.axis1.current_state != 1:
        raise RuntimeError("Both axes must be IDLE")
    if not axis.motor.is_calibrated or axis.motor.config.pole_pairs != 7:
        raise RuntimeError("Expected calibrated 7-pole-pair motor")
    if not 10 <= device.vbus_voltage <= 14:
        raise RuntimeError("Expected approximately 12V supply")
    if not math.isfinite(axis.fet_thermistor.temperature) or axis.fet_thermistor.temperature > 60:
        raise RuntimeError("ODrive is too hot for this test")
    check_errors(axis)
    axis.motor.config.direction = 1
    axis.motor.config.current_lim = current_limit
    axis.motor.config.current_lim_margin = 2
    axis.motor.config.current_control_bandwidth = bandwidth
    if not math.isclose(axis.motor.current_control.p_gain, bandwidth * axis.motor.config.phase_inductance, rel_tol=1e-5):
        raise RuntimeError("Current-controller gain update failed")
    axis.controller.config.control_mode = 2
    axis.controller.config.input_mode = 2 if maximum_rpm is not None else 1
    axis.controller.config.vel_ramp_rate = 1
    axis.controller.config.vel_gain = 0.01
    axis.controller.config.vel_integrator_gain = 0.05
    axis.controller.config.vel_limit = max(stages) * 1.2
    axis.config.sensorless_ramp.current = current
    axis.config.sensorless_ramp.vel = speed * 2 * math.pi * 7
    axis.config.sensorless_ramp.accel = accel
    axis.config.sensorless_ramp.finish_on_vel = True
    axis.config.sensorless_ramp.finish_on_distance = False
    axis.config.sensorless_ramp.finish_on_enc_idx = False
    axis.controller.input_vel = speed
    axis.controller.input_torque = 0
    axis.config.watchdog_timeout = 2
    axis.watchdog_feed()
    axis.config.enable_watchdog = True
    samples = []
    stage_index = 0
    peak_current = 0
    try:
        print(f"{motor.upper()} sensorless test: {speed * 60:.0f}..{stages[-1] * 60:.0f}rpm, {duration}s per stage, ramp {current}A, limit {current_limit}A, current bandwidth {bandwidth}rad/s", flush=True)
        axis.requested_state = 5
        started = time.monotonic()
        holding_since = None
        stable_samples = 0
        tracking_lost_since = None
        next_report = started
        stage_started = started
        while True:
            axis.watchdog_feed()
            check_errors(axis)
            state = axis.current_state
            if state != 5:
                raise RuntimeError(f"Unexpected {motor.upper()} state: {state}")
            velocity = axis.sensorless_estimator.vel_estimate
            voltage = device.vbus_voltage
            measured_current = math.hypot(axis.motor.current_control.Id_measured, axis.motor.current_control.Iq_measured)
            temperature = axis.fet_thermistor.temperature
            if not math.isfinite(velocity) or abs(velocity) > max(stages) * 1.2 or not 10 <= voltage <= 14:
                raise RuntimeError(f"Unsafe telemetry: {velocity} turns/s, {voltage}V")
            if not math.isfinite(measured_current) or measured_current > current_limit + axis.motor.config.current_lim_margin or not math.isfinite(temperature) or temperature > 60:
                raise RuntimeError(f"Unsafe current/temperature: {measured_current:.2f}A, {temperature:.1f}C")
            peak_current = max(peak_current, measured_current)
            ramp_complete = maximum_rpm is None or abs(axis.controller.vel_setpoint - speed) < 0.01
            if axis.lockin_state == 0 and ramp_complete and abs(velocity - speed) <= speed * 0.03:
                tracking_lost_since = None
                stable_samples += 1
                if holding_since is None and stable_samples >= 3:
                    holding_since = time.monotonic()
                    print(f"{speed * 60:.0f}rpm tracking established; hold timer started", flush=True)
                samples.append(velocity)
            else:
                stable_samples = 0
                if holding_since is not None:
                    if tracking_lost_since is None:
                        tracking_lost_since = time.monotonic()
                    elif time.monotonic() - tracking_lost_since >= 1:
                        raise RuntimeError("Speed tracking lost for 1s during timed hold")
            if holding_since is None and time.monotonic() - stage_started > (16 if stage_index == 0 else 8):
                raise TimeoutError(f"{speed * 60:.0f}rpm tracking not established; last stable stage {stages[stage_index - 1] * 60 if stage_index else 0:.0f}rpm")
            if holding_since is not None and stable_samples >= 3 and time.monotonic() - holding_since >= duration:
                print(f"Stage passed: target={speed * 60:.0f}rpm, estimated={sum(samples[-3:]) / 3 * 60:.0f}rpm", flush=True)
                stage_index += 1
                if stage_index == len(stages):
                    break
                speed = stages[stage_index]
                axis.controller.input_vel = speed
                holding_since = None
                stable_samples = 0
                samples = []
                stage_started = time.monotonic()
                print(f"Slow ramp to {speed * 60:.0f}rpm at 60rpm/s", flush=True)
            if time.monotonic() >= next_report:
                held = 0 if holding_since is None else time.monotonic() - holding_since
                print(f"held={held:.1f}s, estimated={velocity * 60:.0f}rpm, current={measured_current:.2f}A, bus={voltage:.2f}V, FET={temperature:.1f}C", flush=True)
                next_report = time.monotonic() + 1
            time.sleep(0.25)
    finally:
        axis.requested_state = 1
        deadline = time.monotonic() + 2
        while axis.current_state != 1:
            axis.watchdog_feed()
            if time.monotonic() > deadline:
                raise RuntimeError("IDLE transition failed; cut motor power immediately")
            time.sleep(0.05)
        axis.config.enable_watchdog = False
        axis.controller.input_vel = 0
        print(f"{motor.upper()} IDLE confirmed; motor output disabled. Test settings not saved.", flush=True)
    check_errors(axis)
    if len(samples) < 3 or any(abs(value - speed) > speed * 0.03 for value in samples[-3:]):
        raise RuntimeError("Sensorless speed tracking did not pass")
    print(f"Test passed: final mean {sum(samples[-3:]) / 3 * 60:.0f}rpm, sampled peak current {peak_current:.2f}A")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Timed unloaded M0/M1 sensorless test on firmware 0.5.1")
    parser.add_argument("--motor", choices=("m0", "m1"), default="m1", help="Motor output to test (default: m1)")
    parser.add_argument("--speed", type=float, default=10)
    parser.add_argument("--current", type=float, default=2)
    parser.add_argument("--duration", type=float, default=3)
    parser.add_argument("--accel", type=float, default=100)
    parser.add_argument("--bandwidth", type=float, default=2000)
    parser.add_argument("--current-limit", type=float, default=10)
    parser.add_argument("--max-rpm", type=int)
    args = parser.parse_args()
    if not 1 <= args.duration <= 30 or not 50 <= args.accel <= 200 or not 500 <= args.bandwidth <= 3000:
        parser.error("Require duration 1..30s, accel 50..200 rad/s^2, bandwidth 500..3000 rad/s")
    spin(args.speed, args.current, args.duration, args.accel, args.bandwidth, args.current_limit, args.max_rpm, motor=args.motor)
