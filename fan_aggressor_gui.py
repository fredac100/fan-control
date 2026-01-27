#!/usr/bin/env python3

from __future__ import annotations

import os
import sys
import json
import subprocess
import threading
from pathlib import Path
from typing import Optional, Dict, Any, Callable

try:
    import gi
    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    from gi.repository import Adw, Gtk, Gio, GLib
except Exception as e:
    sys.stderr.write(
        f"Failed to import GTK4/libadwaita: {e}\n"
        "Install: sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1\n"
    )
    raise

CONFIG_FILE = Path("/etc/fan-aggressor/config.json")
STATE_FILE = Path("/var/run/fan-aggressor.state")
PID_FILE = Path("/var/run/fan-aggressor.pid")

FAN_RPM_MIN = 0
FAN_RPM_MAX = 7500


def load_config() -> Dict[str, Any]:
    default = {
        "cpu_fan_offset": 0,
        "gpu_fan_offset": 0,
        "enabled": False,
        "poll_interval": 1.0,
        "hybrid_mode": True,
        "temp_threshold_engage": 70,
        "temp_threshold_disengage": 65
    }
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE) as f:
                loaded = json.load(f)
                for key in default:
                    if key in loaded:
                        default[key] = loaded[key]
        except (json.JSONDecodeError, PermissionError):
            pass
    return default


def save_config(config: Dict[str, Any]) -> bool:
    try:
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=2)
        return True
    except PermissionError:
        return False


def save_config_privileged(config: Dict[str, Any], callback: Callable[[bool], None]):
    def _worker():
        content = json.dumps(config, indent=2)
        try:
            proc = subprocess.run(
                ["sudo", "-n", "tee", str(CONFIG_FILE)],
                input=content,
                capture_output=True,
                text=True
            )
            if proc.returncode == 0:
                GLib.idle_add(callback, True)
                return
        except Exception:
            pass

        try:
            proc = subprocess.run(
                ["pkexec", "tee", str(CONFIG_FILE)],
                input=content,
                capture_output=True,
                text=True
            )
            GLib.idle_add(callback, proc.returncode == 0)
        except Exception:
            GLib.idle_add(callback, False)

    threading.Thread(target=_worker, daemon=True).start()


def get_state() -> Optional[Dict[str, Any]]:
    if not STATE_FILE.exists():
        return None
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except (json.JSONDecodeError, PermissionError):
        return None


def is_daemon_running() -> bool:
    if not PID_FILE.exists():
        return False
    try:
        with open(PID_FILE) as f:
            pid = int(f.read().strip())
        os.kill(pid, 0)
        return True
    except (ValueError, ProcessLookupError, PermissionError):
        return False


def get_service_status() -> str:
    try:
        result = subprocess.run(
            ["systemctl", "is-active", "fan-aggressor.service"],
            capture_output=True, text=True
        )
        return result.stdout.strip()
    except Exception:
        return "unknown"


def restart_service(callback: Callable[[bool, str], None]):
    def _worker():
        try:
            proc = subprocess.run(
                ["sudo", "-n", "systemctl", "restart", "fan-aggressor.service"],
                capture_output=True, text=True
            )
            if proc.returncode == 0:
                GLib.idle_add(callback, True, "Service restarted")
                return
        except Exception:
            pass

        try:
            proc = subprocess.run(
                ["pkexec", "systemctl", "restart", "fan-aggressor.service"],
                capture_output=True, text=True
            )
            if proc.returncode == 0:
                GLib.idle_add(callback, True, "Service restarted")
            else:
                GLib.idle_add(callback, False, proc.stderr or "Failed to restart")
        except Exception as e:
            GLib.idle_add(callback, False, str(e))

    threading.Thread(target=_worker, daemon=True).start()


