#!/usr/bin/env python3

import shutil
import subprocess
from pathlib import Path
from typing import Dict, Optional

FAN_RPM_MIN = 0
FAN_RPM_MAX = 7500

NVIDIA_SMI_TIMEOUT = 2


class FanMonitor:
    def __init__(self):
        self.hwmon_path = None
        self.coretemp_path = None
        self._nvidia_smi = shutil.which("nvidia-smi")
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

    def _get_nvidia_gpu_temp(self) -> Optional[float]:
        if not self._nvidia_smi:
            return None
        try:
            result = subprocess.run(
                [self._nvidia_smi, "--query-gpu=temperature.gpu",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=NVIDIA_SMI_TIMEOUT
            )
            if result.returncode == 0:
                return float(result.stdout.strip().split("\n")[0])
        except (subprocess.TimeoutExpired, ValueError, IndexError, OSError):
            pass
        return None

    def get_cpu_gpu_temps(self) -> Dict[str, Optional[float]]:
        temps = self.get_temps()
        cpu_temp = temps.get("temp1")
        if cpu_temp is None and not self.hwmon_path and temps:
            cpu_temp = max(temps.values())

        gpu_temp = temps.get("temp2")
        if gpu_temp is None or gpu_temp <= 0:
            gpu_temp = self._get_nvidia_gpu_temp()

        return {"cpu": cpu_temp, "gpu": gpu_temp}

    def get_max_temp(self) -> Optional[float]:
        temps = self.get_temps()
        return max(temps.values()) if temps else None


def rpm_to_percent(rpm: int) -> int:
    if rpm <= FAN_RPM_MIN:
        return 0
    if rpm >= FAN_RPM_MAX:
        return 100
    return int((rpm - FAN_RPM_MIN) / (FAN_RPM_MAX - FAN_RPM_MIN) * 100)
