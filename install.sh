#!/bin/bash

set -e

if [ "$EUID" -ne 0 ]; then
    echo "Por favor, execute como root (sudo ./install.sh)"
    exit 1
fi

echo "=== Instalando Fan Aggressor ==="

echo "1. Copiando executável..."
cp fan_aggressor.py /usr/local/bin/fan_aggressor
chmod +x /usr/local/bin/fan_aggressor

echo "2. Instalando serviço systemd..."
cp fan-aggressor.service /etc/systemd/system/
systemctl daemon-reload

echo "3. Verificando módulo ec_sys..."
if ! lsmod | grep -q ec_sys; then
    echo "Carregando módulo ec_sys..."
    modprobe ec_sys write_support=1
fi

echo "4. Tornando módulo ec_sys permanente..."
if ! grep -q "ec_sys" /etc/modules; then
    echo "ec_sys" >> /etc/modules
fi

if [ ! -f /etc/modprobe.d/ec_sys.conf ]; then
    echo "options ec_sys write_support=1" > /etc/modprobe.d/ec_sys.conf
fi

echo ""
echo "=== Instalação concluída! ==="
echo ""
echo "Uso:"
echo "  fan_aggressor status              - Ver status atual"
echo "  fan_aggressor set cpu +10         - Aumentar 10% CPU fan"
echo "  fan_aggressor set gpu +10         - Aumentar 10% GPU fan"
echo "  fan_aggressor set both +10        - Aumentar 10% ambos"
echo "  fan_aggressor enable              - Habilitar controle"
echo "  fan_aggressor disable             - Desabilitar controle"
echo ""
echo "Para iniciar o serviço:"
echo "  sudo systemctl start fan-aggressor"
echo "  sudo systemctl enable fan-aggressor    # Iniciar automaticamente"
echo ""
echo "Para ver logs:"
echo "  journalctl -u fan-aggressor -f"
echo ""
