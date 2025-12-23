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

NEKROCTL = "/home/fred/nekro-sense/tools/nekroctl.py"

CONFIG_FILE = Path.home() / ".config" / "fan-aggressor" / "config.json"
PID_FILE = "/var/run/fan-aggressor.pid"

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


class ECFanControl:
    EC_ACPI_PATH = "/sys/kernel/debug/ec/ec0/io"
    FAN1_OFFSET = 0x37
    FAN2_OFFSET = 0x3A
    FAN_MODE_OFFSET = 0x03
    FAN_MODE_MANUAL = 0x00

    def __init__(self):
        self.ec_available = os.path.exists(self.EC_ACPI_PATH)
        if not self.ec_available:
            print("Aviso: Acesso ao EC não disponível em /sys/kernel/debug/ec")
            print("Para habilitar, execute: sudo modprobe ec_sys write_support=1")

    def read_ec(self, offset: int) -> Optional[int]:
        if not self.ec_available:
            return None
        try:
            with open(self.EC_ACPI_PATH, 'rb') as f:
                f.seek(offset)
                return ord(f.read(1))
        except (IOError, PermissionError):
            return None

    def write_ec(self, offset: int, value: int) -> bool:
        if not self.ec_available:
            return False
        try:
            with open(self.EC_ACPI_PATH, 'r+b') as f:
                f.seek(offset)
                f.write(bytes([value]))
                f.flush()
            return True
        except (IOError, PermissionError) as e:
            print(f"Erro ao escrever no EC: {e}")
            return False

    def set_fan_duty(self, fan_num: int, duty: int) -> bool:
        duty = max(0, min(100, duty))
        offset = self.FAN1_OFFSET if fan_num == 1 else self.FAN2_OFFSET
        return self.write_ec(offset, duty)

    def set_both_fans(self, cpu_duty: int, gpu_duty: int) -> bool:
        cpu_duty = max(0, min(100, cpu_duty))
        gpu_duty = max(0, min(100, gpu_duty))
        try:
            subprocess.run([NEKROCTL, "fan", "set", str(cpu_duty), str(gpu_duty)],
                          check=True, capture_output=True)
            self.write_ec(self.FAN1_OFFSET, cpu_duty)
            self.write_ec(self.FAN2_OFFSET, gpu_duty)
            return True
        except subprocess.CalledProcessError:
            return False

    def set_auto_mode(self) -> bool:
        try:
            subprocess.run([NEKROCTL, "fan", "auto"], check=True, capture_output=True)
            return True
        except subprocess.CalledProcessError:
            return False


class FanAggressor:
    def __init__(self, config_path: Path = CONFIG_FILE):
        self.config_path = config_path
        self.config = self.load_config()
        self.fan_controller = FanController()
        self.ec_control = ECFanControl()
        self.running = False
        self.baseline_map = {}

    def load_config(self) -> Dict:
        default_config = {
            "cpu_fan_offset": 0,
            "gpu_fan_offset": 0,
            "enabled": False,
            "poll_interval": 0.15,
            "use_ec_control": True
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

        if self.ec_control.ec_available:
            print(f"\nControle EC: Disponível")
        else:
            print(f"\nControle EC: Não disponível")
            print(f"  Para habilitar: sudo modprobe ec_sys write_support=1")

    def calculate_fan_speed(self, temp: float, offset: int) -> int:
        temp_adjusted = temp + (offset * 0.3)

        if temp_adjusted < 50:
            speed = 0
        elif temp_adjusted < 60:
            speed = int(25 + (temp_adjusted - 50) * 1.5)
        elif temp_adjusted < 70:
            speed = int(40 + (temp_adjusted - 60) * 2)
        elif temp_adjusted < 80:
            speed = int(60 + (temp_adjusted - 70) * 2)
        else:
            speed = int(80 + (temp_adjusted - 80) * 2)

        return max(0, min(100, speed))

    def run_daemon(self):
        self.running = True
        self.last_cpu_speed = -1
        self.last_gpu_speed = -1

        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

        try:
            with open(PID_FILE, 'w') as f:
                f.write(str(os.getpid()))
        except PermissionError:
            print("Aviso: Não foi possível criar arquivo PID. Execute com sudo.")

        print("Fan Aggressor daemon iniciado")
        print(f"CPU offset: {self.config['cpu_fan_offset']:+d}%")
        print(f"GPU offset: {self.config['gpu_fan_offset']:+d}%")

        try:
            while self.running:
                self.config = self.load_config()

                if not self.config["enabled"]:
                    time.sleep(1)
                    continue

                if self.ec_control.ec_available:
                    temps = self.fan_controller.get_temps()
                    current_temp = temps.get('temp1', 60.0)

                    cpu_duty = self.calculate_fan_speed(current_temp, self.config['cpu_fan_offset'])
                    gpu_duty = self.calculate_fan_speed(current_temp, self.config['gpu_fan_offset'])

                    if cpu_duty != self.last_cpu_speed or gpu_duty != self.last_gpu_speed:
                        self.ec_control.set_both_fans(cpu_duty, gpu_duty)
                        self.last_cpu_speed = cpu_duty
                        self.last_gpu_speed = gpu_duty

                time.sleep(self.config["poll_interval"])

        finally:
            self.ec_control.set_auto_mode()
            if os.path.exists(PID_FILE):
                os.remove(PID_FILE)
            print("\nFan Aggressor daemon finalizado - modo auto restaurado")

    def _signal_handler(self, signum, frame):
        self.running = False


def main():
    parser = argparse.ArgumentParser(
        description="Fan Aggressor - Controle de agressividade dos ventiladores"
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
