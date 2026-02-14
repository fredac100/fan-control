#!/usr/bin/env python3

from __future__ import annotations

import os
import sys
import json
import subprocess
import threading
from pathlib import Path
from typing import Optional, Dict, Any, Callable

for _p in [str(Path(__file__).parent), "/usr/local/lib/fan-aggressor"]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

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

from fan_monitor import FanMonitor, rpm_to_percent
from cpu_power import (
    get_available_governors, get_current_governor,
    get_available_epp, get_current_epp,
    get_turbo_enabled,
    set_governor, set_epp, set_turbo
)

CONFIG_FILE = Path("/etc/fan-aggressor/config.json")
STATE_FILE = Path("/var/run/fan-aggressor.state")
PID_FILE = Path("/var/run/fan-aggressor.pid")


def load_config() -> Dict[str, Any]:
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
        "link_offsets": True,
        "nekroctl_path": None,
        "failsafe_mode": "auto"
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
        tmp_path = CONFIG_FILE.with_suffix(".tmp")
        with open(tmp_path, 'w') as f:
            json.dump(config, f, indent=2)
        os.replace(tmp_path, CONFIG_FILE)
        return True
    except PermissionError:
        return False


def save_config_privileged(config: Dict[str, Any], callback: Callable[[bool], None]):
    def _worker():
        content = json.dumps(config, indent=2)
        tmp_path = str(CONFIG_FILE.with_suffix(".tmp"))
        try:
            proc = subprocess.run(
                ["sudo", "-n", "tee", tmp_path],
                input=content,
                capture_output=True,
                text=True
            )
            if proc.returncode == 0:
                proc = subprocess.run(
                    ["sudo", "-n", "mv", tmp_path, str(CONFIG_FILE)],
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
                ["pkexec", "tee", tmp_path],
                input=content,
                capture_output=True,
                text=True
            )
            if proc.returncode == 0:
                proc = subprocess.run(
                    ["pkexec", "mv", tmp_path, str(CONFIG_FILE)],
                    capture_output=True,
                    text=True
                )
                GLib.idle_add(callback, proc.returncode == 0)
            else:
                GLib.idle_add(callback, False)
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
        win.set_default_size(850, 955)
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

        main_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        main_box.set_margin_start(12)
        main_box.set_margin_end(12)
        main_box.set_margin_top(12)
        main_box.set_margin_bottom(12)
        main_box.set_homogeneous(True)

        left_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self._build_status_group(left_col)
        self._build_control_group(left_col)
        self._build_offset_group(left_col)
        self._build_threshold_group(left_col)
        main_box.append(left_col)

        right_col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self._build_cpu_power_group(right_col)
        self._build_power_profiles_group(right_col)
        main_box.append(right_col)

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
        self.link_offsets.set_active(self.config.get("link_offsets", True))
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

    def _build_cpu_power_group(self, parent: Gtk.Box):
        group = Adw.PreferencesGroup(
            title="CPU Power Management"
        )

        self.governor_items = Gtk.StringList.new(get_available_governors() or ["powersave", "performance"])
        self.governor_row = Adw.ComboRow(
            title="Governor",
            model=self.governor_items
        )
        current_gov = self.config.get("cpu_governor", "powersave")
        gov_list = get_available_governors() or ["powersave", "performance"]
        if current_gov in gov_list:
            self.governor_row.set_selected(gov_list.index(current_gov))
        self.governor_row.connect("notify::selected", self._on_cpu_power_changed)
        group.add(self.governor_row)

        self.turbo_row = Adw.SwitchRow(
            title="Turbo Boost",
            subtitle="Intel Turbo Boost Technology"
        )
        self.turbo_row.set_active(self.config.get("cpu_turbo_enabled", True))
        self.turbo_row.connect("notify::active", self._on_cpu_power_changed)
        group.add(self.turbo_row)

        epp_options = get_available_epp() or [
            "default", "performance", "balance_performance",
            "balance_power", "power"
        ]
        self.epp_items = Gtk.StringList.new(epp_options)
        self.epp_row = Adw.ComboRow(
            title="Energy Performance",
            subtitle="CPU energy/performance bias",
            model=self.epp_items
        )
        current_epp = self.config.get("cpu_epp", "balance_performance")
        if current_epp in epp_options:
            self.epp_row.set_selected(epp_options.index(current_epp))
        self.epp_row.connect("notify::selected", self._on_cpu_power_changed)
        group.add(self.epp_row)

        parent.append(group)

    def _build_power_profiles_group(self, parent: Gtk.Box):
        group = Adw.PreferencesGroup(title="Power Profiles")

        self.profile_buttons = {}
        self.profile_icons = {}

        profiles = [
            ("stealth", "Stealth Mode", "Silencioso, sem turbo, economia total",
             {"cpu_governor": "powersave", "cpu_turbo_enabled": False, "cpu_epp": "power"}),
            ("cruise", "Cruise Control", "Equilibrado, turbo sob demanda",
             {"cpu_governor": "powersave", "cpu_turbo_enabled": True, "cpu_epp": "balance_power"}),
            ("boost", "Boost Drive", "Alta performance com eficiencia",
             {"cpu_governor": "powersave", "cpu_turbo_enabled": True, "cpu_epp": "balance_performance"}),
            ("nitro", "Nitro Overdrive", "Performance maxima, sem limites",
             {"cpu_governor": "performance", "cpu_turbo_enabled": True, "cpu_epp": "performance"}),
        ]

        for profile_id, title, subtitle, settings in profiles:
            row = Adw.ActionRow(title=title, subtitle=subtitle)

            icon = Gtk.Image()
            icon.set_pixel_size(16)
            row.add_prefix(icon)
            self.profile_icons[profile_id] = icon

            btn = Gtk.Button(label="Activate", valign=Gtk.Align.CENTER)
            btn.connect("clicked", self._on_profile_clicked, profile_id, settings)
            row.add_suffix(btn)
            row.set_activatable_widget(btn)

            self.profile_buttons[profile_id] = btn
            group.add(row)

        parent.append(group)
        self._update_profile_indicator()

    def _on_profile_clicked(self, button, profile_id, settings):
        self.updating = True
        for key, value in settings.items():
            self.config[key] = value

        gov_list = get_available_governors() or ["powersave", "performance"]
        gov = settings.get("cpu_governor", "powersave")
        if gov in gov_list:
            self.governor_row.set_selected(gov_list.index(gov))
        self.turbo_row.set_active(settings.get("cpu_turbo_enabled", True))
        epp_list = get_available_epp() or [
            "default", "performance", "balance_performance",
            "balance_power", "power"
        ]
        epp = settings.get("cpu_epp", "balance_performance")
        if epp in epp_list:
            self.epp_row.set_selected(epp_list.index(epp))
        self.updating = False

        self._save_config()
        self._apply_cpu_power()
        self._update_profile_indicator()

    def _update_profile_indicator(self):
        current_gov = get_current_governor()
        current_turbo = get_turbo_enabled()
        current_epp = get_current_epp()

        profile_map = {
            ("powersave", False, "power"): "stealth",
            ("powersave", True, "balance_power"): "cruise",
            ("powersave", True, "balance_performance"): "boost",
            ("performance", True, "performance"): "nitro",
        }

        active = profile_map.get((current_gov, current_turbo, current_epp))

        for pid, icon in self.profile_icons.items():
            btn = self.profile_buttons[pid]
            if pid == active:
                icon.set_from_icon_name("emblem-ok-symbolic")
                btn.set_label("Active")
                btn.set_sensitive(False)
                btn.remove_css_class("suggested-action")
                btn.add_css_class("success")
            else:
                icon.set_from_icon_name(None)
                btn.set_label("Activate")
                btn.set_sensitive(True)
                btn.remove_css_class("success")

    def _on_cpu_power_changed(self, widget, _):
        if self.updating:
            return

        gov_idx = self.governor_row.get_selected()
        gov_item = self.governor_items.get_string(gov_idx)
        if gov_item:
            self.config["cpu_governor"] = gov_item

        self.config["cpu_turbo_enabled"] = self.turbo_row.get_active()

        epp_idx = self.epp_row.get_selected()
        epp_item = self.epp_items.get_string(epp_idx)
        if epp_item:
            self.config["cpu_epp"] = epp_item

        self._save_config()
        self._apply_cpu_power()
        self._update_profile_indicator()

    def _apply_cpu_power(self):
        gov = self.config.get("cpu_governor")
        turbo = self.config.get("cpu_turbo_enabled", True)
        epp = self.config.get("cpu_epp")

        if set_governor(gov) and set_turbo(turbo) and set_epp(epp):
            return

        def _worker():
            script = (
                f"import sys; sys.path.insert(0, '{Path(__file__).parent}'); "
                f"sys.path.insert(0, '/usr/local/lib/fan-aggressor'); "
                f"from cpu_power import set_governor, set_turbo, set_epp; "
                f"set_governor('{gov}'); set_turbo({turbo}); set_epp('{epp}')"
            )
            try:
                subprocess.run(
                    ["sudo", "-n", "python3", "-c", script],
                    capture_output=True, timeout=5
                )
                return
            except Exception:
                pass
            try:
                subprocess.run(
                    ["pkexec", "python3", "-c", script],
                    capture_output=True, timeout=10
                )
            except Exception:
                pass

        threading.Thread(target=_worker, daemon=True).start()

    def _sync_link_visibility(self):
        linked = self.link_offsets.get_active()
        self.gpu_offset_row.set_visible(not linked)
        if linked:
            self.cpu_offset_row.set_title("Fan Offset (Both)")
        else:
            self.cpu_offset_row.set_title("CPU Offset")

    def _on_link_changed(self, row, _):
        if self.updating:
            return
        self.config["link_offsets"] = self.link_offsets.get_active()
        self._sync_link_visibility()
        if self.link_offsets.get_active():
            self.updating = True
            self.gpu_offset_row.set_value(self.cpu_offset_row.get_value())
            self.updating = False
            self.config["gpu_fan_offset"] = int(self.cpu_offset_row.get_value())
        self._save_config()

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

        if status == "active":
            self.status_label.set_text("Running")
            self.status_label.remove_css_class("error")
            self.status_label.add_css_class("success")
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
        self.link_offsets.set_active(self.config.get("link_offsets", True))

        gov_list = get_available_governors() or ["powersave", "performance"]
        config_gov = self.config.get("cpu_governor", "powersave")
        if config_gov in gov_list:
            self.governor_row.set_selected(gov_list.index(config_gov))
        self.turbo_row.set_active(self.config.get("cpu_turbo_enabled", True))
        epp_list = get_available_epp() or [
            "default", "performance", "balance_performance",
            "balance_power", "power"
        ]
        config_epp = self.config.get("cpu_epp", "balance_performance")
        if config_epp in epp_list:
            self.epp_row.set_selected(epp_list.index(config_epp))

        self.updating = False
        self._sync_link_visibility()

        if self.config.get("hybrid_mode", True):
            self.mode_label.set_text("Hybrid (temp-based)")
        else:
            self.mode_label.set_text("Fixed Curve")

        temp = self.monitor.get_max_temp()
        if temp is None:
            self.temp_label.set_text("N/A")
        else:
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
            if temp is None:
                self.boost_label.set_text("Inactive (temp N/A)")
            elif temp < engage:
                self.boost_label.set_text(f"Inactive (temp < {engage}°C)")
            else:
                self.boost_label.set_text("Waiting...")
            self.boost_label.remove_css_class("accent")
            self.boost_label.add_css_class("dim-label")

        current_gov = get_current_governor()
        current_turbo = get_turbo_enabled()
        current_epp = get_current_epp()

        self.updating = True
        gov_list = get_available_governors() or ["powersave", "performance"]
        if current_gov in gov_list:
            self.governor_row.set_selected(gov_list.index(current_gov))
        self.turbo_row.set_active(current_turbo)
        epp_list = get_available_epp() or [
            "default", "performance", "balance_performance",
            "balance_power", "power"
        ]
        if current_epp in epp_list:
            self.epp_row.set_selected(epp_list.index(current_epp))
        self.updating = False

        self._update_profile_indicator()

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
