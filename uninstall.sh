#!/bin/bash

set -euo pipefail

if [ "$EUID" -ne 0 ]; then
    echo "Por favor, execute como root (sudo ./uninstall.sh)"
    exit 1
fi

echo "=== Desinstalando Fan Aggressor ==="

echo "1. Parando e desabilitando serviços..."
systemctl stop fan-aggressor 2>/dev/null || true
systemctl stop epp-override 2>/dev/null || true
systemctl disable fan-aggressor 2>/dev/null || true
systemctl disable epp-override 2>/dev/null || true

echo "2. Removendo arquivos de serviço..."
rm -f /etc/systemd/system/fan-aggressor.service
rm -f /etc/systemd/system/epp-override.service
systemctl daemon-reload

echo "3. Removendo executáveis..."
rm -f /usr/local/bin/fan_aggressor
rm -f /usr/local/bin/fan-aggressor-gui
rm -f /usr/local/bin/epp_override

echo "4. Removendo biblioteca e helper..."
rm -rf /usr/local/lib/fan-aggressor

echo "5. Removendo PolicyKit policy..."
rm -f /usr/share/polkit-1/actions/com.fancontrol.aggressor.policy

echo "6. Removendo ícone..."
rm -f /usr/share/icons/hicolor/scalable/apps/fan-aggressor.svg
gtk-update-icon-cache -f /usr/share/icons/hicolor/ 2>/dev/null || true

echo "7. Removendo atalho do menu..."
REAL_USER="${SUDO_USER:-$USER}"
REAL_HOME=$(eval echo "~$REAL_USER")
rm -f "$REAL_HOME/.local/share/applications/fan-aggressor.desktop"
update-desktop-database "$REAL_HOME/.local/share/applications/" 2>/dev/null || true

echo "8. Removendo PID e state files..."
rm -f /var/run/fan-aggressor.pid
rm -f /var/run/fan-aggressor.state

echo ""
read -p "Remover configuração (/etc/fan-aggressor)? [s/N] " -n 1 -r
echo
if [[ $REPLY =~ ^[Ss]$ ]]; then
    rm -rf /etc/fan-aggressor
    echo "   Configuração removida"
else
    echo "   Configuração mantida em /etc/fan-aggressor/"
fi

echo ""
echo "=== Desinstalação concluída! ==="
echo ""
echo "Nota: o módulo kernel nekro-sense NÃO foi removido."
echo "Para remover: sudo modprobe -r nekro_sense && sudo dkms remove nekro-sense -v <version> --all"
