#!/bin/bash

NEKROCTL="/home/fred/nekro-sense/tools/nekroctl.py"

show_status() {
    temp=$(awk '{print $1/1000}' /sys/class/hwmon/hwmon7/temp1_input)
    rpm1=$(cat /sys/class/hwmon/hwmon7/fan1_input)
    rpm2=$(cat /sys/class/hwmon/hwmon7/fan2_input)
    echo "Temp: ${temp}°C | Fan1: $rpm1 RPM | Fan2: $rpm2 RPM"
}

case "$1" in
    auto)
        sudo $NEKROCTL fan auto
        sleep 2
        show_status
        ;;
    [0-9]|[0-9][0-9]|100)
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
