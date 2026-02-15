# Fan Aggressor

Controle de ventiladores e gerenciamento de energia CPU para o **Acer Predator Helios Neo 16 (PHN16-72)** no Linux.

> **Aviso**: Desenvolvido e testado exclusivamente no **Acer Predator PHN16-72**. Sem garantia para outros modelos.

![Fan Aggressor GUI](docs/screenshot.png)

## Instalação Rápida (uma linha)

Instala tudo automaticamente: nekro-sense (módulo kernel), Fan Aggressor (CLI + daemon) e interface gráfica.

```bash
git clone https://github.com/fredac100/fan-control.git && cd fan-control && sudo bash setup.sh
```

Ou se já tem o repositório clonado:

```bash
cd fan-control
sudo bash setup.sh
```

Isso instala e configura:
- **nekro-sense** - Módulo kernel para comunicação com o hardware
- **fan_aggressor** - CLI e daemon de controle de fans
- **epp_override** - Correção de EPP do botão Predator
- **Interface gráfica** - GTK4/Libadwaita com ícone na bandeja de aplicativos
- **Serviços systemd** - Tudo habilitado e rodando automaticamente

## Após Instalar

### Interface Gráfica (recomendado)

Procure **"Fan Aggressor"** na bandeja de aplicativos ou execute:

```bash
./fan_aggressor_gui.py
```

### Linha de Comando

```bash
fan_aggressor status              # Ver status, temperaturas e velocidades
fan_aggressor set both +15        # Ajustar offset dos fans (+15%)
fan_aggressor set cpu +20         # CPU e GPU independentes
fan_aggressor set gpu +10
fan_aggressor enable              # Habilitar controle
fan_aggressor disable             # Desabilitar (volta ao automático)
```

### Logs

```bash
journalctl -u fan-aggressor -f
```

## Funcionalidades

### Interface Gráfica (GTK4/Libadwaita)
- Layout em duas colunas: Fans (esquerda) + CPU Power (direita)
- Status em tempo real: temperaturas, RPM, boost status
- Sliders para offset, toggles para enable/hybrid mode
- 5 Power Profiles com um clique

### Controle de Ventiladores
- **Modo Híbrido** - Captura curva do fabricante, adiciona offset apenas quando necessário
- **Offset configurável** - CPU e GPU independentes (-100% a +100%)
- **Thresholds personalizáveis** - Controle de quando o boost ativa/desativa
- **Daemon automático** - Monitora temperatura e ajusta fans continuamente

### Gerenciamento de Energia CPU
- **Governor** - `powersave` ou `performance`
- **Intel Turbo Boost** - ON/OFF
- **EPP** - 5 níveis de eficiência energética
- **EPP Override** - Corrige mapeamento do botão físico Predator

### Power Profiles

| Perfil | Governor | Turbo | EPP | Uso |
|--------|----------|-------|-----|-----|
| **Deep Sleep** | powersave | OFF | power | Economia extrema |
| **Stealth Mode** | powersave | OFF | power | Silencioso |
| **Cruise Control** | powersave | ON | balance_power | Uso diário |
| **Boost Drive** | powersave | ON | balance_performance | Produtividade |
| **Nitro Overdrive** | performance | ON | performance | Gaming |

## Como Funciona

![Como funciona](docs/how-it-works.png)

### Modo Híbrido (Recomendado)

1. Sistema fica no **modo AUTO** enquanto temperatura está baixa (< threshold)
2. Ao atingir o **threshold de engage** (padrão: 70°C), captura snapshot do RPM atual
3. Aplica **curva do fabricante + offset** configurado
4. Quando temperatura cai abaixo do **threshold de disengage** (padrão: 65°C), volta ao AUTO

O sistema **não substitui** a curva do fabricante — apenas **adiciona** o offset sobre ela.

## Configuração

Arquivo: `/etc/fan-aggressor/config.json`

```json
{
  "cpu_fan_offset": 0,
  "gpu_fan_offset": 0,
  "enabled": true,
  "poll_interval": 1.0,
  "hybrid_mode": true,
  "temp_threshold_engage": 70,
  "temp_threshold_disengage": 65,
  "cpu_governor": "powersave",
  "cpu_turbo_enabled": true,
  "cpu_epp": "balance_performance"
}
```

