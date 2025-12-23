#!/bin/bash

set -e

if [ "$EUID" -ne 0 ]; then
    echo "Por favor, execute como root (sudo ./install.sh)"
    exit 1
fi

show_usage() {
    echo "Uso: ./install.sh [versao]"
    echo ""
    echo "Versões disponíveis:"
    echo "  ec      - Controle via EC (Embedded Controller) - padrão"
    echo "  predator - Controle via PredatorSense"
    echo "  nekro   - Controle via nekroctl"
    echo ""
    echo "Exemplos:"
    echo "  sudo ./install.sh         # Instala versão EC"
    echo "  sudo ./install.sh ec      # Instala versão EC"
    echo "  sudo ./install.sh predator # Instala versão PredatorSense"
    echo "  sudo ./install.sh nekro   # Instala versão nekroctl"
}

VERSION="${1:-ec}"

case "$VERSION" in
    ec)
        SOURCE_FILE="fan_aggressor.py"
        NEEDS_EC_MODULE=true
        ;;
    predator)
        SOURCE_FILE="fan_aggressor_v2.py"
        NEEDS_EC_MODULE=false
        ;;
    nekro)
        SOURCE_FILE="fan_aggressor_nekro.py"
        NEEDS_EC_MODULE=false
        ;;
    -h|--help)
        show_usage
        exit 0
        ;;
    *)
        echo "Erro: Versão desconhecida '$VERSION'"
        show_usage
        exit 1
        ;;
esac

if [ ! -f "$SOURCE_FILE" ]; then
    echo "Erro: Arquivo '$SOURCE_FILE' não encontrado"
    exit 1
fi

echo "=== Instalando Fan Aggressor (versão: $VERSION) ==="

echo "1. Copiando executável..."
cp "$SOURCE_FILE" /usr/local/bin/fan_aggressor
chmod +x /usr/local/bin/fan_aggressor

echo "2. Instalando serviço systemd..."
if [ "$NEEDS_EC_MODULE" = true ]; then
    cat > /etc/systemd/system/fan-aggressor.service << 'EOF'
[Unit]
Description=Fan Aggressor - Controle de agressividade dos ventiladores
After=multi-user.target

[Service]
Type=simple
ExecStartPre=/sbin/modprobe ec_sys write_support=1
ExecStart=/usr/local/bin/fan_aggressor daemon
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
else
    cat > /etc/systemd/system/fan-aggressor.service << 'EOF'
[Unit]
Description=Fan Aggressor - Controle de agressividade dos ventiladores
After=multi-user.target

[Service]
Type=simple
ExecStart=/usr/local/bin/fan_aggressor daemon
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
fi

systemctl daemon-reload

if [ "$NEEDS_EC_MODULE" = true ]; then
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
fi

echo ""
echo "=== Instalação concluída! ==="
echo "Versão instalada: $VERSION"
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
