#!/bin/bash

set -e

if [ "$EUID" -ne 0 ]; then
    echo "Por favor, execute como root (sudo ./install.sh)"
    exit 1
fi

echo "=== Instalando Fan Aggressor ==="

echo "1. Copiando executável e módulos..."
cp fan_aggressor.py /usr/local/bin/fan_aggressor
chmod +x /usr/local/bin/fan_aggressor

mkdir -p /usr/local/lib/fan-aggressor
cp fan_monitor.py /usr/local/lib/fan-aggressor/
cp cpu_power.py /usr/local/lib/fan-aggressor/
cp fan-aggressor-helper /usr/local/lib/fan-aggressor/fan-aggressor-helper
chmod +x /usr/local/lib/fan-aggressor/fan-aggressor-helper
cp com.fancontrol.aggressor.policy /usr/share/polkit-1/actions/
cp epp_override.py /usr/local/bin/epp_override
chmod +x /usr/local/bin/epp_override

echo "2. Instalando serviços systemd..."
cat > /etc/systemd/system/fan-aggressor.service << 'EOF'
[Unit]
Description=Fan Aggressor - Controle de agressividade dos ventiladores
After=multi-user.target

[Service]
Type=simple
ExecStartPre=-/sbin/modprobe ec_sys write_support=1
Environment=PYTHONPATH=/usr/local/lib/fan-aggressor
Environment=PYTHONUNBUFFERED=1
ExecStart=/usr/local/bin/fan_aggressor daemon
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ReadWritePaths=/etc/fan-aggressor /var/run

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/epp-override.service << 'EOF'
[Unit]
Description=EPP Override - Corrige mapeamento platform_profile → EPP
After=power-profiles-daemon.service

[Service]
Type=simple
ExecStart=/usr/local/bin/epp_override
Restart=on-failure
RestartSec=3
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload

echo "3. Configurando módulo ec_sys (se disponível)..."
if modprobe ec_sys write_support=1 2>/dev/null; then
    if ! grep -q "ec_sys" /etc/modules 2>/dev/null; then
        echo "ec_sys" >> /etc/modules
    fi
    if [ ! -f /etc/modprobe.d/ec_sys.conf ]; then
        echo "options ec_sys write_support=1" > /etc/modprobe.d/ec_sys.conf
    fi
    echo "   Módulo ec_sys configurado"
else
    echo "   Módulo ec_sys não disponível (usando backend alternativo)"
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "4. Instalando ícone e atalho no menu..."
if [ -f "$SCRIPT_DIR/fan-aggressor.svg" ]; then
    mkdir -p /usr/share/icons/hicolor/scalable/apps
    cp "$SCRIPT_DIR/fan-aggressor.svg" /usr/share/icons/hicolor/scalable/apps/
    gtk-update-icon-cache -f /usr/share/icons/hicolor/ 2>/dev/null || true
fi

if [ -f "$SCRIPT_DIR/fan-aggressor.desktop" ]; then
    REAL_USER="${SUDO_USER:-$USER}"
    REAL_HOME=$(eval echo "~$REAL_USER")
    DESKTOP_DIR="$REAL_HOME/.local/share/applications"
    mkdir -p "$DESKTOP_DIR"
    cp "$SCRIPT_DIR/fan-aggressor.desktop" "$DESKTOP_DIR/"
    chown "$REAL_USER":"$REAL_USER" "$DESKTOP_DIR/fan-aggressor.desktop"
    update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true
    echo "   Atalho instalado no menu de aplicações"
fi

echo "5. Habilitando e iniciando serviços..."
fan_aggressor enable 2>/dev/null || true
systemctl enable --now fan-aggressor 2>/dev/null && \
    echo "   fan-aggressor: ativo e habilitado no boot" || \
    echo "   fan-aggressor: habilitado (pode precisar de reinício)"
systemctl enable --now epp-override 2>/dev/null && \
    echo "   epp-override: ativo e habilitado no boot" || \
    echo "   epp-override: habilitado (pode precisar de reinício)"

echo ""
echo "=== Instalação concluída! ==="
echo ""
echo "Interface Gráfica:"
echo "  Procure 'Fan Aggressor' no menu de aplicações"
echo ""
echo "Comandos:"
echo "  fan_aggressor status          - Ver status e backends disponíveis"
echo "  fan_aggressor set both +10    - Ajustar offset dos fans"
echo "  fan_aggressor enable          - Ativar controle"
echo "  fan_aggressor disable         - Desativar controle"
echo ""
echo "Logs:"
echo "  journalctl -u fan-aggressor -f"
echo ""
