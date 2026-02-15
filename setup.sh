#!/bin/bash

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m'

NEKRO_REPO="https://github.com/fredac100/nekro-sense.git"
FAN_REPO="https://github.com/fredac100/fan-control.git"

print_banner() {
    echo -e "${BLUE}${BOLD}"
    echo "╔══════════════════════════════════════════╗"
    echo "║        Fan Aggressor - Setup             ║"
    echo "║   Acer Predator Helios Neo 16 (Linux)    ║"
    echo "╚══════════════════════════════════════════╝"
    echo -e "${NC}"
}

log_step() {
    echo -e "\n${GREEN}[✓]${NC} ${BOLD}$1${NC}"
}

log_info() {
    echo -e "    ${BLUE}→${NC} $1"
}

log_warn() {
    echo -e "    ${YELLOW}⚠${NC} $1"
}

log_error() {
    echo -e "    ${RED}✗${NC} $1"
}

check_root() {
    if [ "$EUID" -ne 0 ]; then
        echo -e "${RED}Este script precisa ser executado como root.${NC}"
        echo -e "Execute: ${BOLD}sudo bash setup.sh${NC}"
        exit 1
    fi
}

check_dependencies() {
    log_step "Verificando dependências do sistema..."

    local missing=()

    for cmd in git make python3 gcc; do
        if ! command -v $cmd &>/dev/null; then
            missing+=($cmd)
        fi
    done

    if [ ${#missing[@]} -gt 0 ]; then
        log_info "Instalando dependências: ${missing[*]}"
        apt-get update -qq
        apt-get install -y -qq build-essential git python3 dkms linux-headers-$(uname -r) 2>/dev/null || {
            log_error "Falha ao instalar dependências. Instale manualmente: ${missing[*]}"
            exit 1
        }
    else
        log_info "Todas as dependências encontradas"
    fi
}

install_gui_deps() {
    log_step "Instalando dependências da interface gráfica..."
    apt-get install -y -qq \
        libgtk-4-1 \
        libadwaita-1-0 \
        python3-gi \
        python3-gi-cairo \
        gir1.2-gtk-4.0 \
        gir1.2-adw-1 2>/dev/null || {
        log_warn "Algumas dependências da GUI não puderam ser instaladas"
        log_warn "A GUI pode não funcionar, mas a CLI estará disponível"
    }
    log_info "GTK4 + Libadwaita instalados"
}

install_nekro_sense() {
    log_step "Instalando nekro-sense (módulo kernel)..."

    if lsmod | grep -q nekro_sense; then
        log_info "nekro-sense já está carregado"
        return 0
    fi

    local real_user="${SUDO_USER:-$USER}"
    local real_home=$(eval echo "~$real_user")
    local nekro_dir="$real_home/nekro-sense"

    if [ -d "$nekro_dir" ]; then
        log_info "Repositório encontrado em $nekro_dir, atualizando..."
        cd "$nekro_dir"
        git pull --quiet 2>/dev/null || true
    else
        log_info "Clonando repositório nekro-sense..."
        git clone --quiet "$NEKRO_REPO" "$nekro_dir"
        chown -R "$real_user":"$real_user" "$nekro_dir"
        cd "$nekro_dir"
    fi

    log_info "Compilando módulo kernel..."
    make clean 2>/dev/null || true
    make

    log_info "Instalando módulo..."
    make install

    log_info "Carregando módulo..."
    modprobe nekro_sense 2>/dev/null || {
        log_warn "Não foi possível carregar o módulo automaticamente"
        log_warn "Pode ser necessário reiniciar o sistema"
    }

    if lsmod | grep -q nekro_sense; then
        log_info "nekro-sense carregado com sucesso"
    else
        log_warn "Módulo instalado mas não carregado (reinicie o sistema)"
    fi
}

install_fan_aggressor() {
    log_step "Instalando Fan Aggressor..."

    local real_user="${SUDO_USER:-$USER}"
    local real_home=$(eval echo "~$real_user")
    local fan_dir="$real_home/fan-control"

    if [ -d "$fan_dir" ]; then
        log_info "Repositório encontrado em $fan_dir"
        cd "$fan_dir"
        git pull --quiet 2>/dev/null || true
    else
        log_info "Clonando repositório fan-control..."
        git clone --quiet "$FAN_REPO" "$fan_dir"
        chown -R "$real_user":"$real_user" "$fan_dir"
        cd "$fan_dir"
    fi

    log_info "Executando install.sh..."
    bash "$fan_dir/install.sh"

    chmod 644 /usr/local/lib/fan-aggressor/*.py
    chmod 755 /usr/local/lib/fan-aggressor
    rm -rf /usr/local/lib/fan-aggressor/__pycache__
}

print_summary() {
    echo ""
    echo -e "${GREEN}${BOLD}╔══════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}${BOLD}║       Instalação concluída!              ║${NC}"
    echo -e "${GREEN}${BOLD}╚══════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "${BOLD}Interface Gráfica:${NC}"
    echo -e "  Procure ${BLUE}Fan Aggressor${NC} no menu de aplicações"
    echo -e "  Ou execute: ${BLUE}fan-aggressor-gui${NC}"
    echo ""
    echo -e "${BOLD}Linha de Comando:${NC}"
    echo -e "  ${BLUE}fan_aggressor status${NC}        - Ver status"
    echo -e "  ${BLUE}fan_aggressor set both +15${NC}  - Ajustar offset"
    echo -e "  ${BLUE}fan_aggressor enable${NC}        - Habilitar"
    echo -e "  ${BLUE}fan_aggressor disable${NC}       - Desabilitar"
    echo ""
    echo -e "${BOLD}Logs:${NC}"
    echo -e "  ${BLUE}journalctl -u fan-aggressor -f${NC}"
    echo ""
}

print_banner
check_root
check_dependencies
install_gui_deps
install_nekro_sense
install_fan_aggressor
print_summary
