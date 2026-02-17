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

RAPL_PL1_PATH = "/sys/class/powercap/intel-rapl:0/constraint_0_power_limit_uw"
RAPL_PL2_PATH = "/sys/class/powercap/intel-rapl:0/constraint_1_power_limit_uw"
SCALING_MAX_FREQ_ATTR = "cpufreq/scaling_max_freq"
CPUINFO_MAX_FREQ = "cpufreq/cpuinfo_max_freq"

RAPL_PL1_MIN_W = 15
RAPL_PL1_MAX_W = 200
RAPL_PL2_MIN_W = 20
RAPL_PL2_MAX_W = 250
CPU_FREQ_MIN_MHZ = 800
CPU_FREQ_MAX_MHZ = 5500

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


def get_rapl_pl1_watts() -> Optional[int]:
    val = _read_sysfs(RAPL_PL1_PATH)
    if val is None:
        return None
    try:
        return int(val) // 1_000_000
    except (ValueError, TypeError):
        return None


def set_rapl_pl1(watts: int) -> bool:
    watts = max(RAPL_PL1_MIN_W, min(RAPL_PL1_MAX_W, watts))
    return _write_sysfs(RAPL_PL1_PATH, str(watts * 1_000_000))


def get_rapl_pl2_watts() -> Optional[int]:
    val = _read_sysfs(RAPL_PL2_PATH)
    if val is None:
        return None
    try:
        return int(val) // 1_000_000
    except (ValueError, TypeError):
        return None


def set_rapl_pl2(watts: int) -> bool:
    watts = max(RAPL_PL2_MIN_W, min(RAPL_PL2_MAX_W, watts))
    return _write_sysfs(RAPL_PL2_PATH, str(watts * 1_000_000))


def get_cpu_max_freq_mhz() -> Optional[int]:
    val = _read_sysfs(f"{CPU_BASE}/cpu0/{SCALING_MAX_FREQ_ATTR}")
    if val is None:
        return None
    try:
        return int(val) // 1000
    except (ValueError, TypeError):
        return None


def get_cpu_hw_max_freq_mhz() -> Optional[int]:
    val = _read_sysfs(f"{CPU_BASE}/cpu0/{CPUINFO_MAX_FREQ}")
    if val is None:
        return None
    try:
        return int(val) // 1000
    except (ValueError, TypeError):
        return None


def set_cpu_max_freq(mhz: int) -> bool:
    mhz = max(CPU_FREQ_MIN_MHZ, min(CPU_FREQ_MAX_MHZ, mhz))
    khz = str(mhz * 1000)
    success = True
    for cpu in _cpu_dirs():
        if not _write_sysfs(str(cpu / SCALING_MAX_FREQ_ATTR), khz):
            success = False
    return success


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

    pl1 = config.get("cpu_rapl_pl1_w")
    if pl1 is not None:
        set_rapl_pl1(pl1)

    pl2 = config.get("cpu_rapl_pl2_w")
    if pl2 is not None:
        set_rapl_pl2(pl2)

    max_freq = config.get("cpu_max_freq_mhz")
    if max_freq is not None:
        set_cpu_max_freq(max_freq)
