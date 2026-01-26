# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Fan Aggressor is a Linux application for controlling fan aggressiveness on Acer notebooks. It applies configurable offsets to the system's dynamic fan curve, allowing users to increase or decrease fan speeds while maintaining the manufacturer's automatic temperature response.

## Installation & Service Management

```bash
sudo ./install.sh                        # Install service
sudo systemctl start fan-aggressor       # Start service
sudo systemctl enable fan-aggressor      # Enable at boot
journalctl -u fan-aggressor -f           # View logs
```

## CLI Commands

```bash
fan_aggressor status              # Show current status and available backends
fan_aggressor set cpu +20         # Increase CPU fan aggressiveness by 20%
fan_aggressor set gpu -10         # Decrease GPU fan aggressiveness by 10%
fan_aggressor set both +15        # Set both fans to same offset
fan_aggressor backend ec          # Force specific backend (auto|ec|nekro|predator)
fan_aggressor enable              # Enable fan control
fan_aggressor disable             # Disable fan control
fan_aggressor daemon              # Run as daemon (requires root)
```

## Architecture

Single unified implementation (`fan_aggressor.py`) with pluggable backends:

| Backend | Control Method | Detection |
|---------|---------------|-----------|
| `ec` | EC registers via `/sys/kernel/debug/ec` + nekroctl | `/sys/kernel/debug/ec/ec0/io` exists |
| `nekro` | nekroctl only | `/home/fred/nekro-sense/tools/nekroctl.py` exists |
| `predator` | PredatorSense sysfs interface | `/sys/devices/platform/acer-wmi/predator_sense/fan_speed` exists |

Backend selection: `auto` (default) tries ec -> nekro -> predator in order.

### Core Classes

- **FanMonitor**: Reads fan speeds and temperatures from hwmon (`/sys/class/hwmon`, looks for "acer" or "coretemp")
- **ECBackend**: Direct EC register writes + nekroctl for fan duty cycle
- **NekroBackend**: Wrapper for external `nekroctl.py` tool
- **PredatorBackend**: Uses PredatorSense sysfs, maps offsets to modes (0-4)
- **FanAggressor**: Main daemon class handling config, temperature monitoring, and fan speed calculation

### Configuration

Config stored at `~/.config/fan-aggressor/config.json`:

| Key | Type | Range | Default | Description |
|-----|------|-------|---------|-------------|
| `cpu_offset` | int | -100 to +100 | 0 | CPU fan aggressiveness offset |
| `gpu_offset` | int | -100 to +100 | 0 | GPU fan aggressiveness offset |
| `enabled` | bool | - | false | Enable/disable fan control |
| `poll_interval` | float | - | 2.0 | Seconds between temperature checks |
| `backend` | string | auto/ec/nekro/predator | auto | Backend selection |

### Offset to Mode Mapping (PredatorBackend)

When using PredatorSense backend, offsets are converted to modes:

| Offset Range | Mode | Name |
|--------------|------|------|
| <= -50 | 1 | Quiet |
| -49 to -1 | 0 | Auto |
| 0 | 0 | Auto |
| 1 to 25 | 2 | Normal |
| 26 to 50 | 3 | Performance |
| > 50 | 4 | Turbo |

### External Dependencies

- `nekroctl.py` at `/home/fred/nekro-sense/tools/nekroctl.py` (for ec and nekro backends)
- `ec_sys` kernel module with write_support=1 (for ec backend)

## EC Register Map (Acer)

- `0x37`: Fan 1 (CPU) duty cycle
- `0x3A`: Fan 2 (GPU) duty cycle

## Requirements

- Linux kernel 3.17+
- lm-sensors
- Root permissions for daemon and EC access
