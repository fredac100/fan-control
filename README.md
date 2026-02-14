# Fan Aggressor

Controle dinâmico de ventiladores e gerenciamento de energia CPU para notebooks Acer no Linux.

## Compatibilidade

Este projeto funciona **exclusivamente** com notebooks Acer que possuem interface WMI para controle de fans:

- **Acer Predator** (Helios, Triton, etc.)
- **Acer Nitro** (Nitro 5, Nitro 7, etc.)

Requer o módulo kernel [nekro-sense](https://github.com/fredac100/nekro-sense) instalado e funcionando.

## Funcionalidades

### Controle de Ventiladores
- **Curva dinâmica de temperatura** - Velocidade dos fans varia conforme a temperatura
- **Offset configurável** - Adiciona ou remove porcentagem sobre a curva base
- **Modo Híbrido** - Ativa boost apenas quando temperatura atinge threshold
- **Controle separado CPU/GPU** - Offsets independentes para cada ventilador

### Gerenciamento de Energia CPU
- **CPU Governor** - Alterna entre `performance` e `powersave`
- **Intel Turbo Boost** - Liga/desliga turbo boost
- **Energy Performance Preference (EPP)** - 5 níveis de performance/economia
- **EPP Override** - Corrige mapeamento automático do botão Predator

### Interface
- **GUI GTK4** - Interface gráfica moderna com libadwaita em duas colunas
- **CLI completa** - Controle via linha de comando
- **Integração com nekro-sense** - Funciona em conjunto com o módulo kernel
- **Status em tempo real** - Monitoramento de fans, temperatura e CPU power

## Como Funciona

### Modo Híbrido (Recomendado)

1. Sistema fica no **modo AUTO** enquanto temperatura está baixa
2. Quando temperatura atinge o **threshold de engage** (ex: 70°C), ativa o boost
3. Aplica **curva dinâmica + offset** configurado
4. Quando temperatura cai abaixo do **threshold de disengage** (ex: 65°C), volta ao AUTO

### Curva de Temperatura Base

| Temperatura | Velocidade Base |
|-------------|-----------------|
| < 50°C      | 0%              |
| 50-60°C     | 0-20%           |
| 60-70°C     | 20-45%          |
| 70-80°C     | 45-75%          |
| 80-90°C     | 75-100%         |
| > 90°C      | 100%            |

### Exemplo com Offset +15%

| Temperatura | Base | + Offset | Final |
|-------------|------|----------|-------|
| 55°C        | 10%  | +15%     | 25%   |
| 65°C        | 32%  | +15%     | 47%   |
| 75°C        | 60%  | +15%     | 75%   |

### EPP Override para Botão Predator

O botão físico de energia do Predator possui 4 estágios, mas o `power-profiles-daemon` mapeia incorretamente o modo `balanced` para `balance_performance` ao invés de `balance_power`. O serviço `epp-override` corrige isso automaticamente:

| Estágio | Profile | EPP Padrão (errado) | EPP Corrigido |
|---------|---------|---------------------|---------------|
| 1 (ECO) | `low-power` | `power` | `power` ✓ |
| 2 (BALANCED) | `balanced` | `balance_performance` | **`balance_power`** |
| 3 (PERFORMANCE) | `balanced-performance` | `balance_performance` | `balance_performance` ✓ |
| 4 (TURBO) | `performance` | `performance` | `performance` ✓ |

## Requisitos

- Linux com kernel 5.x+
- [nekro-sense](https://github.com/fredac100/nekro-sense) instalado e funcionando
- Python 3.8+
- GTK4 e libadwaita (para GUI)
- `intel_pstate` driver (para controles de CPU power)

## Instalação

```bash
git clone https://github.com/fredac100/fan-control.git
cd fan-control
chmod +x install.sh
sudo ./install.sh
```

Isso instala:
- `/usr/local/bin/fan_aggressor` - CLI e daemon
- `/usr/local/bin/epp_override` - Correção de EPP do botão Predator
- `/usr/local/lib/fan-aggressor/` - Módulos Python (`fan_monitor.py`, `cpu_power.py`)
- `/etc/systemd/system/fan-aggressor.service` - Serviço do daemon
- `/etc/systemd/system/epp-override.service` - Serviço de correção EPP

### Instalar GUI

```bash
./install_gui.sh
```

Isso instala o ícone e adiciona entrada no menu de aplicações.

### Habilitar Serviços

```bash
# Daemon principal
sudo systemctl enable --now fan-aggressor

# Correção de EPP (opcional, mas recomendado para Predator)
sudo systemctl enable --now epp-override
```

## Uso

### Interface Gráfica

```bash
./fan_aggressor_gui.py
```

Ou procure "Fan Aggressor" no menu de aplicações.

A GUI possui **duas colunas**:
- **Esquerda**: Status, controle de fans, offsets e thresholds
- **Direita**: CPU Power Management (governor, turbo, EPP) e CPU Status (valores em tempo real)

### Linha de Comando

#### Ver status

```bash
fan_aggressor status
```

Mostra:
- Status do daemon (enabled/disabled)
- Fan speeds (RPM e % estimado)
- Temperaturas (CPU, GPU)
- CPU Power (governor, turbo boost, EPP)
- Modo híbrido e boost status

#### Configurar offset

```bash
# Aumentar agressividade
fan_aggressor set both +15

# CPU e GPU separados
fan_aggressor set cpu +20
fan_aggressor set gpu +10

# Reduzir ruído (cuidado com temperaturas!)
fan_aggressor set both -10
```

#### Habilitar/Desabilitar

```bash
fan_aggressor enable
fan_aggressor disable
```

### Serviço Systemd

```bash
# Fan Aggressor
sudo systemctl start fan-aggressor
sudo systemctl enable fan-aggressor
journalctl -u fan-aggressor -f

# EPP Override (corrige botão Predator)
sudo systemctl start epp-override
sudo systemctl enable epp-override
journalctl -u epp-override -f
```

## Configuração

Arquivo: `/etc/fan-aggressor/config.json`

```json
{
  "cpu_fan_offset": 0,
  "gpu_fan_offset": 0,
  "enabled": false,
  "poll_interval": 1.0,
  "hybrid_mode": true,
  "temp_threshold_engage": 70,
  "temp_threshold_disengage": 65,
  "cpu_governor": "powersave",
  "cpu_turbo_enabled": true,
  "cpu_epp": "balance_performance",
  "nekroctl_path": null,
  "failsafe_mode": "auto"
}
```

### Parâmetros de Fans

| Parâmetro | Descrição | Range |
|-----------|-----------|-------|
| `cpu_fan_offset` | Offset para CPU | -100 a +100 |
| `gpu_fan_offset` | Offset para GPU | -100 a +100 |
| `enabled` | Ativa/desativa o controle | true/false |
| `poll_interval` | Intervalo de atualização | segundos (padrão: 1.0) |
| `hybrid_mode` | Se true, usa thresholds; se false, controla sempre | true/false |
| `temp_threshold_engage` | Temperatura para ativar boost | °C (padrão: 70) |
| `temp_threshold_disengage` | Temperatura para voltar ao auto | °C (padrão: 65) |
| `nekroctl_path` | Caminho do nekroctl (override) | caminho absoluto ou null |
| `failsafe_mode` | Fail-safe em erro de sensores | `auto` ou `max` |

### Parâmetros de CPU Power

| Parâmetro | Descrição | Valores |
|-----------|-----------|---------|
| `cpu_governor` | Governor do CPU | `powersave`, `performance` |
| `cpu_turbo_enabled` | Intel Turbo Boost | true/false |
| `cpu_epp` | Energy Performance Preference | `default`, `performance`, `balance_performance`, `balance_power`, `power` |

**Nota sobre EPP**: Com governor `performance`, o EPP é controlado automaticamente pelo driver e pode não aceitar mudanças manuais. Use governor `powersave` para controle total do EPP.

## Integração com Nekro-Sense

O Fan Aggressor funciona em conjunto com o nekro-sense:

- Usa `nekroctl.py` para controlar os fans via módulo kernel
- O GUI do nekro-sense detecta quando o aggressor está ativo
- Quando ativo, mostra o status do boost e desabilita controles manuais

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

epp_override.py ──► platform_profile → EPP sysfs
```

## Componentes

### fan_aggressor.py
Daemon principal que monitora temperaturas e controla ventiladores. Aplica curva dinâmica com offsets configuráveis. Também gerencia configurações de CPU power (governor, turbo, EPP).

### fan_aggressor_gui.py
Interface gráfica GTK4/Libadwaita com duas colunas:
- Controles de fans (offsets, thresholds, modo híbrido)
- CPU Power Management com status em tempo real

### cpu_power.py
Módulo para leitura/escrita de controles CPU via sysfs:
- Governor (`/sys/devices/system/cpu/cpu*/cpufreq/scaling_governor`)
- Turbo Boost (`/sys/devices/system/cpu/intel_pstate/no_turbo`)
- EPP (`/sys/devices/system/cpu/cpu*/cpufreq/energy_performance_preference`)

### epp_override.py
Daemon que monitora `/sys/firmware/acpi/platform_profile` e corrige o mapeamento EPP quando o botão físico do Predator é pressionado. Sobrescreve o comportamento padrão do `power-profiles-daemon` para garantir que o modo `balanced` use `balance_power` ao invés de `balance_performance`.

### fan_monitor.py
Módulo para leitura de fan speeds e temperaturas via hwmon (`/sys/class/hwmon`).

## Exemplos de Uso

### Gaming (mais resfriamento + performance)

```bash
fan_aggressor set both +20
fan_aggressor enable
# Via GUI: Governor = performance, Turbo = ON, EPP = performance
```

### Trabalho silencioso (economia de energia)

```bash
fan_aggressor set both -5
fan_aggressor enable
# Via GUI: Governor = powersave, Turbo = OFF, EPP = balance_power
```

### Balanced (padrão recomendado)

```bash
fan_aggressor set both 0
fan_aggressor enable
# Via GUI: Governor = powersave, Turbo = ON, EPP = balance_performance
```

### Desativar controle de fans temporariamente

```bash
fan_aggressor disable
```

Os fans voltam ao modo automático do sistema.

## Avisos

- Monitore as temperaturas ao usar offsets negativos
- O sistema pode atingir throttling se os fans forem muito lentos
- Em caso de superaquecimento, desabilite o aggressor com `fan_aggressor disable`
- Mudanças de CPU power requerem permissões de root (a GUI usa pkexec quando necessário)
- O `epp-override` só é necessário se você usa o botão físico do Predator e quer o mapeamento correto dos modos

## Logs

```bash
# Fan Aggressor
journalctl -u fan-aggressor -f

# EPP Override
journalctl -u epp-override -f

# Ambos
journalctl -u fan-aggressor -u epp-override -f
```

## Desinstalação

```bash
sudo systemctl stop fan-aggressor epp-override
sudo systemctl disable fan-aggressor epp-override
sudo rm /etc/systemd/system/fan-aggressor.service
sudo rm /etc/systemd/system/epp-override.service
sudo rm /usr/local/bin/fan_aggressor
sudo rm /usr/local/bin/epp_override
sudo rm -rf /usr/local/lib/fan-aggressor
sudo rm -rf /etc/fan-aggressor
sudo systemctl daemon-reload
```

## Troubleshooting

### EPP não muda
- Verifique se está usando governor `powersave` (com `performance`, o EPP é gerenciado pelo driver)
- Confira se tem permissões de root: `sudo python3 -c "from cpu_power import set_epp; print(set_epp('balance_power'))"`

### Botão Predator não altera EPP corretamente
- Verifique se o serviço `epp-override` está rodando: `systemctl status epp-override`
- Veja os logs: `journalctl -u epp-override -f`
- Pressione o botão e observe se o log mostra a correção

### Fans não respondem
- Verifique se o nekro-sense está carregado: `lsmod | grep nekro`
- Confira se o daemon está rodando: `systemctl status fan-aggressor`
- Teste manualmente: `sudo python3 /home/fred/nekro-sense/tools/nekroctl.py --fan1 50`

## Licença

MIT
