#!/usr/bin/env python3

import os
import sys
import time
import json
import fcntl
import argparse
import signal
import subprocess
from pathlib import Path
from typing import Dict, Optional

for _p in [str(Path(__file__).parent), "/usr/local/lib/fan-aggressor"]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from fan_monitor import FanMonitor, rpm_to_percent as rpm_to_duty
from cpu_power import (
    apply_cpu_power, get_current_governor, get_turbo_enabled,
    get_current_epp
)

CONFIG_FILE = Path("/etc/fan-aggressor/config.json")
PID_FILE = "/var/run/fan-aggressor.pid"
STATE_FILE = Path("/var/run/fan-aggressor.state")

ALLOWED_NEKROCTL_DIRS = [
    "/usr/local/bin",
    "/usr/bin",
    "/opt/nekro-sense/tools",
]

DEFAULT_NEKROCTL_CANDIDATES = [
    "/usr/local/bin/nekroctl.py",
    "/usr/local/bin/nekroctl",
    "/usr/bin/nekroctl",
    "/opt/nekro-sense/tools/nekroctl.py",
]

SUBPROCESS_TIMEOUT = 5
MAX_FAN_FAILURES = 3
MIN_SANE_TEMP = 5
MAX_SANE_TEMP = 115


def _is_nekroctl_path_allowed(path: str) -> bool:
    try:
        resolved = Path(path).resolve()
        return any(
            resolved.parent == Path(d).resolve()
            for d in ALLOWED_NEKROCTL_DIRS
        )
    except (ValueError, OSError):
        return False


def _find_nekroctl_in_home() -> Optional[str]:
    import glob
    import re
    patterns = [
        "/home/*/nekro-sense/tools/nekroctl.py",
        "/home/*/*/nekro-sense/tools/nekroctl.py",
    ]
    valid_re = re.compile(r"^/home/[a-zA-Z0-9_.-]+(/[a-zA-Z0-9_.-]+)?/nekro-sense/tools/nekroctl\.py$")
    for pattern in patterns:
        for match in glob.glob(pattern):
            resolved = str(Path(match).resolve())
            if valid_re.match(resolved) and os.access(resolved, os.X_OK):
                return resolved
    return None


def _find_nekroctl(config: Dict) -> Optional[str]:
    explicit = config.get("nekroctl_path")
    if explicit:
        if _is_nekroctl_path_allowed(explicit) and os.path.exists(explicit) and os.access(explicit, os.X_OK):
            return explicit
        return None

    env_path = os.getenv("NEKROCTL")
    if env_path and _is_nekroctl_path_allowed(env_path) and os.path.exists(env_path) and os.access(env_path, os.X_OK):
        return env_path

    for candidate in DEFAULT_NEKROCTL_CANDIDATES:
        if os.path.exists(candidate) and os.access(candidate, os.X_OK):
            return candidate

    return _find_nekroctl_in_home()


def set_fan_speed(nekroctl: str, cpu: int, gpu: int) -> bool:
    cpu = max(0, min(100, cpu))
    gpu = max(0, min(100, gpu))
    try:
        subprocess.run([nekroctl, "fan", "set", str(cpu), str(gpu)],
                      check=True, capture_output=True, timeout=SUBPROCESS_TIMEOUT)
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        return False


def set_fan_auto(nekroctl: str) -> bool:
    try:
        subprocess.run([nekroctl, "fan", "auto"], check=True, capture_output=True,
                      timeout=SUBPROCESS_TIMEOUT)
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError):
        return False


def write_state(active: bool, cpu_offset: int = 0, gpu_offset: int = 0, base_cpu: int = 0, base_gpu: int = 0):
    try:
        state = {
            "active": active,
            "cpu_offset": cpu_offset,
            "gpu_offset": gpu_offset,
            "base_cpu": base_cpu,
            "base_gpu": base_gpu
        }
        fd = os.open(str(STATE_FILE), os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o644)
        with os.fdopen(fd, 'w') as f:
            json.dump(state, f)
    except (PermissionError, OSError):
        pass


def clear_state():
    try:
        if STATE_FILE.exists():
            STATE_FILE.unlink()
    except PermissionError:
        pass


def get_fan_speed(nekroctl: str) -> tuple:
    try:
        result = subprocess.run([nekroctl, "fan", "get"],
                               capture_output=True, text=True, check=True,
                               timeout=SUBPROCESS_TIMEOUT)
        parts = result.stdout.strip().split(",")
        if len(parts) == 2:
            return int(parts[0]), int(parts[1])
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, ValueError, IndexError, OSError):
        pass
    return None, None


