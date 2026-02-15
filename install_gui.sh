#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "Installing Fan Aggressor GUI..."

chmod +x "$SCRIPT_DIR/fan_aggressor_gui.py"

sudo cp "$SCRIPT_DIR/fan-aggressor.svg" /usr/share/icons/hicolor/scalable/apps/
sudo gtk-update-icon-cache /usr/share/icons/hicolor/ 2>/dev/null || true

cp "$SCRIPT_DIR/fan-aggressor.desktop" ~/.local/share/applications/
update-desktop-database ~/.local/share/applications/ 2>/dev/null || true

echo "Done! Fan Aggressor GUI installed."
echo "You can now find it in your application menu or run:"
echo "  $SCRIPT_DIR/fan_aggressor_gui.py"
