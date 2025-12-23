#!/usr/bin/env python3

import os
import sys
import time
import json
import argparse
import signal
import subprocess
from pathlib import Path
from typing import Optional, Dict

CONFIG_FILE = Path.home() / ".config" / "fan-aggressor" / "config.json"
PID_FILE = "/var/run/fan-aggressor.pid"
NEKROCTL = "/home/fred/nekro-sense/tools/nekroctl.py"

class FanController:
    def __init__(self):
        self.hwmon_path = None
        self.find_hwmon_device()

    def find_hwmon_device(self):
        hwmon_base = Path("/sys/class/hwmon")
        for device in hwmon_base.iterdir():
            name_file = device / "name"
            if name_file.exists():
                with open(name_file) as f:
                    if f.read().strip() == "acer":
                        self.hwmon_path = device
                        return

        if not self.hwmon_path:
            raise Exception("Dispositivo Acer hwmon não encontrado")

    def get_fan_speeds(self) -> Dict[str, int]:
        speeds = {}
        for fan_num in [1, 2]:
            fan_file = self.hwmon_path / f"fan{fan_num}_input"
            if fan_file.exists():
                with open(fan_file) as f:
                    speeds[f"fan{fan_num}"] = int(f.read().strip())
        return speeds

    def get_temps(self) -> Dict[str, float]:
        temps = {}
        for temp_num in [1, 2, 3]:
            temp_file = self.hwmon_path / f"temp{temp_num}_input"
            if temp_file.exists():
                with open(temp_file) as f:
                    temps[f"temp{temp_num}"] = int(f.read().strip()) / 1000.0
        return temps


class NekroFanControl:
    def __init__(self):
        self.nekroctl = Path(NEKROCTL)
        self.available = self.nekroctl.exists()

        if not self.available:
            print(f"Aviso: nekroctl não encontrado em {NEKROCTL}")

    def set_fan_speed(self, cpu_percent: int, gpu_percent: int) -> bool:
        if not self.available:
            return False

        cpu_percent = max(0, min(100, cpu_percent))
        gpu_percent = max(0, min(100, gpu_percent))

        try:
            if cpu_percent == 0 and gpu_percent == 0:
                subprocess.run([str(self.nekroctl), "fan", "auto"],
                             check=True, capture_output=True)
            else:
                subprocess.run([str(self.nekroctl), "fan", "set",
                              str(cpu_percent), str(gpu_percent)],
                             check=True, capture_output=True)
            return True
        except subprocess.CalledProcessError as e:
            print(f"Erro ao definir velocidade: {e}")
            return False