class FanMonitor:
    def __init__(self):
        self.hwmon_path = None
        self.coretemp_path = None
        self._find_hwmon_devices()

    def _find_hwmon_devices(self):
        hwmon_base = Path("/sys/class/hwmon")
        if not hwmon_base.exists():
            return
        for device in hwmon_base.iterdir():
            name_file = device / "name"
            if name_file.exists():
                with open(name_file) as f:
                    name = f.read().strip()
                    if name == "acer":
                        self.hwmon_path = device
                    elif name == "coretemp":
                        self.coretemp_path = device

    def get_fan_speeds(self) -> Dict[str, int]:
        speeds = {}
        if self.hwmon_path:
            for fan_num in [1, 2]:
                fan_file = self.hwmon_path / f"fan{fan_num}_input"
                if fan_file.exists():
                    try:
                        with open(fan_file) as f:
                            speeds[f"fan{fan_num}"] = int(f.read().strip())
                    except (ValueError, PermissionError):
                        pass
        return speeds

    def get_temps(self) -> Dict[str, float]:
        temps = {}
        if self.hwmon_path:
            for temp_num in [1, 2, 3]:
                temp_file = self.hwmon_path / f"temp{temp_num}_input"
                if temp_file.exists():
                    try:
                        with open(temp_file) as f:
                            temps[f"temp{temp_num}"] = int(f.read().strip()) / 1000.0
                    except (ValueError, PermissionError):
                        pass

        if self.coretemp_path and not temps:
            for temp_file in sorted(self.coretemp_path.glob("temp*_input")):
                try:
                    with open(temp_file) as f:
                        temp_name = temp_file.stem.replace("_input", "")
                        temps[temp_name] = int(f.read().strip()) / 1000.0
                except (ValueError, PermissionError):
                    pass
        return temps

    def get_max_temp(self) -> float:
        temps = self.get_temps()
        return max(temps.values()) if temps else 0.0


def rpm_to_percent(rpm: int) -> int:
    if rpm <= FAN_RPM_MIN:
        return 0
    if rpm >= FAN_RPM_MAX:
        return 100
    return int((rpm - FAN_RPM_MIN) / (FAN_RPM_MAX - FAN_RPM_MIN) * 100)


