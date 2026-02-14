#!/usr/bin/env python3

import glob
from pathlib import Path
from typing import List, Optional

SCALING_GOVERNOR = "cpufreq/scaling_governor"
AVAILABLE_GOVERNORS = "cpufreq/scaling_available_governors"
EPP_PREF = "cpufreq/energy_performance_preference"
EPP_AVAILABLE = "cpufreq/energy_performance_available_preferences"
NO_TURBO = "/sys/devices/system/cpu/intel_pstate/no_turbo"
CPU_BASE = "/sys/devices/system/cpu"
PLATFORM_PROFILE = "/sys/firmware/acpi/platform_profile"

EPP_TO_PROFILE = {
    "power": "quiet",
    "balance_power": "balanced",
    "balance_performance": "balanced-performance",
    "performance": "performance",
    "default": "balanced",
}


def _cpu_dirs() -> List[Path]:
    return sorted(
        Path(p).parent.parent
        for p in glob.glob(f"{CPU_BASE}/cpu[0-9]*/cpufreq/scaling_governor")
    )


def _read_sysfs(path: str) -> Optional[str]:
    try:
        with open(path) as f:
            return f.read().strip()
    except (FileNotFoundError, PermissionError, OSError):
        return None


def _write_sysfs(path: str, value: str) -> bool:
    try:
        with open(path, "w") as f:
            f.write(value)
        return True
    except (FileNotFoundError, PermissionError, OSError):
        return False


def get_available_governors() -> List[str]:
    result = _read_sysfs(f"{CPU_BASE}/cpu0/{AVAILABLE_GOVERNORS}")
    return result.split() if result else []


def get_current_governor() -> str:
    return _read_sysfs(f"{CPU_BASE}/cpu0/{SCALING_GOVERNOR}") or "unknown"


def set_governor(governor: str) -> bool:
    available = get_available_governors()
    if available and governor not in available:
        return False
    success = True
    for cpu in _cpu_dirs():
        if not _write_sysfs(str(cpu / SCALING_GOVERNOR), governor):
            success = False
    return success


def get_available_epp() -> List[str]:
    result = _read_sysfs(f"{CPU_BASE}/cpu0/{EPP_AVAILABLE}")
    return result.split() if result else []


def get_current_epp() -> str:
    return _read_sysfs(f"{CPU_BASE}/cpu0/{EPP_PREF}") or "unknown"


def set_epp(pref: str, platform_profile: str = None) -> bool:
    available = get_available_epp()
    if available and pref not in available:
        return False

    profile = platform_profile or EPP_TO_PROFILE.get(pref)
    if profile:
        _write_sysfs(PLATFORM_PROFILE, profile)

    success = True
    for cpu in _cpu_dirs():
        if not _write_sysfs(str(cpu / EPP_PREF), pref):
            success = False
    return success


def get_turbo_enabled() -> bool:
    val = _read_sysfs(NO_TURBO)
    return val == "0" if val is not None else True


def set_turbo(enabled: bool) -> bool:
    return _write_sysfs(NO_TURBO, "0" if enabled else "1")


def get_platform_profile() -> str:
    return _read_sysfs(PLATFORM_PROFILE) or "unknown"


def apply_cpu_power(config: dict) -> None:
    governor = config.get("cpu_governor")
    if governor:
        set_governor(governor)

    turbo = config.get("cpu_turbo_enabled")
    if turbo is not None:
        set_turbo(turbo)

    epp = config.get("cpu_epp")
    if epp:
        pp = config.get("cpu_platform_profile") or None
        set_epp(epp, platform_profile=pp)
