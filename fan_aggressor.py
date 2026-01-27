#!/usr/bin/env python3

import os
import sys
import time
import json
import argparse
import signal
import subprocess
from pathlib import Path
from typing import Dict

from fan_monitor import FanMonitor, rpm_to_percent as rpm_to_duty

NEKROCTL = "/home/fred/nekro-sense/tools/nekroctl.py"
CONFIG_FILE = Path("/etc/fan-aggressor/config.json")
PID_FILE = "/var/run/fan-aggressor.pid"
STATE_FILE = Path("/var/run/fan-aggressor.state")


def set_fan_speed(cpu: int, gpu: int) -> bool:
    cpu = max(0, min(100, cpu))
    gpu = max(0, min(100, gpu))
    try:
        subprocess.run([NEKROCTL, "fan", "set", str(cpu), str(gpu)],
                      check=True, capture_output=True)
        return True
    except subprocess.CalledProcessError:
        return False


def set_fan_auto() -> bool:
    try:
        subprocess.run([NEKROCTL, "fan", "auto"], check=True, capture_output=True)
        return True
    except subprocess.CalledProcessError:
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
        with open(STATE_FILE, 'w') as f:
            json.dump(state, f)
    except PermissionError:
        pass


def clear_state():
    try:
        if STATE_FILE.exists():
            STATE_FILE.unlink()
    except PermissionError:
        pass


def get_fan_speed() -> tuple:
    try:
        result = subprocess.run([NEKROCTL, "fan", "get"],
                               capture_output=True, text=True, check=True)
        parts = result.stdout.strip().split(",")
        if len(parts) == 2:
            return int(parts[0]), int(parts[1])
    except (subprocess.CalledProcessError, ValueError, IndexError, OSError):
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

    def _load_config(self) -> Dict:
        default = {
            "cpu_fan_offset": 0,
            "gpu_fan_offset": 0,
            "enabled": False,
            "poll_interval": 1.0,
            "hybrid_mode": True,
            "temp_threshold_engage": 70,
            "temp_threshold_disengage": 65
        }
        if self.config_path.exists():
            try:
                with open(self.config_path) as f:
                    loaded = json.load(f)
                    for key in default.keys():
                        if key in loaded:
                            default[key] = loaded[key]
            except json.JSONDecodeError:
                pass
        return default

    def _save_config(self):
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, 'w') as f:
            json.dump(self.config, f, indent=2)

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
        set_fan_auto()

    def status(self):
        speeds = self.monitor.get_fan_speeds()
        temps = self.monitor.get_temps()
        fan_cpu, fan_gpu = get_fan_speed()

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

        if temps:
            print(f"\nTemperaturas:")
            for name, val in temps.items():
                print(f"  {name}: {val:.1f}°C")
            max_temp = self.monitor.get_max_temp()
            print(f"  Max: {max_temp:.1f}°C")

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
                base_duty = temp_to_duty(max_temp)
                print(f"\nCurva fixa para {max_temp:.0f}°C: {base_duty}%")
                print(f"Com offset +{self.config['cpu_fan_offset']}%: {min(100, base_duty + self.config['cpu_fan_offset'])}%")

    def daemon(self):
        self.running = True
        self.is_boosting = False
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

        try:
            with open(PID_FILE, 'w') as f:
                f.write(str(os.getpid()))
        except PermissionError:
            pass

        hybrid = self.config.get('hybrid_mode', True)
        print(f"Fan Aggressor iniciado ({'HIBRIDO' if hybrid else 'CURVA FIXA'})")
        print(f"CPU offset: {self.config['cpu_fan_offset']:+d}%")
        print(f"GPU offset: {self.config['gpu_fan_offset']:+d}%")
        if hybrid:
            print(f"Threshold engage: {self.config.get('temp_threshold_engage', 70)}°C")
            print(f"Threshold disengage: {self.config.get('temp_threshold_disengage', 65)}°C")
            set_fan_auto()
            clear_state()
            print("Iniciando em modo AUTO...")
            time.sleep(2)

        try:
            while self.running:
                self.config = self._load_config()
                hybrid = self.config.get('hybrid_mode', True)

                if not self.config["enabled"]:
                    if self.last_cpu != -1 or self.is_boosting:
                        set_fan_auto()
                        clear_state()
                        self.last_cpu = -1
                        self.last_gpu = -1
                        self.is_boosting = False
                    time.sleep(1)
                    continue

                temp = self.monitor.get_max_temp()
                cpu_offset = self.config["cpu_fan_offset"]
                gpu_offset = self.config["gpu_fan_offset"]
                threshold_engage = self.config.get('temp_threshold_engage', 70)
                threshold_disengage = self.config.get('temp_threshold_disengage', 65)
                if threshold_disengage >= threshold_engage:
                    threshold_disengage = threshold_engage - 5

                if hybrid:
                    if not self.is_boosting and temp >= threshold_engage:
                        self.is_boosting = True
                        print(f"[{temp:.0f}°C] Boost ATIVADO")
                    elif self.is_boosting and temp < threshold_disengage:
                        self.is_boosting = False
                        set_fan_auto()
                        clear_state()
                        self.last_cpu = -1
                        self.last_gpu = -1
                        print(f"[{temp:.0f}°C] Voltando ao AUTO")
                        time.sleep(self.config["poll_interval"])
                        continue

                    if self.is_boosting:
                        base_duty = temp_to_duty(temp)
                        new_cpu = max(0, min(100, base_duty + cpu_offset))
                        new_gpu = max(0, min(100, base_duty + gpu_offset))

                        if new_cpu != self.last_cpu or new_gpu != self.last_gpu:
                            set_fan_speed(new_cpu, new_gpu)
                            write_state(True, cpu_offset, gpu_offset, base_duty, base_duty)
                            self.last_cpu = new_cpu
                            self.last_gpu = new_gpu
                            print(f"[{temp:.0f}°C] Fans: CPU {new_cpu}% ({base_duty}%+{cpu_offset}), GPU {new_gpu}% ({base_duty}%+{gpu_offset})")
                    else:
                        time.sleep(self.config["poll_interval"])
                        continue
                else:
                    base_duty = temp_to_duty(temp)
                    new_cpu = max(0, min(100, base_duty + cpu_offset))
                    new_gpu = max(0, min(100, base_duty + gpu_offset))

                    if new_cpu != self.last_cpu or new_gpu != self.last_gpu:
                        set_fan_speed(new_cpu, new_gpu)
                        write_state(True, cpu_offset, gpu_offset, base_duty, base_duty)
                        self.last_cpu = new_cpu
                        self.last_gpu = new_gpu

                time.sleep(self.config["poll_interval"])

        finally:
            set_fan_auto()
            clear_state()
            if os.path.exists(PID_FILE):
                os.remove(PID_FILE)
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