def temp_to_duty(temp: float) -> int:
    if temp < 60:
        return 0
    elif temp < 70:
        return int((temp - 60) * 1.5)
    elif temp < 80:
        return int(15 + (temp - 70) * 2)
    elif temp < 90:
        return int(35 + (temp - 80) * 2.5)
    elif temp < 100:
        return int(60 + (temp - 90) * 4)
    else:
        return 100


class FanAggressor:
    def __init__(self, config_path: Path = CONFIG_FILE):
        self.config_path = config_path
        self.config = self._load_config()
        self.monitor = FanMonitor()
        self.running = False
        self.last_cpu = -1
        self.last_gpu = -1
        self.is_boosting = False
        self.snapshot_cpu = 0
        self.snapshot_gpu = 0
        self.snapshot_temp = 0
        self.fan_failures = 0
        self.nekroctl_path = _find_nekroctl(self.config)
        self.nekroctl_missing_logged = False

    def _load_config(self) -> Dict:
        default = {
            "cpu_fan_offset": 0,
            "gpu_fan_offset": 0,
            "enabled": False,
            "poll_interval": 1.0,
            "hybrid_mode": True,
            "temp_threshold_engage": 70,
            "temp_threshold_disengage": 65,
            "cpu_governor": "powersave",
            "cpu_turbo_enabled": True,
            "cpu_epp": "balance_performance",
            "cpu_platform_profile": "",
            "nekroctl_path": None,
            "failsafe_mode": "auto",
            "cpu_rapl_pl1_w": None,
            "cpu_rapl_pl2_w": None,
            "cpu_max_freq_mhz": None
        }
        if self.config_path.exists():
            try:
                with open(self.config_path) as f:
                    loaded = json.load(f)
                    for key in default.keys():
                        if key in loaded:
                            default[key] = loaded[key]
            except json.JSONDecodeError:
                if hasattr(self, "config"):
                    return self._sanitize_config(self.config)
                return self._sanitize_config(default)
        return self._sanitize_config(default)

    @staticmethod
    def _safe_int(value, default: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _sanitize_config(self, config: Dict) -> Dict:
        config["cpu_fan_offset"] = self._safe_int(config.get("cpu_fan_offset"), 0)
        config["gpu_fan_offset"] = self._safe_int(config.get("gpu_fan_offset"), 0)
        config["cpu_fan_offset"] = max(-100, min(100, config["cpu_fan_offset"]))
        config["gpu_fan_offset"] = max(-100, min(100, config["gpu_fan_offset"]))

        try:
            poll_interval = float(config.get("poll_interval", 1.0))
        except (TypeError, ValueError):
            poll_interval = 1.0
        if poll_interval <= 0:
            poll_interval = 1.0
        config["poll_interval"] = poll_interval

        try:
            engage = int(config.get("temp_threshold_engage", 70))
        except (TypeError, ValueError):
            engage = 70
        try:
            disengage = int(config.get("temp_threshold_disengage", 65))
        except (TypeError, ValueError):
            disengage = 65
        if disengage >= engage:
            disengage = engage - 5
        config["temp_threshold_engage"] = engage
        config["temp_threshold_disengage"] = disengage

        failsafe = config.get("failsafe_mode", "auto")
        if failsafe not in ("auto", "max"):
            failsafe = "auto"
        config["failsafe_mode"] = failsafe

        nekroctl_path = config.get("nekroctl_path")
        if nekroctl_path and not _is_nekroctl_path_allowed(nekroctl_path):
            nekroctl_path = None
        config["nekroctl_path"] = nekroctl_path if nekroctl_path else None

        pl1 = config.get("cpu_rapl_pl1_w")
        if pl1 is not None:
            try:
                pl1 = int(pl1)
                config["cpu_rapl_pl1_w"] = max(15, min(200, pl1))
            except (TypeError, ValueError):
                config["cpu_rapl_pl1_w"] = None

        pl2 = config.get("cpu_rapl_pl2_w")
        if pl2 is not None:
            try:
                pl2 = int(pl2)
                config["cpu_rapl_pl2_w"] = max(20, min(250, pl2))
            except (TypeError, ValueError):
                config["cpu_rapl_pl2_w"] = None

        if (config.get("cpu_rapl_pl1_w") is not None
                and config.get("cpu_rapl_pl2_w") is not None
                and config["cpu_rapl_pl2_w"] < config["cpu_rapl_pl1_w"]):
            config["cpu_rapl_pl2_w"] = config["cpu_rapl_pl1_w"]

        max_freq = config.get("cpu_max_freq_mhz")
        if max_freq is not None:
            try:
                max_freq = int(max_freq)
                config["cpu_max_freq_mhz"] = max(800, min(5500, max_freq))
            except (TypeError, ValueError):
                config["cpu_max_freq_mhz"] = None

        return config

    def _save_config(self):
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.config_path.with_suffix(".tmp")
        with open(tmp_path, 'w') as f:
            json.dump(self.config, f, indent=2)
        os.replace(tmp_path, self.config_path)

    def set_offset(self, fan: str, offset: int):
        offset = max(-100, min(100, offset))
        if fan in ("cpu", "both"):
            self.config["cpu_fan_offset"] = offset
        if fan in ("gpu", "both"):
            self.config["gpu_fan_offset"] = offset
        self._save_config()

    def enable(self):
        self.config["enabled"] = True
        self._save_config()

    def disable(self):
        self.config["enabled"] = False
        self._save_config()
        if self.nekroctl_path:
            set_fan_auto(self.nekroctl_path)

    def status(self):
        speeds = self.monitor.get_fan_speeds()
        temps = self.monitor.get_temps()
        fan_cpu, fan_gpu = (None, None)
        if self.nekroctl_path:
            fan_cpu, fan_gpu = get_fan_speed(self.nekroctl_path)

        print(f"Status: {'ATIVO' if self.config['enabled'] else 'INATIVO'}")
        hybrid = self.config.get('hybrid_mode', True)
        print(f"Modo: {'HIBRIDO' if hybrid else 'CURVA FIXA'}")
        print(f"\nOffsets configurados:")
        print(f"  CPU: {self.config['cpu_fan_offset']:+d}%")
        print(f"  GPU: {self.config['gpu_fan_offset']:+d}%")

        if hybrid:
            print(f"\nThresholds (modo hibrido):")
            print(f"  Ativar boost: >= {self.config.get('temp_threshold_engage', 70)}°C")
            print(f"  Voltar auto:  <  {self.config.get('temp_threshold_disengage', 65)}°C")

        if fan_cpu is not None and fan_gpu is not None:
            print(f"\nDuty atual (nekroctl):")
            print(f"  CPU: {fan_cpu}% {'(auto)' if fan_cpu == 0 else ''}")
            print(f"  GPU: {fan_gpu}% {'(auto)' if fan_gpu == 0 else ''}")

        if speeds:
            print(f"\nVelocidades:")
            fan1_rpm = speeds.get('fan1', 0)
            fan2_rpm = speeds.get('fan2', 0)
            print(f"  Fan 1 (CPU): {fan1_rpm} RPM (~{rpm_to_duty(fan1_rpm)}% estimado)")
            print(f"  Fan 2 (GPU): {fan2_rpm} RPM (~{rpm_to_duty(fan2_rpm)}% estimado)")

        print(f"\nCPU Power:")
        print(f"  Governor: {get_current_governor()}")
        print(f"  Turbo Boost: {'ON' if get_turbo_enabled() else 'OFF'}")
        print(f"  EPP: {get_current_epp()}")

        if temps:
            cg = self.monitor.get_cpu_gpu_temps()
            print(f"\nTemperaturas:")
            if cg["cpu"] is not None:
                print(f"  CPU: {cg['cpu']:.1f}°C")
            if cg["gpu"] is not None:
                print(f"  GPU: {cg['gpu']:.1f}°C")
            for name, val in temps.items():
                if name not in ("temp1", "temp2"):
                    print(f"  {name}: {val:.1f}°C")
            max_temp = self.monitor.get_max_temp()
            if max_temp is not None:
                print(f"  Max: {max_temp:.1f}°C")
            else:
                print("  Max: indisponível")

            if hybrid and speeds:
                fan1_rpm = speeds.get('fan1', 0)
                fan2_rpm = speeds.get('fan2', 0)
                base_cpu = rpm_to_duty(fan1_rpm)
                base_gpu = rpm_to_duty(fan2_rpm)
                print(f"\nModo hibrido (baseado no RPM atual):")
                print(f"  CPU: {base_cpu}% + {self.config['cpu_fan_offset']:+d}% = {min(100, base_cpu + self.config['cpu_fan_offset'])}%")
                print(f"  GPU: {base_gpu}% + {self.config['gpu_fan_offset']:+d}% = {min(100, base_gpu + self.config['gpu_fan_offset'])}%")
                if max_temp >= self.config.get('temp_threshold_engage', 70):
                    print(f"  -> Boost ATIVARIA (temp {max_temp:.0f}°C >= {self.config.get('temp_threshold_engage', 70)}°C)")
                else:
                    print(f"  -> Em modo AUTO (temp {max_temp:.0f}°C < {self.config.get('temp_threshold_engage', 70)}°C)")
            else:
                if max_temp is not None:
                    base_duty = temp_to_duty(max_temp)
                    print(f"\nCurva fixa para {max_temp:.0f}°C: {base_duty}%")
                    print(f"Com offset +{self.config['cpu_fan_offset']}%: {min(100, base_duty + self.config['cpu_fan_offset'])}%")
                else:
                    print("\nCurva fixa: temperatura indisponível")

    def _get_cpu_power_state(self) -> tuple:
        return (
            self.config.get("cpu_governor"),
            self.config.get("cpu_turbo_enabled"),
            self.config.get("cpu_epp"),
            self.config.get("cpu_platform_profile", ""),
            self.config.get("cpu_rapl_pl1_w"),
            self.config.get("cpu_rapl_pl2_w"),
            self.config.get("cpu_max_freq_mhz"),
        )

    def _acquire_pid_lock(self):
        self._pid_fd = os.open(PID_FILE, os.O_CREAT | os.O_RDWR, 0o644)
        try:
            fcntl.flock(self._pid_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(self._pid_fd)
            self._pid_fd = None
            print("Erro: daemon já está rodando")
            sys.exit(1)
        os.ftruncate(self._pid_fd, 0)
        os.write(self._pid_fd, str(os.getpid()).encode())
        os.fsync(self._pid_fd)

    def _release_pid_lock(self):
        if hasattr(self, '_pid_fd') and self._pid_fd is not None:
            try:
                fcntl.flock(self._pid_fd, fcntl.LOCK_UN)
                os.close(self._pid_fd)
            except OSError:
                pass
        if os.path.exists(PID_FILE):
            try:
                os.remove(PID_FILE)
            except OSError:
                pass

    def daemon(self):
        self.running = True
        self.is_boosting = False

        try:
            self._acquire_pid_lock()
        except PermissionError:
            pass

        hybrid = self.config.get('hybrid_mode', True)
        print(f"Fan Aggressor iniciado ({'HIBRIDO' if hybrid else 'CURVA FIXA'})")
        print(f"CPU offset: {self.config['cpu_fan_offset']:+d}%")
        print(f"GPU offset: {self.config['gpu_fan_offset']:+d}%")

        apply_cpu_power(self.config)
        self.last_cpu_power = self._get_cpu_power_state()
        print(f"CPU Power: governor={self.config.get('cpu_governor')}, "
              f"turbo={'on' if self.config.get('cpu_turbo_enabled', True) else 'off'}, "
              f"epp={self.config.get('cpu_epp')}")

        if hybrid:
            print(f"Threshold engage: {self.config.get('temp_threshold_engage', 70)}°C")
            print(f"Threshold disengage: {self.config.get('temp_threshold_disengage', 65)}°C")
            if self.nekroctl_path:
                set_fan_auto(self.nekroctl_path)
            clear_state()
            print("Iniciando em modo AUTO...")
            time.sleep(2)

        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

        try:
            while self.running:
                try:
                    self.config = self._load_config()
                except Exception:
                    pass
                self.nekroctl_path = _find_nekroctl(self.config)
                hybrid = self.config.get('hybrid_mode', True)

                current_cpu_power = self._get_cpu_power_state()
                if current_cpu_power != self.last_cpu_power:
                    apply_cpu_power(self.config)
                    self.last_cpu_power = current_cpu_power
                    print(f"CPU Power atualizado: governor={self.config.get('cpu_governor')}, "
                          f"turbo={'on' if self.config.get('cpu_turbo_enabled', True) else 'off'}, "
                          f"epp={self.config.get('cpu_epp')}")

                if not self.config["enabled"]:
                    if self.last_cpu != -1 or self.is_boosting:
                        if self.nekroctl_path:
                            set_fan_auto(self.nekroctl_path)
                        clear_state()
                        self.last_cpu = -1
                        self.last_gpu = -1
                        self.is_boosting = False
                        self.fan_failures = 0
                    time.sleep(1)
                    continue

                if not self.nekroctl_path:
                    if not self.nekroctl_missing_logged:
                        print("Erro: nekroctl não encontrado. Verifique 'nekroctl_path' no config ou variável NEKROCTL.")
                        self.nekroctl_missing_logged = True
                    time.sleep(2)
                    continue
                self.nekroctl_missing_logged = False

                cg_temps = self.monitor.get_cpu_gpu_temps()
                _valid = [t for t in cg_temps.values() if t is not None]
                temp = max(_valid) if _valid else None
                if temp is None or temp < MIN_SANE_TEMP or temp > MAX_SANE_TEMP:
                    if self.config.get("failsafe_mode") == "max":
                        if set_fan_speed(self.nekroctl_path, 100, 100):
                            write_state(True, 0, 0, 100, 100)
                        else:
                            print("Falha ao aplicar fail-safe MAX")
                    else:
                        if not set_fan_auto(self.nekroctl_path):
                            print("Falha ao aplicar fail-safe AUTO")
                        clear_state()
                    time.sleep(self.config["poll_interval"])
                    continue
                cpu_offset = self.config["cpu_fan_offset"]
                gpu_offset = self.config["gpu_fan_offset"]
                threshold_engage = self.config.get('temp_threshold_engage', 70)
                threshold_disengage = self.config.get('temp_threshold_disengage', 65)
                if threshold_disengage >= threshold_engage:
                    threshold_disengage = threshold_engage - 5

                if hybrid:
                    if not self.is_boosting and temp >= threshold_engage:
                        speeds = self.monitor.get_fan_speeds()
                        self.snapshot_cpu = rpm_to_duty(speeds.get('fan1', 0)) if speeds else 0
                        self.snapshot_gpu = rpm_to_duty(speeds.get('fan2', 0)) if speeds else 0
                        self.snapshot_temp = temp
                        self.is_boosting = True
                        cpu_t = cg_temps.get("cpu")
                        gpu_t = cg_temps.get("gpu")
                        temp_str = f"CPU {cpu_t:.0f}°C / GPU {gpu_t:.0f}°C" if cpu_t is not None and gpu_t is not None else f"{temp:.0f}°C"
                        print(f"[{temp_str}] Offset ATIVADO (base snapshot: CPU {self.snapshot_cpu}%, GPU {self.snapshot_gpu}%)")
                    elif self.is_boosting and temp < threshold_disengage:
                        self.is_boosting = False
                        self.snapshot_cpu = 0
                        self.snapshot_gpu = 0
                        self.snapshot_temp = 0
                        set_fan_auto(self.nekroctl_path)
                        clear_state()
                        self.last_cpu = -1
                        self.last_gpu = -1
                        cpu_t = cg_temps.get("cpu")
                        gpu_t = cg_temps.get("gpu")
                        temp_str = f"CPU {cpu_t:.0f}°C / GPU {gpu_t:.0f}°C" if cpu_t is not None and gpu_t is not None else f"{temp:.0f}°C"
                        print(f"[{temp_str}] Offset DESATIVADO, voltando ao AUTO")
                        time.sleep(self.config["poll_interval"])
                        continue
                    if self.is_boosting:
                        new_cpu = max(0, min(100, self.snapshot_cpu + cpu_offset))
                        new_gpu = max(0, min(100, self.snapshot_gpu + gpu_offset))

                        if new_cpu != self.last_cpu or new_gpu != self.last_gpu:
                            if set_fan_speed(self.nekroctl_path, new_cpu, new_gpu):
                                self.fan_failures = 0
                                write_state(True, cpu_offset, gpu_offset, self.snapshot_cpu, self.snapshot_gpu)
                                self.last_cpu = new_cpu
                                self.last_gpu = new_gpu
                                cpu_t = cg_temps.get("cpu")
                                gpu_t = cg_temps.get("gpu")
                                temp_str = f"CPU {cpu_t:.0f}°C / GPU {gpu_t:.0f}°C" if cpu_t is not None and gpu_t is not None else f"{temp:.0f}°C"
                                print(f"[{temp_str}] Fans: CPU {new_cpu}% (base {self.snapshot_cpu}% + {cpu_offset}%), GPU {new_gpu}% (base {self.snapshot_gpu}% + {gpu_offset}%)")
                            else:
                                self.fan_failures += 1
                                print("Falha ao setar fans")
                    else:
                        time.sleep(self.config["poll_interval"])
                        continue
                else:
                    base_duty = temp_to_duty(temp)
                    new_cpu = max(0, min(100, base_duty + cpu_offset))
                    new_gpu = max(0, min(100, base_duty + gpu_offset))

                    if new_cpu != self.last_cpu or new_gpu != self.last_gpu:
                        if set_fan_speed(self.nekroctl_path, new_cpu, new_gpu):
                            self.fan_failures = 0
                            write_state(True, cpu_offset, gpu_offset, base_duty, base_duty)
                            self.last_cpu = new_cpu
                            self.last_gpu = new_gpu
                        else:
                            self.fan_failures += 1
                            print("Falha ao setar fans (curva fixa)")

                if self.fan_failures >= MAX_FAN_FAILURES:
                    print("Múltiplas falhas ao controlar fans; retornando ao AUTO")
                    set_fan_auto(self.nekroctl_path)
                    clear_state()
                    self.last_cpu = -1
                    self.last_gpu = -1
                    self.is_boosting = False
                    self.fan_failures = 0
                    time.sleep(5)
                    continue

                time.sleep(self.config["poll_interval"])

        finally:
            if self.nekroctl_path:
                set_fan_auto(self.nekroctl_path)
            clear_state()
            self._release_pid_lock()
            print("\nDaemon finalizado - modo auto restaurado")

    def _signal_handler(self, signum, frame):
        self.running = False


def main():
    parser = argparse.ArgumentParser(
        description="Fan Aggressor - Controle de agressividade dos ventiladores",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
  fan_aggressor status              Mostra status atual
  fan_aggressor set cpu +20         Aumenta 20% sobre curva base
  fan_aggressor set gpu -10         Diminui 10% sobre curva base
  fan_aggressor set both +15        Define ambos os fans
  fan_aggressor enable              Ativa controle
  fan_aggressor disable             Desativa (volta ao auto)
  fan_aggressor daemon              Inicia daemon (requer root)

MODO HIBRIDO (padrao):
  - Sistema fica em AUTO ate temperatura >= threshold_engage (70C)
  - Quando ativa, le RPM atual e adiciona offset configurado
  - Volta ao AUTO quando temp < threshold_disengage (65C)
  - Nao substitui a curva do sistema, apenas adiciona boost quando precisa

  Exemplo com RPM atual = 3000 (~55%) e offset = +10%:
    Final: 65%

MODO CURVA FIXA (hybrid_mode=false no config):
  Curva base (similar ao fabricante):
    <45C  ->  0%
    45-55C -> 0-30%
    55-65C -> 30-60%
    65-75C -> 60-80%
    75-85C -> 80-100%
    >85C  -> 100%

Config: /etc/fan-aggressor/config.json
  hybrid_mode: true/false
  temp_threshold_engage: 70 (graus para ativar boost)
  temp_threshold_disengage: 65 (graus para voltar ao auto)
""")

    sub = parser.add_subparsers(dest="cmd", metavar="COMANDO")

    p_set = sub.add_parser("set", help="Define offset de ventilador")
    p_set.add_argument("fan", choices=["cpu", "gpu", "both"], help="Ventilador alvo")
    p_set.add_argument("offset", type=int, help="Offset (-100 a +100)")

    sub.add_parser("enable", help="Ativa controle")
    sub.add_parser("disable", help="Desativa controle")
    sub.add_parser("status", help="Mostra status")
    sub.add_parser("daemon", help="Executa daemon (root)")

    args = parser.parse_args()
    aggressor = FanAggressor()

    if args.cmd == "set":
        if not -100 <= args.offset <= 100:
            print("Erro: Offset deve estar entre -100 e +100")
            sys.exit(1)
        aggressor.set_offset(args.fan, args.offset)
        print(f"Offset {args.fan}: {args.offset:+d}%")

    elif args.cmd == "enable":
        aggressor.enable()
        print("Controle ativado")

    elif args.cmd == "disable":
        aggressor.disable()
        print("Controle desativado")

    elif args.cmd == "status":
        aggressor.status()

    elif args.cmd == "daemon":
        if os.geteuid() != 0:
            print("Erro: Daemon requer root")
            sys.exit(1)
        aggressor.daemon()

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
