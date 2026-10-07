import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from spin import speed_stages, spin

assert speed_stages(10, None) == [10]
assert [round(speed * 60) for speed in speed_stages(10, 1200)] == list(range(600, 1201, 100))
assert [round(speed * 60) for speed in speed_stages(10, 2000)] == list(range(600, 2001, 100))
for maximum in (500, 650, 2100):
    try:
        speed_stages(10, maximum)
    except ValueError:
        pass
    else:
        raise AssertionError("Unsafe maximum accepted")
try:
    spin(10, 3, 3, 50, 2000, current_limit=2, maximum_rpm=1200)
except ValueError:
    pass
else:
    raise AssertionError("Startup current exceeds current limit")
print("Bounded gradual-speed plan checks passed; no motor connection made")
