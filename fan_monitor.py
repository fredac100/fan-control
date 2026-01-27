#!/usr/bin/env python3

from pathlib import Path
from typing import Dict

FAN_RPM_MIN = 0
FAN_RPM_MAX = 7500


class FanMonitor:
    def __init__(self):
        self.hwmon_path = None
        self.coretemp_path = None
        self._find_hwmon_devices()

    def _find_hwmon_devices(self):
        hwmon_base = Path("/sys/class/hwmon")
        if not hwmon_base.exists():
            return
        for device in hwmon_base.iterdir():
            name_file = device / "name"
            if name_file.exists():
                try:
                    with open(name_file) as f:
                        name = f.read().strip()
                        if name == "acer":
                            self.hwmon_path = device
                        elif name == "coretemp":
                            self.coretemp_path = device
                except (PermissionError, OSError):
                    pass

    def get_fan_speeds(self) -> Dict[str, int]:
        speeds = {}
        if self.hwmon_path:
            for fan_num in [1, 2]:
                fan_file = self.hwmon_path / f"fan{fan_num}_input"
                if fan_file.exists():
                    try:
                        with open(fan_file) as f:
                            speeds[f"fan{fan_num}"] = int(f.read().strip())
                    except (ValueError, PermissionError, OSError):
                        pass
        return speeds

    def get_temps(self) -> Dict[str, float]:
        temps = {}
        if self.hwmon_path:
            for temp_num in [1, 2, 3]:
                temp_file = self.hwmon_path / f"temp{temp_num}_input"
                if temp_file.exists():
                    try:
                        with open(temp_file) as f:
                            temps[f"temp{temp_num}"] = int(f.read().strip()) / 1000.0
                    except (ValueError, PermissionError, OSError):
                        pass

        if self.coretemp_path and not temps:
            for temp_file in sorted(self.coretemp_path.glob("temp*_input")):
                try:
                    with open(temp_file) as f:
                        temp_name = temp_file.stem.replace("_input", "")
                        temps[temp_name] = int(f.read().strip()) / 1000.0
                except (ValueError, PermissionError, OSError):
                    pass
        return temps

    def get_max_temp(self) -> float:
        temps = self.get_temps()
        return max(temps.values()) if temps else 50.0


def rpm_to_percent(rpm: int) -> int:
    if rpm <= FAN_RPM_MIN:
        return 0
    if rpm >= FAN_RPM_MAX:
        return 100
    return int((rpm - FAN_RPM_MIN) / (FAN_RPM_MAX - FAN_RPM_MIN) * 100)
