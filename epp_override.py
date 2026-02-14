#!/usr/bin/env python3

import sys
import time
import signal
from pathlib import Path

PLATFORM_PROFILE = Path("/sys/firmware/acpi/platform_profile")
EPP_CPU0 = Path("/sys/devices/system/cpu/cpu0/cpufreq/energy_performance_preference")
NO_TURBO = Path("/sys/devices/system/cpu/intel_pstate/no_turbo")
CPU_BASE = Path("/sys/devices/system/cpu")

PROFILE_TO_EPP = {
    "low-power": "power",
    "quiet": "power",
    "balanced": "balance_power",
    "balanced-performance": "balance_performance",
    "performance": "performance",
}

PROFILE_TURBO = {
    "low-power": False,
    "quiet": False,
    "balanced": True,
    "balanced-performance": True,
    "performance": True,
}

PROFILE_GOVERNOR = {
    "low-power": "powersave",
    "quiet": "powersave",
    "balanced": "powersave",
    "balanced-performance": "powersave",
    "performance": "performance",
}

SCALING_GOVERNOR = "cpufreq/scaling_governor"


def read_profile() -> str:
    try:
        return PLATFORM_PROFILE.read_text().strip()
    except (FileNotFoundError, PermissionError, OSError):
        return ""


def read_epp() -> str:
    try:
        return EPP_CPU0.read_text().strip()
    except (FileNotFoundError, PermissionError, OSError):
        return ""


def set_epp(value: str) -> bool:
    success = True
    for gov_file in sorted(CPU_BASE.glob("cpu[0-9]*/cpufreq/energy_performance_preference")):
        try:
            gov_file.write_text(value)
        except (PermissionError, OSError):
            success = False
    return success


def set_turbo(enabled: bool) -> bool:
    try:
        NO_TURBO.write_text("0" if enabled else "1")
        return True
    except (PermissionError, OSError):
        return False


def get_turbo() -> bool:
    try:
        val = NO_TURBO.read_text().strip()
        return val == "0"
    except (FileNotFoundError, PermissionError, OSError):
        return True


def get_governor() -> str:
    try:
        return (CPU_BASE / "cpu0" / SCALING_GOVERNOR).read_text().strip()
    except (FileNotFoundError, PermissionError, OSError):
        return "unknown"


def set_governor(value: str) -> bool:
    success = True
    for gov_file in sorted(CPU_BASE.glob("cpu[0-9]*/cpufreq/scaling_governor")):
        try:
            gov_file.write_text(value)
        except (PermissionError, OSError):
            success = False
    return success


def main():
    running = True

    def stop(signum, frame):
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    last_profile = ""
    last_log = {}
    print("EPP Override iniciado")

    while running:
        profile = read_profile()
        if not profile:
            time.sleep(1)
            continue

        expected_epp = PROFILE_TO_EPP.get(profile)
        expected_turbo = PROFILE_TURBO.get(profile)
        expected_gov = PROFILE_GOVERNOR.get(profile)

        if expected_epp or expected_turbo is not None or expected_gov:
            profile_changed = profile != last_profile
            if profile_changed:
                time.sleep(0.3)

            current_epp = read_epp()
            current_turbo = get_turbo()
            current_gov = get_governor()

            changed = []

            if expected_gov and current_gov != expected_gov:
                if set_governor(expected_gov):
                    changed.append(f"Gov: {current_gov} -> {expected_gov}")
                else:
                    changed.append(f"Gov: falha")

            if expected_turbo is not None and current_turbo != expected_turbo:
                if set_turbo(expected_turbo):
                    turbo_state = "ON" if expected_turbo else "OFF"
                    changed.append(f"Turbo: {turbo_state}")
                else:
                    changed.append(f"Turbo: falha")

            if expected_epp and current_epp != expected_epp:
                if set_epp(expected_epp):
                    changed.append(f"EPP: {current_epp} -> {expected_epp}")
                else:
                    changed.append(f"EPP: falha")

            current_state = (current_gov, current_epp, current_turbo)
            if changed:
                print(f"[{profile}] {', '.join(changed)}")
                last_log[profile] = current_state
            elif profile_changed and last_log.get(profile) != current_state:
                turbo_state = "ON" if current_turbo else "OFF"
                print(f"[{profile}] Gov={current_gov}, EPP={current_epp}, Turbo={turbo_state}")
                last_log[profile] = current_state

        last_profile = profile
        time.sleep(1)

    print("EPP Override finalizado")


if __name__ == "__main__":
    main()