class FanAggressor:
    def __init__(self, config_path: Path = CONFIG_FILE):
        self.config_path = config_path
        self.config = self.load_config()
        self.fan_controller = FanController()
        self.nekro_control = NekroFanControl()
        self.running = False
        self.is_auto_mode = True
        self.last_cpu_speed = 0
        self.last_gpu_speed = 0

    def load_config(self) -> Dict:
        default_config = {
            "cpu_fan_offset": 0,
            "gpu_fan_offset": 0,
            "enabled": False,
            "poll_interval": 2,
            "temp_source": "temp1"
        }

        if self.config_path.exists():
            try:
                with open(self.config_path) as f:
                    loaded = json.load(f)
                    default_config.update(loaded)
            except json.JSONDecodeError:
                pass

        return default_config

    def save_config(self):
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, 'w') as f:
            json.dump(self.config, f, indent=2)

    def set_offset(self, fan: str, offset: int):
        if fan == "cpu":
            self.config["cpu_fan_offset"] = offset
        elif fan == "gpu":
            self.config["gpu_fan_offset"] = offset
        elif fan == "both":
            self.config["cpu_fan_offset"] = offset
            self.config["gpu_fan_offset"] = offset
        self.save_config()

    def enable(self):
        self.config["enabled"] = True
        self.save_config()

    def disable(self):
        self.config["enabled"] = False
        self.save_config()

    def status(self):
        speeds = self.fan_controller.get_fan_speeds()
        temps = self.fan_controller.get_temps()

        print(f"Status: {'Habilitado' if self.config['enabled'] else 'Desabilitado'}")
        print(f"CPU Fan Offset: {self.config['cpu_fan_offset']:+d}%")
        print(f"GPU Fan Offset: {self.config['gpu_fan_offset']:+d}%")
        print(f"\nVelocidades atuais:")
        print(f"  Fan 1 (CPU): {speeds.get('fan1', 0)} RPM")
        print(f"  Fan 2 (GPU): {speeds.get('fan2', 0)} RPM")
        print(f"\nTemperaturas:")
        for temp_name, temp_val in temps.items():
            print(f"  {temp_name}: {temp_val:.1f}°C")

        if self.nekro_control.available:
            print(f"\nControle Nekro: Disponível")
        else:
            print(f"\nControle Nekro: Não disponível")

    def update_auto_mode(self, temp: float):
        if self.is_auto_mode:
            if temp >= 68:
                self.is_auto_mode = False
        else:
            if temp < 62:
                self.is_auto_mode = True

    def get_base_speed_for_temp(self, temp: float) -> int:
        if temp < 75:
            return 30
        elif temp < 85:
            return 50
        else:
            return 80

    def calculate_base_speed(self, temp: float) -> int:
        self.update_auto_mode(temp)
        if self.is_auto_mode:
            return 0
        return self.get_base_speed_for_temp(temp)

    def run_daemon(self):
        self.running = True
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

        try:
            with open(PID_FILE, 'w') as f:
                f.write(str(os.getpid()))
        except PermissionError:
            print("Aviso: Não foi possível criar arquivo PID. Execute com sudo.")

        print("Fan Aggressor (Nekro) daemon iniciado")
        print(f"CPU offset: {self.config['cpu_fan_offset']:+d}%")
        print(f"GPU offset: {self.config['gpu_fan_offset']:+d}%")

        if not self.nekro_control.available:
            print("ERRO: nekroctl não disponível. Daemon não pode funcionar.")
            return

        try:
            while self.running:
                if not self.config['enabled']:
                    time.sleep(1)
                    continue

                temps = self.fan_controller.get_temps()
                temp_source = self.config['temp_source']
                if temp_source not in temps:
                    print(f"Aviso: Sensor '{temp_source}' não encontrado, usando temp1")
                    temp_source = 'temp1'
                current_temp = temps.get(temp_source, 60.0)

                base_speed = self.calculate_base_speed(current_temp)
                base_cpu = base_speed
                base_gpu = base_speed

                target_cpu = min(100, max(0, base_cpu + self.config['cpu_fan_offset']))
                target_gpu = min(100, max(0, base_gpu + self.config['gpu_fan_offset']))

                if target_cpu != self.last_cpu_speed or target_gpu != self.last_gpu_speed:
                    self.nekro_control.set_fan_speed(target_cpu, target_gpu)
                    self.last_cpu_speed = target_cpu
                    self.last_gpu_speed = target_gpu

                time.sleep(self.config["poll_interval"])

        finally:
            if os.path.exists(PID_FILE):
                os.remove(PID_FILE)

            self.nekro_control.set_fan_speed(0, 0)
            print("\nModo restaurado para Auto")

    def _signal_handler(self, signum, frame):
        self.running = False


def main():
    parser = argparse.ArgumentParser(
        description="Fan Aggressor (Nekro) - Controle dinâmico usando nekroctl"
    )

    subparsers = parser.add_subparsers(dest='command', help='Comandos disponíveis')

    set_parser = subparsers.add_parser('set', help='Define offset de ventilador')
    set_parser.add_argument('fan', choices=['cpu', 'gpu', 'both'], help='Qual ventilador')
    set_parser.add_argument('offset', type=int, help='Offset em porcentagem (-100 a +100)')

    subparsers.add_parser('enable', help='Habilita controle')
    subparsers.add_parser('disable', help='Desabilita controle')
    subparsers.add_parser('status', help='Mostra status atual')
    subparsers.add_parser('daemon', help='Executa como daemon')

    args = parser.parse_args()

    aggressor = FanAggressor()

    if args.command == 'set':
        if args.offset < -100 or args.offset > 100:
            print("Erro: Offset deve estar entre -100 e +100")
            sys.exit(1)
        aggressor.set_offset(args.fan, args.offset)
        print(f"Offset configurado: {args.fan} = {args.offset:+d}%")

    elif args.command == 'enable':
        aggressor.enable()
        print("Fan Aggressor habilitado")

    elif args.command == 'disable':
        aggressor.disable()
        print("Fan Aggressor desabilitado")

    elif args.command == 'status':
        aggressor.status()

    elif args.command == 'daemon':
        if os.geteuid() != 0:
            print("Erro: Daemon deve ser executado como root")
            sys.exit(1)
        aggressor.run_daemon()

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
