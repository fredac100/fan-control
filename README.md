# Fan Aggressor

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.8+](https://img.shields.io/badge/Python-3.8%2B-green.svg)](https://www.python.org/)
[![Ubuntu 24.04+](https://img.shields.io/badge/Ubuntu-24.04%2B-orange.svg)](https://ubuntu.com/)

Fan control and CPU power management for **Acer Predator** notebooks on Linux.
Built on top of [nekro-sense](https://github.com/fredac100/nekro-sense) (kernel module for Acer WMI hardware access).

### What does Fan Aggressor actually do?

Fan Aggressor is **not** a traditional fan controller that replaces your fan curve with fixed speeds. Instead, it works **on top of** the manufacturer's automatic fan curve.

Think of it like this: your laptop already knows how to manage its fans — it ramps them up when things get hot and slows them down when they cool off. Fan Aggressor doesn't interfere with that intelligence. What it does is give the fans a **standing instruction**: *"when the CPU hits 70°C, take whatever speed you're already running at and add 25% more."*

The key difference:
- **Traditional fan control**: "Run at 3000 RPM." (ignores what the system thinks)
- **Fan Aggressor**: "Whatever speed you'd normally be at, push 25% harder." (respects and amplifies the system's own decisions)

When the temperature drops back below the threshold, Fan Aggressor steps aside completely and lets the manufacturer's curve run untouched. The result is a fan behavior that still feels natural — it just reacts more aggressively (or more gently, with a negative offset) within the temperature range you define.

<p align="center">
  <img src="docs/screenshot.png" alt="Fan Aggressor GUI" width="700">
  <br>
  <em>Real-time monitoring with hybrid fan control active</em>
</p>

## Quick Install (one-liner)

Automatically installs everything: nekro-sense (kernel module), Fan Aggressor (CLI + daemon), and the graphical interface.

```bash
git clone https://github.com/fredac100/fan-control.git && cd fan-control && sudo bash setup.sh
```

Or if you already have the repository cloned:

```bash
cd fan-control
sudo bash setup.sh
```

This installs and configures:
- **nekro-sense** — Kernel module for hardware communication
- **fan_aggressor** — CLI and fan control daemon
- **epp_override** — EPP correction for the Predator button
- **Graphical interface** — GTK4/Libadwaita with application menu icon
- **systemd services** — Everything enabled and running automatically

## After Installing

### Graphical Interface (recommended)

Search for **"Fan Aggressor"** in your application menu or run:

```bash
fan-aggressor-gui
```

### Command Line

```bash
fan_aggressor status              # Show status, temperatures and speeds
fan_aggressor set both +15        # Adjust fan offset (+15%)
fan_aggressor set cpu +20         # Set CPU and GPU independently
fan_aggressor set gpu +10
fan_aggressor enable              # Enable fan control
fan_aggressor disable             # Disable (returns to automatic)
```

### Logs

```bash
journalctl -u fan-aggressor -f
```

## Features

### Graphical Interface (GTK4/Libadwaita)
- Two-column layout: Fans (left) + CPU Power (right)
- Real-time status: temperatures, RPM, boost status
- Sliders for offset, toggles for enable/hybrid mode
- 5 Power Profiles with one click
- Single authentication — prompts for password only once per session

### Fan Control
- **Hybrid Mode** — Captures manufacturer's fan curve, adds offset only when needed
- **Configurable offset** — CPU and GPU independent (-100% to +100%)
- **Custom thresholds** — Control when boost activates/deactivates
- **Automatic daemon** — Continuously monitors temperature and adjusts fans

### CPU Power Management
- **Governor** — `powersave` or `performance`
- **Intel Turbo Boost** — ON/OFF
- **EPP** — 5 energy efficiency levels
- **TDP Sustentado (PL1)** — Sustained power limit via Intel RAPL (15–200W)
- **TDP Burst (PL2)** — Short-term burst power limit via Intel RAPL (20–250W)
- **Max Frequency** — Per-core scaling limit (800–5500 MHz)
- **EPP Override** — Corrects physical Predator button mapping

### Power Profiles

| Profile | Governor | Turbo | EPP | PL1 | PL2 | Max Freq | Use Case |
|---------|----------|-------|-----|-----|-----|----------|----------|
| **Deep Sleep** | powersave | OFF | power | 15W | 20W | 2000 MHz | Extreme battery saving |
| **Stealth Mode** | powersave | OFF | power | 25W | 35W | 3200 MHz | Silent operation |
| **Cruise Control** | powersave | ON | balance_power | 45W | 65W | 4400 MHz | Daily use |
| **Boost Drive** | powersave | ON | balance_performance | 65W | 100W | 5300 MHz | Productivity |
| **Nitro Overdrive** | performance | ON | performance | 125W | 157W | 5500 MHz | Gaming |

> **Deep Sleep** vs **Stealth Mode**: both disable turbo and use maximum power saving, but Deep Sleep also forces the `low-power` platform profile, which may further reduce hardware clocks and fan activity at the firmware level. Deep Sleep additionally caps TDP to 15W — ideal for reading or writing on battery.

> **TDP controls** use Intel RAPL (Running Average Power Limit) via `/sys/class/powercap`. PL1 sets the sustained power budget; PL2 allows short bursts above PL1. The GUI enforces PL2 ≥ PL1 automatically.

## How It Works

![How it works](docs/how-it-works.png)

### Hybrid Mode (Recommended)

1. System stays in **AUTO mode** while temperature is low (< threshold)
2. When the **engage threshold** is reached (default: 70°C), captures a snapshot of current RPM
3. Applies **manufacturer's curve + configured offset**
4. When temperature drops below the **disengage threshold** (default: 65°C), returns to AUTO

The system **does not replace** the manufacturer's fan curve — it only **adds** the offset on top of it.

## Configuration

File: `/etc/fan-aggressor/config.json`

```json
{
  "cpu_fan_offset": 0,
  "gpu_fan_offset": 0,
  "enabled": true,
  "poll_interval": 1.0,
  "hybrid_mode": true,
  "temp_threshold_engage": 70,
  "temp_threshold_disengage": 65,
  "cpu_governor": "powersave",
  "cpu_turbo_enabled": true,
  "cpu_epp": "balance_performance",
  "cpu_rapl_pl1_w": null,
  "cpu_rapl_pl2_w": null,
  "cpu_max_freq_mhz": null
}
```

The daemon automatically reloads the config — no need to restart the service.

### Main Parameters

| Parameter | Description | Range/Values |
|-----------|-------------|--------------|
| `cpu_fan_offset` | CPU offset | -100 to +100 |
| `gpu_fan_offset` | GPU offset | -100 to +100 |
| `enabled` | Enable control | true/false |
| `hybrid_mode` | Use thresholds | true/false |
| `temp_threshold_engage` | Temperature to activate boost | °C (default: 70) |
| `temp_threshold_disengage` | Temperature to return to auto | °C (default: 65) |
| `cpu_governor` | CPU governor | powersave, performance |
| `cpu_turbo_enabled` | Turbo Boost | true/false |
| `cpu_epp` | Energy Performance Preference | power, balance_power, balance_performance, performance |
| `cpu_rapl_pl1_w` | Sustained TDP (PL1) | 15–200 W (null = hardware default) |
| `cpu_rapl_pl2_w` | Burst TDP (PL2) | 20–250 W (null = hardware default) |
| `cpu_max_freq_mhz` | Maximum CPU frequency | 800–5500 MHz (null = hardware default) |

## Use Cases

**Gaming** — Nitro Overdrive profile + offset +20% to +30%:
```bash
fan_aggressor set both +25
```

**Silent work** — Stealth Mode profile + offset 0%:
```bash
fan_aggressor set both 0
```

**Daily use** — Cruise Control profile + offset +10% to +15%:
```bash
fan_aggressor set both +10
```

## Manual Installation (step by step)

If you prefer to install manually instead of the automated script:

### 1. nekro-sense (prerequisite)

```bash
git clone https://github.com/fredac100/nekro-sense.git
cd nekro-sense
make
sudo make install
sudo modprobe nekro_sense
```

### 2. Fan Aggressor

```bash
git clone https://github.com/fredac100/fan-control.git
cd fan-control
sudo ./install.sh
```

### 3. GUI Dependencies

```bash
sudo apt install libgtk-4-1 libadwaita-1-0 python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-adw-1
```

> `install.sh` already enables and starts all services, installs the application menu icon, and configures everything.

## Troubleshooting

### Fans not responding
```bash
lsmod | grep nekro                    # Is nekro-sense loaded?
systemctl status fan-aggressor        # Is the daemon running?
journalctl -u fan-aggressor | grep nekroctl  # Is nekroctl found?
```

### Fans ramp up to 100%
Update to the latest version:
```bash
cd fan-control && git pull
sudo ./install.sh
```

### EPP not changing
Use governor `powersave` — with `performance`, EPP is managed by the driver.

### Sensors not working
```bash
cat /sys/class/hwmon/hwmon*/name      # Should show "acer" or "coretemp"
```

## Uninstall

```bash
sudo ./uninstall.sh
```

Or manually:

```bash
sudo systemctl stop fan-aggressor epp-override
sudo systemctl disable fan-aggressor epp-override
sudo rm /etc/systemd/system/fan-aggressor.service /etc/systemd/system/epp-override.service
sudo rm /usr/local/bin/fan_aggressor /usr/local/bin/fan-aggressor-gui /usr/local/bin/epp_override
sudo rm -rf /usr/local/lib/fan-aggressor /etc/fan-aggressor
sudo rm /usr/share/polkit-1/actions/com.fancontrol.aggressor.policy
rm ~/.local/share/applications/fan-aggressor.desktop
sudo systemctl daemon-reload
```

## Architecture

```
fan-aggressor-gui (GTK4) ──► fan-aggressor-helper (pkexec) ──┐
                                                              │
fan_aggressor (CLI) ──► fan_aggressor.py (daemon) ───► cpu_power.py
                                    │                         │
                                    ▼                         ▼
                            nekroctl.py                sysfs (cpufreq)
                                    │
                                    ▼
                          nekro-sense (kernel module)
                                    │
                                    ▼
                              Hardware (WMI)
```

## Requirements

- **OS**: Linux with kernel 5.x+ (tested on Ubuntu 24.04+)
- **CPU**: Intel (for Turbo Boost and EPP via `intel_pstate`)
- **Python**: 3.8+
- **Hardware**: Requires [nekro-sense](https://github.com/fredac100/nekro-sense) kernel module

## Compatibility

Developed and tested on the **Acer Predator Helios Neo 16 (PHN16-72)**. May work on other Acer Predator models supported by [nekro-sense](https://github.com/fredac100/nekro-sense) — if you get it running on a different model, PRs and reports are welcome.

## License

MIT
