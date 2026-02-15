# Fan Aggressor

Fan control and CPU power management for the **Acer Predator Helios Neo 16 (PHN16-72)** on Linux.

> **Warning**: Developed and tested exclusively on the **Acer Predator PHN16-72**. No guarantees for other models.

![Fan Aggressor GUI](docs/screenshot.png)

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
- **EPP Override** — Corrects physical Predator button mapping

### Power Profiles

| Profile | Governor | Turbo | EPP | Use Case |
|---------|----------|-------|-----|----------|
| **Deep Sleep** | powersave | OFF | power | Extreme battery saving |
| **Stealth Mode** | powersave | OFF | power | Silent operation |
| **Cruise Control** | powersave | ON | balance_power | Daily use |
| **Boost Drive** | powersave | ON | balance_performance | Productivity |
| **Nitro Overdrive** | performance | ON | performance | Gaming |

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
  "cpu_epp": "balance_performance"
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

- **Notebook**: Acer Predator Helios Neo 16 (PHN16-72)
- **OS**: Linux with kernel 5.x+ (tested on Ubuntu 24.04+)
- **CPU**: Intel (for Turbo Boost and EPP via `intel_pstate`)
- **Python**: 3.8+

## License

MIT