class FanAggressorApp(Adw.Application):
    def __init__(self):
        super().__init__(
            application_id="com.fancontrol.aggressor",
            flags=Gio.ApplicationFlags.FLAGS_NONE
        )
        self.monitor = FanMonitor()
        self.config = load_config()
        self.updating = False
        self.refresh_timeout_id = None

    def do_activate(self):
        win = self.props.active_window
        if not win:
            win = self._build_window()
        win.present()

    def _build_window(self) -> Adw.ApplicationWindow:
        win = Adw.ApplicationWindow(application=self)
        win.set_title("Fan Aggressor")
        win.set_default_size(420, 580)
        win.set_resizable(True)

        icon_theme = Gtk.IconTheme.get_for_display(win.get_display())
        icon_theme.add_search_path("/usr/share/icons/hicolor/scalable/apps")

        try:
            win.set_icon_name("fan-aggressor")
        except Exception:
            pass

        header = Adw.HeaderBar()

        refresh_btn = Gtk.Button(icon_name="view-refresh-symbolic")
        refresh_btn.set_tooltip_text("Refresh")
        refresh_btn.connect("clicked", lambda _: self._refresh_all())
        header.pack_end(refresh_btn)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        content.append(header)

        scroll = Gtk.ScrolledWindow(vexpand=True, hexpand=True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        main_box.set_margin_start(12)
        main_box.set_margin_end(12)
        main_box.set_margin_top(12)
        main_box.set_margin_bottom(12)

        self._build_status_group(main_box)
        self._build_control_group(main_box)
        self._build_offset_group(main_box)
        self._build_threshold_group(main_box)

        scroll.set_child(main_box)
        content.append(scroll)
        win.set_content(content)

        win.connect("close-request", self._on_close)

        key_controller = Gtk.EventControllerKey()
        key_controller.connect("key-pressed", self._on_key_pressed)
        win.add_controller(key_controller)

        self._refresh_all()
        self.refresh_timeout_id = GLib.timeout_add(2000, self._auto_refresh)

        return win

    def _on_key_pressed(self, controller, keyval, keycode, state):
        if keyval in (Gtk.accelerator_parse("q")[0], Gtk.accelerator_parse("Escape")[0]):
            self.props.active_window.close()
            return True
        return False

    def _build_status_group(self, parent: Gtk.Box):
        group = Adw.PreferencesGroup(title="Status")

        self.status_row = Adw.ActionRow(title="Service")
        self.status_label = Gtk.Label(xalign=1)
        self.status_label.add_css_class("dim-label")
        self.status_row.add_suffix(self.status_label)
        group.add(self.status_row)

        self.mode_row = Adw.ActionRow(title="Mode")
        self.mode_label = Gtk.Label(xalign=1)
        self.mode_label.add_css_class("dim-label")
        self.mode_row.add_suffix(self.mode_label)
        group.add(self.mode_row)

        self.temp_row = Adw.ActionRow(title="Temperature")
        self.temp_label = Gtk.Label(xalign=1)
        self.temp_label.add_css_class("dim-label")
        self.temp_row.add_suffix(self.temp_label)
        group.add(self.temp_row)

        self.fan_row = Adw.ActionRow(title="Fan Speeds")
        self.fan_label = Gtk.Label(xalign=1)
        self.fan_label.add_css_class("dim-label")
        self.fan_row.add_suffix(self.fan_label)
        group.add(self.fan_row)

        self.boost_row = Adw.ActionRow(title="Boost Status")
        self.boost_label = Gtk.Label(xalign=1)
        self.boost_label.add_css_class("dim-label")
        self.boost_row.add_suffix(self.boost_label)
        group.add(self.boost_row)

        parent.append(group)

    def _build_control_group(self, parent: Gtk.Box):
        group = Adw.PreferencesGroup(title="Control")

        self.enabled_row = Adw.SwitchRow(
            title="Enabled",
            subtitle="Enable fan aggressor control"
        )
        self.enabled_row.set_active(self.config.get("enabled", False))
        self.enabled_row.connect("notify::active", self._on_enabled_changed)
        group.add(self.enabled_row)

        self.hybrid_row = Adw.SwitchRow(
            title="Hybrid Mode",
            subtitle="Use temperature thresholds (recommended)"
        )
        self.hybrid_row.set_active(self.config.get("hybrid_mode", True))
        self.hybrid_row.connect("notify::active", self._on_config_changed)
        group.add(self.hybrid_row)

        restart_row = Adw.ActionRow(title="Restart Service")
        restart_btn = Gtk.Button(label="Restart", valign=Gtk.Align.CENTER)
        restart_btn.add_css_class("suggested-action")
        restart_btn.connect("clicked", self._on_restart_clicked)
        restart_row.add_suffix(restart_btn)
        restart_row.set_activatable_widget(restart_btn)
        group.add(restart_row)

        parent.append(group)

    def _build_offset_group(self, parent: Gtk.Box):
        group = Adw.PreferencesGroup(
            title="Fan Offset",
            description="Percentage added to base fan curve"
        )

        self.link_offsets = Adw.SwitchRow(title="Link CPU and GPU")
        self.link_offsets.set_active(True)
        self.link_offsets.connect("notify::active", self._on_link_changed)
        group.add(self.link_offsets)

        self.cpu_offset_row = Adw.SpinRow(
            title="CPU Offset",
            adjustment=Gtk.Adjustment(
                lower=-50, upper=100, step_increment=5, page_increment=10,
                value=self.config.get("cpu_fan_offset", 0)
            )
        )
        self.cpu_offset_row.connect("notify::value", self._on_cpu_offset_changed)
        group.add(self.cpu_offset_row)

        self.gpu_offset_row = Adw.SpinRow(
            title="GPU Offset",
            adjustment=Gtk.Adjustment(
                lower=-50, upper=100, step_increment=5, page_increment=10,
                value=self.config.get("gpu_fan_offset", 0)
            )
        )
        self.gpu_offset_row.connect("notify::value", self._on_gpu_offset_changed)
        group.add(self.gpu_offset_row)

        self._sync_link_visibility()

        parent.append(group)

    def _build_threshold_group(self, parent: Gtk.Box):
        group = Adw.PreferencesGroup(
            title="Temperature Thresholds",
            description="When to activate/deactivate boost (hybrid mode)"
        )

        self.engage_row = Adw.SpinRow(
            title="Engage Temperature",
            subtitle="Activate boost when temp reaches this",
            adjustment=Gtk.Adjustment(
                lower=40, upper=95, step_increment=5, page_increment=10,
                value=self.config.get("temp_threshold_engage", 70)
            )
        )
        self.engage_row.connect("notify::value", self._on_config_changed)
        group.add(self.engage_row)

        self.disengage_row = Adw.SpinRow(
            title="Disengage Temperature",
            subtitle="Return to auto when temp falls below this",
            adjustment=Gtk.Adjustment(
                lower=35, upper=90, step_increment=5, page_increment=10,
                value=self.config.get("temp_threshold_disengage", 65)
            )
        )
        self.disengage_row.connect("notify::value", self._on_config_changed)
        group.add(self.disengage_row)

        parent.append(group)

    def _sync_link_visibility(self):
        linked = self.link_offsets.get_active()
        self.gpu_offset_row.set_visible(not linked)
        if linked:
            self.cpu_offset_row.set_title("Fan Offset (Both)")
        else:
            self.cpu_offset_row.set_title("CPU Offset")

    def _on_link_changed(self, row, _):
        self._sync_link_visibility()
        if self.link_offsets.get_active():
            self.gpu_offset_row.set_value(self.cpu_offset_row.get_value())
            self._on_config_changed(None, None)

    def _on_cpu_offset_changed(self, row, _):
        if self.updating:
            return
        if self.link_offsets.get_active():
            self.updating = True
            self.gpu_offset_row.set_value(row.get_value())
            self.updating = False
        self._on_config_changed(None, None)

    def _on_gpu_offset_changed(self, row, _):
        if self.updating:
            return
        self._on_config_changed(None, None)

    def _on_enabled_changed(self, row, _):
        self._on_config_changed(None, None)

    def _on_config_changed(self, widget, _):
        if self.updating:
            return

        self.config["enabled"] = self.enabled_row.get_active()
        self.config["hybrid_mode"] = self.hybrid_row.get_active()
        self.config["cpu_fan_offset"] = int(self.cpu_offset_row.get_value())
        self.config["gpu_fan_offset"] = int(self.gpu_offset_row.get_value())
        self.config["temp_threshold_engage"] = int(self.engage_row.get_value())
        self.config["temp_threshold_disengage"] = int(self.disengage_row.get_value())

        if self.config["temp_threshold_disengage"] >= self.config["temp_threshold_engage"]:
            self.config["temp_threshold_disengage"] = self.config["temp_threshold_engage"] - 5

        self._save_config()

    def _save_config(self):
        if save_config(self.config):
            return

        def on_saved(success):
            if not success:
                dialog = Adw.MessageDialog(
                    transient_for=self.props.active_window,
                    heading="Error",
                    body="Failed to save configuration"
                )
                dialog.add_response("ok", "OK")
                dialog.present()

        save_config_privileged(self.config, on_saved)

    def _on_restart_clicked(self, button):
        button.set_sensitive(False)

        def on_done(success, msg):
            button.set_sensitive(True)
            self._refresh_all()
            if not success:
                dialog = Adw.MessageDialog(
                    transient_for=self.props.active_window,
                    heading="Error",
                    body=msg
                )
                dialog.add_response("ok", "OK")
                dialog.present()

        restart_service(on_done)

    def _refresh_all(self):
        status = get_service_status()
        running = is_daemon_running()

        if status == "active" and running:
            self.status_label.set_text("Running")
            self.status_label.remove_css_class("error")
            self.status_label.add_css_class("success")
        elif status == "active":
            self.status_label.set_text("Starting...")
            self.status_label.remove_css_class("error")
            self.status_label.remove_css_class("success")
        else:
            self.status_label.set_text("Stopped")
            self.status_label.add_css_class("error")
            self.status_label.remove_css_class("success")

        self.config = load_config()
        self.updating = True
        self.enabled_row.set_active(self.config.get("enabled", False))
        self.hybrid_row.set_active(self.config.get("hybrid_mode", True))
        self.cpu_offset_row.set_value(self.config.get("cpu_fan_offset", 0))
        self.gpu_offset_row.set_value(self.config.get("gpu_fan_offset", 0))
        self.engage_row.set_value(self.config.get("temp_threshold_engage", 70))
        self.disengage_row.set_value(self.config.get("temp_threshold_disengage", 65))
        self.updating = False

        if self.config.get("hybrid_mode", True):
            self.mode_label.set_text("Hybrid (temp-based)")
        else:
            self.mode_label.set_text("Fixed Curve")

        temp = self.monitor.get_max_temp()
        self.temp_label.set_text(f"{temp:.0f}°C")

        speeds = self.monitor.get_fan_speeds()
        if speeds:
            fan1 = speeds.get('fan1', 0)
            fan2 = speeds.get('fan2', 0)
            p1 = rpm_to_percent(fan1)
            p2 = rpm_to_percent(fan2)
            self.fan_label.set_text(f"CPU: {fan1} RPM ({p1}%) | GPU: {fan2} RPM ({p2}%)")
        else:
            self.fan_label.set_text("N/A")

        state = get_state()
        if state and state.get("active"):
            offset = state.get("cpu_offset", 0)
            base = state.get("base_cpu", 0)
            self.boost_label.set_text(f"Active: base {base}% + {offset}% = {base + offset}%")
            self.boost_label.remove_css_class("dim-label")
            self.boost_label.add_css_class("accent")
        else:
            engage = self.config.get("temp_threshold_engage", 70)
            if temp < engage:
                self.boost_label.set_text(f"Inactive (temp < {engage}°C)")
            else:
                self.boost_label.set_text("Waiting...")
            self.boost_label.remove_css_class("accent")
            self.boost_label.add_css_class("dim-label")

    def _auto_refresh(self) -> bool:
        self._refresh_all()
        return True

    def _on_close(self, window):
        if self.refresh_timeout_id:
            GLib.source_remove(self.refresh_timeout_id)
            self.refresh_timeout_id = None
        return False


def main():
    app = FanAggressorApp()
    return app.run(sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
