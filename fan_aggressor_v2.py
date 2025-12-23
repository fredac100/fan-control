#!/usr/bin/env python3

import os
import sys
import time
import json
import argparse
import signal
from pathlib import Path
from typing import Optional, Dict

CONFIG_FILE = Path.home() / ".config" / "fan-aggressor" / "config.json"
PID_FILE = "/var/run/fan-aggressor.pid"
FAN_SPEED_PATH = "/sys/devices/platform/acer-wmi/predator_sense/fan_speed"

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


class PredatorFanControl:
    def __init__(self):
        self.fan_speed_path = Path(FAN_SPEED_PATH)
        self.available = self.fan_speed_path.exists()

        if not self.available:
            print("Aviso: Interface PredatorSense não disponível")
            print(f"  Esperado em: {FAN_SPEED_PATH}")

    def get_current_mode(self) -> Optional[str]:
        if not self.available:
            return None
        try:
            with open(self.fan_speed_path) as f:
                return f.read().strip()
        except (IOError, PermissionError):
            return None

    def set_fan_mode(self, fan1_mode: int, fan2_mode: int) -> bool:
        if not self.available:
            return False

        fan1_mode = max(0, min(4, fan1_mode))
        fan2_mode = max(0, min(4, fan2_mode))

        try:
            with open(self.fan_speed_path, 'w') as f:
                f.write(f"{fan1_mode},{fan2_mode}")
            return True
        except (IOError, PermissionError) as e:
            print(f"Erro ao configurar modo: {e}")
            return False


class FanAggressor:
    MODE_NAMES = {
        0: "Auto",
        1: "Quiet",
        2: "Normal",
        3: "Performance",
        4: "Turbo"
    }

    def __init__(self, config_path: Path = CONFIG_FILE):
        self.config_path = config_path
        self.config = self.load_config()
        self.fan_controller = FanController()
        self.predator_control = PredatorFanControl()
        self.running = False

    def load_config(self) -> Dict:
        default_config = {
            "cpu_fan_mode": 0,
            "gpu_fan_mode": 0,
            "enabled": False,
            "monitor_interval": 5
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

    def set_mode(self, fan: str, mode: int):
        if mode < 0 or mode > 4:
            print("Erro: Modo deve estar entre 0 (Auto) e 4 (Turbo)")
            return False

        if fan == "cpu":
            self.config["cpu_fan_mode"] = mode
        elif fan == "gpu":
            self.config["gpu_fan_mode"] = mode
        elif fan == "both":
            self.config["cpu_fan_mode"] = mode
            self.config["gpu_fan_mode"] = mode

        self.save_config()
        return True

    def enable(self):
        self.config["enabled"] = True
        self.save_config()

    def disable(self):
        self.config["enabled"] = False
        self.save_config()

    def status(self):
        speeds = self.fan_controller.get_fan_speeds()
        temps = self.fan_controller.get_temps()
        current_mode = self.predator_control.get_current_mode()

        print(f"Status: {'Habilitado' if self.config['enabled'] else 'Desabilitado'}")
        print(f"CPU Fan Mode: {self.config['cpu_fan_mode']} ({self.MODE_NAMES[self.config['cpu_fan_mode']]})")
        print(f"GPU Fan Mode: {self.config['gpu_fan_mode']} ({self.MODE_NAMES[self.config['gpu_fan_mode']]})")
        print(f"\nModo atual do sistema: {current_mode}")
        print(f"\nVelocidades atuais:")
        print(f"  Fan 1 (CPU): {speeds.get('fan1', 0)} RPM")
        print(f"  Fan 2 (GPU): {speeds.get('fan2', 0)} RPM")
        print(f"\nTemperaturas:")
        for temp_name, temp_val in temps.items():
            print(f"  {temp_name}: {temp_val:.1f}°C")

        if self.predator_control.available:
            print(f"\nControle PredatorSense: Disponível")
        else:
            print(f"\nControle PredatorSense: Não disponível")

    def run_daemon(self):
        self.running = True
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

        try:
            with open(PID_FILE, 'w') as f:
                f.write(str(os.getpid()))
        except PermissionError:
            print("Aviso: Não foi possível criar arquivo PID. Execute com sudo.")

        print("Fan Aggressor daemon iniciado")
        print(f"CPU mode: {self.config['cpu_fan_mode']} ({self.MODE_NAMES[self.config['cpu_fan_mode']]})")
        print(f"GPU mode: {self.config['gpu_fan_mode']} ({self.MODE_NAMES[self.config['gpu_fan_mode']]})")

        if not self.predator_control.available:
            print("ERRO: PredatorSense não disponível. Daemon não pode funcionar.")
            return

        try:
            while self.running:
                if not self.config['enabled']:
                    time.sleep(1)
                    continue

                cpu_mode = self.config['cpu_fan_mode']
                gpu_mode = self.config['gpu_fan_mode']

                self.predator_control.set_fan_mode(cpu_mode, gpu_mode)

                time.sleep(self.config["monitor_interval"])

        finally:
            if os.path.exists(PID_FILE):
                os.remove(PID_FILE)

            self.predator_control.set_fan_mode(0, 0)
            print("\nModo restaurado para Auto (0,0)")

    def _signal_handler(self, signum, frame):
        self.running = False


def main():
    parser = argparse.ArgumentParser(
        description="Fan Aggressor V2 - Controle de modos de ventilador via PredatorSense"
    )

    subparsers = parser.add_subparsers(dest='command', help='Comandos disponíveis')

    set_parser = subparsers.add_parser('set', help='Define modo de ventilador')
    set_parser.add_argument('fan', choices=['cpu', 'gpu', 'both'], help='Qual ventilador')
    set_parser.add_argument('mode', type=int, help='Modo (0=Auto, 1=Quiet, 2=Normal, 3=Performance, 4=Turbo)')

    subparsers.add_parser('enable', help='Habilita controle')
    subparsers.add_parser('disable', help='Desabilita controle')
    subparsers.add_parser('status', help='Mostra status atual')
    subparsers.add_parser('daemon', help='Executa como daemon')

    args = parser.parse_args()

    aggressor = FanAggressor()

    if args.command == 'set':
        if aggressor.set_mode(args.fan, args.mode):
            mode_name = FanAggressor.MODE_NAMES[args.mode]
            print(f"Modo configurado: {args.fan} = {args.mode} ({mode_name})")
        else:
            sys.exit(1)

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
