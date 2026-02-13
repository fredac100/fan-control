#!/usr/bin/env python3

import sys
import time
import signal
from pathlib import Path

PLATFORM_PROFILE = Path("/sys/firmware/acpi/platform_profile")
EPP_CPU0 = Path("/sys/devices/system/cpu/cpu0/cpufreq/energy_performance_preference")
CPU_BASE = Path("/sys/devices/system/cpu")

PROFILE_TO_EPP = {
    "low-power": "power",
    "quiet": "balance_power",
    "balanced": "balance_power",
    "balanced-performance": "balance_performance",
    "performance": "performance",
}


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


def main():
    running = True

    def stop(signum, frame):
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    last_profile = ""
    print("EPP Override iniciado")

    while running:
        profile = read_profile()
        if profile and profile != last_profile:
            expected_epp = PROFILE_TO_EPP.get(profile)
            if expected_epp:
                current_epp = read_epp()
                time.sleep(0.3)
                current_epp = read_epp()
                if current_epp != expected_epp:
                    if set_epp(expected_epp):
                        print(f"[{profile}] EPP: {current_epp} -> {expected_epp}")
                    else:
                        print(f"[{profile}] Falha ao definir EPP {expected_epp}")
                else:
                    print(f"[{profile}] EPP já correto: {current_epp}")
            last_profile = profile
        time.sleep(1)

    print("EPP Override finalizado")


if __name__ == "__main__":
    main()
