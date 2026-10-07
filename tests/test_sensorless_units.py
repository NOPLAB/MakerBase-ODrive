import math
from pathlib import Path

source = Path(__file__).resolve().parents[1] / "mks-source/ODrive-fw-v0.5.1/Firmware/MotorControl"
axis = (source / "axis.cpp").read_text()
sensorless_loop = axis.split("bool Axis::run_sensorless_control_loop()", 1)[1].split("bool Axis::run_closed_loop_control_loop()", 1)[0]
assert "motor_.update(torque_setpoint, sensorless_estimator_.phase_, sensorless_estimator_.vel_estimate_erad_)" in sensorless_loop
estimator = (source / "sensorless_estimator.cpp").read_text()
assert "vel_estimate_ = vel_estimate_erad_ / (std::max((float)axis_->motor_.config_.pole_pairs, 1.0f) * 2.0f * M_PI)" in estimator
assert "float pwm_phase = phase + 1.5f * current_meas_period * phase_vel" in (source / "motor.cpp").read_text()
electrical_speed = (600 / 60) * 7 * 2 * math.pi
assert math.isclose(electrical_speed, 439.822971502571, rel_tol=1e-12)
assert not math.isclose(electrical_speed, 600 / 60)
print("Sensorless electrical-speed contract passed: 600rpm, 7 pole pairs -> 439.823rad/s")
assert "initialize_voltage" in sensorless_loop
assert "control.p_gain * (desired_d - c * current_alpha - s * current_beta)" in sensorless_loop
assert "control.p_gain * (desired_q - c * current_beta + s * current_alpha)" in sensorless_loop
for phase in (-3.0, -1.0, 0.0, 1.5, 3.0):
    pwm_phase = phase + 0.08
    cosine, sine = math.cos(pwm_phase), math.sin(pwm_phase)
    voltage_alpha, voltage_beta = 1.2, -2.3
    error_d, error_q, gain = -1.0, 2.0, 0.04
    integral_d = cosine * voltage_alpha + sine * voltage_beta - gain * error_d
    integral_q = cosine * voltage_beta - sine * voltage_alpha - gain * error_q
    voltage_d = integral_d + gain * error_d
    voltage_q = integral_q + gain * error_q
    assert math.isclose(cosine * voltage_d - sine * voltage_q, voltage_alpha, abs_tol=1e-12)
    assert math.isclose(cosine * voltage_q + sine * voltage_d, voltage_beta, abs_tol=1e-12)
print("Sensorless handoff voltage continuity passed")
