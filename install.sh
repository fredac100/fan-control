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

echo ""
echo "=== Instalação concluída! ==="
echo ""
echo "Comandos:"
echo "  fan_aggressor status          - Ver status e backends disponíveis"
echo "  fan_aggressor set cpu +10     - Aumentar agressividade CPU"
echo "  fan_aggressor set gpu +10     - Aumentar agressividade GPU"
echo "  fan_aggressor set both +10    - Aumentar ambos"
echo "  fan_aggressor backend auto    - Selecionar backend (auto|ec|nekro|predator)"
echo "  fan_aggressor enable          - Ativar controle"
echo "  fan_aggressor disable         - Desativar controle"
echo ""
echo "Para iniciar o serviço:"
echo "  sudo systemctl start fan-aggressor"
echo "  sudo systemctl enable fan-aggressor"
echo ""
echo "Para ver logs:"
echo "  journalctl -u fan-aggressor -f"
echo ""
