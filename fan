#!/bin/bash

NEKROCTL="/home/fred/nekro-sense/tools/nekroctl.py"

find_hwmon_device() {
    for device in /sys/class/hwmon/hwmon*; do
        if [ -f "$device/name" ]; then
            name=$(cat "$device/name")
            if [ "$name" = "acer" ]; then
                echo "$device"
                return 0
            fi
        fi
    done
    echo ""
    return 1
}

HWMON_PATH=$(find_hwmon_device)

show_status() {
    if [ -z "$HWMON_PATH" ]; then
        echo "Erro: Dispositivo Acer hwmon não encontrado"
        exit 1
    fi
    temp=$(awk '{print $1/1000}' "$HWMON_PATH/temp1_input")
    rpm1=$(cat "$HWMON_PATH/fan1_input")
    rpm2=$(cat "$HWMON_PATH/fan2_input")
    echo "Temp: ${temp}°C | Fan1: $rpm1 RPM | Fan2: $rpm2 RPM"
}

case "$1" in
    auto)
        sudo $NEKROCTL fan auto
        sleep 2
        show_status
        ;;
    [0-9]|[1-9][0-9]|100)
        if [ "$1" -lt 0 ] || [ "$1" -gt 100 ]; then
            echo "Erro: Valor deve estar entre 0 e 100"
            exit 1
        fi
        sudo $NEKROCTL fan set "$1" "$1"
        sleep 2
        show_status
        ;;
    status|"")
        show_status
        ;;
    *)
        echo "Uso: fan [auto|0-100|status]"
        echo ""
        echo "Exemplos:"
        echo "  fan auto       # Modo automático"
        echo "  fan 30         # 30% fixo"
        echo "  fan 50         # 50% fixo"
        echo "  fan status     # Ver status"
        exit 1
        ;;
esac