O daemon recarrega o config automaticamente — não é necessário reiniciar o serviço.

### Parâmetros Principais

| Parâmetro | Descrição | Range/Valores |
|-----------|-----------|---------------|
| `cpu_fan_offset` | Offset CPU | -100 a +100 |
| `gpu_fan_offset` | Offset GPU | -100 a +100 |
| `enabled` | Ativar controle | true/false |
| `hybrid_mode` | Usar thresholds | true/false |
| `temp_threshold_engage` | Temperatura para ativar boost | °C (padrão: 70) |
| `temp_threshold_disengage` | Temperatura para voltar ao auto | °C (padrão: 65) |
| `cpu_governor` | Governor do CPU | powersave, performance |
| `cpu_turbo_enabled` | Turbo Boost | true/false |
| `cpu_epp` | Energy Performance Preference | power, balance_power, balance_performance, performance |

## Cenários de Uso

**Gaming** — perfil Nitro Overdrive + offset +20% a +30%:
```bash
fan_aggressor set both +25
```

**Trabalho silencioso** — perfil Stealth Mode + offset 0%:
```bash
fan_aggressor set both 0
```

**Uso diário** — perfil Cruise Control + offset +10% a +15%:
```bash
fan_aggressor set both +10
```

## Instalação Manual (passo a passo)

Se preferir instalar manualmente ao invés do script automatizado:

### 1. nekro-sense (pré-requisito)

```bash
git clone https://github.com/fredac100/nekro-sense.git
cd nekro-sense
make
sudo make install
sudo modprobe nekro_sense
```

### 2. Fan Aggressor

```bash
git clone https://github.com/fredac100/fan-control.git
cd fan-control
sudo ./install.sh
```

### 3. Dependências da GUI

```bash
sudo apt install libgtk-4-1 libadwaita-1-0 python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-adw-1
```

> O `install.sh` já habilita e inicia os serviços automaticamente, instala o ícone na bandeja de aplicativos e configura tudo.

## Troubleshooting

### Fans não respondem
```bash
lsmod | grep nekro                    # nekro-sense carregado?
systemctl status fan-aggressor        # daemon rodando?
journalctl -u fan-aggressor | grep nekroctl  # nekroctl encontrado?
```

### Fans escalam até 100%
Atualize para a versão mais recente:
```bash
cd /home/fred/fan-control && git pull
sudo ./install.sh
sudo systemctl restart fan-aggressor
```

### EPP não muda
Use governor `powersave` — com `performance`, o EPP é gerenciado pelo driver.

### Sensores não funcionam
```bash
cat /sys/class/hwmon/hwmon*/name      # deve mostrar "acer" ou "coretemp"
```

## Desinstalação

```bash
sudo systemctl stop fan-aggressor epp-override
sudo systemctl disable fan-aggressor epp-override
sudo rm /etc/systemd/system/fan-aggressor.service /etc/systemd/system/epp-override.service
sudo rm /usr/local/bin/fan_aggressor /usr/local/bin/epp_override
sudo rm -rf /usr/local/lib/fan-aggressor /etc/fan-aggressor
sudo systemctl daemon-reload
```

## Arquitetura

```
fan_aggressor_gui.py  ──┐
                        ├──► fan_aggressor.py (daemon) ───► cpu_power.py
fan_aggressor (CLI)   ──┘           │                           │
                                    ▼                           ▼
                            nekroctl.py                  sysfs (cpufreq)
                                    │
                                    ▼
                          nekro-sense (kernel module)
                                    │
                                    ▼
                              Hardware (WMI)
```

## Requisitos

- **Notebook**: Acer Predator Helios Neo 16 (PHN16-72)
- **OS**: Linux com kernel 5.x+ (testado em Ubuntu 24.04+)
- **CPU**: Intel (para turbo boost e EPP via `intel_pstate`)
- **Python**: 3.8+

## Licença

MIT
